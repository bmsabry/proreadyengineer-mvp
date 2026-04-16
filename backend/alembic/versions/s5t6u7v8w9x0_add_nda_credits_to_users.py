"""add nda credits to users

Revision ID: s5t6u7v8w9x0
Revises: r3s4t5u6v7w8
Create Date: 2026-04-08 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's5t6u7v8w9x0'
down_revision: Union[str, None] = 'r3s4t5u6v7w8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add monthly NDA credit tracking columns to users table
    op.add_column(
        'users',
        sa.Column(
            'monthly_nda_credits_used',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'nda_credits_reset_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'nda_credits_reset_at')
    op.drop_column('users', 'monthly_nda_credits_used')
