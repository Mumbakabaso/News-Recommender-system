"""
Live news ingestion: pulls articles from every source in news_sources.py
(BBC, Al Jazeera, CNN and Zambian outlets) into the local Postgres cache.

Pipeline per source:
  fetch (RSS feed, or NewsAPI for CNN)
    -> normalise each entry to {title, summary, url, image, published, tags}
    -> categorise into one of NEWS_CATEGORIES (the bandit's arms)
    -> tag region ('international' / 'zambia')
    -> upsert into `articles` keyed by a hash of the URL (re-running never
       creates duplicates; it just refreshes the text)

One broken source never stops the others: each is fetched in its own
try/except and its outcome is recorded in SOURCE_STATUS, which
GET /api/sources exposes so you can see at a glance which feeds are
working.

If *every* live source fails and the database has no live articles at all
(e.g. a demo machine with no internet), the bundled mock dataset is loaded
instead so the app is never empty.
"""
from __future__ import annotations
import calendar
import hashlib
import html
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from app.extensions import db
from app.models.article import Article
from app.services.categoriser import categorise, is_about_zambia
from app.services.news_sources import enabled_sources

NEWSAPI_TOP_HEADLINES = 'https://newsapi.org/v2/top-headlines'
MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'mock_articles.json')
MOCK_URL_PREFIX = 'https://example.com/mock/'

# Some publishers reject requests without a browser-like User-Agent.
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; NewsRecommendationSystem/1.0; academic news recommender prototype)',
    'Accept': 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5',
}
FETCH_TIMEOUT = 20
IMAGE_LOOKUP_TIMEOUT = 6

# key -> {'ok', 'last_run', 'fetched', 'saved', 'error'}; read by /api/sources.
SOURCE_STATUS: dict[str, dict] = {}
LAST_RUN: dict = {'started_at': None, 'finished_at': None, 'used_mock': False}

# Prevents the background scheduler and a manual "Refresh now" from running
# two ingestions at the same time.
_ingest_lock = threading.Lock()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _external_id(url: str) -> str:
    return hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]


_TAG_RE = re.compile(r'<[^>]+>')
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',
    re.IGNORECASE,
)
# WordPress feeds append "The post X appeared first on Y." to every summary.
_WP_FOOTER_RE = re.compile(r'The post .{0,400}? appeared first on .{0,200}?\.?\s*$', re.IGNORECASE | re.DOTALL)


def clean_text(raw: str | None, limit: int = 1200) -> str:
    if not raw:
        return ''
    text = _TAG_RE.sub(' ', raw)
    text = html.unescape(text)
    text = _WP_FOOTER_RE.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\[(?:…|\.\.\.|&#8230;)\]$', '…', text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(' ', 1)[0] + '…'
    return text


def _entry_image(entry) -> str | None:
    for key in ('media_thumbnail', 'media_content'):
        items = entry.get(key) or []
        # BBC lists several sizes; take the largest declared width.
        best = None
        for m in items:
            url = m.get('url')
            if not url:
                continue
            width = int(m.get('width') or 0) if str(m.get('width') or '0').isdigit() else 0
            if best is None or width > best[0]:
                best = (width, url)
        if best:
            return best[1]
    for enc in entry.get('enclosures') or []:
        if (enc.get('type') or '').startswith('image') and enc.get('href'):
            return enc['href']
    for block in (entry.get('content') or []):
        m = _IMG_RE.search(block.get('value') or '')
        if m:
            return m.group(1)
    m = _IMG_RE.search(entry.get('summary') or '')
    return m.group(1) if m else None


def _entry_published(entry) -> datetime | None:
    for key in ('published_parsed', 'updated_parsed'):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def _lookup_og_image(url: str) -> str | None:
    """Fetch the article page and read its og:image (feeds without thumbnails)."""
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=IMAGE_LOOKUP_TIMEOUT, stream=True)
        if resp.status_code != 200:
            return None
        # The <head> is all we need; don't download whole pages.
        buf = b''
        for part in resp.iter_content(chunk_size=16_384):
            buf += part
            if len(buf) >= 150_000 or b'</head>' in buf:
                break
        resp.close()
        chunk = buf.decode('utf-8', errors='ignore')
        m = _OG_IMAGE_RE.search(chunk)
        if m:
            return html.unescape(m.group(1) or m.group(2))
    except Exception:
        return None
    return None


def describe_error(e: Exception) -> str:
    """Short, human-readable reason a source failed (shown in the admin page)."""
    if isinstance(e, requests.exceptions.SSLError):
        return "SSL certificate problem on the publisher's site"
    if isinstance(e, requests.exceptions.Timeout):
        return 'Timed out — the site is slow or unreachable'
    if isinstance(e, requests.exceptions.ProxyError):
        return 'Blocked by a proxy/firewall on this network'
    if isinstance(e, requests.exceptions.ConnectionError):
        return 'Could not connect — check the internet connection'
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        return f'The site returned HTTP {e.response.status_code}'
    return str(e)[:300]


# --------------------------------------------------------------------------
# Fetchers -> list of normalised dicts
# --------------------------------------------------------------------------
def fetch_rss(source: dict) -> list[dict]:
    resp = requests.get(source['url'], headers=HTTP_HEADERS, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f'could not parse feed: {feed.bozo_exception}')

    items = []
    for e in feed.entries:
        content_html = ''
        if e.get('content'):
            content_html = e['content'][0].get('value') or ''
        summary = clean_text(e.get('summary') or content_html, limit=500)
        body = clean_text(content_html or e.get('summary'), limit=1500)
        items.append({
            'title': clean_text(e.get('title'), limit=500),
            'summary': summary,
            'content': body if len(body) > len(summary) else summary,
            'url': e.get('link'),
            'image_url': _entry_image(e),
            'published_at': _entry_published(e),
            'tags': [t.get('term', '') for t in (e.get('tags') or []) if t.get('term')],
        })
    return items


def fetch_newsapi(source: dict, api_key: str) -> list[dict]:
    if not api_key:
        raise RuntimeError('NEWSAPI_KEY not set (CNN has no working public RSS feed, so it needs a free NewsAPI key)')
    resp = requests.get(
        NEWSAPI_TOP_HEADLINES,
        params={'sources': source['newsapi_id'], 'pageSize': 50, 'apiKey': api_key},
        headers=HTTP_HEADERS,
        timeout=FETCH_TIMEOUT,
    )
    data = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
    if resp.status_code != 200 or data.get('status') != 'ok':
        raise RuntimeError(data.get('message') or f'NewsAPI HTTP {resp.status_code}')

    items = []
    for a in data.get('articles', []):
        if not a.get('title') or a['title'] == '[Removed]':
            continue
        published = None
        if a.get('publishedAt'):
            try:
                published = datetime.fromisoformat(a['publishedAt'].replace('Z', '+00:00'))
            except ValueError:
                published = None
        summary = clean_text(a.get('description'), limit=500)
        # NewsAPI truncates `content` with "... [+1234 chars]"; strip that.
        content = re.sub(r'\s*\[\+\d+ chars\]$', '', clean_text(a.get('content'), limit=1500))
        items.append({
            'title': clean_text(a['title'], limit=500),
            'summary': summary,
            'content': content if len(content) > len(summary) else summary,
            'url': a.get('url'),
            'image_url': a.get('urlToImage'),
            'published_at': published,
            'tags': [],
        })
    return items


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def _upsert(item: dict, source: dict, categories: list[str]) -> Article | None:
    url = item.get('url')
    title = item.get('title')
    if not url or not title:
        return None

    category = source.get('category') or categorise(
        title, item.get('summary', ''), item.get('tags', []), categories, source['default_category']
    )
    if category not in categories:
        category = source['default_category'] if source['default_category'] in categories else categories[0]

    region = source['region']
    if region != 'zambia' and is_about_zambia(title, item.get('summary', '')):
        region = 'zambia'

    ext_id = _external_id(url)
    article = Article.query.filter_by(external_id=ext_id).first()
    # Category is only set on first insert: an existing article keeps its
    # category so rewards already logged against it stay on the same arm.
    if article is None:
        article = Article(external_id=ext_id, category=category, source_name=source['name'],
                          source_key=source['key'])
        db.session.add(article)

    article.title = title[:500]
    article.description = item.get('summary') or None
    article.content = item.get('content') or item.get('summary') or None
    article.url = url[:1000]
    if item.get('image_url'):
        article.image_url = item['image_url'][:1000]
    # The same story can appear in several feeds (BBC World and BBC Africa);
    # it stays attributed to the first source, but a Zambian tag from any
    # feed sticks.
    if article.region != 'zambia':
        article.region = region
    article.published_at = item.get('published_at') or article.published_at or datetime.now(timezone.utc)
    return article


def ingest_source(source: dict, categories: list[str], api_key: str, max_age_days: int,
                  image_lookups: int) -> dict:
    if source['kind'] == 'newsapi':
        items = fetch_newsapi(source, api_key)
    else:
        items = fetch_rss(source)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    saved = 0
    lookups_left = image_lookups
    for item in items:
        pub = item.get('published_at')
        if pub is not None and pub < cutoff:
            continue
        if not item.get('image_url') and lookups_left > 0 and item.get('url'):
            existing = Article.query.filter_by(external_id=_external_id(item['url'])).first()
            if existing and existing.image_url:
                item['image_url'] = existing.image_url
            else:
                item['image_url'] = _lookup_og_image(item['url'])
                lookups_left -= 1
        if _upsert(item, source, categories) is not None:
            saved += 1
    db.session.commit()
    return {'fetched': len(items), 'saved': saved}


def ingest_from_mock(categories: list[str]) -> dict:
    with open(MOCK_DATA_PATH, encoding='utf-8') as f:
        mock = json.load(f)

    counts = {}
    for category in categories:
        n = 0
        for a in mock.get(category, []):
            url = a.get('url')
            if not url or not a.get('title'):
                continue
            ext_id = _external_id(url)
            article = Article.query.filter_by(external_id=ext_id).first()
            if article is None:
                article = Article(external_id=ext_id, category=category)
                db.session.add(article)
            article.title = a['title'][:500]
            article.description = a.get('description')
            article.content = a.get('content') or a.get('description')
            article.url = url
            article.image_url = a.get('urlToImage')
            article.source_name = (a.get('source') or {}).get('name', 'Sample data')
            article.source_key = 'mock'
            article.region = 'zambia' if is_about_zambia(a['title'], a.get('description', '')) else 'international'
            try:
                article.published_at = datetime.fromisoformat(a['publishedAt'].replace('Z', '+00:00'))
            except (KeyError, ValueError, AttributeError):
                article.published_at = datetime.now(timezone.utc)
            n += 1
        counts[category] = n
    db.session.commit()
    return counts


def _has_live_articles() -> bool:
    return db.session.query(Article.id).filter(~Article.url.startswith(MOCK_URL_PREFIX)).first() is not None


def run_ingestion(config) -> dict:
    """
    Ingest from every enabled source. `config` is app.config (or any mapping
    with the same keys). Returns {'sources': {key: status}, 'total_saved': n,
    'used_mock': bool}.
    """
    if not _ingest_lock.acquire(blocking=False):
        return {'skipped': True, 'reason': 'an ingestion run is already in progress'}
    try:
        categories = config['NEWS_CATEGORIES']
        api_key = config.get('NEWSAPI_KEY', '')
        max_age = int(config.get('NEWS_MAX_AGE_DAYS', 7))
        image_lookups = int(config.get('NEWS_IMAGE_LOOKUPS_PER_SOURCE', 8))
        LAST_RUN['started_at'] = datetime.now(timezone.utc).isoformat()

        results = {}
        total_saved = 0
        for source in enabled_sources(config.get('NEWS_DISABLED_SOURCES', [])):
            now = datetime.now(timezone.utc).isoformat()
            try:
                r = ingest_source(source, categories, api_key, max_age, image_lookups)
                status = {'ok': True, 'last_run': now, 'error': None, **r}
                total_saved += r['saved']
            except Exception as e:  # one bad feed must not stop the rest
                db.session.rollback()
                status = {'ok': False, 'last_run': now, 'fetched': 0, 'saved': 0, 'error': describe_error(e)}
                print(f"[news_ingestion] {source['key']}: {status['error']}")
            SOURCE_STATUS[source['key']] = status
            results[source['key']] = status

        used_mock = False
        if total_saved == 0 and not _has_live_articles():
            print('[news_ingestion] no live source succeeded and the DB has no live articles; loading mock data')
            ingest_from_mock(categories)
            used_mock = True

        # New articles can change what's trending.
        from app.services.trending import clear_cache
        clear_cache()

        LAST_RUN['finished_at'] = datetime.now(timezone.utc).isoformat()
        LAST_RUN['used_mock'] = used_mock
        return {'sources': results, 'total_saved': total_saved, 'used_mock': used_mock}
    finally:
        _ingest_lock.release()
