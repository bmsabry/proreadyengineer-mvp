"""add users.agent_autonomous_enabled + agent_autonomous_consented_at

Opt-in autonomous AI-assistant mode (explicit risk consent; hard-stop toggles off).

Revision ID: a7d0e5f41b22
Revises: f6c9d4e32a10
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7d0e5f41b22'
down_revision = 'f6c9d4e32a10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'agent_autonomous_enabled' not in cols:
        op.add_column('users', sa.Column('agent_autonomous_enabled', sa.Boolean(),
                                         nullable=False, server_default='false'))
    if 'agent_autonomous_consented_at' not in cols:
        op.add_column('users', sa.Column('agent_autonomous_consented_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('users')]
    if 'agent_autonomous_consented_at' in cols:
        op.drop_column('users', 'agent_autonomous_consented_at')
    if 'agent_autonomous_enabled' in cols:
        op.drop_column('users', 'agent_autonomous_enabled')
