"""Add users.phone (optional contact phone collected at registration)

Revision ID: d4a7e2b91c08
Revises: c3f8e1a90b21
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4a7e2b91c08'
down_revision = 'c3f8e1a90b21'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("users")]
    if "phone" not in cols:
        op.add_column("users", sa.Column("phone", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("users")]
    if "phone" in cols:
        op.drop_column("users", "phone")
