from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.article import Article
from app.services.news_sources import REGIONS
from app.services.feedback import attach_feedback, set_feedback, feedback_map
from app.routes.helpers import current_identity

bp = Blueprint('articles', __name__, url_prefix='/api/articles')


@bp.get('')
def list_articles():
    """
    Query params (all optional):
      category  politics | economics | technology | global-affairs | sports | health
      region    international | zambia
      source    source key(s) from /api/sources, comma-separated, e.g. lusaka-times or bbc-world,bbc-africa
      q         free-text search in title/description
      page, page_size
    """
    category = request.args.get('category')
    region = request.args.get('region')
    source = request.args.get('source')
    q = (request.args.get('q') or '').strip()
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 20)), 1), 100)

    query = Article.query
    if category:
        query = query.filter_by(category=category)
    if region in REGIONS:
        query = query.filter_by(region=region)
    if source:
        query = query.filter(Article.source_key.in_([k.strip() for k in source.split(',') if k.strip()]))
    if q:
        like = f'%{q}%'
        query = query.filter(Article.title.ilike(like) | Article.description.ilike(like))
    query = query.order_by(Article.published_at.desc().nullslast())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return jsonify({
        'articles': attach_feedback([a.to_dict() for a in items], current_identity()[0]),
        'page': page,
        'page_size': page_size,
        'total': total,
    })


@bp.get('/<int:article_id>')
@jwt_required()
def get_article(article_id):
    """Full article (body + link to the publisher). Account required."""
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'error': 'Article not found.'}), 404
    d = article.to_dict(full=True)
    d['my_feedback'] = feedback_map(int(get_jwt_identity()), [article.id]).get(article.id, 0)
    return jsonify(d)


@bp.put('/<int:article_id>/feedback')
@jwt_required()
def put_feedback(article_id):
    """
    Like / dislike an article.
    Body: {"value": 1}  like
          {"value": -1} dislike
          {"value": 0}  clear the reaction
    """
    if not Article.query.get(article_id):
        return jsonify({'error': 'Article not found.'}), 404
    value = (request.get_json(silent=True) or {}).get('value')
    if value not in (-1, 0, 1):
        return jsonify({'error': 'value must be 1 (like), -1 (dislike) or 0 (clear).'}), 400
    stored = set_feedback(int(get_jwt_identity()), article_id, value)
    return jsonify({'article_id': article_id, 'my_feedback': stored})


@bp.get('/<int:article_id>/summary')
@jwt_required()
def get_summary(article_id):
    """
    Readable in-app summary of the article. When other outlets covered the
    same story, their reporting is combined into one summary (?related=0 to
    summarise only this article). Account required, like the full article.
    The first request for a story can take several seconds (pages are
    fetched and summarised); after that it is served from the cache.
    """
    from app.services.summarizer import summarise_article
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'error': 'Article not found.'}), 404
    include_related = request.args.get('related', '1') != '0'
    return jsonify(summarise_article(article, include_related=include_related))
