"""Add advertisement workflow fields: page_type, LLM content, tracking, review.

Revision ID: t6u7v8w9x0y1
Revises: q2r3s4t5u6v7
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 't6u7v8w9x0y1'
down_revision = 'q2r3s4t5u6v7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New columns on advertisements table
    op.add_column('advertisements', sa.Column('page_type', sa.Text(), nullable=True))
    op.add_column('advertisements', sa.Column('llm_extracted_content', sa.JSON(), nullable=True))
    op.add_column('advertisements', sa.Column('source_website_url', sa.Text(), nullable=True))
    op.add_column('advertisements', sa.Column('uploaded_materials_s3_keys', sa.JSON(), nullable=True))
    op.add_column('advertisements', sa.Column('click_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('advertisements', sa.Column('impression_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('advertisements', sa.Column('admin_review_notes', sa.Text(), nullable=True))
    op.add_column('advertisements', sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('advertisements', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('advertisements', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column('advertisements', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column('advertisements', 'updated_at')
    op.drop_column('advertisements', 'created_at')
    op.drop_column('advertisements', 'reviewed_at')
    op.drop_column('advertisements', 'reviewed_by_user_id')
    op.drop_column('advertisements', 'admin_review_notes')
    op.drop_column('advertisements', 'impression_count')
    op.drop_column('advertisements', 'click_count')
    op.drop_column('advertisements', 'uploaded_materials_s3_keys')
    op.drop_column('advertisements', 'source_website_url')
    op.drop_column('advertisements', 'llm_extracted_content')
    op.drop_column('advertisements', 'page_type')
