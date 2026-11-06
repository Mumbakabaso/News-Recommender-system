"""full-text search index on articles

GIN index over to_tsvector('english', title || ' ' || description), used by
GET /api/search (app/services/search.py builds the same expression).

Revision ID: c4e7a9b2d5f1
Revises: b8d2e4f6a1c3
Create Date: 2026-10-06 14:00:00.000000

"""
from alembic import op


revision = 'c4e7a9b2d5f1'
down_revision = 'b8d2e4f6a1c3'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_fulltext ON articles USING gin "
        "(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')))"
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_articles_fulltext')
