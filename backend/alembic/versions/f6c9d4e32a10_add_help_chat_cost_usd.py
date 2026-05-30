"""add help_chat_logs.cost_usd

Per-turn estimated USD cost, for per-user monthly budget metering.

Revision ID: f6c9d4e32a10
Revises: e5b8c3d21f09
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6c9d4e32a10'
down_revision = 'e5b8c3d21f09'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('help_chat_logs')]
    if 'cost_usd' not in cols:
        op.add_column('help_chat_logs', sa.Column('cost_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('help_chat_logs')]
    if 'cost_usd' in cols:
        op.drop_column('help_chat_logs', 'cost_usd')
