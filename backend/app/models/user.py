from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # Set when the user finishes the "choose your interests" onboarding step.
    # NULL means the frontend should send them there first.
    onboarded_at = db.Column(db.DateTime, nullable=True)

    interactions = db.relationship('Interaction', backref='user', lazy='dynamic')
    interests = db.relationship(
        'UserInterest', backref='user', lazy='select', cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def interest_slugs(self):
        return sorted(i.category for i in self.interests)

    @property
    def needs_onboarding(self):
        """
        True until the user has picked at least one interest. The "For You"
        feed is only served once this is False, so every personalised feed
        starts from a real profile. (Accounts that skipped onboarding before
        it became mandatory are asked again.)
        """
        return self.onboarded_at is None or not self.interests

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'is_admin': self.is_admin,
            'interests': self.interest_slugs,
            'needs_onboarding': self.needs_onboarding,
        }
