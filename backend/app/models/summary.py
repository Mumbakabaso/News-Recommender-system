from datetime import datetime, timezone
from app.extensions import db


class Summary(db.Model):
    """
    Cached reader-friendly summary of one article, or of several articles
    about the same story bundled together (see app/services/summarizer.py).

    cache_key identifies exactly which articles went in and which engine
    wrote it ("gemini:<hash of sorted ids>" / "extractive:<hash>"), so when a
    new outlet covers the story the article set changes and a fresh summary
    is written automatically, and adding a Gemini key later upgrades old
    offline summaries.
    """
    __tablename__ = 'summaries'

    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)          # 'article' | 'story'
    article_ids = db.Column(db.String(500), nullable=False)  # comma-separated, sorted
    engine = db.Column(db.String(40), nullable=False)        # 'gemini' | 'extractive'
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
