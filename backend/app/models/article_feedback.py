from datetime import datetime, timezone
from app.extensions import db


class ArticleFeedback(db.Model):
    """
    A reader's explicit like (+1) or dislike (-1) on an article.

    Implicit feedback (clicks, reading time) in the interactions table is
    noisy: a click can be curiosity, and a short read can mean the article
    was bad or just short. A thumbs up/down is the reader telling us
    directly. The recommender uses it three ways (see
    app/services/recommender.py):
      1. as a stronger-than-a-click signal in the bandit's per-category
         context (likes raise a category's CTR/reward features, dislikes
         lower them),
      2. disliked articles are never served to that reader again,
      3. it counts as engagement, so the onboarding-interest prior fades
         faster once a reader starts giving explicit feedback.

    One row per (user, article). Changing your mind updates the row, and
    clearing the reaction deletes it.
    """
    __tablename__ = 'article_feedback'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'article_id', name='uq_article_feedback_user_article'),
        db.CheckConstraint('value IN (-1, 1)', name='ck_article_feedback_value'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False, index=True)
    value = db.Column(db.SmallInteger, nullable=False)  # +1 like, -1 dislike
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    article = db.relationship('Article')
