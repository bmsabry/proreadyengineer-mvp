"""Add server defaults and timestamps to ip_usage_tracking

Revision ID: b2c3d4e5f6a7
Revises: abc123resize
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'abc123resize'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_at with server default (idempotent)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ip_usage_tracking'
                  AND column_name = 'created_at'
            ) THEN
                ALTER TABLE ip_usage_tracking
                    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE
                        NOT NULL DEFAULT NOW();
            ELSE
                ALTER TABLE ip_usage_tracking
                    ALTER COLUMN created_at SET DEFAULT NOW(),
                    ALTER COLUMN created_at SET NOT NULL;
            END IF;
        END $$;
    """)

    # Add updated_at with server default (idempotent)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'ip_usage_tracking'
                  AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE ip_usage_tracking
                    ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE
                        NOT NULL DEFAULT NOW();
            ELSE
                ALTER TABLE ip_usage_tracking
                    ALTER COLUMN updated_at SET DEFAULT NOW(),
                    ALTER COLUMN updated_at SET NOT NULL;
            END IF;
        END $$;
    """)

    # Unique constraint ip+month (idempotent)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_ip_usage_tracking_ip_month'
            ) THEN
                ALTER TABLE ip_usage_tracking
                    ADD CONSTRAINT uq_ip_usage_tracking_ip_month
                    UNIQUE (ip_address, usage_month);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ip_usage_tracking DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE ip_usage_tracking DROP COLUMN IF EXISTS created_at")