"""
Full-text fetching: gets the whole story from the publisher's page so the
summariser works from the complete article, not just the 1-2 sentence RSS
teaser.

Extraction uses trafilatura (a widely used open-source library for pulling
the main article text out of a news page and dropping menus, adverts, cookie
banners and "related stories" boxes). If trafilatura isn't installed, a
simple built-in fallback collects the page's <p> paragraphs instead.

Results are stored on the article (full_text / full_text_status) so each
page is downloaded at most once. The text is only used as input for
summaries. It is never sent to the browser, so readers see a summary with a
link to the publisher, not a copy of the publisher's article.
"""
from __future__ import annotations
import html as html_lib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

from app.extensions import db

try:
    import trafilatura  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    trafilatura = None

HTTP_HEADERS = {
    # A normal browser UA: many publishers serve a stripped page (or a 403)
    # to unknown clients.
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 NewsRecommendationSystem/1.0'),
    'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
}
FETCH_TIMEOUT = 12
MAX_PAGE_BYTES = 3_000_000
MAX_TEXT_CHARS = 20_000
MIN_USEFUL_CHARS = 400        # less than this is a paywall stub / cookie wall
RETRY_FAILED_AFTER = timedelta(hours=6)

# Lines that are page furniture, not story text.
_JUNK_LINE_RE = re.compile(
    r'^(advertisement|sponsored|read more|related|share this|follow us|sign up|subscribe|'
    r'image (source|caption)|getty images|copyright|all rights reserved|click here|'
    r'watch:|listen:|you may also like|more on this story)\b',
    re.IGNORECASE,
)


class _ParagraphCollector(HTMLParser):
    """Fallback extractor: text of <p> elements, skipping scripts/nav/footers."""
    SKIP = {'script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript', 'figure'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth_skip = 0
        self.in_p = False
        self.buf: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth_skip += 1
        elif tag == 'p' and not self.depth_skip:
            self.in_p, self.buf = True, []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1
        elif tag == 'p' and self.in_p:
            self.in_p = False
            text = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
            if len(text) >= 60:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self.in_p and not self.depth_skip:
            self.buf.append(data)


def _fallback_extract(page: str) -> str:
    parser = _ParagraphCollector()
    try:
        parser.feed(page)
    except Exception:
        return ''
    return '\n\n'.join(parser.paragraphs)


def clean_article_text(text: str) -> str:
    lines = []
    seen = set()
    for raw in (text or '').splitlines():
        line = html_lib.unescape(re.sub(r'\s+', ' ', raw)).strip()
        if not line or _JUNK_LINE_RE.match(line):
            continue
        key = line.lower()
        if key in seen:  # repeated captions / pull quotes
            continue
        seen.add(key)
        lines.append(line)
    text = '\n\n'.join(lines)
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS].rsplit(' ', 1)[0]
    return text


def download_and_extract(url: str) -> str | None:
    """Download one article page and return its main text (None on failure)."""
    if not url or url.startswith('https://example.com/mock/'):
        return None
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=FETCH_TIMEOUT, stream=True)
        if resp.status_code != 200 or 'html' not in resp.headers.get('content-type', 'text/html'):
            resp.close()
            return None
        chunks, size = [], 0
        for part in resp.iter_content(chunk_size=65_536):
            chunks.append(part)
            size += len(part)
            if size >= MAX_PAGE_BYTES:
                break
        resp.close()
        raw = b''.join(chunks)
        page = raw.decode(resp.encoding or 'utf-8', errors='ignore') if resp.encoding else raw.decode('utf-8', errors='ignore')
    except Exception:
        return None

    text = ''
    if trafilatura is not None:
        try:
            text = trafilatura.extract(page, url=url, include_comments=False, include_tables=False,
                                       favor_precision=True) or ''
        except Exception:
            text = ''
    if len(text) < MIN_USEFUL_CHARS:
        alt = _fallback_extract(page)
        if len(alt) > len(text):
            text = alt
    text = clean_article_text(text)
    return text if len(text) >= MIN_USEFUL_CHARS else None


def _needs_fetch(article) -> bool:
    if article.full_text_status == 'ok' and article.full_text:
        return False
    if article.full_text_status == 'failed' and article.full_text_fetched_at:
        fetched = article.full_text_fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched > RETRY_FAILED_AFTER
    return True


def ensure_full_text(articles: list) -> None:
    """
    Make sure each article has full_text where possible. Pages are downloaded
    in parallel (network only; the database is written afterwards on this
    thread, because SQLAlchemy sessions aren't thread-safe).
    """
    todo = [a for a in articles if _needs_fetch(a) and a.url]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=min(6, len(todo))) as pool:
        texts = list(pool.map(lambda a: download_and_extract(a.url), todo))
    now = datetime.now(timezone.utc)
    for article, text in zip(todo, texts):
        article.full_text_fetched_at = now
        if text:
            article.full_text = text
            article.full_text_status = 'ok'
        else:
            article.full_text_status = 'failed'
    db.session.commit()


def best_text(article) -> str:
    """Longest text we have for an article: full page text, else the feed body/summary."""
    candidates = [article.full_text or '', article.content or '', article.description or '']
    return max(candidates, key=len)
