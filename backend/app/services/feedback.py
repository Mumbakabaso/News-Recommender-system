"""Helpers for explicit likes / dislikes (see models/article_feedback.py)."""
from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import func

from app.extensions import db
from app.models.article import Article
from app.models.article_feedback import ArticleFeedback


def set_feedback(user_id: int, article_id: int, value: int) -> int:
    """value: 1 like, -1 dislike, 0 clear. Returns the stored value (0 if cleared)."""
    row = ArticleFeedback.query.filter_by(user_id=user_id, article_id=article_id).first()
    if value == 0:
        if row:
            db.session.delete(row)
        db.session.commit()
        return 0
    if row is None:
        row = ArticleFeedback(user_id=user_id, article_id=article_id, value=value)
        db.session.add(row)
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return value


def feedback_map(user_id: int | None, article_ids) -> dict[int, int]:
    """{article_id: +1/-1} for this user, limited to the given articles."""
    ids = list({i for i in article_ids if i is not None})
    if not user_id or not ids:
        return {}
    rows = (
        db.session.query(ArticleFeedback.article_id, ArticleFeedback.value)
        .filter(ArticleFeedback.user_id == user_id, ArticleFeedback.article_id.in_(ids))
        .all()
    )
    return {a: v for a, v in rows}


def attach_feedback(article_dicts: list[dict], user_id: int | None) -> list[dict]:
    """Adds `my_feedback` (1, -1 or 0) to each article dict for a signed-in user."""
    if not user_id:
        return article_dicts
    fb = feedback_map(user_id, [a.get('id') for a in article_dicts])
    for a in article_dicts:
        a['my_feedback'] = fb.get(a.get('id'), 0)
    return article_dicts


def per_category_counts(user_id: int) -> dict[str, dict[str, int]]:
    """{category: {'likes': n, 'dislikes': m}} for one user (fed into the bandit context)."""
    rows = (
        db.session.query(Article.category, ArticleFeedback.value, func.count(ArticleFeedback.id))
        .join(Article, Article.id == ArticleFeedback.article_id)
        .filter(ArticleFeedback.user_id == user_id)
        .group_by(Article.category, ArticleFeedback.value)
        .all()
    )
    out: dict[str, dict[str, int]] = {}
    for category, value, n in rows:
        d = out.setdefault(category, {'likes': 0, 'dislikes': 0})
        d['likes' if value > 0 else 'dislikes'] += int(n)
    return out


def disliked_article_ids(user_id: int) -> set[int]:
    return {
        a for (a,) in db.session.query(ArticleFeedback.article_id)
        .filter(ArticleFeedback.user_id == user_id, ArticleFeedback.value < 0)
        .all()
    }
