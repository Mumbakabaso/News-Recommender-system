"""
Entity resolution and disambiguation: deciding WHO a name refers to.

Known people (already in the database) are found by the gazetteer. A name
we have not seen before is looked up on Wikidata and every candidate item
is scored:

    0.50 x name match      exact label/alias = 1.0; same first + last name
                           (middle names omitted) = 0.9; otherwise rejected
  + 0.25  Zambian citizen, in a Zambian story          (Zambia-first)
  + 0.05  Zambian citizen, in an international story
  - 0.10  not Zambian and little known, in a Zambian story
  + 0.15  the person's field fits the article's topic (a footballer in a
          sports story, a politician in a politics story)
  - 0.20  the field clearly does not fit
  + 0.15  the title used in the article fits ("Minister" + holds office)
  + 0..0.15 how notable the person is (Wikipedia language editions)

A candidate is accepted only if it scores at least ACCEPT_SCORE and is
clearly ahead of the runner-up (MARGIN). Anything less stays unlinked: a
missing link is better than a wrong one. Every decision is recorded in
person_candidates so the same name is not looked up again for a week.
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.person import Person, PersonCandidate
from app.services.people import sources as src
from app.services.people.ner import NameCandidate
from app.services.people.registry import person_from_entity, news_only_person
from app.services.people.text import normalize, DOMAIN_WORDS, OFFICE_TITLES

ACCEPT_SCORE = 0.70
MARGIN = 0.10
RELOOKUP_AFTER = timedelta(days=7)
# A local figure who is not on Wikidata gets a news-only profile once they
# have been named with an office title by at least this many different outlets.
NEWS_ONLY_MIN_SOURCES = 2


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _name_score(cand_norm: str, ent: dict) -> float:
    names = [src.label(ent) or ''] + src.aliases(ent)
    best = 0.0
    c_tokens = cand_norm.split()
    for n in names:
        nn = normalize(n)
        if not nn:
            continue
        if nn == cand_norm:
            return 1.0
        t = nn.split()
        if len(c_tokens) >= 2 and len(t) >= 2 and c_tokens[0] == t[0] and c_tokens[-1] == t[-1] \
                and set(c_tokens) <= set(t):
            best = max(best, 0.9)
    return best


def _domain_fit(category: str | None, ent: dict) -> float:
    words = DOMAIN_WORDS.get(category or '')
    if not words:
        return 0.0
    desc = (src.description(ent) or '').lower()
    text = set(desc.replace('-', ' ').split())
    if src.claims(ent, 'P39'):
        text |= {'politician', 'official'}
    if not text:
        return 0.0
    if text & words:
        return 0.15
    # Description names a different field entirely
    other = set().union(*[w for k, w in DOMAIN_WORDS.items() if k != category]) - words
    return -0.20 if text & other else 0.0


def score_entity(cand: NameCandidate, ent: dict, zambian_ctx: bool, category: str | None) -> float:
    name = _name_score(normalize(cand.name), ent)
    if name == 0:
        return 0.0
    score = 0.5 * name
    zambian = src.ZAMBIA_QID in [src.claim_value(c) for c in src.claims(ent, 'P27')]
    if zambian:
        score += 0.25 if zambian_ctx else 0.05
    elif zambian_ctx and src.sitelink_count(ent) < 30:
        score -= 0.10   # a little-known foreigner is an unlikely match in a Zambian story
    score += _domain_fit(category, ent)
    if cand.title and any(t in cand.title for t in OFFICE_TITLES) and \
            (src.claims(ent, 'P39') or 'politician' in (src.description(ent) or '').lower()):
        score += 0.15
    score += 0.15 * min(math.log1p(src.sitelink_count(ent)) / math.log1p(40), 1.0)
    return round(score, 3)


def _is_human(ent: dict) -> bool:
    return src.HUMAN_QID in [src.claim_value(c) for c in src.claims(ent, 'P31')]


def lookup_wikidata(cand: NameCandidate, zambian_ctx: bool, category: str | None) -> tuple[str, dict, float] | None:
    """Best-matching human on Wikidata, or None if nobody is a confident match."""
    qids = src.wikidata_search(cand.name)
    if not qids:
        return None
    ents = src.wikidata_entities(qids)
    scored = []
    for qid in qids:
        ent = ents.get(qid)
        if not ent or not _is_human(ent):
            continue
        s = score_entity(cand, ent, zambian_ctx, category)
        if s > 0:
            scored.append((s, qid, ent))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    if best[0] < ACCEPT_SCORE:
        return None
    if len(scored) > 1 and best[0] - scored[1][0] < MARGIN:
        return None  # two people fit almost equally well: don't guess
    return best[1], best[2], best[0]


def record_candidate(cand: NameCandidate, article, zambian_ctx: bool) -> PersonCandidate:
    norm = normalize(cand.name)
    pc = PersonCandidate.query.filter_by(normalized=norm).first()
    if not pc:
        pc = PersonCandidate(normalized=norm, name=cand.name, mention_count=0, article_ids=[], sources=[])
        db.session.add(pc)
    ids = list(pc.article_ids or [])
    if article.id not in ids:
        ids.append(article.id)
        pc.mention_count = (pc.mention_count or 0) + 1
        if zambian_ctx:
            pc.zambian_context = (pc.zambian_context or 0) + 1
    pc.article_ids = ids[-50:]
    srcs = list(pc.sources or [])
    if article.source_name and article.source_name not in srcs:
        srcs.append(article.source_name)
    pc.sources = srcs[-20:]
    if cand.title and not pc.title_cue:
        pc.title_cue = cand.title[:80]
    pc.last_seen_at = _now()
    return pc


def resolve_candidate(cand: NameCandidate, article, zambian_ctx: bool, allow_lookup: bool) -> tuple[Person | None, float, str]:
    """
    Returns (person, confidence, method) or (None, 0, reason). Uses the
    candidate cache so each unknown name costs at most one Wikidata lookup a week.
    """
    pc = record_candidate(cand, article, zambian_ctx)
    if pc.status == 'rejected':
        return None, 0.0, 'rejected'
    if pc.status == 'resolved' and pc.person_id:
        p = Person.query.get(pc.person_id)
        if p:
            return p, 0.9, 'candidate-cache'

    fresh = pc.lookup_attempted_at and _now() - pc.lookup_attempted_at < RELOOKUP_AFTER
    if not fresh and allow_lookup and cand.strength in ('strong', 'medium'):
        pc.lookup_attempted_at = _now()
        cand.looked_up = True
        try:
            found = lookup_wikidata(cand, zambian_ctx, article.category)
        except src.SourceError as e:
            print(f'[people.resolver] Wikidata lookup failed for "{cand.name}": {e}')
            pc.status = 'lookup_failed'
            pc.lookup_attempted_at = None   # retry next run
            found = None
        if found:
            qid, ent, score = found
            person = person_from_entity(qid, ent)
            pc.status, pc.person_id = 'resolved', person.id
            return person, min(score, 1.0), 'wikidata'
        if pc.status != 'lookup_failed':
            pc.status = 'unresolved'

    # Local figures not on Wikidata (councillors, mayors, ward officials...):
    # a news-only profile once several outlets name them with an office.
    if pc.status == 'unresolved' and pc.title_cue and any(t in pc.title_cue for t in OFFICE_TITLES) \
            and len(pc.sources or []) >= NEWS_ONLY_MIN_SOURCES and (pc.zambian_context or 0) >= 1:
        person = news_only_person(pc.name, pc.title_cue, zambian=True)
        pc.status, pc.person_id = 'resolved', person.id
        # Earlier articles that named them before they qualified get rescanned on the next run.
        from app.models.article import Article
        others = [i for i in (pc.article_ids or []) if i != article.id]
        if others:
            Article.query.filter(Article.id.in_(others)).update({Article.people_scanned_at: None},
                                                                synchronize_session=False)
        return person, 0.7, 'news_only'
    return None, 0.0, pc.status
