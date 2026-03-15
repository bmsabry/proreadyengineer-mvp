"""Fix system_config: add created_at, fix updated_by type INTEGER->VARCHAR

Revision ID: f1g2h3i4j5k6
Revises: e1f2g3h4i5j6
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'f1g2h3i4j5k6'
down_revision = 'e1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Add created_at column if missing
    try:
        op.add_column('system_config',
            sa.Column('created_at', sa.DateTime(), nullable=True,
                      server_default=sa.text('NOW()')),
        )
    except Exception:
        pass  # Column already exists

    # Fix updated_by column type from INTEGER to VARCHAR(100)
    # Use raw SQL to handle type casting safely
    try:
        conn.execute(sa.text(
            "ALTER TABLE system_config "
            "ALTER COLUMN updated_by TYPE VARCHAR(100) "
            "USING COALESCE(updated_by::TEXT, NULL)"
        ))
    except Exception:
        pass  # Column already correct type or doesn't exist


def downgrade():
    pass
