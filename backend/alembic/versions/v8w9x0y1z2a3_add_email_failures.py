"""add email_failures table

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'v8w9x0y1z2a3'
down_revision = 'u7v8w9x0y1z2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'email_failures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('to_email', sa.String(320), nullable=False),
        sa.Column('subject', sa.String(512), nullable=True),
        sa.Column('source', sa.String(48), nullable=False),
        sa.Column('error_code', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_response', sa.Text(), nullable=True),
        sa.Column('resend_email_id', sa.String(128), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_email_failures_to_email', 'email_failures', ['to_email'])
    op.create_index('ix_email_failures_source', 'email_failures', ['source'])
    op.create_index('ix_email_failures_resend_email_id', 'email_failures', ['resend_email_id'])
    op.create_index('ix_email_failures_resolved', 'email_failures', ['resolved'])
    op.create_index('ix_email_failures_resolved_created_at', 'email_failures',
                    ['resolved', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_email_failures_resolved_created_at', table_name='email_failures')
    op.drop_index('ix_email_failures_resolved', table_name='email_failures')
    op.drop_index('ix_email_failures_resend_email_id', table_name='email_failures')
    op.drop_index('ix_email_failures_source', table_name='email_failures')
    op.drop_index('ix_email_failures_to_email', table_name='email_failures')
    op.drop_table('email_failures')
