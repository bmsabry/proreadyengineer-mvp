"""Fix system_config: add created_at, fix updated_by type INTEGER->VARCHAR

Revision ID: f1g2h3i4j5k6
Revises: e1f2g3h4i5j6
Create Date: 2026-03-15

Uses SAVEPOINTS around each DDL statement so that if a statement fails
(e.g. column already exists), the PostgreSQL transaction is NOT aborted.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1g2h3i4j5k6'
down_revision = 'e1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Add created_at if missing - SAVEPOINT prevents transaction abort on failure
    conn.execute(sa.text("SAVEPOINT sp_created_at"))
    try:
        conn.execute(sa.text(
            "ALTER TABLE system_config ADD COLUMN created_at TIMESTAMP DEFAULT NOW()"
        ))
        conn.execute(sa.text("RELEASE SAVEPOINT sp_created_at"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp_created_at"))

    # Fix updated_by type INTEGER -> VARCHAR(100) - SAVEPOINT prevents abort
    conn.execute(sa.text("SAVEPOINT sp_updated_by"))
    try:
        conn.execute(sa.text(
            "ALTER TABLE system_config "
            "ALTER COLUMN updated_by TYPE VARCHAR(100) "
            "USING COALESCE(updated_by::TEXT, NULL)"
        ))
        conn.execute(sa.text("RELEASE SAVEPOINT sp_updated_by"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp_updated_by"))


def downgrade():
    pass
