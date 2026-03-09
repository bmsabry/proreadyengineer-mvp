"""Payment processing and subscription management models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    JSON)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import PaymentPurpose, PaymentStatus, SubscriptionStatus, SubscriptionType, WebhookProcessingStatus

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.advertising import Advertisement


class PaymentAttempt(Base):
    """Payment attempt records with idempotency support.
    
    Tracks all payment initiations and their fulfillment status.
    """
    
    __tablename__ = "payment_attempts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_name: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # stripe, paypal, braintree
    external_payment_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_checkout_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    purpose: Mapped[PaymentPurpose] = mapped_column(String, nullable=False)
    related_entity_type: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # rfq, subscription, etc.
    related_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="USD", server_default="USD"
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        String, nullable=False, default=PaymentStatus.INITIATED
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        Text, unique=True, nullable=True
    )
    initiated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    
    # Relationships
    initiated_by_user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="payment_attempts"
    )


class Subscription(Base):
    """Subscription records for search tiers, provider profiles, and ads."""
    
    __tablename__ = "subscriptions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    provider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("providers.id"), nullable=True
    )
    advertisement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advertisements.id"), nullable=True
    )
    provider_name: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # stripe, paypal
    external_subscription_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    subscription_type: Mapped[SubscriptionType] = mapped_column(
        String, nullable=False
    )
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        String, nullable=False, default=SubscriptionStatus.ACTIVE
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="subscriptions"
    )
    provider: Mapped[Optional["Provider"]] = relationship(
        "Provider", back_populates="subscriptions"
    )
    advertisement: Mapped[Optional["Advertisement"]] = relationship(
        "Advertisement", back_populates="subscription"
    )


class WebhookEvent(Base):
    """Webhook event storage with processing status tracking.
    
    Stores raw events from Stripe, PayPal, and SignRequest for audit and replay.
    """
    
    __tablename__ = "webhook_events"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_name: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # stripe, paypal, signrequest
    external_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    processing_status: Mapped[WebhookProcessingStatus] = mapped_column(
        String, nullable=False, default=WebhookProcessingStatus.RECEIVED
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    
    # Note: Unique constraint on (provider_name, external_event_id) enforced at DB level
