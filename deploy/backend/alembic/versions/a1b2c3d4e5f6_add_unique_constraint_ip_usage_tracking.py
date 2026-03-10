"""Add unique constraint to ip_usage_tracking

Revision ID: a1b2c3d4e5f6
Revises: 66ab93e4c8e1
Create Date: 2026-03-09 23:18:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '66ab93e4c8e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove duplicate rows before adding constraint.
    # Keep the row with the highest search_count for each (ip_address, usage_month) pair.
    op.execute("""
        DELETE FROM ip_usage_tracking
        WHERE id NOT IN (
            SELECT DISTINCT ON (ip_address, usage_month) id
            FROM ip_usage_tracking
            ORDER BY ip_address, usage_month, search_count DESC, created_at ASC
        )
    """)

    # Add unique constraint on (ip_address, usage_month)
    op.create_unique_constraint(
        'uq_ip_usage_tracking_ip_month',
        'ip_usage_tracking',
        ['ip_address', 'usage_month']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_ip_usage_tracking_ip_month',
        'ip_usage_tracking',
        type_='unique'
    )
