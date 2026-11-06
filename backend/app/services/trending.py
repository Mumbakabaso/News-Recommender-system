"""
"Trending now": finds the stories that many outlets are covering at once.

There's no external "trending" API involved. A story counts as hot when
several independent sources (BBC, Al Jazeera, CNN, Zambian outlets...)
publish about the same thing within a short time window. That's the same
signal news editors use, and it's computed entirely from articles we have
already ingested.

Steps:
  1. Take articles published in the last `hours` (default 48).
  2. Reduce each headline to its key terms: lower-cased words minus stop
     words. Words that appear capitalised mid-sentence in any headline
     (names, places: "Hichilema", "Gaza", "Morgan Freeman") are treated as
     entities everywhere they occur, including at the start of a headline.
  3. Group headlines into stories (single-link clustering): two articles
     join the same story when they share at least two key terms, at least
     one of which is an entity, or when their term overlap (Jaccard) is
     ≥ 0.35.
  4. Score each story:
        score = 3.0 * distinct sources
              + 1.0 * articles
              + 2.5 if it's breaking-type news (deaths, disasters, attacks...)
              + 0.5 * recent clicks (user engagement from the interactions table)
        then multiplied by a recency decay with a 12-hour half-life
  5. Label each story with its most shared entity phrase, plus the event
     word when there is one (e.g. "Turkey earthquake") and return the top N with a lead article and the sources
     covering it.

Results are cached for a few minutes, because clustering runs over every
recent article.
"""
from __future__ import annotations
import math
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models.article import Article
from app.models.interaction import Interaction

STOP_WORDS = set("""
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our
out over own same she should so some such than that the their them then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your
says say said new news live latest update updates report reports amid after over year years day days week weeks
first last us uk vs via how what why who video watch photos pictures analysis opinion explained could may might
one two three four five six seven eight nine ten get gets got make makes made take takes took back set sets
""".split())

# Words that mark breaking-type news — deaths, disasters, attacks, major
# political events. Matched as whole words in the headline.
BREAKING_TERMS = {
    'death': ['dies', 'died', 'dead', 'death', 'passes away', 'passed away', 'obituary', 'killed', 'mourns',
              'tributes', 'funeral', 'dies aged'],
    'disaster': ['earthquake', 'quake', 'tsunami', 'hurricane', 'cyclone', 'typhoon', 'flood', 'floods',
                 'flooding', 'wildfire', 'wildfires', 'landslide', 'volcano', 'eruption', 'drought', 'storm',
                 'tornado', 'disaster', 'evacuate', 'evacuated', 'evacuation'],
    'emergency': ['explosion', 'blast', 'crash', 'plane crash', 'attack', 'shooting', 'gunman', 'bomb',
                  'collapse', 'collapsed', 'fire', 'outbreak', 'emergency', 'breaking', 'state of emergency'],
    'politics': ['resigns', 'resignation', 'ousted', 'coup', 'impeached', 'elected', 'wins election',
                 'sworn in', 'arrested'],
}
_BREAKING_RES = {
    kind: re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b', re.IGNORECASE)
    for kind, words in BREAKING_TERMS.items()
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
CACHE_SECONDS = 300
_cache: dict = {}
_cache_lock = threading.Lock()


def _tokens(title: str) -> list[tuple[str, str, bool]]:
    """
    Split a headline into (original word, normalised term, capitalised mid-sentence?).
    Stop words come back with an empty term so phrase boundaries are kept.
    """
    out = []
    words = _WORD_RE.findall(title or '')
    # Title Case Headlines ("Chipolopolo Edge Malawi To Boost Hopes", common
    # on Zambian sites) capitalise every word, so capitalisation says nothing
    # about names there.
    caps = sum(1 for w in words if w[0].isupper())
    title_case = len(words) >= 4 and caps / len(words) > 0.7
    prev_end = 0
    text = title or ''
    for i, m in enumerate(_WORD_RE.finditer(text)):
        w = m.group(0)
        clean = w.strip("'-").lower()
        if clean.endswith("'s"):
            clean = clean[:-2]
        before = text[prev_end:m.start()]
        prev_end = m.end()
        sentence_start = i == 0 or ':' in before or '?' in before or '.' in before
        is_cap_mid = (w[0].isupper() and not sentence_start and not title_case) or (w.isupper() and len(w) > 1)
        if len(clean) < 3 or clean in STOP_WORDS:
            out.append((w, '', False))
        else:
            out.append((w.strip("'-").removesuffix("'s"), clean, is_cap_mid))
    return out


def _entity_vocab(token_lists) -> set[str]:
    """Words that appear capitalised mid-sentence in any headline = names/places."""
    vocab = set()
    for toks in token_lists:
        for _, term, cap in toks:
            if term and cap:
                vocab.add(term)
    return vocab


def _terms(tokens, vocab) -> tuple[set[str], set[str], list[str]]:
    """Return (key terms, entity terms, entity phrases) for one tokenised headline."""
    terms, entities, phrases, current = set(), set(), [], []
    for word, term, _ in tokens:
        if term:
            terms.add(term)
        if term and term in vocab:
            entities.add(term)
            current.append(word[0].upper() + word[1:])
        elif current:
            phrases.append(' '.join(current))
            current = []
    if current:
        phrases.append(' '.join(current))
    return terms, entities, phrases


def _breaking_kind(text: str) -> str | None:
    for kind, rx in _BREAKING_RES.items():
        if rx.search(text or ''):
            return kind
    return None


def _cluster(items: list[dict]) -> list[list[int]]:
    """Single-link clustering over headline term overlap (union-find)."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Only compare articles that share at least one entity: an inverted index
    # keeps this fast even with thousands of recent articles.
    by_entity = defaultdict(list)
    for idx, it in enumerate(items):
        for e in it['entities']:
            by_entity[e].append(idx)

    for idxs in by_entity.values():
        if len(idxs) > 200:  # extremely common word ("Trump") — too broad to link on alone
            idxs = idxs[:200]
        for a_pos in range(len(idxs)):
            a = items[idxs[a_pos]]
            for b_idx in idxs[a_pos + 1:]:
                b = items[b_idx]
                shared = a['terms'] & b['terms']
                if not shared:
                    continue
                jaccard = len(shared) / len(a['terms'] | b['terms'])
                if (len(shared) >= 2 and shared & (a['entities'] | b['entities'])) or jaccard >= 0.35:
                    ra, rb = find(idxs[a_pos]), find(b_idx)
                    if ra != rb:
                        parent[rb] = ra

    groups = defaultdict(list)
    for i in range(len(items)):
        groups[find(i)].append(i)
    return list(groups.values())


EVENT_NOUNS = ['earthquake', 'tsunami', 'hurricane', 'cyclone', 'typhoon', 'floods', 'flood', 'wildfire',
               'wildfires', 'landslide', 'eruption', 'drought', 'storm', 'tornado', 'explosion', 'blast', 'crash',
               'attack', 'shooting', 'outbreak', 'coup', 'election', 'reshuffle', 'strike', 'protests']
_EVENT_RE = re.compile(r'\b(' + '|'.join(EVENT_NOUNS) + r')\b', re.IGNORECASE)


def _label(members: list[dict]) -> str:
    """Main entity phrase, plus the event word when there is one: "Turkey earthquake"."""
    base = _base_label(members)
    events = Counter(m.group(1).lower() for it in members for m in [_EVENT_RE.search(it['article'].title)] if m)
    if events:
        event, n = events.most_common(1)[0]
        if n >= max(1, len(members) // 2) and event not in base.lower():
            return f'{base} {event}'
    return base


def _base_label(members: list[dict]) -> str:
    """Most frequent entity phrase across the story's headlines."""
    phrase_counts = Counter()
    for m in members:
        for p in set(m['phrases']):
            phrase_counts[p] += 1
    if phrase_counts:
        # Prefer phrases seen in more headlines, then longer ones ("Hurricane
        # Milton" over "Milton").
        best = max(phrase_counts.items(), key=lambda kv: (kv[1], len(kv[0].split()), len(kv[0])))
        if best[1] >= 2 or len(members) == 1:
            return best[0]
    term_counts = Counter(t for m in members for t in m['entities'] or m['terms'])
    if term_counts:
        return ' '.join(w.title() for w, _ in term_counts.most_common(2))
    return members[0]['article'].title[:60]


def compute_trending(region: str | None = None, hours: int = 48, limit: int = 10) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    q = Article.query.filter(Article.published_at >= since)
    if region:
        q = q.filter(Article.region == region)
    articles = q.order_by(Article.published_at.desc()).limit(3000).all()

    # Recent engagement per article (clicks + reads in the window).
    engagement = dict(
        db.session.query(Interaction.article_id, func.count(Interaction.id))
        .filter(Interaction.event_type.in_(['click', 'read']), Interaction.created_at >= since)
        .group_by(Interaction.article_id)
        .all()
    ) if articles else {}

    tokenised = [(a, _tokens(a.title)) for a in articles]
    vocab = _entity_vocab(t for _, t in tokenised)
    items = []
    for a, toks in tokenised:
        terms, entities, phrases = _terms(toks, vocab)
        if len(terms) < 2:
            continue
        items.append({'article': a, 'terms': terms, 'entities': entities, 'phrases': phrases})

    stories = []
    for group in _cluster(items):
        members = [items[i] for i in group]
        arts = [m['article'] for m in members]
        sources = sorted({a.source_name for a in arts if a.source_name})
        kinds = Counter(k for a in arts if (k := _breaking_kind(f'{a.title} {a.description or ""}')))
        kind = kinds.most_common(1)[0][0] if kinds else None
        clicks = sum(engagement.get(a.id, 0) for a in arts)

        newest = max((a.published_at for a in arts if a.published_at), default=now.replace(tzinfo=None))
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        age_hours = max((now - newest).total_seconds() / 3600, 0)
        decay = 0.5 ** (age_hours / 12)

        raw = 3.0 * len(sources) + 1.0 * len(arts) + (2.5 if kind else 0) + 0.5 * clicks
        score = raw * decay

        # A one-article "story" is only trending if it's breaking-type news
        # or people are actually clicking it.
        if len(sources) < 2 and not kind and clicks < 3:
            continue

        # Lead article: prefer one with an image, then the newest.
        arts.sort(key=lambda a: (bool(a.image_url), a.published_at or datetime.min), reverse=True)
        lead = arts[0]
        stories.append({
            'label': _label(members),
            'score': round(score, 3),
            'kind': kind,
            'is_breaking': kind in ('death', 'disaster', 'emergency') and age_hours <= 24,
            'source_count': len(sources),
            'sources': sources,
            'article_count': len(arts),
            'clicks': clicks,
            'latest_at': newest.isoformat(),
            'region': 'zambia' if any(a.region == 'zambia' for a in arts) else 'international',
            'lead': lead.to_dict(),
            'articles': [a.to_dict() for a in arts[:5]],
        })

    stories.sort(key=lambda s: s['score'], reverse=True)
    stories = stories[:limit]

    # "Hot topics" chips: the most-covered entity words across the window,
    # weighted by how many different sources used them.
    entity_sources = defaultdict(set)
    for it in items:
        for p in it['phrases']:
            entity_sources[p].add(it['article'].source_name)
    hot_topics = [
        {'topic': p, 'source_count': len(srcs)}
        for p, srcs in sorted(entity_sources.items(), key=lambda kv: (len(kv[1]), len(kv[0])), reverse=True)
        if len(srcs) >= 2 and p.lower() not in STOP_WORDS
    ][:12]

    return {
        'generated_at': now.isoformat(),
        'window_hours': hours,
        'region': region,
        'stories': stories,
        'hot_topics': hot_topics,
    }


def get_trending(region: str | None = None, hours: int = 48, limit: int = 10) -> dict:
    key = (region, hours, limit)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    result = compute_trending(region, hours, limit)
    with _cache_lock:
        _cache[key] = (time.time(), result)
    return result


def clear_cache():
    with _cache_lock:
        _cache.clear()
