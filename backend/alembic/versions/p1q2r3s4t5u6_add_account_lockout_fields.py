"""add account lockout fields

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-04-05 07:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, None] = 'o0p1q2r3s4t5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add failed_login_count if not exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='failed_login_count'
            ) THEN
                ALTER TABLE users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0;
            END IF;
        END
        $$;
    """)

    # Add locked_until if not exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='locked_until'
            ) THEN
                ALTER TABLE users ADD COLUMN locked_until TIMESTAMP WITH TIME ZONE;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='locked_until'
            ) THEN
                ALTER TABLE users DROP COLUMN locked_until;
            END IF;
        END
        $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='failed_login_count'
            ) THEN
                ALTER TABLE users DROP COLUMN failed_login_count;
            END IF;
        END
        $$;
    """)
