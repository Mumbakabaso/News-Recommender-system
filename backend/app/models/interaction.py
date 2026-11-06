from datetime import datetime, timezone
from app.extensions import db

EVENT_TYPES = ('impression', 'click', 'read')


class Interaction(db.Model):
    """
    One logged event tying a user (or anonymous visitor) to an article.
    This is the raw feedback stream the RL engine's reward signal is built
    from: reward = f(click, dwell_seconds), per the dissertation's
    methodology (implicit feedback via clicks + reading time).
    """
    __tablename__ = 'interactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    anon_id = db.Column(db.String(64), nullable=True, index=True)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False)  # impression | click | read
    dwell_seconds = db.Column(db.Integer, default=0, nullable=False)
    position = db.Column(db.Integer, nullable=True)  # slot in the recommendation list
    reward = db.Column(db.Float, default=0.0, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    article = db.relationship('Article')

    def to_dict(self):
        return {
            'id': self.id,
            'article_id': self.article_id,
            'event_type': self.event_type,
            'dwell_seconds': self.dwell_seconds,
            'reward': self.reward,
            'created_at': self.created_at.isoformat(),
        }
