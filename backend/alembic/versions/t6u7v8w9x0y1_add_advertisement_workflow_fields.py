"""Add advertisement workflow fields: page_type, LLM content, tracking, review.

Revision ID: t6u7v8w9x0y1
Revises: q2r3s4t5u6v7
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect as sa_inspect

# revision identifiers
revision = 't6u7v8w9x0y1'
down_revision = 'q2r3s4t5u6v7'
branch_labels = None
depends_on = None


def _get_existing_columns(table_name: str) -> set:
    """Return set of column names that already exist on the table."""
    conn = op.get_bind()
    inspector = sa_inspect(conn)
    return {c['name'] for c in inspector.get_columns(table_name)}


def _add_column_if_not_exists(table_name: str, column: sa.Column, existing: set):
    if column.name not in existing:
        op.add_column(table_name, column)


def upgrade() -> None:
    existing = _get_existing_columns('advertisements')

    # New columns on advertisements table
    _add_column_if_not_exists('advertisements', sa.Column('page_type', sa.Text(), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('llm_extracted_content', sa.JSON(), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('source_website_url', sa.Text(), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('uploaded_materials_s3_keys', sa.JSON(), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('click_count', sa.Integer(), server_default='0', nullable=False), existing)
    _add_column_if_not_exists('advertisements', sa.Column('impression_count', sa.Integer(), server_default='0', nullable=False), existing)
    _add_column_if_not_exists('advertisements', sa.Column('admin_review_notes', sa.Text(), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True), existing)
    _add_column_if_not_exists('advertisements', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), existing)
    _add_column_if_not_exists('advertisements', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), existing)


def downgrade() -> None:
    # Only drop columns that this migration would have added (not pre-existing ones like created_at/updated_at)
    existing = _get_existing_columns('advertisements')
    new_cols = [
        'reviewed_at', 'reviewed_by_user_id', 'admin_review_notes',
        'impression_count', 'click_count', 'uploaded_materials_s3_keys',
        'source_website_url', 'llm_extracted_content', 'page_type',
    ]
    for col in new_cols:
        if col in existing:
            op.drop_column('advertisements', col)
