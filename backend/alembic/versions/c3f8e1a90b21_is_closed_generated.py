"""Make rfqs.is_closed a GENERATED column (derived from rfq_status)

is_closed was a writable boolean that repeatedly drifted from rfq_status (ORM validator,
Core update(), raw SQL all wrote it independently). It is now a database GENERATED column =
(rfq_status IN <closed statuses>), so it has NO writable path and can never drift.

Revision ID: c3f8e1a90b21
Revises: b1f3d9a2c7e4
Revision date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3f8e1a90b21'
down_revision = 'b1f3d9a2c7e4'
branch_labels = None
depends_on = None

_EXPR = ("rfq_status IN ('quote_limit_reached','customer_selected_provider',"
         "'closed_no_selection','cancelled')")


def upgrade():
    bind = op.get_bind()
    # Postgres can't convert an existing column to GENERATED in place: drop + re-add.
    if bind.dialect.name == "postgresql":
        op.drop_column("rfqs", "is_closed")
        op.execute(
            f"ALTER TABLE rfqs ADD COLUMN is_closed BOOLEAN "
            f"GENERATED ALWAYS AS ({_EXPR}) STORED"
        )
    else:
        # SQLite (tests): rebuild is awkward; create_all already makes the generated
        # column for fresh DBs, so this branch is a no-op safeguard.
        pass


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_column("rfqs", "is_closed")
        op.add_column(
            "rfqs",
            sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
