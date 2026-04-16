"""Add provider campaign, invites, and founding access grant tables.

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-04-05 02:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'n9o0p1q2r3s4'
down_revision = 'm8n9o0p1q2r3'
branch_labels = None
depends_on = None


def upgrade():
    # --- provider_campaigns ---
    op.create_table(
        'provider_campaigns',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('email_subject', sa.Text(), nullable=False, server_default=''),
        sa.Column('email_body_html', sa.Text(), nullable=False, server_default=''),
        sa.Column('founding_slots_total', sa.Integer(), nullable=False, server_default='250'),
        sa.Column('founding_slots_claimed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('founding_duration_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('batch_size_per_day', sa.Integer(), nullable=False, server_default='150'),
        sa.Column('total_providers', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_bounced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_opened', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_clicked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_registered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # --- provider_campaign_invites ---
    op.create_table(
        'provider_campaign_invites',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', UUID(as_uuid=True), sa.ForeignKey('provider_campaigns.id'), nullable=False),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('providers.id'), nullable=False),
        sa.Column('invite_token', sa.Text(), nullable=False, unique=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resend_message_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_provider_campaign_invites_campaign_id', 'provider_campaign_invites', ['campaign_id'])
    op.create_index('ix_provider_campaign_invites_provider_id', 'provider_campaign_invites', ['provider_id'])
    op.create_index('ix_provider_campaign_invites_invite_token', 'provider_campaign_invites', ['invite_token'], unique=True)
    op.create_index('ix_provider_campaign_invites_status', 'provider_campaign_invites', ['status'])

    # --- founding_access_grants ---
    op.create_table(
        'founding_access_grants',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('providers.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('campaign_id', UUID(as_uuid=True), sa.ForeignKey('provider_campaigns.id'), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_founding_access_grants_provider_id', 'founding_access_grants', ['provider_id'])
    op.create_index('ix_founding_access_grants_user_id', 'founding_access_grants', ['user_id'])
    op.create_index('ix_founding_access_grants_is_active', 'founding_access_grants', ['is_active'])


def downgrade():
    op.drop_table('founding_access_grants')
    op.drop_table('provider_campaign_invites')
    op.drop_table('provider_campaigns')
