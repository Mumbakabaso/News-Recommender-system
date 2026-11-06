"""
AI People Profiles: data model.

A Person is a real individual mentioned in the news. Everything shown on a
profile is traceable to an InfoSource row (Wikidata, Wikipedia, a news
article, an official site), so the profile never contains claims that came
only from an AI model's memory.

    people ──< person_aliases        every name form that refers to them
           ──< person_positions      offices held, with dates (history kept)
           ──< person_facts          education, party, occupation, family, ...
           ──< person_achievements   awards / milestones, verified vs claimed
           ──< person_developments   latest news about them (deduplicated)
           ──< article_mentions >── articles
           ──< person_sources >──── info_sources
    person_candidates                names seen in articles that could not be
                                     confidently identified (never linked)
"""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Person(db.Model):
    __tablename__ = 'people'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    # Wikidata item id (e.g. "Q123") - the anchor that stops duplicate
    # profiles: two different spellings that resolve to the same QID are the
    # same person. Null for news-only profiles of local figures that are not
    # on Wikidata.
    wikidata_id = db.Column(db.String(20), unique=True, index=True)
    wikipedia_title = db.Column(db.String(300))

    full_name = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)   # commonly known name
    short_description = db.Column(db.String(400))              # "President of Zambia since 2021"
    headline_position = db.Column(db.String(300))              # current or last verified position
    headline_position_current = db.Column(db.Boolean)
    nationality = db.Column(db.String(200))
    is_zambian = db.Column(db.Boolean, default=False, nullable=False, index=True)
    category = db.Column(db.String(40))                        # politician, business, sport, ...

    birth_date = db.Column(db.String(40))                      # ISO date or year, as precise as the source
    birth_place = db.Column(db.String(200))

    image_url = db.Column(db.String(1000))
    image_credit = db.Column(db.String(300))
    image_source_url = db.Column(db.String(1000))

    # 'wikidata' = identity confirmed against Wikidata;
    # 'news_only' = local figure profiled only from news reports.
    verification = db.Column(db.String(20), nullable=False, default='wikidata')
    # 'pending' (identified, profile not built yet) | 'ready' | 'failed'
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    last_error = db.Column(db.String(500))

    # Generated profile sections (see services/people/profile_builder.py):
    # {"summary": "...", "sections": {"biography": [{text, sources, status}], ...},
    #  "disagreements": [...], "unverified_notes": [...]}
    profile = db.Column(db.JSON)
    profile_engine = db.Column(db.String(40))                  # 'gemini' | 'offline'

    # How well known the person is: number of Wikipedia language editions
    # with an article about them (from Wikidata). Used to judge how much
    # supporting context a name match needs.
    notability = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    mention_count = db.Column(db.Integer, nullable=False, default=0)
    last_mentioned_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)
    facts_checked_at = db.Column(db.DateTime)        # Wikidata facts/positions last fetched
    bio_updated_at = db.Column(db.DateTime)          # profile text last (re)generated
    developments_updated_at = db.Column(db.DateTime) # latest news last retrieved

    aliases = db.relationship('PersonAlias', backref='person', cascade='all, delete-orphan', lazy='selectin')
    positions = db.relationship('PersonPosition', backref='person', cascade='all, delete-orphan',
                                order_by='PersonPosition.sort_key.desc()')
    facts = db.relationship('PersonFact', backref='person', cascade='all, delete-orphan')
    achievements = db.relationship('PersonAchievement', backref='person', cascade='all, delete-orphan')

    def card(self):
        """Compact form used by link previews and lists."""
        return {
            'id': self.id,
            'slug': self.slug,
            'name': self.display_name,
            'full_name': self.full_name,
            'headline_position': self.headline_position,
            'headline_position_current': self.headline_position_current,
            'short_description': self.short_description,
            'image_url': self.image_url,
            'is_zambian': self.is_zambian,
            'category': self.category,
            'verification': self.verification,
            'status': self.status,
        }


class PersonAlias(db.Model):
    __tablename__ = 'person_aliases'
    __table_args__ = (db.UniqueConstraint('person_id', 'normalized', name='uq_person_alias'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    alias = db.Column(db.String(200), nullable=False)
    normalized = db.Column(db.String(200), nullable=False, index=True)
    # full | surname | title | nickname | abbreviation | label
    kind = db.Column(db.String(20), nullable=False, default='full')
    # Ambiguous aliases (a bare surname, initials like "HH") are only linked
    # when the article also clearly refers to this person.
    is_ambiguous = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(40))  # wikidata | wikipedia | curated | admin | derived | article
    created_at = db.Column(db.DateTime, default=_now)


class InfoSource(db.Model):
    """A document a profile statement can be traced back to."""
    __tablename__ = 'info_sources'

    id = db.Column(db.Integer, primary_key=True)
    url_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    url = db.Column(db.String(1500), nullable=False)
    title = db.Column(db.String(600))
    publisher = db.Column(db.String(200))
    domain = db.Column(db.String(200))
    # wikidata | wikipedia | news | official | local_article
    kind = db.Column(db.String(20), nullable=False)
    # 1 = official Zambian government / Parliament / ECZ ... 7 = other; lower is more authoritative
    tier = db.Column(db.Integer, nullable=False, default=7)
    published_at = db.Column(db.DateTime)
    retrieved_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'publisher': self.publisher,
            'domain': self.domain,
            'kind': self.kind,
            'tier': self.tier,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'retrieved_at': self.retrieved_at.isoformat() if self.retrieved_at else None,
        }


class PersonSource(db.Model):
    __tablename__ = 'person_sources'
    __table_args__ = (db.UniqueConstraint('person_id', 'source_id', name='uq_person_source'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey('info_sources.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(30))  # identity | biography | development | position
    source = db.relationship('InfoSource')


class PersonPosition(db.Model):
    """
    An office or role. Never deleted: when a position ends it gets an
    end_date and is_current=False, so the history is kept and the profile
    never presents a former role as current.
    """
    __tablename__ = 'person_positions'
    __table_args__ = (db.UniqueConstraint('person_id', 'statement_key', name='uq_person_position'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    # Wikidata statement id, or a hash for positions found elsewhere.
    statement_key = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    organization = db.Column(db.String(300))     # "of" / jurisdiction / electoral district
    party = db.Column(db.String(200))
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    is_current = db.Column(db.Boolean, nullable=False, default=False)
    sort_key = db.Column(db.String(20), nullable=False, default='')
    source_id = db.Column(db.Integer, db.ForeignKey('info_sources.id'))
    first_seen_at = db.Column(db.DateTime, default=_now)
    last_verified_at = db.Column(db.DateTime, default=_now)
    ended_detected_at = db.Column(db.DateTime)   # when we noticed it had ended
    # True when the source no longer lists it (kept for history, flagged).
    withdrawn = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'organization': self.organization, 'party': self.party,
            'start_date': self.start_date, 'end_date': self.end_date, 'is_current': self.is_current,
            'source_id': self.source_id,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
        }


class PersonFact(db.Model):
    """Biographical facts: education, party, occupation, family, citizenship, website..."""
    __tablename__ = 'person_facts'
    __table_args__ = (db.UniqueConstraint('person_id', 'kind', 'statement_key', name='uq_person_fact'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)  # education | party | occupation | family | citizenship | website | birth_date | birth_place
    statement_key = db.Column(db.String(120), nullable=False)
    value = db.Column(db.String(500), nullable=False)
    detail = db.Column(db.String(300))               # degree, relationship, ...
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    source_id = db.Column(db.Integer, db.ForeignKey('info_sources.id'))
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    def to_dict(self):
        return {'kind': self.kind, 'value': self.value, 'detail': self.detail,
                'start_date': self.start_date, 'end_date': self.end_date, 'source_id': self.source_id}


class PersonAchievement(db.Model):
    __tablename__ = 'person_achievements'
    __table_args__ = (db.UniqueConstraint('person_id', 'statement_key', name='uq_person_achievement'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    statement_key = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(400), nullable=False)
    year = db.Column(db.String(10))
    description = db.Column(db.Text)
    # independent = recorded by an independent source (e.g. an award in Wikidata);
    # claimed = stated by the person, their office or supporters.
    verification = db.Column(db.String(20), nullable=False, default='independent')
    source_id = db.Column(db.Integer, db.ForeignKey('info_sources.id'))

    def to_dict(self):
        return {'title': self.title, 'year': self.year, 'description': self.description,
                'verification': self.verification, 'source_id': self.source_id}


class ArticleMention(db.Model):
    __tablename__ = 'article_mentions'
    __table_args__ = (db.UniqueConstraint('article_id', 'person_id', name='uq_article_mention'),)

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    surface_forms = db.Column(db.JSON, nullable=False, default=list)  # exact strings seen in this article
    mention_count = db.Column(db.Integer, nullable=False, default=1)
    confidence = db.Column(db.Float, nullable=False, default=1.0)
    method = db.Column(db.String(30))  # gazetteer | wikidata | coref | news_only
    created_at = db.Column(db.DateTime, default=_now)

    person = db.relationship('Person')


class PersonDevelopment(db.Model):
    """A recent news item about a person. url_hash makes re-fetching idempotent."""
    __tablename__ = 'person_developments'
    __table_args__ = (db.UniqueConstraint('person_id', 'url_hash', name='uq_person_development'),)

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='CASCADE'), nullable=False, index=True)
    url_hash = db.Column(db.String(64), nullable=False)
    title = db.Column(db.String(600), nullable=False)
    summary = db.Column(db.Text)
    url = db.Column(db.String(1500))
    publisher = db.Column(db.String(200))
    tier = db.Column(db.Integer, nullable=False, default=7)
    published_at = db.Column(db.DateTime, index=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='SET NULL'))  # when it's in our own feed
    source_id = db.Column(db.Integer, db.ForeignKey('info_sources.id'))
    # appointment | resignation | statement | legal | election | other
    kind = db.Column(db.String(20), default='other')
    discovered_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'summary': self.summary, 'url': self.url,
            'publisher': self.publisher, 'tier': self.tier, 'kind': self.kind,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'article_id': self.article_id,
            'discovered_at': self.discovered_at.isoformat() if self.discovered_at else None,
        }


class PersonCandidate(db.Model):
    """
    A name found in articles that could not be identified with confidence.
    It is never hyperlinked. Candidates seen often enough across different
    outlets with a clear title ("Hon.", "Mayor", "Minister") can become a
    news-only profile; an admin can also resolve or reject them.
    """
    __tablename__ = 'person_candidates'

    id = db.Column(db.Integer, primary_key=True)
    normalized = db.Column(db.String(200), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    title_cue = db.Column(db.String(80))            # "Minister", "Mayor", ...
    mention_count = db.Column(db.Integer, nullable=False, default=0)
    article_ids = db.Column(db.JSON, nullable=False, default=list)
    sources = db.Column(db.JSON, nullable=False, default=list)  # distinct outlet names
    zambian_context = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='unresolved')  # unresolved | rejected | resolved | lookup_failed
    lookup_attempted_at = db.Column(db.DateTime)
    person_id = db.Column(db.Integer, db.ForeignKey('people.id', ondelete='SET NULL'))
    last_seen_at = db.Column(db.DateTime, default=_now)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'title_cue': self.title_cue,
                'mention_count': self.mention_count, 'sources': self.sources,
                'status': self.status, 'person_id': self.person_id,
                'article_ids': (self.article_ids or [])[-10:],
                'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None}
