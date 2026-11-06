from datetime import datetime, timezone
from app.extensions import db


class RecommendationLog(db.Model):
    """
    Every article the bandit chose to surface, with the arm (category) and
    score it assigned. Joining this against Interaction lets us compute
    per-arm CTR — i.e. evaluate the policy — without re-deriving it from
    scratch each time.
    """
    __tablename__ = 'recommendation_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    anon_id = db.Column(db.String(64), nullable=True, index=True)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False, index=True)  # the "arm"
    score = db.Column(db.Float, nullable=False)
    position = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
