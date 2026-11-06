from flask import Blueprint, request, jsonify, current_app

from app.extensions import db
from app.models.article import Article
from app.models.interaction import Interaction, EVENT_TYPES
from app.services.reward import compute_reward
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint('interactions', __name__, url_prefix='/api/interactions')


@bp.post('')
@jwt_required()
def log_interaction():
    """Clicks / reading time from signed-in users: the bandit's reward signal."""
    data = request.get_json(silent=True) or {}
    article_id = data.get('article_id')
    event_type = data.get('event_type')
    dwell_seconds = int(data.get('dwell_seconds') or 0)
    position = data.get('position')

    if not article_id or event_type not in EVENT_TYPES:
        return jsonify({'error': f'article_id and event_type (one of {EVENT_TYPES}) are required.'}), 400

    article = Article.query.get(article_id)
    if not article:
        return jsonify({'error': 'Article not found.'}), 404

    user_id, anon_id = int(get_jwt_identity()), None

    reward = compute_reward(event_type, dwell_seconds)

    interaction = Interaction(
        user_id=user_id, anon_id=anon_id, article_id=article.id,
        event_type=event_type, dwell_seconds=dwell_seconds, position=position, reward=reward,
    )
    db.session.add(interaction)

    if event_type == 'click':
        article.clicks = (article.clicks or 0) + 1
    if event_type == 'read':
        article.total_dwell_seconds = (article.total_dwell_seconds or 0) + dwell_seconds

    db.session.commit()
    return jsonify({'ok': True, 'reward': reward}), 201
