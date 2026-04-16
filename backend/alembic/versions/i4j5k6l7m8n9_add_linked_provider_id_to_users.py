"""Add linked_provider_id to users table.

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-03-21 19:25:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'i4j5k6l7m8n9'
down_revision = 'h3i4j5k6l7m8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('linked_provider_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'linked_provider_id')
