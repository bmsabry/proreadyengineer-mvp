"""Make rfqs.is_closed a GENERATED column (derived from rfq_status)

is_closed was a writable boolean that repeatedly drifted from rfq_status. It is now a
database GENERATED column = (rfq_status IN <closed statuses>), with NO writable path.

Revision ID: c3f8e1a90b21
Revises: v8w9x0y1z2a3
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3f8e1a90b21'
down_revision = 'v8w9x0y1z2a3'
branch_labels = None
depends_on = None

_EXPR = ("rfq_status IN ('quote_limit_reached','customer_selected_provider',"
         "'closed_no_selection','cancelled')")


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite/test DBs build the generated column via create_all
    # Postgres cannot convert a column to GENERATED in place: drop + re-add.
    op.drop_column("rfqs", "is_closed")
    op.execute(
        f"ALTER TABLE rfqs ADD COLUMN is_closed BOOLEAN "
        f"GENERATED ALWAYS AS ({_EXPR}) STORED"
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_column("rfqs", "is_closed")
    op.add_column(
        "rfqs",
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
