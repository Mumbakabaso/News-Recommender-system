"""
Article people linker: finds the people in an article and records them as
article_mentions, which the frontend turns into clickable names.

For one article:
  1. Gather its text: headline, teaser, body, the full text fetched for
     summaries, and any cached in-app summary of it.
  2. Gazetteer pass: every known alias. A hit on an unambiguous alias
     (a full name) identifies the person directly.
  3. NER pass: unknown names -> resolver.py (Wikidata lookup + scoring,
     or a news-only profile for well-attested local officials).
  4. Ambiguous hits ("Hichilema", "President Hichilema", "HH") are kept
     only when the context supports them:
       - the same person is already identified in this article by full
         name (within-document coreference), or
       - the alias belongs to exactly one known person, that person is
         Zambian, the article is about Zambia, and the alias is a title +
         surname or a curated nickname/abbreviation.
     Otherwise they are left as plain text.
  5. All forms that referred to the same person are stored together, so
     every reference in the article opens the same profile.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone

from app.extensions import db
from app.models.article import Article
from app.models.person import Person, PersonAlias, ArticleMention
from app.models.summary import Summary
from app.services.people.ner import extract_from_document
from app.services.people.registry import Gazetteer
from app.services.people.resolver import resolve_candidate
from app.services.people.text import normalize, TITLES, surname_of, DOMAIN_WORDS

_TITLE_BEFORE_RE = re.compile(rf"(?:{'|'.join(re.escape(t) for t in TITLES)})\s+$")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def article_blocks(article: Article) -> list[str]:
    blocks = [article.title or '', article.description or '', article.content or '']
    if article.full_text:
        blocks.append(article.full_text[:20_000])
    # Cached summaries that include this article (written by summarizer.py)
    like = f'%{article.id}%'
    for s in Summary.query.filter(Summary.article_ids.like(like)).limit(5).all():
        if str(article.id) not in (s.article_ids or '').split(','):
            continue
        p = s.payload or {}
        blocks += list(p.get('paragraphs') or []) + list(p.get('key_points') or [])
        if p.get('why_it_matters'):
            blocks.append(p['why_it_matters'])
        if p.get('title'):
            blocks.append(p['title'])
    return [b for b in blocks if b]


_ZAMBIA_RE = re.compile(
    r'\b(?:Zambia|Zambian|Zambians|Lusaka|Ndola|Kitwe|Copperbelt|Livingstone|Kabwe|Chipata|Kasama|Solwezi|'
    r'Mongu|Mansa|Chingola|Chipolopolo|UPND|Patriotic Front|ZNBC|Kwacha|State House)\b')
NOTABLE = 15   # Wikipedia language editions; above this a full-name match needs no extra context


def is_zambian_context(article: Article, text: str) -> bool:
    return article.region == 'zambia' or bool(_ZAMBIA_RE.search(text))


def _field_mismatch(person: Person, category: str | None, block: str, start: int, end: int) -> bool:
    """
    True when a little-known person's field clearly doesn't fit the story
    and nothing nearby supports the match - e.g. a Zambian footballer
    called "John Banda" vs. "John Banda, a local trader" in a politics story.
    """
    if (person.notability or 0) >= NOTABLE or not person.short_description:
        return False
    words = DOMAIN_WORDS.get(category or '')
    if not words:
        return False
    desc = set(re.sub(r'[^a-z ]', ' ', person.short_description.lower()).split())
    if desc & words:
        return False
    own_fields = [w for k, w in DOMAIN_WORDS.items() if desc & w]
    if not own_fields:
        return False          # description says nothing about a field: no basis to reject
    near = block[max(0, start - 120):end + 120].lower()
    own = set().union(*own_fields)
    return not any(re.search(rf'\b{re.escape(w)}', near) for w in own)


def scan_article(article: Article, allow_lookups: bool = True, lookup_budget: list | None = None) -> list[ArticleMention]:
    """
    Identify the people in one article and store the mentions. Safe to
    re-run: existing mentions are updated, not duplicated.
    lookup_budget is a one-element list [n] shared across a batch, limiting
    Wikidata lookups per run (politeness + speed).
    """
    blocks = article_blocks(article)
    full = '\n'.join(blocks)
    zambian_ctx = is_zambian_context(article, full)

    found: dict[int, dict] = {}   # person_id -> {'forms': set, 'count', 'conf', 'method', 'strong': bool}

    def add(pid, form, conf, method, strong):
        f = found.setdefault(pid, {'forms': set(), 'count': 0, 'conf': 0.0, 'method': method, 'strong': False})
        f['forms'].add(form)
        f['count'] += 1
        if conf > f['conf']:
            f['conf'], f['method'] = conf, method
        f['strong'] = f['strong'] or strong

    # --- 2. gazetteer -------------------------------------------------------
    ambiguous_hits = []
    for block in blocks:
        for hit in Gazetteer.find(block):
            entries = hit['entries']
            pids = {e[0] for e in entries}
            clear = [e for e in entries if not e[2]]
            if len(pids) == 1 and clear:
                p = Person.query.get(entries[0][0])
                if p and _field_mismatch(p, article.category, block, hit['start'], hit['end']):
                    continue
                add(entries[0][0], hit['surface'], 1.0, 'gazetteer', True)
            else:
                before = block[max(0, hit['start'] - 40):hit['start']]
                title = _TITLE_BEFORE_RE.search(before)
                ambiguous_hits.append((hit, title.group(0).strip() if title else None))

    # --- 3. NER for unknown names -----------------------------------------------
    known_forms = {normalize(f) for d in found.values() for f in d['forms']}
    known_alias_norms = set()
    for cand in extract_from_document(blocks):
        norm = normalize(cand.name)
        if norm in known_forms:
            continue
        # Already a (possibly ambiguous) alias of someone we know -> gazetteer handles it.
        if norm in known_alias_norms or PersonAlias.query.filter_by(normalized=norm).first():
            continue
        can_lookup = allow_lookups and (lookup_budget is None or lookup_budget[0] > 0)
        person, conf, method = resolve_candidate(cand, article, zambian_ctx, can_lookup)
        if getattr(cand, 'looked_up', False) and lookup_budget is not None:
            lookup_budget[0] -= 1
        if person:
            add(person.id, cand.name, conf, method, True)
            known_alias_norms.add(norm)

    # --- 4. ambiguous hits: only with supporting context ---------------------------
    people_cache: dict[int, Person] = {}

    def person(pid):
        if pid not in people_cache:
            people_cache[pid] = Person.query.get(pid)
        return people_cache[pid]

    for hit, title in ambiguous_hits:
        entries = hit['entries']
        pids = list({e[0] for e in entries})
        strong_here = [pid for pid in pids if pid in found and found[pid]['strong']]
        if len(strong_here) == 1:
            add(strong_here[0], (title + ' ' if title else '') + hit['surface'], 0.95, 'coref', False)
            continue
        if len(pids) != 1 or not zambian_ctx:
            continue
        p = person(pids[0])
        if not p or not p.is_zambian:
            continue
        kind = entries[0][1]
        if kind == 'surname' and title:
            add(p.id, f"{title} {hit['surface']}", 0.8, 'title+surname', False)
        elif kind in ('abbreviation', 'nickname') and any(e[1] in ('abbreviation', 'nickname') for e in entries):
            # curated or Wikidata nickname in a Zambian story ("HH")
            add(p.id, hit['surface'], 0.75, 'nickname', False)

    # --- 5. store -------------------------------------------------------------------
    existing = {m.person_id: m for m in ArticleMention.query.filter_by(article_id=article.id).all()}
    now = _now()
    result = []
    for pid, d in found.items():
        m = existing.get(pid)
        forms = sorted(d['forms'], key=len, reverse=True)
        if m:
            m.surface_forms = sorted(set(m.surface_forms or []) | set(forms), key=len, reverse=True)
            m.mention_count = max(m.mention_count or 0, d['count'])
            m.confidence = max(m.confidence or 0, d['conf'])
        else:
            m = ArticleMention(article_id=article.id, person_id=pid, surface_forms=forms,
                               mention_count=d['count'], confidence=d['conf'], method=d['method'])
            db.session.add(m)
            p = person(pid)
            if p:
                p.mention_count = (p.mention_count or 0) + 1
                pub = article.published_at or now
                if not p.last_mentioned_at or pub > p.last_mentioned_at:
                    p.last_mentioned_at = pub
        result.append(m)
    article.people_scanned_at = now
    db.session.commit()
    return result


def link_forms(mentions: list[ArticleMention]) -> dict[int, list[str]]:
    """
    The exact strings the frontend should hyperlink for each person: what
    was seen in the article, the person's unambiguous full names, and their
    surname when no other linked person shares it (journalists refer to
    people by surname after the first mention, and AI summaries do too).
    """
    out: dict[int, list[str]] = {}
    surnames: dict[str, list[int]] = {}
    for m in mentions:
        p = m.person
        if p and surname_of(p.full_name):
            surnames.setdefault(normalize(surname_of(p.full_name)), []).append(p.id)
    for m in mentions:
        p = m.person
        if not p:
            continue
        forms = set(m.surface_forms or [])
        forms |= {a.alias for a in p.aliases if not a.is_ambiguous and a.kind in ('full', 'label')}
        sn = surname_of(p.full_name)
        if sn and len(surnames.get(normalize(sn), [])) == 1 and m.confidence >= 0.9:
            forms.add(sn)
        # Possessives and other suffixes are handled by the frontend's word-boundary match.
        out[p.id] = sorted((f for f in forms if len(f) >= 2), key=len, reverse=True)
    return out


def scan_pending(limit: int = 100, lookup_limit: int = 25, allow_lookups: bool = True) -> dict:
    """Scan articles not scanned yet (newest first). Used by the scheduler and the CLI."""
    Gazetteer.refresh_if_db_changed()
    budget = [lookup_limit]
    articles = (Article.query.filter(Article.people_scanned_at.is_(None))
                .order_by(Article.published_at.desc().nullslast()).limit(limit).all())
    mentions = 0
    for a in articles:
        try:
            mentions += len(scan_article(a, allow_lookups=allow_lookups, lookup_budget=budget))
        except Exception as e:  # one bad article never stops the batch
            db.session.rollback()
            print(f'[people.linker] scan failed for article {a.id}: {e}')
    return {'articles': len(articles), 'mentions': mentions, 'lookups_used': lookup_limit - budget[0]}
