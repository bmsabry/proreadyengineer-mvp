"""add help_chat_logs.feedback (thumbs up/down)

Revision ID: b8e1f6c43d21
Revises: a7d0e5f41b22
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8e1f6c43d21'
down_revision = 'a7d0e5f41b22'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('help_chat_logs')]
    if 'feedback' not in cols:
        op.add_column('help_chat_logs', sa.Column('feedback', sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('help_chat_logs')]
    if 'feedback' in cols:
        op.drop_column('help_chat_logs', 'feedback')
