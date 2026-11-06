"""
People registry: creating people without duplicates, their aliases, and
the source documents profile statements are traced to.

Duplicate prevention
  - A Wikidata QID can belong to only one Person (unique column), so two
    spellings that resolve to the same QID always reach the same profile.
  - Aliases are normalised (case, accents, punctuation) before matching.
  - News-only profiles (no QID) are keyed by their normalised full name and
    are merged into the Wikidata profile if that person later appears there.
"""
from __future__ import annotations
import json
import os
import re
import threading
from datetime import datetime, timezone

from app.extensions import db
from app.models.person import Person, PersonAlias, InfoSource, PersonSource
from app.services.people import sources as src
from app.services.people.text import normalize, surname_of, slugify, strip_title, initials_of, url_hash

CURATED_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'people_aliases.json')
_curated_cache = None


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def curated_aliases() -> dict[str, list[str]]:
    global _curated_cache
    if _curated_cache is None:
        try:
            with open(CURATED_PATH, encoding='utf-8') as f:
                data = json.load(f)
            _curated_cache = {normalize(p['name']): p.get('aliases', []) for p in data.get('people', [])}
        except (OSError, ValueError, KeyError):
            _curated_cache = {}
    return _curated_cache


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def get_or_create_source(url: str, kind: str, title: str | None = None, publisher: str | None = None,
                         published_at: datetime | None = None, tier: int | None = None) -> InfoSource:
    h = url_hash(url)
    s = InfoSource.query.filter_by(url_hash=h).first()
    if s:
        if title and not s.title:
            s.title = title[:600]
        if published_at and not s.published_at:
            s.published_at = published_at
        s.retrieved_at = _now()
        return s
    s = InfoSource(url_hash=h, url=url[:1500], kind=kind, title=(title or '')[:600] or None,
                   publisher=(publisher or '')[:200] or None, domain=src.domain_of(url),
                   tier=tier if tier is not None else src.credibility_tier(url), published_at=published_at)
    db.session.add(s)
    db.session.flush()
    return s


def link_source(person: Person, source: InfoSource, role: str):
    if not PersonSource.query.filter_by(person_id=person.id, source_id=source.id).first():
        db.session.add(PersonSource(person_id=person.id, source_id=source.id, role=role))


# --------------------------------------------------------------------------
# Aliases
# --------------------------------------------------------------------------
def classify_alias(alias: str, full_name: str) -> tuple[str, bool]:
    """(kind, is_ambiguous) for an alias of a person called full_name."""
    a = alias.strip()
    words = a.split()
    if re.fullmatch(r'[A-Z]{2,5}', a.replace('.', '')):
        return 'abbreviation', True
    if len(words) == 1:
        if surname_of(full_name) and normalize(a) == normalize(surname_of(full_name)):
            return 'surname', True
        return 'nickname', True
    _, title = strip_title(a)
    if title:
        return 'title', len(strip_title(a)[0].split()) < 2
    return 'full', False


def add_alias(person: Person, alias: str, kind: str | None = None, source: str = 'derived',
              ambiguous: bool | None = None) -> PersonAlias | None:
    alias = re.sub(r'\s+', ' ', (alias or '').strip())
    norm = normalize(alias)
    if not norm or len(norm) < 2 or len(alias) > 200:
        return None
    for a in person.aliases:
        if a.normalized == norm:
            return a
    k, amb = classify_alias(alias, person.full_name)
    pa = PersonAlias(person_id=person.id, alias=alias, normalized=norm, kind=kind or k,
                     is_ambiguous=amb if ambiguous is None else ambiguous, source=source)
    db.session.add(pa)
    person.aliases.append(pa)
    Gazetteer.invalidate()
    return pa


def derive_aliases(person: Person, extra: list[str] | None = None, source: str = 'wikidata'):
    """Label, Wikidata aliases, 'First Last' without middle names, surname, curated nicknames."""
    add_alias(person, person.full_name, 'full', source, False)
    if person.display_name != person.full_name:
        add_alias(person, person.display_name, 'full', source, False)
    for a in extra or []:
        # Skip aliases that are just a title ("President of Zambia") or
        # other languages' scripts.
        if not re.search(r'[A-Za-z]', a) or normalize(a).startswith(('president of', 'minister of')):
            continue
        add_alias(person, a, None, source)
    parts = strip_title(person.full_name)[0].split()
    if len(parts) >= 3:
        add_alias(person, f'{parts[0]} {parts[-1]}', 'full', 'derived', False)
    sn = surname_of(person.full_name)
    if sn:
        add_alias(person, sn, 'surname', 'derived', True)
    for nick in curated_aliases().get(normalize(person.full_name), []) + \
            curated_aliases().get(normalize(person.display_name), []):
        add_alias(person, nick, None, 'curated')


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------
def _unique_slug(name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while Person.query.filter_by(slug=slug).first():
        slug, n = f'{base}-{n}', n + 1
    return slug


def person_from_entity(qid: str, ent: dict) -> Person:
    """Get or create the Person for a Wikidata item (never creates a duplicate)."""
    existing = Person.query.filter_by(wikidata_id=qid).first()
    if existing:
        return existing
    name = src.label(ent) or qid
    # A news-only profile with the same name is upgraded rather than duplicated.
    news_only = (Person.query.filter(Person.wikidata_id.is_(None), Person.verification == 'news_only')
                 .join(PersonAlias).filter(PersonAlias.normalized == normalize(name)).first())
    citizenships = [src.claim_value(c) for c in src.claims(ent, 'P27')]
    p = news_only or Person(slug=_unique_slug(name), full_name=name, display_name=name)
    p.wikidata_id = qid
    p.verification = 'wikidata'
    p.full_name = p.full_name if news_only else name
    p.short_description = (src.description(ent) or '')[:400] or None
    p.wikipedia_title = src.enwiki_title(ent)
    p.is_zambian = src.ZAMBIA_QID in citizenships
    p.notability = src.sitelink_count(ent)
    p.status = 'pending'
    if not news_only:
        db.session.add(p)
    db.session.flush()
    derive_aliases(p, src.aliases(ent))
    s = get_or_create_source(src.wikidata_url(qid), 'wikidata', title=f'{name} (Wikidata {qid})',
                             publisher='Wikidata', tier=6)
    link_source(p, s, 'identity')
    return p


def news_only_person(name: str, title_cue: str | None, zambian: bool) -> Person:
    norm = normalize(name)
    existing = (Person.query.join(PersonAlias).filter(PersonAlias.normalized == norm, PersonAlias.kind == 'full')
                .first())
    if existing:
        return existing
    p = Person(slug=_unique_slug(name), full_name=name, display_name=name, verification='news_only',
               is_zambian=zambian, status='pending',
               short_description=(f'{title_cue} (as described in news reports)' if title_cue else None))
    db.session.add(p)
    db.session.flush()
    derive_aliases(p, [], source='article')
    return p


# --------------------------------------------------------------------------
# Gazetteer: every alias of every known person, as one regex
# --------------------------------------------------------------------------
class Gazetteer:
    """
    Fast lookup of known people in text. Rebuilt lazily whenever aliases
    change (process-local cache; cheap to rebuild for thousands of aliases).
    """
    _lock = threading.Lock()
    _version = 0
    _built_version = -1
    _regex = None
    _by_norm: dict[str, list[tuple[int, str, bool]]] = {}

    @classmethod
    def invalidate(cls):
        cls._version += 1

    @classmethod
    def _build(cls):
        rows = db.session.query(PersonAlias.alias, PersonAlias.normalized, PersonAlias.person_id,
                                PersonAlias.kind, PersonAlias.is_ambiguous).all()
        by_norm: dict[str, list] = {}
        forms = set()
        for alias, norm, pid, kind, amb in rows:
            by_norm.setdefault(norm, []).append((pid, kind, amb))
            forms.add(alias)
        cls._by_norm = by_norm
        if forms:
            alt = '|'.join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
            # Case-sensitive on purpose: "Bally" the nickname, not "bally";
            # abbreviations like "HH" must be upper case.
            cls._regex = re.compile(rf"(?<![\w’'-])(?:{alt})(?![\w-])")
        else:
            cls._regex = None
        cls._built_version = cls._version

    @classmethod
    def find(cls, text: str) -> list[dict]:
        with cls._lock:
            if cls._built_version != cls._version:
                cls._build()
            regex, by_norm = cls._regex, cls._by_norm
        if not regex or not text:
            return []
        out = []
        for m in regex.finditer(text):
            entries = by_norm.get(normalize(m.group(0)), [])
            if entries:
                out.append({'surface': m.group(0), 'start': m.start(), 'end': m.end(), 'entries': entries})
        return out

    @classmethod
    def refresh_if_db_changed(cls):
        """Called at the start of a scan run so aliases added by another
        process (CLI bootstrap while the server runs) are picked up."""
        cls.invalidate()


def initials(person: Person) -> str | None:
    return initials_of(person.full_name)
