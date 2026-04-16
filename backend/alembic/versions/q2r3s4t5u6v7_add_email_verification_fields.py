"""add email verification fields

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-04-05 07:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q2r3s4t5u6v7'
down_revision: Union[str, None] = 'p1q2r3s4t5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email_verified (default True so existing users are not locked out)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='email_verified'
            ) THEN
                ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;
        END
        $$;
    """)

    # Add email_verify_token_hash
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='email_verify_token_hash'
            ) THEN
                ALTER TABLE users ADD COLUMN email_verify_token_hash TEXT;
            END IF;
        END
        $$;
    """)

    # Add email_verify_token_expires_at
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='email_verify_token_expires_at'
            ) THEN
                ALTER TABLE users ADD COLUMN email_verify_token_expires_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    for col in ('email_verify_token_expires_at', 'email_verify_token_hash', 'email_verified'):
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='users' AND column_name='{col}'
                ) THEN
                    ALTER TABLE users DROP COLUMN {col};
                END IF;
            END
            $$;
        """)
