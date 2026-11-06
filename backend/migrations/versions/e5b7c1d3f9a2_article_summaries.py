"""article full text + summaries cache

Adds articles.full_text / full_text_status / full_text_fetched_at (the
publisher's full story, fetched on demand for summarising) and the
summaries table (cached single-article and multi-source story summaries).

Revision ID: e5b7c1d3f9a2
Revises: d9a3f5c7e2b1
Create Date: 2026-10-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5b7c1d3f9a2'
down_revision = 'd9a3f5c7e2b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('full_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('full_text_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('full_text_fetched_at', sa.DateTime(), nullable=True))

    op.create_table(
        'summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cache_key', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('article_ids', sa.String(length=500), nullable=False),
        sa.Column('engine', sa.String(length=40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('summaries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_summaries_cache_key'), ['cache_key'], unique=True)


def downgrade():
    with op.batch_alter_table('summaries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_summaries_cache_key'))
    op.drop_table('summaries')
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_column('full_text_fetched_at')
        batch_op.drop_column('full_text_status')
        batch_op.drop_column('full_text')
