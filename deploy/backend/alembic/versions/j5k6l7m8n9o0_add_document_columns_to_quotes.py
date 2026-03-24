"""add document columns to quotes

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'j5k6l7m8n9o0'
down_revision = 'i4j5k6l7m8n9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('quotes', sa.Column('document_s3_key', sa.Text(), nullable=True))
    op.add_column('quotes', sa.Column('document_filename', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('quotes', 'document_filename')
    op.drop_column('quotes', 'document_s3_key')
