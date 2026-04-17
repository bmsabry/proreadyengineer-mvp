"""add help_chat_logs table

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-04-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'u7v8w9x0y1z2'
down_revision = '92a49adae23c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'help_chat_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_role', sa.String(32), nullable=True),
        sa.Column('user_email', sa.String(255), nullable=True),
        sa.Column('user_message', sa.Text(), nullable=False, server_default=''),
        sa.Column('assistant_reply', sa.Text(), nullable=False, server_default=''),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('model', sa.String(128), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index(
        'ix_help_chat_logs_user_id_created_at',
        'help_chat_logs',
        ['user_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_help_chat_logs_user_id_created_at', table_name='help_chat_logs')
    op.drop_table('help_chat_logs')
