
"""add rfqmatch dispatched fields

Revision ID: d2e3f4g5h6i7
Revises: c1d2e3f4g5h6
Create Date: 2026-03-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd2e3f4g5h6i7'
down_revision = 'c1d2e3f4g5h6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    rfq_match_cols = {c["name"] for c in inspector.get_columns("rfq_matches")}
    if "is_dispatched" not in rfq_match_cols:
        op.add_column(
            "rfq_matches",
            sa.Column("is_dispatched", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "dispatched_at" not in rfq_match_cols:
        op.add_column(
            "rfq_matches",
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        )

    dispatch_cols = {c["name"] for c in inspector.get_columns("rfq_provider_dispatches")}
    if "batch_id" not in dispatch_cols:
        op.add_column(
            "rfq_provider_dispatches",
            sa.Column(
                "batch_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("rfq_dispatch_batches.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    rfq_match_cols = {c["name"] for c in inspector.get_columns("rfq_matches")}
    if "dispatched_at" in rfq_match_cols:
        op.drop_column("rfq_matches", "dispatched_at")
    if "is_dispatched" in rfq_match_cols:
        op.drop_column("rfq_matches", "is_dispatched")
