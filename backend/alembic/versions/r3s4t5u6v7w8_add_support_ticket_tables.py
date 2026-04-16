"""add support ticket tables

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-04-06 05:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'r3s4t5u6v7w8'
down_revision = 'q2r3s4t5u6v7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # support_tickets
    # -----------------------------------------------------------------------
    op.create_table(
        'support_tickets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('submitter_email', sa.Text(), nullable=False),
        sa.Column('submitter_name', sa.Text(), nullable=True),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('category', sa.String(64), nullable=True, server_default='general'),
        sa.Column('priority', sa.Integer(), nullable=True, server_default='5'),
        sa.Column('status', sa.String(64), nullable=False, server_default='new'),
        sa.Column('email_message_id', sa.Text(), nullable=True),
        sa.Column('inbound_in_reply_to', sa.Text(), nullable=True),
        sa.Column('source', sa.String(64), nullable=False, server_default='contact_form'),
        sa.Column('assigned_to_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('llm_session', postgresql.JSON(), nullable=True),
        sa.Column('llm_attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_spam', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('first_responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_customer_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_support_tickets_user_id', 'support_tickets', ['user_id'])
    op.create_index('ix_support_tickets_submitter_email', 'support_tickets', ['submitter_email'])
    op.create_index('ix_support_tickets_status', 'support_tickets', ['status'])
    op.create_index('ix_support_tickets_priority', 'support_tickets', ['priority'])
    op.create_index('ix_support_tickets_email_message_id', 'support_tickets', ['email_message_id'])
    op.create_index('ix_support_tickets_assigned_to_user_id', 'support_tickets', ['assigned_to_user_id'])

    # -----------------------------------------------------------------------
    # support_ticket_messages
    # -----------------------------------------------------------------------
    op.create_table(
        'support_ticket_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ticket_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sender_type', sa.String(32), nullable=False),
        sa.Column('sender_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sender_name', sa.Text(), nullable=True),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('email_message_id', sa.Text(), nullable=True),
        sa.Column('direction', sa.String(16), nullable=False, server_default='form'),
        sa.Column('email_delivered', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_support_ticket_messages_ticket_id', 'support_ticket_messages', ['ticket_id'])

    # -----------------------------------------------------------------------
    # support_ticket_events
    # -----------------------------------------------------------------------
    op.create_table(
        'support_ticket_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ticket_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('support_tickets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('payload', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_support_ticket_events_ticket_id', 'support_ticket_events', ['ticket_id'])


def downgrade() -> None:
    op.drop_table('support_ticket_events')
    op.drop_table('support_ticket_messages')
    op.drop_table('support_tickets')
