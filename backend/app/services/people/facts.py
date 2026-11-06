"""
Structured facts from Wikidata: positions (with dates), party, education,
occupation, awards, family, birth details, citizenship, photo.

Each Wikidata statement has a stable id, stored as statement_key, so
re-syncing updates rows in place instead of duplicating them. Positions are
never deleted:
  - a position that gains an end date is marked is_current=False and
    ended_detected_at is recorded (the profile then says "Former ...");
  - a position Wikidata no longer lists is kept but flagged withdrawn.
So the profile keeps the person's history and never presents an old role as
their current one.

When Wikidata itself holds conflicting values (two birth dates, two
birthplaces, both "normal" rank) both are kept and reported as a
disagreement instead of silently picking one.
"""
from __future__ import annotations
from datetime import datetime, timezone

from app.extensions import db
from app.models.person import Person, PersonPosition, PersonFact, PersonAchievement
from app.services.people import sources as src
from app.services.people.registry import get_or_create_source, link_source, derive_aliases

# Wikidata properties used
P = {
    'birth_date': 'P569', 'death_date': 'P570', 'birth_place': 'P19', 'citizenship': 'P27',
    'education': 'P69', 'occupation': 'P106', 'position': 'P39', 'party': 'P102', 'award': 'P166',
    'spouse': 'P26', 'image': 'P18', 'website': 'P856', 'employer': 'P108', 'sport_team': 'P54',
    'nickname': 'P1449', 'sport': 'P641',
}
Q = {'start': 'P580', 'end': 'P582', 'point_in_time': 'P585', 'of': 'P642', 'district': 'P768',
     'jurisdiction': 'P1001', 'party_q': 'P4100', 'degree': 'P512', 'major': 'P812', 'end_cause': 'P1534'}

POLITICAL_WORDS = ('politician', 'president', 'minister', 'member of parliament', 'member of the national assembly',
                   'mayor', 'governor', 'senator', 'diplomat', 'ambassador', 'speaker', 'judge')
SPORT_WORDS = ('footballer', 'athlete', 'boxer', 'cricketer', 'coach', 'runner', 'player', 'sprinter', 'swimmer')
BUSINESS_WORDS = ('businessperson', 'businessman', 'businesswoman', 'entrepreneur', 'executive', 'economist',
                  'banker', 'investor')


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sort_key(date_str: str | None) -> str:
    return (date_str or '').ljust(10, '0')[:10]


def categorise(description: str | None, occupations: list[str], has_office: bool) -> str:
    text = ' '.join([description or ''] + occupations).lower()
    if has_office or any(w in text for w in POLITICAL_WORDS):
        return 'politics'
    if any(w in text for w in SPORT_WORDS):
        return 'sport'
    if any(w in text for w in BUSINESS_WORDS):
        return 'business'
    for word, cat in (('judge', 'law'), ('lawyer', 'law'), ('journalist', 'media'), ('musician', 'arts'),
                      ('singer', 'arts'), ('actor', 'arts'), ('artist', 'arts'), ('scientist', 'academia'),
                      ('academic', 'academia'), ('professor', 'academia'), ('activist', 'civil-society'),
                      ('bishop', 'religion'), ('pastor', 'religion'), ('chief', 'traditional-leadership')):
        if word in text:
            return cat
    return 'public-figure'


def sync_wikidata(person: Person) -> dict:
    """
    Fetch the person's Wikidata item and update positions, facts,
    achievements, aliases, headline position, photo and birth details.
    Returns {'entity', 'disagreements', 'source_id', 'labels'} for the
    profile builder.
    """
    qid = person.wikidata_id
    ents = src.wikidata_entities([qid])
    ent = ents.get(qid)
    if not ent:
        raise src.SourceError(f'Wikidata item {qid} not found')

    wd_source = get_or_create_source(src.wikidata_url(qid), 'wikidata',
                                     title=f'{src.label(ent) or person.full_name} (Wikidata {qid})',
                                     publisher='Wikidata', tier=6)
    link_source(person, wd_source, 'identity')

    # Resolve every referenced item's English label in one go.
    referenced = []
    for prop in P.values():
        for c in src.claims(ent, prop):
            v = src.claim_value(c)
            if isinstance(v, str) and v.startswith('Q'):
                referenced.append(v)
            for qp in Q.values():
                qv = src.qualifier(c, qp)
                if isinstance(qv, str) and qv.startswith('Q'):
                    referenced.append(qv)
    labels = src.wikidata_labels(referenced)
    L = lambda q: labels.get(q) if isinstance(q, str) else None  # noqa: E731

    now = _now()
    disagreements = []

    # --- identity --------------------------------------------------------
    person.full_name = src.label(ent) or person.full_name
    if person.verification == 'wikidata' and not person.display_name:
        person.display_name = person.full_name
    person.short_description = (src.description(ent) or person.short_description or '')[:400] or None
    person.wikipedia_title = src.enwiki_title(ent) or person.wikipedia_title
    person.notability = src.sitelink_count(ent)
    citizenships = [src.claim_value(c) for c in src.claims(ent, P['citizenship'])]
    person.is_zambian = src.ZAMBIA_QID in citizenships
    person.nationality = ', '.join(filter(None, (L(c) for c in citizenships)))[:200] or None
    derive_aliases(person, src.aliases(ent) + [src.claim_value(c) for c in src.claims(ent, P['nickname'])
                                                if isinstance(src.claim_value(c), str)])

    # --- birth (keep disagreements visible) --------------------------------
    births = []
    for c in src.claims(ent, P['birth_date']):
        d = src.wd_time_to_str(src.claim_value(c))
        if d and d not in births:
            births.append(d)
    if births:
        person.birth_date = births[0]
        if len({b[:4] for b in births}) > 1:
            disagreements.append({'topic': 'Date of birth',
                                  'details': 'Sources list different dates of birth: ' + ' / '.join(births),
                                  'source_ids': [wd_source.id]})
    places = [L(src.claim_value(c)) for c in src.claims(ent, P['birth_place'])]
    places = [p for i, p in enumerate(places) if p and p not in places[:i]]
    if places:
        person.birth_place = places[0]
        if len(places) > 1:
            disagreements.append({'topic': 'Place of birth',
                                  'details': 'Sources list different places of birth: ' + ' / '.join(places),
                                  'source_ids': [wd_source.id]})
    deaths = [src.wd_time_to_str(src.claim_value(c)) for c in src.claims(ent, P['death_date'])]
    deaths = [d for d in deaths if d]

    # --- photo -----------------------------------------------------------
    imgs = [src.claim_value(c) for c in src.claims(ent, P['image'])]
    if imgs and isinstance(imgs[0], str):
        person.image_url, person.image_source_url = src.commons_image(imgs[0])
        person.image_credit = 'Wikimedia Commons (see file page for author and licence)'

    # --- simple facts ------------------------------------------------------
    def upsert_fact(kind, key, value, detail=None, start=None, end=None):
        if not value:
            return
        f = PersonFact.query.filter_by(person_id=person.id, kind=kind, statement_key=key).first()
        if not f:
            f = PersonFact(person_id=person.id, kind=kind, statement_key=key, value=value[:500])
            db.session.add(f)
        f.value, f.detail, f.start_date, f.end_date, f.source_id = value[:500], detail, start, end, wd_source.id

    seen_fact_keys = set()
    for kind, prop in (('education', 'education'), ('occupation', 'occupation'), ('party', 'party'),
                       ('family', 'spouse'), ('citizenship', 'citizenship'), ('employer', 'employer'),
                       ('team', 'sport_team')):
        for c in src.claims(ent, P[prop]):
            v = L(src.claim_value(c))
            detail = None
            if kind == 'education':
                detail = ', '.join(filter(None, [L(src.qualifier(c, Q['degree'])), L(src.qualifier(c, Q['major']))])) or None
            if kind == 'family':
                detail = 'Spouse'
            start = src.wd_time_to_str(src.qualifier(c, Q['start']))
            end = src.wd_time_to_str(src.qualifier(c, Q['end']))
            key = c.get('id') or f'{kind}:{v}'
            seen_fact_keys.add((kind, key))
            upsert_fact(kind, key, v, detail, start, end)
    for c in src.claims(ent, P['website']):
        v = src.claim_value(c)
        if isinstance(v, str):
            seen_fact_keys.add(('website', c.get('id') or v))
            upsert_fact('website', c.get('id') or v, v)
    if person.birth_date:
        upsert_fact('birth_date', 'birth', person.birth_date)
    if person.birth_place:
        upsert_fact('birth_place', 'birth', person.birth_place)
    if deaths:
        upsert_fact('death_date', 'death', deaths[0])
    # Facts Wikidata no longer states are removed (they were derived, not history).
    for f in PersonFact.query.filter_by(person_id=person.id).all():
        if f.kind in ('education', 'occupation', 'party', 'family', 'citizenship', 'employer', 'team', 'website') \
                and (f.kind, f.statement_key) not in seen_fact_keys:
            db.session.delete(f)

    # --- positions (history kept) -------------------------------------------
    seen_positions = set()
    party_now = None
    for c in src.claims(ent, P['party']):
        if not src.qualifier(c, Q['end']):
            party_now = L(src.claim_value(c))
            break
    for c in src.claims(ent, P['position']):
        title = L(src.claim_value(c))
        if not title:
            continue
        key = c.get('id') or f"pos:{src.claim_value(c)}:{src.qualifier(c, Q['start'])}"
        seen_positions.add(key)
        start = src.wd_time_to_str(src.qualifier(c, Q['start']))
        end = src.wd_time_to_str(src.qualifier(c, Q['end']))
        org = L(src.qualifier(c, Q['district'])) or L(src.qualifier(c, Q['of'])) or None
        party = L(src.qualifier(c, Q['party_q']))
        pos = PersonPosition.query.filter_by(person_id=person.id, statement_key=key).first()
        if not pos:
            pos = PersonPosition(person_id=person.id, statement_key=key, title=title[:300], first_seen_at=now)
            db.session.add(pos)
        if pos.is_current and end:
            pos.ended_detected_at = now   # change detected: the position has ended
        pos.title, pos.organization, pos.party = title[:300], org, party
        pos.start_date, pos.end_date = start, end
        pos.is_current = (not end) and not deaths
        pos.sort_key = _sort_key(start)
        pos.source_id, pos.last_verified_at, pos.withdrawn = wd_source.id, now, False
    for pos in PersonPosition.query.filter_by(person_id=person.id).all():
        if pos.statement_key not in seen_positions and pos.source_id == wd_source.id and not pos.withdrawn:
            pos.withdrawn = True
            if pos.is_current:
                pos.is_current = False
                pos.ended_detected_at = now

    # --- achievements (awards are independently recorded) ---------------------
    for c in src.claims(ent, P['award']):
        title = L(src.claim_value(c))
        if not title:
            continue
        key = c.get('id') or f'award:{title}'
        year = (src.wd_time_to_str(src.qualifier(c, Q['point_in_time'])) or '')[:4] or None
        a = PersonAchievement.query.filter_by(person_id=person.id, statement_key=key).first()
        if not a:
            a = PersonAchievement(person_id=person.id, statement_key=key, title=title[:400])
            db.session.add(a)
        a.title, a.year, a.verification, a.source_id = title[:400], year, 'independent', wd_source.id

    db.session.flush()

    # --- headline: current or last verified position ---------------------------
    positions = PersonPosition.query.filter_by(person_id=person.id, withdrawn=False).all()
    current = sorted([p for p in positions if p.is_current], key=lambda p: p.sort_key, reverse=True)
    past = sorted([p for p in positions if not p.is_current and p.end_date], key=lambda p: _sort_key(p.end_date),
                  reverse=True)
    if current:
        p0 = current[0]
        person.headline_position = _pos_label(p0)
        person.headline_position_current = True
    elif past:
        p0 = past[0]
        person.headline_position = f'Former {_pos_label(p0, lower_first=True)} (until {p0.end_date[:4]})'
        person.headline_position_current = False
    else:
        person.headline_position = (person.short_description or '').capitalize() or None
        person.headline_position_current = None
    if deaths:
        person.headline_position = (person.headline_position or '') + f' (died {deaths[0][:4]})'

    occupations = [L(src.claim_value(c)) or '' for c in src.claims(ent, P['occupation'])]
    person.category = categorise(person.short_description, occupations, bool(positions))
    if party_now:
        upsert_fact('party_current', 'current', party_now)
    person.facts_checked_at = now
    return {'entity': ent, 'disagreements': disagreements, 'source_id': wd_source.id, 'labels': labels,
            'deceased': bool(deaths)}


def _pos_label(p: PersonPosition, lower_first: bool = False) -> str:
    t = p.title
    if p.organization and p.organization.lower() not in t.lower():
        t = f'{t} ({p.organization})'
    if lower_first and t[:1].isupper() and not t.split()[0].isupper():
        # "Former member of ..." but keep proper nouns like "Former President of Zambia"
        first = t.split()[0]
        if first.lower() in ('member', 'deputy', 'minister', 'leader', 'chairperson', 'mayor', 'speaker'):
            t = t[0].lower() + t[1:]
    return t
