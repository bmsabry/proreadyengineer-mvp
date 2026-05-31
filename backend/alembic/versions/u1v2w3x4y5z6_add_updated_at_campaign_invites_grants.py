"""add updated_at to provider_campaign_invites and founding_access_grants

These two tables were created without an updated_at column, but every model
inherits updated_at from Base, so the ORM INSERT lists updated_at and Postgres
raises UndefinedColumnError. (SQLite tests use create_all from the models, which
always include updated_at, so the drift never surfaced in CI.)

Revision ID: u1v2w3x4y5z6
Revises: c9f2a7e54b33
"""
from alembic import op
import sqlalchemy as sa


revision = "u1v2w3x4y5z6"
down_revision = "c9f2a7e54b33"
branch_labels = None
depends_on = None


def _has_column(bind, table, column):
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    for table in ("provider_campaign_invites", "founding_access_grants"):
        if not _has_column(bind, table, "updated_at"):
            op.add_column(
                table,
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("NOW()"),
                ),
            )


def downgrade():
    bind = op.get_bind()
    for table in ("founding_access_grants", "provider_campaign_invites"):
        if _has_column(bind, table, "updated_at"):
            op.drop_column(table, "updated_at")
