"""User authentication and session models."""

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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ClaimStatus, MembershipRole, MembershipStatus, PaymentPurpose, PaymentStatus, QuoteStatus, RfqStatus, SubscriptionStatus, SubscriptionType, TierEvaluationStatus, UnlockStatus

if TYPE_CHECKING:
    from app.models.provider import Provider, ProviderClaimRequest, ProviderMembership
    from app.models.rfq import RFQ, RFQDispatch, RFQFile, RFQMatch, RFQUnlock
    from app.models.quote import Quote
    from app.models.payment import PaymentAttempt, Subscription, WebhookEvent
    from app.models.admin import AuditLog, TierEvaluationRequest
    from app.models.advertising import Advertisement
    from app.models.nda import RFQNDA


class User(Base):
    """Unified user accounts with multi-role support."""
    
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    roles: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    
    # Admin permission flags
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_review_claims: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_moderate_providers: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_moderate_ads: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_manage_refunds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_override_rfq_status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    can_review_tier_requests: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    
    # Account security
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Search quota tracking
    monthly_search_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    search_count_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # NDA credit tracking (3 free NDAs/month for subscribed customers)
    monthly_nda_credits_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    nda_credits_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Provider invite: stores provider_id from invite token at registration
    linked_provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None
    )

    # Entity type for NDA: "Individual" or "Company"
    entity_type: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="Individual"
    )

    # State/province for NDA governing law clause
    state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Email verification (REQUIRE_EMAIL_VERIFICATION config toggle)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    email_verify_token_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email_verify_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )
    provider_memberships: Mapped[List["ProviderMembership"]] = relationship(
        "ProviderMembership", back_populates="user", foreign_keys="ProviderMembership.user_id"
    )
    claim_requests: Mapped[List["ProviderClaimRequest"]] = relationship(
        "ProviderClaimRequest", back_populates="claimant_user", foreign_keys="ProviderClaimRequest.claimant_user_id"
    )
    reviewed_claims: Mapped[List["ProviderClaimRequest"]] = relationship(
        "ProviderClaimRequest", back_populates="reviewed_by_user", foreign_keys="ProviderClaimRequest.reviewed_by"
    )
    rfqs: Mapped[List["RFQ"]] = relationship(
        "RFQ", back_populates="customer_user", foreign_keys="RFQ.customer_user_id"
    )
    quotes: Mapped[List["Quote"]] = relationship(
        "Quote", back_populates="submitter_user"
    )
    payment_attempts: Mapped[List["PaymentAttempt"]] = relationship(
        "PaymentAttempt", back_populates="initiated_by_user"
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="user"
    )
    advertisements: Mapped[List["Advertisement"]] = relationship(
        "Advertisement", back_populates="advertiser_user"
    )
    tier_evaluation_requests: Mapped[List["TierEvaluationRequest"]] = relationship(
        "TierEvaluationRequest", back_populates="requested_by_user", foreign_keys="TierEvaluationRequest.requested_by_user_id"
    )
    reviewed_tier_requests: Mapped[List["TierEvaluationRequest"]] = relationship(
        "TierEvaluationRequest", back_populates="reviewed_by_user", foreign_keys="TierEvaluationRequest.reviewed_by"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="actor_user"
    )
    rfq_files: Mapped[List["RFQFile"]] = relationship(
        "RFQFile", back_populates="uploaded_by_user"
    )
    rfq_unlocks: Mapped[List["RFQUnlock"]] = relationship(
        "RFQUnlock", back_populates="unlocked_by_user"
    )
    claimed_providers: Mapped[List["Provider"]] = relationship(
        "Provider", back_populates="claimed_by_user"
    )
    ndas: Mapped[List["RFQNDA"]] = relationship(
        "RFQNDA", back_populates="customer_user"
    )


class RefreshToken(Base):
    """Server-side refresh token storage with rotation support."""
    
    __tablename__ = "refresh_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_token_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refresh_tokens.id"), nullable=True
    )
    created_ip: Mapped[Optional[str]] = mapped_column(nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
    replaced_by_token: Mapped[Optional["RefreshToken"]] = relationship(
        "RefreshToken", remote_side=[id], uselist=False
    )


class PasswordResetToken(Base):
    """Single-use password reset tokens with 1-hour expiration."""
    
    __tablename__ = "password_reset_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_ip: Mapped[Optional[str]] = mapped_column(nullable=True)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_reset_tokens")
