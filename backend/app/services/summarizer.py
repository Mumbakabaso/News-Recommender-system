"""
Smart summaries: turns one article, or several outlets' articles about the
same story, into a single readable summary inside the app, so readers don't
have to leave for the publisher's site to understand the news.

Pipeline
  1. Pick the articles. For one article, related coverage of the same story
     from other outlets is found with the same headline-matching rules the
     Trending page uses (app/services/trending.py), within 72 hours of it.
     Trending stories pass their article ids directly.
  2. Fetch the full text of each article from the publisher
     (app/services/fulltext.py), falling back to the feed text.
  3. Summarise with one of two engines (hybrid design):
       - "gemini": Google's Gemini API rewrites the material as a clear,
         neutral summary with key points and "why it matters". Used when
         GEMINI_API_KEY is set.
       - "extractive": offline, no key, no cost. Scores every sentence by
         how central it is to the story (word-frequency centroid over all
         the articles), plus a lead-position bonus, then picks the top
         sentences while skipping near-duplicates (the same fact reported
         by two outlets). The result is the most informative sentences in
         reading order.
     If Gemini fails (no key, quota, network) the extractive engine is used,
     so a summary is always shown.
  4. Cache the result in the summaries table, keyed by engine + the exact
     article set, so each summary is written once and refreshed only when
     new coverage of the story arrives.

Copyright note: summaries are short, written in new words (Gemini) or limited
to a handful of sentences (extractive), always credit each outlet and link
to the original. The full text itself is never shown.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from app.extensions import db
from app.models.article import Article
from app.models.summary import Summary
from app.services.fulltext import ensure_full_text, best_text
from app.services import trending as trending_svc

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
# Tried in order if the configured model name isn't available on the account.
GEMINI_FALLBACK_MODELS = ['gemini-flash-latest', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']
GEMINI_TIMEOUT = 60
MAX_CHARS_PER_ARTICLE = 9_000
MAX_PROMPT_CHARS = 40_000
MAX_BUNDLE = 6
RELATED_WINDOW_HOURS = 72
WORDS_PER_MINUTE = 220

# Failed AI attempts are remembered briefly so a quota error doesn't make
# every page load wait for Gemini again.
_ai_backoff_until = 0.0
_inflight: dict[str, threading.Lock] = {}
_inflight_guard = threading.Lock()


# --------------------------------------------------------------------------
# 1. Choosing the articles
# --------------------------------------------------------------------------
def find_related(article: Article, limit: int = MAX_BUNDLE - 1) -> list[Article]:
    """
    Other outlets' articles about the same story, newest first. Uses the
    Trending page's matching rule: share ≥2 key headline terms including a
    named entity, or a term overlap (Jaccard) ≥ 0.35.
    """
    anchor_time = article.published_at or datetime.now(timezone.utc).replace(tzinfo=None)
    if anchor_time.tzinfo is not None:
        anchor_time = anchor_time.astimezone(timezone.utc).replace(tzinfo=None)
    window = timedelta(hours=RELATED_WINDOW_HOURS)
    candidates = (
        Article.query
        .filter(Article.id != article.id,
                Article.published_at >= anchor_time - window,
                Article.published_at <= anchor_time + window)
        .order_by(Article.published_at.desc())
        .limit(1500)
        .all()
    )
    if not candidates:
        return []

    toks = [(a, trending_svc._tokens(a.title)) for a in [article] + candidates]
    vocab = trending_svc._entity_vocab(t for _, t in toks)
    terms = {}
    for a, t in toks:
        terms[a.id] = trending_svc._terms(t, vocab)[:2]  # (key terms, entities)

    a_terms, a_ents = terms[article.id]
    if len(a_terms) < 2:
        return []

    a_vec = None
    scored = []
    for c in candidates:
        c_terms, c_ents = terms[c.id]
        shared = a_terms & c_terms
        if not shared:
            continue
        jaccard = len(shared) / len(a_terms | c_terms)
        if (len(shared) >= 2 and shared & (a_ents | c_ents)) or jaccard >= 0.35:
            scored.append((jaccard + 0.1 * len(shared), c))
        elif shared & (a_ents | c_ents):
            # Same name/place in both headlines but different wording
            # ("Kafue floods kill nine" vs "K20 million for Kafue flood
            # victims"): compare the story text itself.
            if a_vec is None:
                a_vec = _text_vector(article)
            sim = _cosine(a_vec, _text_vector(c))
            if sim >= 0.3:
                scored.append((sim, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    # One article per outlet, unless that's all there is: a story told by
    # three outlets beats three versions from the same feed.
    picked, seen_sources = [], {article.source_name}
    for _, c in scored:
        if c.source_name in seen_sources:
            continue
        picked.append(c)
        seen_sources.add(c.source_name)
        if len(picked) >= limit:
            break
    return picked


def _text_vector(a: Article) -> Counter:
    text = f"{a.title} {a.description or ''} {(a.full_text or a.content or '')[:1500]}"
    return Counter(_words(text))


def _cosine(u: Counter, v: Counter) -> float:
    if not u or not v:
        return 0.0
    dot = sum(u[k] * v[k] for k in u.keys() & v.keys())
    return dot / (math.sqrt(sum(x * x for x in u.values())) * math.sqrt(sum(x * x for x in v.values())))


# --------------------------------------------------------------------------
# 2-3a. Extractive engine (offline)
# --------------------------------------------------------------------------
_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])["”’)]?\s+(?=["“‘(]?[A-Z0-9])')
_WORD_RE = re.compile(r"[a-z][a-z'\-]+")
_ABBREV_FIX_RE = re.compile(r'\b(Mr|Mrs|Ms|Dr|Prof|St|Gen|Lt|Col|Sgt|Rev|Hon|Jr|Sr|No|vs|Inc|Ltd|Co)\.\s')
STOP = trending_svc.STOP_WORDS | set("""
also its it's he's she's they're we're i'm i've don't doesn't didn't won't can't isn't wasn't aren't
told according added including while since however although though still even well much many
""".split())


def split_sentences(text: str) -> list[str]:
    protected = _ABBREV_FIX_RE.sub(lambda m: m.group(1) + '<DOT> ', text)
    out = []
    for para in re.split(r'\n\s*\n|\n', protected):
        for s in _SENT_SPLIT_RE.split(para.strip()):
            s = s.replace('<DOT>', '.').strip()
            if 40 <= len(s) <= 400 and not s.endswith(':') and s.count(' ') >= 6:
                out.append(s)
    return out


def _stem(w: str) -> str:
    """Very light stemming so 'floods'/'flooding'/'flooded' count as one word."""
    for suffix in ('ing', 'ed', 'es', 's'):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            return w[: -len(suffix)]
    return w


def _words(s: str) -> list[str]:
    return [_stem(w) for w in _WORD_RE.findall(s.lower()) if w not in STOP and len(w) > 2]


def extractive_summary(docs: list[dict], target_sentences: int) -> list[str]:
    """
    docs: [{'text': ..., 'title': ...}] in priority order.
    Returns (doc index, sentence) pairs for the chosen sentences, in reading order.
    """
    sentences = []  # (doc_idx, position, sentence, words)
    for d_idx, d in enumerate(docs):
        for pos, s in enumerate(split_sentences(d['text'])):
            w = _words(s)
            if len(w) >= 4:
                sentences.append((d_idx, pos, s, w))
    if not sentences:
        return []

    # Centroid: how often each word appears across the whole story, with
    # headline words counted extra (headlines name what the story is about).
    freq = Counter()
    for *_, w in sentences:
        freq.update(set(w))
    for d in docs:
        for w in set(_words(d.get('title') or '')):
            freq[w] += 3
    top = freq.most_common(1)[0][1]

    def score(item):
        d_idx, pos, s, w = item
        centrality = sum(freq[x] / top for x in set(w)) / math.sqrt(len(set(w)))
        lead_bonus = 1.0 + 0.6 * math.exp(-pos / 3)     # journalists put key facts first
        source_bonus = 1.0 if d_idx == 0 else 0.92      # the article the reader opened leads
        quote_penalty = 0.85 if s.count('"') + s.count('“') >= 2 and len(s) > 200 else 1.0
        return centrality * lead_bonus * source_bonus * quote_penalty

    # Greedy selection with a novelty penalty (a simple form of Maximal
    # Marginal Relevance): a sentence is worth less the more of its words are
    # already covered by sentences we picked, so the same fact reported by
    # two outlets appears once and each outlet adds what's new.
    base = {id(it): score(it) for it in sentences}
    covered = Counter()
    chosen, pool = [], list(sentences)
    while pool and len(chosen) < target_sentences:
        def value(it):
            w = set(it[3])
            overlap = sum(1 for x in w if covered[x]) / len(w)
            return base[id(it)] * (1 - overlap) ** 1.5
        best = max(pool, key=value)
        pool.remove(best)
        w = set(best[3])
        if chosen and sum(1 for x in w if covered[x]) / len(w) > 0.6:
            continue  # mostly repeats what's already there
        chosen.append(best)
        covered.update(w)

    # Reading order: the opened article's sentences in their original order,
    # then what the other outlets add.
    chosen.sort(key=lambda x: (x[0], x[1]))
    return [(c[0], c[2]) for c in chosen]


def _paragraphs(picked: list[tuple[int, str]], per_para: int = 3) -> list[str]:
    """Group sentences into paragraphs, never mixing two outlets in one paragraph
    (so "He said..." always follows a sentence from the same article)."""
    paras, current, current_doc = [], [], None
    for doc, sent in picked:
        if current and (doc != current_doc or len(current) >= per_para):
            paras.append(' '.join(current))
            current = []
        current.append(sent)
        current_doc = doc
    if current:
        paras.append(' '.join(current))
    return paras


# --------------------------------------------------------------------------
# 3b. Gemini engine
# --------------------------------------------------------------------------
PROMPT = """You are a news editor writing for a news app used by readers in Zambia and around the world.
Write a clear, accurate summary of the story below so a reader understands it fully WITHOUT opening the original articles.

Rules:
- Use ONLY facts stated in the source articles. Do not add outside facts, guesses or opinions.
- Write in your own words, in plain English. Do not copy sentences from the sources.
- Neutral tone. Attribute claims to whoever made them ("police said", "according to Al Jazeera").
- {multi_rule}
- Explain any background a general reader needs (who people are, what an organisation does) only if the sources give it.
- Length: {length}.

Return ONLY a JSON object with exactly these keys:
{{
  "title": "a clear, neutral headline (max 14 words)",
  "summary": ["paragraph 1", "paragraph 2", "..."],
  "key_points": ["3 to 5 short bullet points with the most important facts"],
  "why_it_matters": "1-2 sentences on why this matters to readers, or an empty string if the sources don't say"
}}

SOURCE ARTICLES:
{articles}
"""


def _gemini_models(cfg) -> list[str]:
    first = (cfg.get('GEMINI_MODEL') or '').strip()
    models = [first] if first else []
    return models + [m for m in GEMINI_FALLBACK_MODELS if m not in models]


def gemini_summary(articles: list[Article], texts: list[str], cfg) -> dict | None:
    global _ai_backoff_until
    api_key = (cfg.get('GEMINI_API_KEY') or '').strip()
    if not api_key or time.time() < _ai_backoff_until:
        return None

    blocks, budget = [], MAX_PROMPT_CHARS
    for i, (a, t) in enumerate(zip(articles, texts), start=1):
        t = t[:min(MAX_CHARS_PER_ARTICLE, max(budget, 0))]
        if not t:
            break
        budget -= len(t)
        when = a.published_at.strftime('%d %b %Y %H:%M UTC') if a.published_at else 'unknown time'
        blocks.append(f'--- Article {i}: {a.source_name} ({when})\nHeadline: {a.title}\n\n{t}')

    multi = len(blocks) > 1
    prompt = PROMPT.format(
        multi_rule=('Several outlets covered this story. Combine them into ONE story; mention where outlets '
                    'report different numbers or details, and name the outlet when a fact comes from only one.')
        if multi else 'Summarise this single article.',
        length='4 to 6 short paragraphs (about 300-500 words)' if multi else '3 to 5 short paragraphs (about 200-400 words)',
        articles='\n\n'.join(blocks),
    )
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.3, 'responseMimeType': 'application/json', 'maxOutputTokens': 2048},
    }

    last_error = None
    for model in _gemini_models(cfg):
        try:
            resp = requests.post(GEMINI_URL.format(model=model), json=body, timeout=GEMINI_TIMEOUT,
                                 headers={'x-goog-api-key': api_key, 'Content-Type': 'application/json'})
        except requests.RequestException as e:
            last_error = str(e)
            break
        if resp.status_code == 404:          # model name not available: try the next one
            last_error = f'model {model} not found'
            continue
        if resp.status_code != 200:
            try:
                last_error = resp.json().get('error', {}).get('message') or f'HTTP {resp.status_code}'
            except ValueError:
                last_error = f'HTTP {resp.status_code}'
            if resp.status_code in (429, 503):  # quota / overloaded: back off for a few minutes
                _ai_backoff_until = time.time() + 300
            break
        try:
            data = resp.json()
            text = ''.join(p.get('text', '') for p in data['candidates'][0]['content']['parts'])
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            parsed = json.loads(text)
            paragraphs = [p.strip() for p in parsed.get('summary', []) if isinstance(p, str) and p.strip()]
            if not paragraphs:
                raise ValueError('empty summary')
            return {
                'engine': 'gemini',
                'model': model,
                'title': (parsed.get('title') or '').strip() or None,
                'paragraphs': paragraphs,
                'key_points': [k.strip() for k in parsed.get('key_points', []) if isinstance(k, str) and k.strip()][:6],
                'why_it_matters': (parsed.get('why_it_matters') or '').strip() or None,
            }
        except (KeyError, IndexError, ValueError, TypeError) as e:
            last_error = f'unreadable response ({e})'
            break

    print(f'[summarizer] Gemini unavailable, using offline summary: {last_error}')
    return None


# --------------------------------------------------------------------------
# 4. Orchestration + cache
# --------------------------------------------------------------------------
def _cache_key(engine: str, ids: list[int]) -> str:
    # The lead article matters (its reporting opens the summary), the order
    # of the rest doesn't.
    lead, rest = ids[0], sorted(ids[1:])
    digest = hashlib.sha1(f"{lead}|{','.join(map(str, rest))}".encode()).hexdigest()[:24]
    return f'{engine}:{digest}'


def _source_entry(a: Article) -> dict:
    return {
        'id': a.id,
        'title': a.title,
        'source_name': a.source_name,
        'url': a.url,
        'published_at': a.published_at.isoformat() if a.published_at else None,
        'had_full_text': a.full_text_status == 'ok',
    }


def _lock_for(key: str) -> threading.Lock:
    with _inflight_guard:
        return _inflight.setdefault(key, threading.Lock())


def summarise_articles(articles: list[Article], kind: str) -> dict:
    """Summary for this exact list of articles (first = lead). Cached."""
    cfg = current_app.config
    articles = articles[:MAX_BUNDLE]
    ids = [a.id for a in articles]
    wants_ai = bool((cfg.get('GEMINI_API_KEY') or '').strip())
    preferred_key = _cache_key('gemini' if wants_ai else 'extractive', ids)

    with _lock_for(preferred_key):  # two readers opening the same story = one summary run
        cached = Summary.query.filter_by(cache_key=preferred_key).first()
        if cached:
            return {**cached.payload, 'cached': True}

        offline_key = _cache_key('extractive', ids)
        offline_cached = Summary.query.filter_by(cache_key=offline_key).first() if wants_ai else None
        if offline_cached and time.time() < _ai_backoff_until:
            # Gemini is in a quota back-off: serve the offline version we already have.
            return {**offline_cached.payload, 'cached': True}

        ensure_full_text(articles)
        texts = [best_text(a) for a in articles]

        result = gemini_summary(articles, texts, cfg) if wants_ai else None
        if result is None and offline_cached:
            return {**offline_cached.payload, 'cached': True}
        if result is None:
            n_sent = 7 if len(articles) == 1 else min(12, 6 + 2 * len(articles))
            docs = [{'text': t, 'title': a.title} for a, t in zip(articles, texts)]
            sentences = extractive_summary(docs, n_sent)
            if not sentences:  # nothing longer than a headline to work with
                sentences = [(0, s) for s in (articles[0].description, articles[0].content) if s][:1]
            result = {
                'engine': 'extractive',
                'model': None,
                'title': None,
                'paragraphs': _paragraphs(sentences),
                'key_points': [],
                'why_it_matters': None,
            }

        words = sum(len(p.split()) for p in result['paragraphs'] + result['key_points'])
        payload = {
            **result,
            'kind': kind,
            'title': result['title'] or articles[0].title,
            'reading_minutes': max(1, round(words / WORDS_PER_MINUTE)),
            'source_count': len({a.source_name for a in articles}),
            'sources': [_source_entry(a) for a in articles],
            'full_text_count': sum(1 for a in articles if a.full_text_status == 'ok'),
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        # Only cache what the reader would actually want to keep: if Gemini
        # was wanted but failed, don't store the offline version under the AI
        # key; it's stored under its own key and Gemini is retried next time.
        key = _cache_key(payload['engine'], ids)
        if not Summary.query.filter_by(cache_key=key).first():
            db.session.add(Summary(cache_key=key, kind=kind, engine=payload['engine'],
                                   article_ids=','.join(map(str, sorted(ids))), payload=payload))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return {**payload, 'cached': False}


def summarise_article(article: Article, include_related: bool = True) -> dict:
    related = find_related(article) if include_related else []
    return summarise_articles([article] + related, 'story' if related else 'article')


def summarise_story(article_ids: list[int]) -> dict | None:
    found = {a.id: a for a in Article.query.filter(Article.id.in_(article_ids)).all()}
    articles = [found[i] for i in article_ids if i in found]
    if not articles:
        return None
    return summarise_articles(articles, 'story' if len(articles) > 1 else 'article')


def prewarm_trending(app, top: int = 5) -> int:
    """Write summaries for the top trending stories ahead of time (called after each news refresh)."""
    done = 0
    try:
        data = trending_svc.get_trending(hours=48, limit=top)
    except Exception as e:
        print(f'[summarizer] prewarm skipped: {e}')
        return 0
    for story in data.get('stories', []):
        ids = [a['id'] for a in story.get('articles', [])]
        if len(ids) < 2:
            continue
        try:
            summarise_story(ids)
            done += 1
        except Exception as e:
            db.session.rollback()
            print(f'[summarizer] prewarm failed for "{story.get("label")}": {e}')
    return done
