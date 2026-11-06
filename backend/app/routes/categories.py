from flask import Blueprint, jsonify, current_app
from app.models.category import Category

bp = Blueprint('categories', __name__, url_prefix='/api/categories')


@bp.get('')
def list_categories():
    rows = Category.query.order_by(Category.name).all()
    if rows:
        return jsonify({'categories': [c.to_dict() for c in rows]})
    # DB not seeded yet — fall back to configured category list.
    fallback = [{'slug': c, 'name': c.replace('-', ' ').title()} for c in current_app.config['NEWS_CATEGORIES']]
    return jsonify({'categories': fallback})
