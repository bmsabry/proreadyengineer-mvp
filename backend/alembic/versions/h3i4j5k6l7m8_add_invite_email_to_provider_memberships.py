"""add_invite_email_to_provider_memberships

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-03-21 09:34:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'h3i4j5k6l7m8'
down_revision = 'g2h3i4j5k6l7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'provider_memberships',
        sa.Column('invite_email', sa.Text(), nullable=True,
                  comment='Email address the invite was originally sent to, for audit purposes')
    )


def downgrade() -> None:
    op.drop_column('provider_memberships', 'invite_email')
