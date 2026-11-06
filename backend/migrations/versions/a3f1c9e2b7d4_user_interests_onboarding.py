"""user interests + onboarding

Adds explicit-interest onboarding:
  - users.onboarded_at (NULL = user still needs to pick interests)
  - user_interests join table (user_id, category)

Revision ID: a3f1c9e2b7d4
Revises: d6bdfe04b607
Create Date: 2026-10-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3f1c9e2b7d4'
down_revision = 'd6bdfe04b607'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('onboarded_at', sa.DateTime(), nullable=True))

    op.create_table('user_interests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'category', name='uq_user_interest')
    )
    with op.batch_alter_table('user_interests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_interests_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_interests_category'), ['category'], unique=False)


def downgrade():
    with op.batch_alter_table('user_interests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_interests_category'))
        batch_op.drop_index(batch_op.f('ix_user_interests_user_id'))
    op.drop_table('user_interests')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('onboarded_at')
