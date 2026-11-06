from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.article import Article
from app.models.interaction import Interaction
from app.models.recommendation_log import RecommendationLog
from app.models.user_interest import UserInterest
from app.models.article_feedback import ArticleFeedback

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def _require_admin():
    user = User.query.get(int(get_jwt_identity()))
    return user if user and user.is_admin else None


@bp.get('/analytics')
@jwt_required()
def analytics():
    if not _require_admin():
        return jsonify({'error': 'Admin access required.'}), 403

    total_interactions = db.session.query(func.count(Interaction.id)).scalar() or 0
    total_impressions = (
        db.session.query(func.count(Interaction.id)).filter(Interaction.event_type == 'impression').scalar() or 0
    )
    total_clicks = (
        db.session.query(func.count(Interaction.id)).filter(Interaction.event_type == 'click').scalar() or 0
    )
    overall_ctr = (total_clicks / total_impressions) if total_impressions else 0.0
    reward_sum = db.session.query(func.coalesce(func.sum(Interaction.reward), 0.0)).scalar() or 0.0
    avg_reward = (reward_sum / total_impressions) if total_impressions else 0.0

    reward_rows = (
        db.session.query(
            func.date_trunc('day', Interaction.created_at).label('bucket'),
            func.avg(Interaction.reward),
        )
        .filter(Interaction.event_type.in_(['click', 'read']))
        .group_by('bucket')
        .order_by('bucket')
        .all()
    )
    reward_over_time = [
        {'bucket': bucket.strftime('%Y-%m-%d'), 'avg_reward': round(float(avg_r), 4)}
        for bucket, avg_r in reward_rows
    ]

    total_likes = db.session.query(func.count(ArticleFeedback.id)).filter(ArticleFeedback.value > 0).scalar() or 0
    total_dislikes = db.session.query(func.count(ArticleFeedback.id)).filter(ArticleFeedback.value < 0).scalar() or 0
    fb_rows = (
        db.session.query(Article.category, ArticleFeedback.value, func.count(ArticleFeedback.id))
        .join(Article, Article.id == ArticleFeedback.article_id)
        .group_by(Article.category, ArticleFeedback.value)
        .all()
    )
    fb_by_cat = {}
    for cat, value, n in fb_rows:
        d = fb_by_cat.setdefault(cat, {'likes': 0, 'dislikes': 0})
        d['likes' if value > 0 else 'dislikes'] += int(n)

    categories = current_app.config['NEWS_CATEGORIES']
    # How many users picked each category at onboarding (explicit interest),
    # shown next to how often the bandit actually served it (implicit).
    interest_counts = dict(
        db.session.query(UserInterest.category, func.count(UserInterest.id))
        .group_by(UserInterest.category)
        .all()
    )
    ctr_by_category = []
    arm_performance = []
    for category in categories:
        recommended = (
            db.session.query(func.count(RecommendationLog.id))
            .filter(RecommendationLog.category == category)
            .scalar() or 0
        )
        clicked = (
            db.session.query(func.count(Interaction.id))
            .join(Article, Article.id == Interaction.article_id)
            .filter(Article.category == category, Interaction.event_type == 'click')
            .scalar() or 0
        )
        ctr = (clicked / recommended) if recommended else 0.0
        ctr_by_category.append({'category': category, 'ctr': round(ctr, 4)})
        arm_performance.append({
            'category': category, 'recommended': recommended, 'clicked': clicked, 'ctr': round(ctr, 4),
            'interested_users': int(interest_counts.get(category, 0)),
            'likes': fb_by_cat.get(category, {}).get('likes', 0),
            'dislikes': fb_by_cat.get(category, {}).get('dislikes', 0),
        })

    return jsonify({
        'summary': {
            'total_interactions': total_interactions,
            'total_clicks': total_clicks,
            'overall_ctr': round(overall_ctr, 4),
            'avg_reward': round(avg_reward, 4),
            'total_likes': total_likes,
            'total_dislikes': total_dislikes,
        },
        'reward_over_time': reward_over_time,
        'ctr_by_category': ctr_by_category,
        'arm_performance': arm_performance,
    })
