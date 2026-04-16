"""Add target_mode column to provider_campaigns table.

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-04-05 04:12:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'o0p1q2r3s4t5'
down_revision = 'n9o0p1q2r3s4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'provider_campaigns',
        sa.Column(
            'target_mode',
            sa.String(),
            nullable=False,
            server_default='all',
        ),
    )


def downgrade():
    op.drop_column('provider_campaigns', 'target_mode')
