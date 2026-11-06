"""
Assigns each incoming article to one of the recommender's topic categories
(the bandit's "arms") and decides whether it is Zambian news.

General feeds (Al Jazeera's "all", Lusaka Times, Times of Zambia...) mix
every topic in one stream, but the RL engine needs every article in exactly
one of NEWS_CATEGORIES. This is a transparent keyword scorer rather than an
ML classifier on purpose: it needs no training data, it's easy to explain in
the write-up, and the publisher's own RSS <category> tags (when present) are
weighted more heavily than words in the text.

Region is decided separately: anything from a Zambian outlet is 'zambia',
and an international story is also tagged 'zambia' when it is clearly about
Zambia (e.g. a BBC Africa piece on Lusaka), so the "Zambia" filter shows
both local and international coverage of the country.
"""
from __future__ import annotations
import re

# Publisher <category> tags -> our category. Matched case-insensitively as
# substrings, so 'Power and Politics' hits 'politics', 'Mining & Energy'
# hits 'mining', etc.
TAG_MAP = {
    'politic': 'politics', 'election': 'politics', 'parliament': 'politics', 'court': 'politics',
    'government': 'politics', 'governance': 'politics',
    'business': 'economics', 'econom': 'economics', 'market': 'economics', 'mining': 'economics',
    'energy': 'economics', 'agricultur': 'economics', 'finance': 'economics', 'money': 'economics',
    'tech': 'technology', 'science': 'technology', 'digital': 'technology', 'innovation': 'technology',
    'sport': 'sports', 'football': 'sports', 'soccer': 'sports', 'goal diggers': 'sports',
    'health': 'health', 'covid': 'health', 'medic': 'health',
    'world': 'global-affairs', 'international': 'global-affairs', 'africa': 'global-affairs',
    'middle east': 'global-affairs', 'diplomac': 'global-affairs',
}

KEYWORDS = {
    'politics': [
        'president', 'parliament', 'minister', 'election', 'vote', 'voter', 'party', 'opposition',
        'government', 'cabinet', 'senator', 'congress', 'lawmaker', 'constitution', 'policy',
        'hichilema', 'upnd', 'pf ', 'patriotic front', 'state house', 'ecz', 'by-election', 'court',
        'judge', 'corruption', 'campaign', 'governor', 'prime minister', 'bill', 'legislation',
    ],
    'economics': [
        'economy', 'economic', 'inflation', 'kwacha', 'dollar', 'interest rate', 'central bank',
        'bank of zambia', 'boz', 'gdp', 'budget', 'debt', 'imf', 'world bank', 'investment',
        'investor', 'market', 'stock', 'shares', 'trade', 'tariff', 'export', 'import', 'copper',
        'mining', 'mine', 'fuel', 'price', 'prices', 'tax', 'revenue', 'business', 'company',
        'jobs', 'unemployment', 'farmers', 'maize', 'agriculture', 'energy', 'electricity',
        'zesco', 'load-shedding', 'loadshedding', 'oil', 'earnings', 'profit',
    ],
    'technology': [
        'technology', 'tech', ' ai ', 'artificial intelligence', 'software', 'app ', 'apple',
        'google', 'microsoft', 'meta', 'openai', 'chip', 'semiconductor', 'internet', 'cyber',
        'hack', 'data', 'digital', 'smartphone', 'startup', 'robot', 'space', 'nasa', 'satellite',
        'mobile money', 'airtel', 'mtn', 'zamtel', 'telecom', 'innovation', 'science',
        '5g', '4g', 'broadband', 'ict', 'fibre', 'network coverage', 'e-government', 'smart zambia',
        'zicta', 'computer', 'online',
    ],
    'global-affairs': [
        'united nations', ' un ', 'war', 'conflict', 'ceasefire', 'military', 'troops', 'nato',
        'diplomat', 'summit', 'sanctions', 'refugee', 'gaza', 'israel', 'ukraine', 'russia',
        'china', 'iran', 'sudan', 'congo', 'drc', 'sadc', 'african union', 'foreign',
        'embassy', 'border', 'international', 'global', 'humanitarian',
    ],
    'sports': [
        'sport', 'football', 'soccer', 'match', 'league', 'cup', 'goal', 'coach', 'striker',
        'tournament', 'olympic', 'athlete', 'fifa', 'caf', 'afcon', 'chipolopolo', 'copper queens',
        'faz', 'super league', 'zesco united', 'power dynamos', 'nkana', 'red arrows', 'tennis',
        'cricket', 'rugby', 'boxing', 'marathon', 'champions league', 'premier league', 'nba',
        'formula 1', 'f1 ', 'win over', 'defeat', 'fixture', 'squad',
    ],
    'health': [
        'health', 'hospital', 'disease', 'virus', 'outbreak', 'cholera', 'malaria', 'hiv', 'aids',
        'tuberculosis', 'vaccine', 'vaccination', 'doctor', 'nurse', 'patient', 'medical',
        'medicine', 'drug', 'cancer', 'covid', 'mpox', 'clinic', 'ministry of health',
        'world health organization', 'mental health', 'nutrition', 'maternal',
    ],
}

# Words that appear in almost every Zambian story whatever it's about
# ("the Minister of Health said...", "government will support farmers...").
# Counted at a fraction of a normal keyword, otherwise nearly every local
# health, tech or farming story is filed under politics and readers who
# chose those topics see almost nothing in the Zambia feed.
WEAK_KEYWORDS = {
    'politics': {'minister', 'government', 'policy', 'cabinet', 'bill', 'party', 'court', 'judge'},
}
WEAK_WEIGHT = 0.4

ZAMBIA_MARKERS = [
    'zambia', 'zambian', 'lusaka', 'ndola', 'kitwe', 'livingstone', 'copperbelt', 'kabwe',
    'chingola', 'hichilema', 'kwacha', 'chipolopolo', 'zesco', 'znbc',
]

TAG_WEIGHT = 3.0


def _compile(words):
    # Whole-word match (with an optional plural "s"), so 'war' doesn't fire on
    # 'software' and 'mine' doesn't fire on 'determine'.
    alts = '|'.join(re.escape(w.strip()) for w in words)
    return re.compile(r'\b(?:' + alts + r')s?\b', re.IGNORECASE)


_KEYWORD_RES = {
    cat: [(_compile([w]), WEAK_WEIGHT if w.strip() in WEAK_KEYWORDS.get(cat, ()) else 1.0) for w in words]
    for cat, words in KEYWORDS.items()
}
_ZAMBIA_RE = _compile(ZAMBIA_MARKERS)


def categorise(title: str, summary: str, tags: list[str], allowed: list[str], default: str) -> str:
    """Return the best-matching category from `allowed`, or `default`."""
    scores = {c: 0.0 for c in allowed}

    for tag in tags or []:
        t = tag.lower()
        for needle, cat in TAG_MAP.items():
            if needle in t and cat in scores:
                scores[cat] += TAG_WEIGHT
                break

    # Title hits count double: headlines are a much cleaner topic signal
    # than the summary text.
    title = title or ''
    summary = summary or ''
    for cat, patterns in _KEYWORD_RES.items():
        if cat not in scores:
            continue
        for pat, weight in patterns:
            if pat.search(title):
                scores[cat] += 2.0 * weight
            if pat.search(summary):
                scores[cat] += 1.0 * weight

    # On a tie, prefer a specific topic over the feed's catch-all default
    # (usually politics for Zambian outlets).
    best_cat, best_score = (
        max(scores.items(), key=lambda kv: (kv[1], kv[0] != default)) if scores else (default, 0)
    )
    if best_score <= 0:
        return default if default in allowed else (allowed[0] if allowed else default)
    return best_cat


def is_about_zambia(title: str, summary: str) -> bool:
    return bool(_ZAMBIA_RE.search(f'{title or ""} {summary or ""}'))
