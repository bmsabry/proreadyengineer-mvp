"""Provider campaign models for mass email invite system."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CampaignStatus, InviteStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider


class ProviderCampaign(Base):
    """Mass email campaign targeting unregistered providers in the directory.

    Tracks all campaign configuration, batch-send progress, and aggregate
    analytics for the Provider Campaign Command Room.
    """

    __tablename__ = "provider_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        String, nullable=False, default=CampaignStatus.DRAFT, server_default="draft"
    )
    email_subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Founding-access offer configuration
    founding_slots_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=250, server_default="250"
    )
    founding_slots_claimed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    founding_duration_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )

    # Batch send configuration
    batch_size_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=150, server_default="150"
    )

    # Targeting mode: 'all' = all eligible providers, 'selected' = hand-picked list
    target_mode: Mapped[str] = mapped_column(
        String, nullable=False, default="all", server_default="all"
    )


    # Aggregate counters
    total_providers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_sent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_bounced: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_opened: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_clicked: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_registered: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Lifecycle timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Ownership
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    invites: Mapped[List["ProviderCampaignInvite"]] = relationship(
        "ProviderCampaignInvite", back_populates="campaign", lazy="dynamic"
    )


class ProviderCampaignInvite(Base):
    """Individual invite record linking a campaign to a specific provider.

    One row per provider per campaign. Tracks per-invite status, tracking
    events, Resend message ID, and the unique pre-filled registration token.
    """

    __tablename__ = "provider_campaign_invites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_campaigns.id"), nullable=False, index=True
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False, index=True
    )
    invite_token: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, index=True
    )
    status: Mapped[InviteStatus] = mapped_column(
        String, nullable=False, default=InviteStatus.PENDING, server_default="pending"
    )

    # Tracking timestamps
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clicked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Email provider tracking
    resend_message_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    campaign: Mapped["ProviderCampaign"] = relationship(
        "ProviderCampaign", back_populates="invites"
    )
    provider: Mapped["Provider"] = relationship("Provider")


class FoundingAccessGrant(Base):
    """Founding-member RFQ access grant for early-registered providers.

    Grants free RFQ unlock access (no profile editing) for a limited period.
    The grant is checked BEFORE the payment gate in the RFQ unlock flow.
    """

    __tablename__ = "founding_access_grants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_campaigns.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    provider: Mapped["Provider"] = relationship("Provider")
    user: Mapped["User"] = relationship("User")
    campaign: Mapped["ProviderCampaign"] = relationship("ProviderCampaign")
