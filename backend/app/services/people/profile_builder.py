"""
Profile builder: turns retrieved sources into the reader-facing profile.

Retrieval first, generation second. The builder
  1. refreshes the structured facts from Wikidata (facts.py),
  2. reads the person's Wikipedia article (split into sections),
  3. refreshes the latest news about them (developments.py),
  4. writes the profile with one of two engines (the same hybrid design as
     the article summaries):

  "gemini"  Google Gemini is given ONLY the numbered source documents
            [S1], [S2], ... and must return JSON in which every statement
            lists the sources it came from and is labelled verified /
            reported / claimed / disputed, and legal matters are labelled
            allegation / investigation / charge / court finding /
            conviction / acquittal. After generation, every statement is
            checked: one that cites no valid source is DROPPED, so nothing
            from the model's own memory reaches the reader.

  "offline" No key needed. Builds the profile from Wikidata's structured
            statements (positions, education, party, awards) and the most
            relevant sentences of each Wikipedia section, mapped to the
            profile's sections by heading.

Responsible reporting rules applied by both engines:
  - sensitive personal details unrelated to public life (health, sexuality,
    religion, children, home address) are filtered out;
  - controversies keep their legal status visible, and an allegation is
    never presented as a finding;
  - when sources disagree, the disagreement is shown, not resolved;
  - news-only profiles (local figures not on Wikidata) say so clearly.
"""
from __future__ import annotations
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from app.extensions import db
from app.models.person import Person, PersonPosition, PersonFact, PersonAchievement, InfoSource, PersonDevelopment
from app.services.people import sources as src
from app.services.people.facts import sync_wikidata
from app.services.people.developments import refresh_developments
from app.services.people.registry import get_or_create_source, link_source
from app.services.people.text import url_hash

DEVELOPMENTS_MAX_AGE = timedelta(hours=6)
PROFILE_MAX_AGE = timedelta(days=7)
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
GEMINI_FALLBACK_MODELS = ['gemini-flash-latest', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']
GEMINI_TIMEOUT = 75
MAX_WIKI_CHARS = 28_000

SECTION_ORDER = ['biography', 'career', 'policies', 'achievements', 'controversies', 'current']
SECTION_TITLES = {
    'biography': 'Biography and background',
    'career': 'Political journey',
    'policies': 'Major decisions and policies',
    'achievements': 'Achievements and contributions',
    'controversies': 'Controversies and public debate',
    'current': 'Current activities',
}
CAREER_TITLES = {
    'politics': 'Political journey', 'sport': 'Sporting career', 'business': 'Business career',
    'law': 'Legal career', 'media': 'Career in media', 'arts': 'Career', 'academia': 'Academic career',
    'civil-society': 'Work and activism', 'religion': 'Ministry and public role',
    'traditional-leadership': 'Traditional leadership', 'public-figure': 'Professional journey',
}
HEADING_MAP = [
    ('skip', r'see also|references|external links|notes|further reading|bibliography|filmography|discography|'
             r'electoral history|career statistics|statistics|gallery|sources|citations|footnotes'),
    ('controversies', r'controvers|legal|criticism|allegation|arrest|trial|scandal|investigation|treason|'
                      r'court case|imprisonment|detention|corruption|dispute'),
    ('achievements', r'award|honou?r|recognition|legacy|achievement|accolade|record'),
    ('policies', r'polic|reform|economic|domestic|foreign|agenda|programme|program|initiative|budget'),
    ('biography', r'early life|background|education|personal life|family|biography|childhood|upbringing'),
    ('career', r'career|business|politic|professional|presiden|tenure|administration|minister|government|'
               r'opposition|election|club|international|playing|coaching|military|academic|work|leadership|'
               r'activism|life and|return|exile|parliament|cabinet|mayor'),
]
SENSITIVE_RE = re.compile(
    r'\b(HIV|AIDS|cancer|diabet\w*|diagnos\w*|terminal(?:ly)? ill|mental health|depressi\w*|sexual\w*|gay|lesbian|'
    r'homosexual\w*|bisexual|transgender|religio\w*|denomination|congregat\w*|church|mosque|adventist|catholic|'
    r'muslim|christian|anglican|pentecostal|evangelical|his children|her children|their children|'
    r'(?:one|two|three|four|five|six|seven|eight|nine|\d+) (?:children|sons|daughters|kids)|home address|'
    r'residential address|lives at|phone number|miscarriage|pregnan\w*|divorce\w*)\b',
    re.IGNORECASE)
LEGAL_RULES = [
    ('conviction', r'\b(convicted|found guilty|sentenced|jailed for)\b'),
    ('acquittal', r'\b(acquitted|cleared of|found not guilty|charges (?:were )?dropped|nolle prosequi|discharged)\b'),
    ('court_finding', r'\b(court (?:ruled|found|held)|tribunal (?:ruled|found)|judgment|judgement|ruled that)\b'),
    ('charge', r'\b(charged with|indicted|faces? charges|was charged)\b'),
    ('investigation', r'\b(investigat\w*|probe\w*|questioned by|summoned|under inquiry|inquiry into)\b'),
    ('allegation', r'\b(alleg\w*|accus\w*|claimed that|claims that)\b'),
]
POLICY_SENT_RE = re.compile(r'\b(introduc\w+|polic(?:y|ies)|reform\w*|launch\w*|programme|program|abolish\w*|'
                            r'signed into law|enact\w*|budget|restructur\w*|initiative|implement\w*|'
                            r'his government|her government|the administration)\b', re.I)
LEGAL_SENT_RE = re.compile(r'\b(arrest\w*|charged|treason|convicted|acquitted|indicted|investigat\w*|'
                           r'alleg\w*|accus\w*|corruption|fraud|detained|imprison\w*|court case|trial)\b', re.I)
CLAIM_RE = re.compile(r'\b(he claims|she claims|according to (?:his|her) (?:office|campaign|supporters|party)|'
                      r'his supporters|her supporters|described himself|described herself|boasted)\b', re.I)

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_ai_backoff_until = 0.0


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _lock(pid: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def legal_status(text: str) -> str | None:
    for status, pat in LEGAL_RULES:
        if re.search(pat, text, re.I):
            return status
    return None


def _split_sentences(text: str) -> list[str]:
    from app.services.summarizer import split_sentences
    return split_sentences(text)


def _section_for(heading: str) -> str | None:
    h = heading.lower()
    for name, pat in HEADING_MAP:
        if re.search(pat, h):
            return None if name == 'skip' else name
    return 'career'


# --------------------------------------------------------------------------
# Source gathering
# --------------------------------------------------------------------------
def gather(person: Person, refresh_news: bool = True) -> dict:
    """Retrieve everything the profile is written from. Never raises for one failed source."""
    errors, wiki, wiki_source, facts_info = [], None, None, {'disagreements': []}

    if person.wikidata_id:
        try:
            facts_info = sync_wikidata(person)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            errors.append(f'Wikidata: {e}')

    if person.wikipedia_title:
        try:
            wiki = src.wikipedia_article(person.wikipedia_title)
            if wiki:
                wiki_source = get_or_create_source(wiki['url'], 'wikipedia', title=f"{wiki['title']} - Wikipedia",
                                                   publisher='Wikipedia', tier=6)
                link_source(person, wiki_source, 'biography')
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            errors.append(f'Wikipedia: {e}')

    if refresh_news and (not person.developments_updated_at or
                         _now() - person.developments_updated_at > DEVELOPMENTS_MAX_AGE):
        try:
            r = refresh_developments(person)
            errors += r['errors']
        except Exception as e:
            db.session.rollback()
            errors.append(f'News: {e}')

    developments = (PersonDevelopment.query.filter_by(person_id=person.id)
                    .order_by(PersonDevelopment.published_at.desc().nullslast()).limit(15).all())
    return {'wiki': wiki, 'wiki_source': wiki_source, 'facts_info': facts_info,
            'developments': developments, 'errors': errors}


def _facts_lines(person: Person) -> list[str]:
    lines = []
    if person.full_name:
        lines.append(f'Name: {person.full_name}')
    if person.short_description:
        lines.append(f'Description: {person.short_description}')
    if person.birth_date:
        lines.append(f'Date of birth: {person.birth_date}')
    if person.birth_place:
        lines.append(f'Place of birth: {person.birth_place}')
    if person.nationality:
        lines.append(f'Citizenship: {person.nationality}')
    for p in sorted(person.positions, key=lambda x: x.sort_key):
        if p.withdrawn:
            continue
        span = f"from {p.start_date or 'unknown date'}" + (f" to {p.end_date}" if p.end_date else ' (no end date recorded)')
        lines.append(f"Position held: {p.title}{' - ' + p.organization if p.organization else ''} {span}"
                     + (f"; party {p.party}" if p.party else ''))
    for f in person.facts:
        if f.kind in ('education', 'party', 'occupation', 'employer', 'team', 'family'):
            label = {'education': 'Educated at', 'party': 'Member of political party', 'occupation': 'Occupation',
                     'employer': 'Employer', 'team': 'Team', 'family': 'Spouse'}[f.kind]
            extra = ' '.join(filter(None, [f'({f.detail})' if f.detail and f.kind != 'family' else '',
                                           f'from {f.start_date}' if f.start_date else '',
                                           f'to {f.end_date}' if f.end_date else '']))
            lines.append(f'{label}: {f.value} {extra}'.strip())
    for a in person.achievements:
        lines.append(f"Award received: {a.title}{' (' + a.year + ')' if a.year else ''}")
    return lines


# --------------------------------------------------------------------------
# Gemini engine
# --------------------------------------------------------------------------
PROMPT = """You are a careful, neutral reference editor for a Zambian news app. Write a profile of {name}
using ONLY the numbered source documents below. You must not use any knowledge that is not in these sources.

Rules:
- Every statement must cite the source ids it comes from, e.g. ["S1","S3"]. Statements without a source will be deleted.
- Be balanced and factual. No praise, no promotional or partisan language. Attribute opinions to whoever holds them.
- status for each statement: "verified" (structured record or official source), "reported" (stated by a reference work or news outlet),
  "claimed" (said by the person, their office, party or supporters), or "disputed" (sources disagree).
- For legal matters set legal_status to one of: "allegation", "investigation", "charge", "court_finding", "conviction",
  "acquittal", "public_debate". Never present an allegation, investigation or charge as an established fact.
- Do NOT include sensitive personal details unrelated to public life (health, sexuality, religion, children, addresses).
- Distinguish past roles from current ones. A position is current only if the sources say it has no end date{as_of}.
- If sources disagree on a fact, add it to "disagreements" instead of choosing one.
- Leave a section as an empty list if the sources say nothing about it.
- {career_hint}

Return ONLY JSON with exactly this shape:
{{
  "summary": {{"text": "2-3 neutral sentences: who they are, current or last known role", "sources": ["S1"]}},
  "sections": {{
    "biography": [{{"text": "...", "sources": ["S2"], "status": "reported"}}],
    "career": [...],
    "policies": [...],
    "achievements": [...],
    "controversies": [{{"text": "...", "sources": ["S5"], "status": "reported", "legal_status": "allegation"}}],
    "current": [{{"text": "...", "sources": ["S7"], "status": "reported", "date": "YYYY-MM-DD"}}]
  }},
  "disagreements": [{{"topic": "...", "details": "...", "sources": ["S1","S2"]}}]
}}
Section meanings: biography = early life, upbringing, education, family background (only if publicly documented and relevant), how they became known;
career = positions held, appointments, milestones; policies = major policies, decisions and initiatives (empty for non-officials);
achievements = accomplishments, awards, contributions; controversies = controversies or public debates covered by credible sources;
current = latest activities from the most recent news sources.

SOURCES:
{sources}
"""


def _gemini_models(cfg) -> list[str]:
    first = (cfg.get('GEMINI_MODEL') or '').strip()
    models = [first] if first else []
    return models + [m for m in GEMINI_FALLBACK_MODELS if m not in models]


def _source_docs(person: Person, data: dict, wd_source_id: int | None) -> tuple[list[str], dict[str, int]]:
    docs, smap, n = [], {}, 0

    def add(text, source_id, header):
        nonlocal n
        if not text or not source_id:
            return
        n += 1
        sid = f'S{n}'
        smap[sid] = source_id
        docs.append(f'[{sid}] {header}\n{text}')

    if wd_source_id:
        add('\n'.join(_facts_lines(person)), wd_source_id, 'Wikidata structured record (verified data)')
    wiki = data.get('wiki')
    if wiki and data.get('wiki_source'):
        parts, budget = [], MAX_WIKI_CHARS
        for s in wiki['sections']:
            if _section_for(s['heading']) is None:
                continue
            t = s['text'][:min(6000, max(budget, 0))]
            if not t:
                break
            budget -= len(t)
            parts.append(f"== {s['heading']} ==\n{t}")
        add('\n\n'.join(parts), data['wiki_source'].id, f"Wikipedia article: {wiki['title']}")
    for d in data.get('developments') or []:
        when = d.published_at.strftime('%Y-%m-%d') if d.published_at else 'date unknown'
        tier = src.TIER_LABELS.get(d.tier, '')
        add(f"Headline: {d.title}\n{d.summary or ''}".strip(), d.source_id,
            f'News item, {d.publisher or "unknown publisher"} ({tier}), published {when}')
    return docs, smap


def gemini_profile(person: Person, data: dict, wd_source_id: int | None, cfg) -> dict | None:
    global _ai_backoff_until
    key = (cfg.get('GEMINI_API_KEY') or '').strip()
    if not key or time.time() < _ai_backoff_until:
        return None
    docs, smap = _source_docs(person, data, wd_source_id)
    if not docs:
        return None
    career_hint = (f'For this person (field: {person.category or "public figure"}) the "career" section means: '
                   f'{CAREER_TITLES.get(person.category or "public-figure", "Professional journey")}.')
    prompt = PROMPT.format(name=person.full_name, sources='\n\n'.join(docs), career_hint=career_hint,
                           as_of=f' (today is {_now():%Y-%m-%d})')
    body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json', 'maxOutputTokens': 4096}}
    last_error = None
    for model in _gemini_models(cfg):
        try:
            resp = requests.post(GEMINI_URL.format(model=model), json=body, timeout=GEMINI_TIMEOUT,
                                 headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
        except requests.RequestException as e:
            last_error = str(e)
            break
        if resp.status_code == 404:
            last_error = f'model {model} not found'
            continue
        if resp.status_code != 200:
            last_error = f'HTTP {resp.status_code}'
            if resp.status_code in (429, 503):
                _ai_backoff_until = time.time() + 300
            break
        try:
            text = ''.join(p.get('text', '') for p in resp.json()['candidates'][0]['content']['parts'])
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            parsed = json.loads(text)
            validated = validate_ai_profile(parsed, smap)
            if not validated['sections_nonempty'] and not validated['summary']:
                raise ValueError('no sourced statements')
            validated['model'] = model
            return validated
        except (KeyError, IndexError, ValueError, TypeError) as e:
            last_error = f'unreadable response ({e})'
            break
    print(f'[people.profile] Gemini unavailable for {person.full_name}, using offline profile: {last_error}')
    return None


def _map_sources(ids, smap) -> list[int]:
    out = []
    for i in ids or []:
        sid = smap.get(str(i).strip().strip('[]'))
        if sid and sid not in out:
            out.append(sid)
    return out


def validate_ai_profile(parsed: dict, smap: dict[str, int]) -> dict:
    """Keep only statements that cite at least one real source document."""
    dropped = 0
    sections = {}
    allowed_status = {'verified', 'reported', 'claimed', 'disputed'}
    allowed_legal = {'allegation', 'investigation', 'charge', 'court_finding', 'conviction', 'acquittal', 'public_debate'}
    for name in SECTION_ORDER:
        items = []
        for st in (parsed.get('sections') or {}).get(name) or []:
            if not isinstance(st, dict) or not str(st.get('text') or '').strip():
                continue
            ids = _map_sources(st.get('sources'), smap)
            text = str(st['text']).strip()
            if not ids or SENSITIVE_RE.search(text):
                dropped += 1
                continue
            item = {'text': text, 'source_ids': ids,
                    'status': st.get('status') if st.get('status') in allowed_status else 'reported'}
            ls = st.get('legal_status')
            if name == 'controversies':
                item['legal_status'] = ls if ls in allowed_legal else (legal_status(text) or 'public_debate')
            if st.get('date'):
                item['date'] = str(st['date'])[:10]
            items.append(item)
        sections[name] = items
    summary = None
    s = parsed.get('summary') or {}
    if isinstance(s, dict) and s.get('text'):
        ids = _map_sources(s.get('sources'), smap)
        if ids:
            summary = {'text': str(s['text']).strip(), 'source_ids': ids}
    disagreements = []
    for d in parsed.get('disagreements') or []:
        if isinstance(d, dict) and d.get('details'):
            ids = _map_sources(d.get('sources'), smap)
            if ids:
                disagreements.append({'topic': str(d.get('topic') or 'Conflicting information'),
                                      'details': str(d['details']), 'source_ids': ids})
    return {'engine': 'gemini', 'summary': summary, 'sections': sections, 'disagreements': disagreements,
            'dropped_unsourced': dropped, 'sections_nonempty': sum(1 for v in sections.values() if v)}


# --------------------------------------------------------------------------
# Offline engine
# --------------------------------------------------------------------------
def _fmt_span(start, end, current):
    s = (start or '')[:4]
    e = (end or '')[:4]
    if s and e:
        return f'{s}–{e}' if s != e else s
    if s and current:
        return f'since {s}'
    if s:
        return f'from {s}'
    if e:
        return f'until {e}'
    return ''


def offline_profile(person: Person, data: dict, wd_source_id: int | None) -> dict:
    sections = {k: [] for k in SECTION_ORDER}
    caps = {'biography': 6, 'career': 9, 'policies': 6, 'achievements': 5, 'controversies': 6}

    # --- structured facts (verified) ---
    if wd_source_id:
        edu = [f for f in person.facts if f.kind == 'education']
        if edu:
            parts = [f.value + (f' ({f.detail})' if f.detail else '') for f in edu]
            sections['biography'].append({'text': 'Educated at ' + '; '.join(parts) + '.',
                                          'source_ids': [wd_source_id], 'status': 'verified'})
        positions = [p for p in person.positions if not p.withdrawn]
        for p in sorted(positions, key=lambda x: x.sort_key, reverse=True)[:12]:
            span = _fmt_span(p.start_date, p.end_date, p.is_current)
            text = f"{'Serves' if p.is_current else 'Served'} as {p.title}"
            if p.organization and p.organization.lower() not in p.title.lower():
                text += f' ({p.organization})'
            text += f' {span}.' if span else '.'
            if p.party:
                text = text[:-1] + f', representing {p.party}.'
            sections['career'].append({'text': text, 'source_ids': [wd_source_id], 'status': 'verified',
                                       'current': p.is_current})
        parties = [f for f in person.facts if f.kind == 'party']
        for f in parties:
            span = _fmt_span(f.start_date, f.end_date, not f.end_date)
            sections['career'].append({'text': f'Member of {f.value}' + (f' ({span})' if span else '') + '.',
                                       'source_ids': [wd_source_id], 'status': 'verified'})
        for a in person.achievements:
            sections['achievements'].append({'text': f"Received the {a.title}" + (f' in {a.year}' if a.year else '') + '.',
                                             'source_ids': [wd_source_id], 'status': 'verified'})

    # --- Wikipedia sections (reported) ---
    wiki, wsrc = data.get('wiki'), data.get('wiki_source')
    summary = None
    if wiki and wsrc:
        lead_sents = [s for s in _split_sentences(wiki.get('lead') or '') if not SENSITIVE_RE.search(s)]
        if lead_sents:
            summary = {'text': ' '.join(lead_sents[:3]), 'source_ids': [wsrc.id]}
        for s in wiki['sections'][1:]:
            target = _section_for(s['heading'])
            if not target:
                continue
            room = caps[target] - sum(1 for x in sections[target] if wsrc.id in x['source_ids'])
            if room <= 0:
                continue
            sents = [x for x in _split_sentences(s['text']) if not SENSITIVE_RE.search(x)]
            taken = 0
            for sent in sents:
                # Route single sentences to a better section: a treason charge
                # in "Political career" is a legal matter; "his government
                # introduced free education" is a policy.
                dest = target
                if LEGAL_SENT_RE.search(sent) and target != 'controversies':
                    dest = 'controversies'
                elif target == 'career' and person.category == 'politics' and POLICY_SENT_RE.search(sent):
                    dest = 'policies'
                if dest == target and taken >= min(room, 3):
                    continue
                if len(sections[dest]) >= caps[dest] + 3:
                    continue
                item = {'text': sent, 'source_ids': [wsrc.id],
                        'status': 'claimed' if CLAIM_RE.search(sent) else 'reported', 'from_section': s['heading']}
                if dest == 'controversies':
                    item['legal_status'] = legal_status(sent) or 'public_debate'
                sections[dest].append(item)
                if dest == target:
                    taken += 1

    # --- latest news (reported) ---
    for d in (data.get('developments') or [])[:6]:
        sections['current'].append({
            'text': d.title + (f' ({d.publisher})' if d.publisher else ''),
            'source_ids': [d.source_id] if d.source_id else [], 'status': 'reported',
            'date': d.published_at.strftime('%Y-%m-%d') if d.published_at else None})

    if not summary:
        bits = [person.full_name]
        if person.birth_date:
            bits.append(f'(born {person.birth_date[:4]}{" in " + person.birth_place if person.birth_place else ""})')
        role = person.headline_position or person.short_description
        text = ' '.join(bits) + (f' — {role}.' if role else '.')
        ids = [wd_source_id] if wd_source_id else [d.source_id for d in (data.get('developments') or [])[:3] if d.source_id]
        summary = {'text': text, 'source_ids': ids}
    return {'engine': 'offline', 'model': None, 'summary': summary, 'sections': sections, 'disagreements': []}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def build_profile(person: Person, refresh_news: bool = True) -> Person:
    with _lock(person.id):
        db.session.refresh(person)
        data = gather(person, refresh_news=refresh_news)
        wd_source_id = data['facts_info'].get('source_id') if data['facts_info'] else None
        if not wd_source_id and person.wikidata_id:
            s = InfoSource.query.filter_by(url_hash=url_hash(src.wikidata_url(person.wikidata_id))).first()
            wd_source_id = s.id if s else None

        has_material = bool(wd_source_id and (person.positions or person.facts)) or data['wiki'] or data['developments']
        if not has_material:
            person.status = 'failed' if data['errors'] else 'ready'
            person.last_error = '; '.join(data['errors'])[:500] or None
            person.profile = person.profile or {
                'summary': None, 'sections': {k: [] for k in SECTION_ORDER}, 'disagreements': [],
                'notes': ['Not enough publicly available information was found to write this profile yet.'],
                'engine': 'none', 'generated_at': _now().isoformat()}
            db.session.commit()
            return person

        cfg = current_app.config
        result = gemini_profile(person, data, wd_source_id, cfg) or offline_profile(person, data, wd_source_id)

        disagreements = list(data['facts_info'].get('disagreements') or []) + result.get('disagreements', [])
        notes = []
        if person.verification == 'news_only':
            notes.append('This person could not be matched to a reference database. The profile is based only on '
                         'news reports and has not been independently verified.')
        if person.headline_position_current:
            notes.append(f'Current position as recorded on {person.facts_checked_at:%d %B %Y}. '
                         'Check the latest developments for any very recent changes.')
        if data['errors']:
            notes.append('Some sources could not be reached when this profile was last updated: '
                         + '; '.join(e.split(':')[0] for e in data['errors']) + '.')
        if result.get('dropped_unsourced'):
            notes.append(f"{result['dropped_unsourced']} AI-written statement(s) were removed because they "
                         'did not cite a source.')

        used_ids = set()
        for items in result['sections'].values():
            for it in items:
                used_ids |= set(it.get('source_ids') or [])
        if result.get('summary'):
            used_ids |= set(result['summary'].get('source_ids') or [])
        for d in disagreements:
            used_ids |= set(d.get('source_ids') or [])

        titles = dict(SECTION_TITLES)
        titles['career'] = CAREER_TITLES.get(person.category or 'public-figure', 'Professional journey')
        if person.category != 'politics':
            titles['policies'] = 'Notable work and decisions'

        person.profile = {
            'summary': result.get('summary'),
            'sections': result['sections'],
            'section_order': SECTION_ORDER,
            'section_titles': titles,
            'disagreements': disagreements,
            'notes': notes,
            'source_ids': sorted(used_ids),
            'engine': result['engine'],
            'model': result.get('model'),
            'generated_at': _now().isoformat(),
        }
        person.profile_engine = result['engine']
        person.status = 'ready'
        person.last_error = '; '.join(data['errors'])[:500] or None
        person.bio_updated_at = _now()
        db.session.commit()
        return person


def needs_rebuild(person: Person) -> bool:
    return (person.status != 'ready' or not person.profile or not person.bio_updated_at
            or _now() - person.bio_updated_at > PROFILE_MAX_AGE)


def needs_news(person: Person) -> bool:
    return not person.developments_updated_at or _now() - person.developments_updated_at > DEVELOPMENTS_MAX_AGE


def serialize(person: Person, developments_limit: int = 8) -> dict:
    """Everything the profile panel / page needs, in one response."""
    from app.services.people.developments import list_developments
    profile = person.profile or {}
    ids = set(profile.get('source_ids') or [])
    ids |= {p.source_id for p in person.positions if p.source_id}
    sources = {s.id: s.to_dict() for s in InfoSource.query.filter(InfoSource.id.in_(ids)).all()} if ids else {}
    for s in sources.values():
        s['tier_label'] = src.TIER_LABELS.get(s['tier'])
        if s['url'].startswith('app://'):
            s['url'] = None
    facts = {}
    for f in person.facts:
        facts.setdefault(f.kind, []).append(f.to_dict())
    positions = [p.to_dict() for p in person.positions if not p.withdrawn]
    return {
        **person.card(),
        'wikidata_id': person.wikidata_id,
        'nationality': person.nationality,
        'birth_date': person.birth_date,
        'birth_place': person.birth_place,
        'image_credit': person.image_credit,
        'image_source_url': person.image_source_url,
        'facts': facts,
        'positions': positions,
        'current_positions': [p for p in positions if p['is_current']],
        'achievements': [a.to_dict() for a in person.achievements],
        'profile': profile,
        'sources': sources,
        'developments': list_developments(person, limit=developments_limit),
        'mention_count': person.mention_count,
        'last_error': person.last_error,
        'updated': {
            'facts_checked_at': person.facts_checked_at.isoformat() if person.facts_checked_at else None,
            'bio_updated_at': person.bio_updated_at.isoformat() if person.bio_updated_at else None,
            'developments_updated_at': person.developments_updated_at.isoformat() if person.developments_updated_at else None,
        },
    }
