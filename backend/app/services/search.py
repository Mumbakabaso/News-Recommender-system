"""
Article search, using PostgreSQL's built-in full-text search.

Why full-text search rather than a plain LIKE '%word%':
  - stemming: "flood" also finds "floods" / "flooding"
  - ranking: articles where the words appear in the headline, and appear
    more often, come first (ts_rank), blended with freshness so a week-old
    match doesn't outrank today's
  - query syntax users already know (websearch_to_tsquery): "exact phrase",
    -exclude, OR

The GIN index from migration c4e7a9b2d5f1 keeps it fast. If full-text search
finds nothing (e.g. a partial word like "hichil" or a name the English
stemmer mangles), it falls back to a case-insensitive substring match so the
user still gets results.
"""
from __future__ import annotations
from sqlalchemy import func, literal_column, or_

from app.models.article import Article

# Must match the indexed expression in the migration exactly, or Postgres
# can't use the index.
SEARCH_DOCUMENT = func.to_tsvector(
    literal_column("'english'"),
    func.coalesce(Article.title, '') + ' ' + func.coalesce(Article.description, ''),
)
TITLE_DOCUMENT = func.to_tsvector(literal_column("'english'"), func.coalesce(Article.title, ''))


def search_articles(q: str, region=None, category=None, source=None, page=1, page_size=20):
    q = (q or '').strip()[:200]
    if not q:
        return [], 0, 'none'

    def filtered(query):
        if region:
            query = query.filter(Article.region == region)
        if category:
            query = query.filter(Article.category == category)
        if source:
            query = query.filter(Article.source_key.in_([k for k in source.split(',') if k]))
        return query

    tsq = func.websearch_to_tsquery(literal_column("'english'"), q)
    # Headline hits count double; freshness divides the score by
    # (1 + age in days) so recent matches rise.
    age_days = func.extract('epoch', func.now() - func.coalesce(Article.published_at, func.now())) / 86400.0
    rank = (func.ts_rank(SEARCH_DOCUMENT, tsq) + func.ts_rank(TITLE_DOCUMENT, tsq)) / (1.0 + age_days)

    fts = filtered(Article.query.filter(SEARCH_DOCUMENT.op('@@')(tsq)))
    total = fts.count()
    if total:
        items = fts.order_by(rank.desc(), Article.published_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total, 'fulltext'

    like = f'%{q}%'
    sub = filtered(Article.query.filter(or_(Article.title.ilike(like), Article.description.ilike(like))))
    total = sub.count()
    items = sub.order_by(Article.published_at.desc().nullslast()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total, 'substring'
