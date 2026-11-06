"""Search and trending endpoints."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app.services.news_sources import REGIONS
from app.services.search import search_articles
from app.services.trending import get_trending
from app.services.feedback import attach_feedback
from app.routes.helpers import current_identity

bp = Blueprint('discover', __name__, url_prefix='/api')


def _region():
    r = request.args.get('region')
    return r if r in REGIONS else None


@bp.get('/search')
def search():
    """
    GET /api/search?q=floods&region=zambia&category=health&source=bbc-world&page=1&page_size=20
    q supports "exact phrases", -excluded words and OR.
    """
    q = request.args.get('q', '')
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 20)), 1), 50)
    items, total, mode = search_articles(
        q,
        region=_region(),
        category=request.args.get('category') or None,
        source=request.args.get('source') or None,
        page=page,
        page_size=page_size,
    )
    return jsonify({
        'query': q,
        'articles': attach_feedback([a.to_dict() for a in items], current_identity()[0]),
        'total': total,
        'page': page,
        'page_size': page_size,
        'match_mode': mode,
    })


@bp.get('/trending')
def trending():
    """
    GET /api/trending?region=zambia&hours=48&limit=10
    Stories covered by several outlets at once, plus breaking-type news
    (deaths, disasters...). See app/services/trending.py for the scoring.
    """
    hours = min(max(int(request.args.get('hours', 48)), 6), 168)
    limit = min(max(int(request.args.get('limit', 10)), 1), 30)
    return jsonify(get_trending(region=_region(), hours=hours, limit=limit))


@bp.get('/stories/summary')
@jwt_required()
def story_summary():
    """
    GET /api/stories/summary?ids=12,45,78
    One combined summary of several articles about the same story (used by
    the Trending page's "Read the briefing"). The first id is the lead
    article. Account required.
    """
    from app.services.summarizer import summarise_story, MAX_BUNDLE
    try:
        ids = [int(x) for x in (request.args.get('ids') or '').split(',') if x.strip()]
    except ValueError:
        return jsonify({'error': 'ids must be a comma-separated list of article ids.'}), 400
    ids = list(dict.fromkeys(ids))[:MAX_BUNDLE]
    if not ids:
        return jsonify({'error': 'Pass at least one article id, e.g. ?ids=12,45.'}), 400
    result = summarise_story(ids)
    if result is None:
        return jsonify({'error': 'None of those articles exist.'}), 404
    return jsonify(result)
