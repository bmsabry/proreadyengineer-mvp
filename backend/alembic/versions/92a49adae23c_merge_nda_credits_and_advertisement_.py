"""merge nda_credits and advertisement_workflow branches

Revision ID: 92a49adae23c
Revises: s5t6u7v8w9x0, t6u7v8w9x0y1
Create Date: 2026-04-16 01:58:39.147677

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = '92a49adae23c'
down_revision = ('s5t6u7v8w9x0', 't6u7v8w9x0y1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
