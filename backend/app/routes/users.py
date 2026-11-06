from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models.user import User
from app.models.user_interest import UserInterest
from app.models.article_feedback import ArticleFeedback

bp = Blueprint('users', __name__, url_prefix='/api/users')

MAX_INTERESTS = 10


def _current_user():
    return User.query.get(int(get_jwt_identity()))


@bp.get('/me/interests')
@jwt_required()
def get_interests():
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found.'}), 404
    return jsonify({'interests': user.interest_slugs, 'needs_onboarding': user.needs_onboarding})


@bp.put('/me/interests')
@jwt_required()
def set_interests():
    """
    Replace the user's interest list. Called from the onboarding page right
    after sign-up and from "Edit interests" later on.

    Body: {"interests": ["politics", "technology", ...]}
    At least one interest is required: the personalised "For You" feed is
    only built once the user has told us something about what they like.
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}
    raw = data.get('interests')
    if not isinstance(raw, list):
        return jsonify({'error': '"interests" must be a list of category slugs.'}), 400

    allowed = set(current_app.config['NEWS_CATEGORIES'])
    wanted = []
    for slug in raw:
        slug = str(slug).strip().lower()
        if slug not in allowed:
            return jsonify({'error': f'Unknown category: {slug}'}), 400
        if slug not in wanted:
            wanted.append(slug)
    if not wanted:
        return jsonify({'error': 'Pick at least one interest to build your personalised feed.'}), 400
    if len(wanted) > MAX_INTERESTS:
        return jsonify({'error': f'Pick at most {MAX_INTERESTS} interests.'}), 400

    # Replace the whole set. delete-orphan on User.interests removes the
    # rows that are no longer in the list.
    existing = {i.category: i for i in user.interests}
    user.interests = [existing.get(slug) or UserInterest(category=slug) for slug in wanted]
    user.onboarded_at = user.onboarded_at or datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({'user': user.to_dict()})


@bp.get('/me/feedback')
@jwt_required()
def my_feedback():
    """
    Articles the user has liked (default) or disliked, newest reaction first.
    GET /api/users/me/feedback?value=like|dislike&page=1&page_size=24
    """
    user = _current_user()
    if not user:
        return jsonify({'error': 'User not found.'}), 404
    want = -1 if request.args.get('value') == 'dislike' else 1
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 24)), 1), 100)

    q = ArticleFeedback.query.filter_by(user_id=user.id, value=want).order_by(ArticleFeedback.updated_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    articles = []
    for r in rows:
        d = r.article.to_dict()
        d['my_feedback'] = r.value
        articles.append(d)

    # Per-category summary: what this reader has told us they want more / less of.
    from app.services.feedback import per_category_counts
    return jsonify({
        'articles': articles,
        'total': total,
        'page': page,
        'by_category': per_category_counts(user.id),
    })
