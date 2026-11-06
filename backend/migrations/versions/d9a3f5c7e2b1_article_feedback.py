"""article likes / dislikes

Adds article_feedback: one explicit reaction (+1 like / -1 dislike) per
user per article.

Revision ID: d9a3f5c7e2b1
Revises: c4e7a9b2d5f1
Create Date: 2026-10-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9a3f5c7e2b1'
down_revision = 'c4e7a9b2d5f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'article_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('value IN (-1, 1)', name='ck_article_feedback_value'),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'article_id', name='uq_article_feedback_user_article'),
    )
    with op.batch_alter_table('article_feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_article_feedback_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_article_feedback_article_id'), ['article_id'], unique=False)


def downgrade():
    with op.batch_alter_table('article_feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_article_feedback_article_id'))
        batch_op.drop_index(batch_op.f('ix_article_feedback_user_id'))
    op.drop_table('article_feedback')
