"""
Latest developments: recent news about a person, retrieved fresh rather
than frozen at the time the profile was first written.

Sources, merged and deduplicated:
  1. The app's own articles that mention the person (article_mentions),
     from BBC, Al Jazeera, CNN and the Zambian outlets already ingested.
  2. Google News search for the person's name (Zambia edition for Zambian
     figures), plus a search restricted to official Zambian domains
     (gov.zm, parliament.gov.zm, elections.org.zm).

Deduplication: a development is unique per (person, URL hash); the same
story syndicated under different URLs is also caught by comparing
normalised headlines. Items already captured are never added twice, so
re-running only adds what is new.

Each item is tagged with a kind (appointment, resignation, legal, election,
statement) from its headline, so changes of position stand out, and with
the publisher's credibility tier.
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.article import Article
from app.models.person import Person, PersonDevelopment, ArticleMention
from app.services.people import sources as src
from app.services.people.registry import get_or_create_source, link_source
from app.services.people.text import url_hash, normalize

MAX_AGE_DAYS = 120
KIND_RULES = [
    ('appointment', r'\b(appoint\w*|sworn in|swears in|named as|nominat\w*|elected|ratif\w*|takes office|new (?:minister|ceo|coach|chief))\b'),
    ('resignation', r'\b(resign\w*|steps? down|quits?|fired|sack\w*|dismiss\w*|reshuffl\w*|removed|suspend\w*|retire\w*)\b'),
    ('legal', r'\b(arrest\w*|charg\w*|court|trial|convict\w*|acquit\w*|sentenc\w*|investigat\w*|probe|allegation\w*|accus\w*|lawsuit|sued|petition\w*|warrant)\b'),
    ('election', r'\b(election\w*|campaign\w*|poll\w*|vote\w*|ballot|candidate|by-election|primaries)\b'),
    ('statement', r'\b(says|said|warns?|urges?|calls? for|announces?|statement|address\w*|speech|declares?)\b'),
]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def classify(title: str) -> str:
    t = (title or '').lower()
    for kind, pat in KIND_RULES:
        if re.search(pat, t):
            return kind
    return 'other'


def _title_key(title: str) -> str:
    return ' '.join(sorted(set(normalize(title).split())))[:300]


def _mentions_person(person: Person, text: str) -> bool:
    """Google search results occasionally match only part of a name; keep
    items whose headline or snippet contains a full name or the surname."""
    t = normalize(text)
    names = {normalize(a.alias) for a in person.aliases if a.kind in ('full', 'label') or not a.is_ambiguous}
    names.add(normalize(person.full_name))
    if any(n and n in t for n in names):
        return True
    from app.services.people.text import surname_of
    sn = surname_of(person.full_name)
    return bool(sn and re.search(rf'\b{re.escape(normalize(sn))}\b', t))


def refresh_developments(person: Person, use_web: bool = True) -> dict:
    """Add new developments for one person. Returns counts."""
    existing_hashes = {h for (h,) in db.session.query(PersonDevelopment.url_hash)
                       .filter_by(person_id=person.id).all()}
    existing_titles = {_title_key(t) for (t,) in db.session.query(PersonDevelopment.title)
                       .filter_by(person_id=person.id).all()}
    added, errors = 0, []
    cutoff = _now() - timedelta(days=MAX_AGE_DAYS)

    def add_item(title, url, publisher, published_at, summary=None, article_id=None, kind_hint=None):
        nonlocal added
        if not title or not url:
            return
        if published_at and published_at < cutoff:
            return
        h = url_hash(url)
        tk = _title_key(title)
        if h in existing_hashes or tk in existing_titles:
            return
        source = get_or_create_source(url, 'local_article' if article_id else 'news', title=title,
                                      publisher=publisher, published_at=published_at)
        link_source(person, source, 'development')
        db.session.add(PersonDevelopment(
            person_id=person.id, url_hash=h, title=title[:600], summary=(summary or None),
            url=url[:1500], publisher=(publisher or source.domain or '')[:200], tier=source.tier,
            published_at=published_at, article_id=article_id, source_id=source.id,
            kind=kind_hint or classify(title)))
        existing_hashes.add(h)
        existing_titles.add(tk)
        added += 1

    # 1. Our own ingested articles
    rows = (db.session.query(Article).join(ArticleMention, ArticleMention.article_id == Article.id)
            .filter(ArticleMention.person_id == person.id)
            .order_by(Article.published_at.desc().nullslast()).limit(40).all())
    for a in rows:
        if a.url and not a.url.startswith('https://example.com/mock/'):
            add_item(a.title, a.url, a.source_name, a.published_at, a.description, article_id=a.id)
        elif a.url:
            # Mock/demo articles: keep them as in-app items (linked by article id)
            add_item(a.title, f'app://article/{a.id}', a.source_name, a.published_at, a.description, article_id=a.id)

    # 2. Web news search
    if use_web:
        name = person.display_name or person.full_name
        queries = [(f'"{name}"', person.is_zambian)]
        if person.is_zambian:
            queries.append((f'"{name}" (site:gov.zm OR site:parliament.gov.zm OR site:elections.org.zm)', True))
        for q, zm in queries:
            try:
                items = src.google_news(q + ' when:60d', zambia=zm)
            except src.SourceError as e:
                errors.append(f'news search: {e}')
                continue
            for it in items:
                if not _mentions_person(person, f"{it['title']} {it.get('summary') or ''}"):
                    continue
                pub_url = it.get('publisher_url') or ''
                tier = src.credibility_tier(pub_url) if pub_url else 7
                # The Google link redirects; the tier comes from the publisher's own domain.
                url = it['url']
                if url and url_hash(url) not in existing_hashes:
                    src_row = get_or_create_source(url, 'official' if tier <= 4 else 'news', title=it['title'],
                                                   publisher=it.get('publisher'), published_at=it.get('published_at'),
                                                   tier=tier)
                    src_row.domain = src.domain_of(pub_url) or src_row.domain
                add_item(it['title'], url, it.get('publisher'), it.get('published_at'), it.get('summary'))

    person.developments_updated_at = _now()
    db.session.commit()
    return {'added': added, 'errors': errors}


def list_developments(person: Person, limit: int = 10, offset: int = 0) -> list[dict]:
    rows = (PersonDevelopment.query.filter_by(person_id=person.id)
            .order_by(PersonDevelopment.published_at.desc().nullslast(), PersonDevelopment.tier.asc())
            .offset(offset).limit(limit).all())
    out = []
    for d in rows:
        item = d.to_dict()
        item['tier_label'] = src.TIER_LABELS.get(d.tier)
        if item['url'] and item['url'].startswith('app://'):
            item['url'] = None
        out.append(item)
    return out
