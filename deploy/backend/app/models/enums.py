"""Enumeration types for ProReadyEngineer MVP."""

from enum import Enum as PyEnum


class RfqStatus(str, PyEnum):
    """RFQ lifecycle status values."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    AWAITING_NDA_PAYMENT = "awaiting_nda_payment"
    AWAITING_CUSTOMER_SIGNATURE = "awaiting_customer_signature"
    OPEN_FOR_DISPATCH = "open_for_dispatch"
    DISPATCHING = "dispatching"
    OPEN_FOR_UNLOCK = "open_for_unlock"
    QUOTE_LIMIT_REACHED = "quote_limit_reached"
    CUSTOMER_SELECTED_PROVIDER = "customer_selected_provider"
    CLOSED_NO_SELECTION = "closed_no_selection"
    CANCELLED = "cancelled"


class QuoteStatus(str, PyEnum):
    """Quote lifecycle status values."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"
    CUSTOMER_VIEWED = "customer_viewed"
    SHORTLISTED = "shortlisted"
    ACCEPTED = "accepted"
    NOT_SELECTED = "not_selected"
    EXPIRED = "expired"


class NdaStatus(str, PyEnum):
    """NDA signing status values."""
    NOT_REQUIRED = "not_required"
    PAYMENT_PENDING = "payment_pending"
    CUSTOMER_SIGNATURE_PENDING = "customer_signature_pending"
    PROVIDER_SIGNATURE_PENDING = "provider_signature_pending"
    FULLY_SIGNED = "fully_signed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClaimStatus(str, PyEnum):
    """Provider claim request status values."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MembershipRole(str, PyEnum):
    """Provider membership roles."""
    OWNER = "owner"
    EDITOR = "editor"
    BILLING_MANAGER = "billing_manager"
    VIEWER = "viewer"


class MembershipStatus(str, PyEnum):
    """Provider membership status values."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class DispatchStatus(str, PyEnum):
    """RFQ dispatch status values."""
    PENDING = "pending"
    SENT = "sent"
    BOUNCED = "bounced"
    OPENED = "opened"


class UnlockStatus(str, PyEnum):
    """RFQ unlock status values."""
    PAYMENT_PENDING = "payment_pending"
    UNLOCKED = "unlocked"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class PaymentStatus(str, PyEnum):
    """Payment attempt status values."""
    INITIATED = "initiated"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class SubscriptionType(str, PyEnum):
    """Subscription type values."""
    SEARCH_TIER_1 = "search_tier_1"
    SEARCH_TIER_2 = "search_tier_2"
    PROVIDER_PROFILE = "provider_profile"
    ADVERTISEMENT = "advertisement"


class SubscriptionStatus(str, PyEnum):
    """Subscription status values."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    TRIALING = "trialing"


class PaymentPurpose(str, PyEnum):
    """Payment purpose values."""
    SEARCH_SUBSCRIPTION = "search_subscription"
    NDA_FEE = "nda_fee"
    RFQ_UNLOCK = "rfq_unlock"
    PROVIDER_PROFILE_SUBSCRIPTION = "provider_profile_subscription"
    ADVERTISEMENT_SUBSCRIPTION = "advertisement_subscription"


class AdStatus(str, PyEnum):
    """Advertisement status values."""
    EMPTY = "empty"
    RESERVED_CHECKOUT_PENDING = "reserved_checkout_pending"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class WebhookProcessingStatus(str, PyEnum):
    """Webhook event processing status values."""
    RECEIVED = "received"
    VERIFIED = "verified"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class TierEvaluationStatus(str, PyEnum):
    """Tier evaluation request status values."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# Role constants for users.roles array
class UserRole:
    """User role constants for roles TEXT[] field."""
    CUSTOMER = "customer"
    PROVIDER = "provider"
    ADVERTISER = "advertiser"
    ADMIN = "admin"
