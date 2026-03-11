"""add user profile fields

Revision ID: c1d2e3f4g5h6
Revises: b2c3d4e5f6a7
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4g5h6'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('business_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'business_name')
    op.drop_column('users', 'full_name')
