from datetime import datetime, timezone
from app.extensions import db


class Article(db.Model):
    __tablename__ = 'articles'

    id = db.Column(db.Integer, primary_key=True)
    # Hash of source URL — lets us upsert on re-ingestion without duplicates.
    external_id = db.Column(db.String(64), unique=True, nullable=False, index=True)

    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)
    url = db.Column(db.String(1000))
    image_url = db.Column(db.String(1000))
    source_name = db.Column(db.String(200))
    # Which entry in app/services/news_sources.py this came from (e.g.
    # 'bbc-world', 'lusaka-times'); 'mock' for the bundled sample data.
    source_key = db.Column(db.String(60), index=True)
    # 'international' or 'zambia' — powers the region filter in the UI and
    # the ?region= parameter on /api/articles and /api/recommendations.
    region = db.Column(db.String(20), index=True, nullable=False, default='international',
                       server_default='international')

    category = db.Column(db.String(60), index=True, nullable=False)
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Full text of the story, fetched from the publisher's page on demand
    # (app/services/fulltext.py) so the summariser has the whole story to
    # work with, not just the RSS teaser. Never sent to the browser: readers
    # get the summary, and a link to the publisher for the original.
    full_text = db.Column(db.Text)
    # None = not tried yet, 'ok', or 'failed' (paywall, blocked, no article body found)
    full_text_status = db.Column(db.String(20))
    full_text_fetched_at = db.Column(db.DateTime)

    # When the AI People Profiles scanner last looked for people in this
    # article (services/people/linker.py). Null = not scanned yet.
    people_scanned_at = db.Column(db.DateTime, index=True)

    # Popularity/engagement counters denormalized here for fast bandit context
    # feature lookup (avoids an aggregate query on every recommendation call).
    impressions = db.Column(db.Integer, default=0, nullable=False)
    clicks = db.Column(db.Integer, default=0, nullable=False)
    total_dwell_seconds = db.Column(db.Integer, default=0, nullable=False)

    def to_dict(self, score=None, full=False):
        """
        full=False (default) is the public "teaser" used by every list,
        search, trending and recommendation response: headline, summary,
        image, source. The article body and the link to the publisher are
        only included with full=True, which GET /api/articles/<id> uses and
        which requires a logged-in account.
        """
        d = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'image_url': self.image_url,
            'source_name': self.source_name,
            'source_key': self.source_key,
            'region': self.region,
            'category': self.category,
            'published_at': self.published_at.isoformat() if self.published_at else None,
        }
        if full:
            d['content'] = self.content
            d['url'] = self.url
        if score is not None:
            d['recommendation_score'] = score
        return d

    @property
    def ctr(self):
        return (self.clicks / self.impressions) if self.impressions else 0.0
