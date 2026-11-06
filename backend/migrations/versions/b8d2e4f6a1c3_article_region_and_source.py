"""article region + source_key (live multi-source news)

Adds:
  - articles.region      'international' | 'zambia'
  - articles.source_key  which configured news source an article came from

Existing rows are backfilled: region='zambia' when the text mentions Zambia
or Lusaka, and source_key='mock' for the bundled sample articles.

Revision ID: b8d2e4f6a1c3
Revises: a3f1c9e2b7d4
Create Date: 2026-10-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8d2e4f6a1c3'
down_revision = 'a3f1c9e2b7d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_key', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('region', sa.String(length=20), nullable=False,
                                      server_default='international'))
        batch_op.create_index(batch_op.f('ix_articles_source_key'), ['source_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_articles_region'), ['region'], unique=False)

    op.execute("UPDATE articles SET source_key = 'mock' WHERE url LIKE 'https://example.com/mock/%'")
    op.execute(
        "UPDATE articles SET region = 'zambia' "
        "WHERE title ILIKE '%zambia%' OR title ILIKE '%lusaka%' "
        "OR description ILIKE '%zambia%' OR description ILIKE '%lusaka%'"
    )


def downgrade():
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_articles_region'))
        batch_op.drop_index(batch_op.f('ix_articles_source_key'))
        batch_op.drop_column('region')
        batch_op.drop_column('source_key')
