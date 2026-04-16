"""Fix system_config: ensure created_at exists and updated_by is VARCHAR

Revision ID: g2h3i4j5k6l7
Revises: f1g2h3i4j5k6
Create Date: 2026-03-15

This migration ensures the system_config table has the correct schema:
- created_at column exists (add if missing)
- updated_at column exists (add if missing)  
- updated_by is VARCHAR not INTEGER (alter if needed)
- is_secret column exists (add if missing)

All operations use SAVEPOINTs to avoid transaction abort on already-applied changes.
"""
from alembic import op
import sqlalchemy as sa

revision = 'g2h3i4j5k6l7'
down_revision = 'f1g2h3i4j5k6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Add created_at if missing
    conn.execute(sa.text("SAVEPOINT sp1"))
    try:
        conn.execute(sa.text("ALTER TABLE system_config ADD COLUMN created_at TIMESTAMP DEFAULT NOW()"))
        conn.execute(sa.text("RELEASE SAVEPOINT sp1"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp1"))

    # Add updated_at if missing
    conn.execute(sa.text("SAVEPOINT sp2"))
    try:
        conn.execute(sa.text("ALTER TABLE system_config ADD COLUMN updated_at TIMESTAMP DEFAULT NOW()"))
        conn.execute(sa.text("RELEASE SAVEPOINT sp2"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp2"))

    # Add is_secret if missing
    conn.execute(sa.text("SAVEPOINT sp3"))
    try:
        conn.execute(sa.text("ALTER TABLE system_config ADD COLUMN is_secret BOOLEAN DEFAULT TRUE"))
        conn.execute(sa.text("RELEASE SAVEPOINT sp3"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp3"))

    # Convert updated_by from INTEGER to VARCHAR if needed
    conn.execute(sa.text("SAVEPOINT sp4"))
    try:
        conn.execute(sa.text(
            "ALTER TABLE system_config "
            "ALTER COLUMN updated_by TYPE VARCHAR(255) "
            "USING COALESCE(updated_by::TEXT, NULL)"
        ))
        conn.execute(sa.text("RELEASE SAVEPOINT sp4"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp4"))

    # Add updated_by if missing entirely
    conn.execute(sa.text("SAVEPOINT sp5"))
    try:
        conn.execute(sa.text("ALTER TABLE system_config ADD COLUMN updated_by VARCHAR(255)"))
        conn.execute(sa.text("RELEASE SAVEPOINT sp5"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT sp5"))


def downgrade():
    pass
