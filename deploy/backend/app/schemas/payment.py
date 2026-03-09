"""Payment and subscription request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# Payment enums as Literals
PaymentPurpose = Literal[
    "search_subscription", "nda_fee", "rfq_unlock",
    "provider_profile_subscription", "advertisement_subscription"
]
PaymentStatus = Literal["pending", "processing", "confirmed", "failed", "refunded", "disputed"]
SubscriptionType = Literal["search_tier_1", "search_tier_2", "provider_profile", "advertisement"]
SubscriptionStatus = Literal["active", "past_due", "cancelled", "expired", "incomplete"]
WebhookProcessingStatus = Literal["pending", "processing", "completed", "failed", "retrying"]


# === Payment Attempts ===

class PaymentCreateRequest(BaseSchema):
    """Create payment attempt."""
    purpose: PaymentPurpose
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(default="USD", max_length=3)
    related_entity_type: Optional[str] = None  # rfq, subscription, etc.
    related_entity_id: Optional[UUID] = None
    metadata: Optional[dict[str, Any]] = None


class PaymentResponse(ResponseSchema):
    """Payment attempt response."""
    id: UUID
    provider_name: str  # stripe, paypal, braintree
    external_payment_id: Optional[str]
    external_checkout_id: Optional[str]
    purpose: PaymentPurpose
    related_entity_type: Optional[str]
    related_entity_id: Optional[UUID]
    amount: Decimal
    currency: str
    payment_status: PaymentStatus
    idempotency_key: Optional[str]
    initiated_at: datetime
    confirmed_at: Optional[datetime]
    failed_at: Optional[datetime]
    failure_reason: Optional[str]
    metadata: Optional[dict[str, Any]]


class PaymentCheckoutResponse(BaseSchema):
    """Payment checkout session response."""
    payment_id: UUID
    checkout_url: str
    amount: Decimal
    currency: str
    expires_at: Optional[datetime]


class BillingPortalResponse(BaseSchema):
    """Stripe billing portal response."""
    portal_url: str


# === Subscriptions ===

class SubscriptionCreateRequest(BaseSchema):
    """Create subscription request."""
    subscription_type: SubscriptionType
    provider_id: Optional[int] = None  # For provider profile subscription
    advertisement_id: Optional[UUID] = None  # For ad subscription
    payment_provider: str = Field(default="stripe", pattern="^(stripe|paypal)$")


class SubscriptionResponse(ResponseSchema):
    """Subscription response."""
    id: UUID
    user_id: Optional[UUID]
    provider_id: Optional[int]
    advertisement_id: Optional[UUID]
    provider_name: str  # stripe, paypal
    external_subscription_id: Optional[str]
    subscription_type: SubscriptionType
    subscription_status: SubscriptionStatus
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at: Optional[datetime]
    cancelled_at: Optional[datetime]


class SubscriptionListResponse(BaseSchema):
    """User's subscriptions list."""
    subscriptions: list[SubscriptionResponse]
    active_count: int


# === Webhook Events ===

class WebhookEventResponse(ResponseSchema):
    """Webhook event response."""
    id: UUID
    provider_name: str  # stripe, paypal, signrequest
    external_event_id: str
    event_type: str
    payload: dict[str, Any]
    signature_verified: bool
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processed_at: Optional[datetime]
    error_message: Optional[str]
    retry_count: int


class WebhookReplayRequest(BaseSchema):
    """Replay failed webhook request."""
    pass  # Action only


class WebhookReplayResponse(BaseSchema):
    """Webhook replay response."""
    success: bool
    message: str
    event_id: UUID
    new_status: WebhookProcessingStatus



# === Payment Intent Response ===

class PaymentIntentResponse(BaseSchema):
    """Payment intent creation response."""
    client_secret: str
    payment_intent_id: str
    amount: Decimal
    currency: str
    status: str


# Aliases for compatibility
StripeCheckoutResponse = PaymentIntentResponse  # If used elsewhere



# === Payment Attempt Response ===

class PaymentAttemptResponse(ResponseSchema):
    """Payment attempt details response."""
    id: UUID
    provider_name: str
    purpose: str
    amount: Decimal
    currency: str
    payment_status: str
    related_entity_type: Optional[str]
    related_entity_id: Optional[str]
    initiated_at: datetime
    confirmed_at: Optional[datetime]


# === Webhook Event Response ===

class WebhookEventResponse(ResponseSchema):
    """Webhook event details for admin."""
    id: UUID
    provider_name: str
    event_type: str
    external_event_id: str
    signature_verified: bool
    processing_status: str
    received_at: datetime
    processed_at: Optional[datetime]
    error_message: Optional[str]


class WebhookReplayRequest(BaseSchema):
    """Request to replay a webhook event."""
    reason: str = Field(..., min_length=5, max_length=500)
