from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.user import User
from app.services.recommender import get_recommendations
from app.services.news_sources import REGIONS
from app.services.feedback import attach_feedback

bp = Blueprint('recommendations', __name__, url_prefix='/api/recommendations')


@bp.get('')
@jwt_required()
def recommendations():
    """
    The personalised "For You" feed. Only for signed-in users who have
    finished onboarding (picked their interests), so every feed served is
    built from a real profile rather than an anonymous cold start.
    """
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({'error': 'User not found.'}), 404
    if user.needs_onboarding:
        return jsonify({'error': 'Choose your interests first to build your personalised feed.',
                        'code': 'onboarding_required'}), 403

    count = min(max(int(request.args.get('count', 10)), 1), 50)
    # Optional ?region=zambia|international: the bandit still picks the
    # category mix; only the candidate articles are restricted to the region.
    region = request.args.get('region')
    region = region if region in REGIONS else None
    interests = user.interest_slugs

    articles = get_recommendations(
        categories=current_app.config['NEWS_CATEGORIES'],
        model_path=current_app.config['RL_MODEL_PATH'],
        user_id=user.id,
        count=count,
        interests=interests,
        region=region,
    )
    return jsonify({'articles': attach_feedback(articles, user.id), 'interests': interests, 'region': region})
