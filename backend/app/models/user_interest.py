from datetime import datetime, timezone
from app.extensions import db


class UserInterest(db.Model):
    """
    One category a user explicitly said they're interested in during
    onboarding (or later, from "Edit interests").

    This is *explicit* feedback, kept separate from the *implicit* feedback
    in the interactions table (clicks, reading time). The recommender uses it
    as an informative prior for cold-start users: it shapes the very first
    feed, then fades out as real interaction data builds up and the
    contextual bandit takes over (see app/services/recommender.py).

    Stored as a join table (user_id, category) rather than a list column on
    users, which keeps the schema normalised (3NF) and lets the admin
    analytics query interest distribution with a plain GROUP BY.
    """
    __tablename__ = 'user_interests'
    __table_args__ = (db.UniqueConstraint('user_id', 'category', name='uq_user_interest'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False, index=True)  # category slug
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
