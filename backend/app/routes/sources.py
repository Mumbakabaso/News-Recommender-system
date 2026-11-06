from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from app.extensions import db
from app.models.article import Article
from app.models.user import User
from app.services.news_sources import SOURCES, REGIONS
from app.services import news_ingestion

bp = Blueprint('sources', __name__, url_prefix='/api/sources')


@bp.get('')
def list_sources():
    """Every configured news source with its article count and last fetch status."""
    disabled = set(current_app.config.get('NEWS_DISABLED_SOURCES', []))
    counts = dict(
        db.session.query(Article.source_key, func.count(Article.id)).group_by(Article.source_key).all()
    )
    sources = []
    for s in SOURCES:
        status = news_ingestion.SOURCE_STATUS.get(s['key'], {})
        sources.append({
            'key': s['key'],
            'name': s['name'],
            'region': s['region'],
            'kind': s['kind'],
            'enabled': s['key'] not in disabled,
            'article_count': int(counts.get(s['key'], 0)),
            'ok': status.get('ok'),
            'last_run': status.get('last_run'),
            'last_saved': status.get('saved'),
            'error': status.get('error'),
        })
    return jsonify({
        'sources': sources,
        'regions': list(REGIONS),
        'last_run': news_ingestion.LAST_RUN,
        'mock_articles': int(counts.get('mock', 0)),
    })


@bp.post('/refresh')
@jwt_required()
def refresh():
    """Admin-only: fetch all sources right now instead of waiting for the scheduler."""
    user = User.query.get(int(get_jwt_identity()))
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required.'}), 403
    result = news_ingestion.run_ingestion(current_app.config)
    if result.get('skipped'):
        return jsonify(result), 409
    return jsonify(result)
