"""add quotes.provider_contacted_at

Persists the provider's "customer already contacted" dismissal on accepted RFQs
so it survives reloads / new devices (was localStorage-only before).

Revision ID: e5b8c3d21f09
Revises: d4a7e2b91c08
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5b8c3d21f09'
down_revision = 'd4a7e2b91c08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('quotes')]
    if 'provider_contacted_at' not in cols:
        op.add_column('quotes', sa.Column('provider_contacted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('quotes')]
    if 'provider_contacted_at' in cols:
        op.drop_column('quotes', 'provider_contacted_at')
