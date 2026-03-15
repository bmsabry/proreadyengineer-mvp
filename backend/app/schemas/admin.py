"""Admin moderation and backoffice request and response schemas."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, PaginationParams, PaginatedResponse, ResponseSchema


# Admin enums as Literals
RfqStatus = Literal[
    "draft", "submitted", "awaiting_nda_payment", "awaiting_customer_signature",
    "open_for_dispatch", "dispatching", "open_for_unlock", "quote_limit_reached",
    "customer_selected_provider", "closed_no_selection", "cancelled"
]
ClaimStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
TierEvaluationStatus = Literal["pending", "approved", "rejected", "cancelled"]


# === Admin RFQ Management ===

class AdminRFQListParams(PaginationParams):
    """Query parameters for admin RFQ list."""
    status: Optional[RfqStatus] = None
    customer_email: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    is_closed: Optional[bool] = None


class AdminRFQListItem(BaseSchema):
    """RFQ list item for admin."""
    id: UUID
    customer_email: str
    customer_user_id: Optional[UUID]
    business_name: Optional[str]
    rfq_status: RfqStatus
    quote_count: int
    is_closed: bool
    nda_required: bool
    created_at: datetime
    submitted_at: Optional[datetime]


class AdminRFQListResponse(PaginatedResponse):
    """Paginated RFQ list for admin."""
    items: list[AdminRFQListItem]


class AdminRFQDetailResponse(BaseSchema):
    """Full RFQ details for admin."""
    id: UUID
    customer_user_id: Optional[UUID]
    customer_email: str
    business_name: Optional[str]
    contact_name: Optional[str]
    project_description: str
    urgency: Optional[str]
    tollgate_phases: Optional[list[str]]
    nda_required: bool
    rfq_status: RfqStatus
    quote_count: int
    is_closed: bool
    selected_provider_id: Optional[int]
    has_documents: bool
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime]
    closed_at: Optional[datetime]


class AdminRFQStatusOverrideRequest(BaseSchema):
    """Override RFQ status (admin only)."""
    new_status: RfqStatus
    reason: str = Field(..., min_length=5, max_length=1000)


class AdminRFQStatusOverrideResponse(BaseSchema):
    """RFQ status override response."""
    rfq_id: UUID
    previous_status: RfqStatus
    new_status: RfqStatus
    overridden_by: UUID
    reason: str
    overridden_at: datetime


# === Admin Provider Claims ===

class AdminProviderClaimListParams(PaginationParams):
    """Query parameters for admin claim list."""
    status: Optional[ClaimStatus] = None
    provider_id: Optional[int] = None


class AdminProviderClaimListItem(ResponseSchema):
    """Provider claim list item for admin."""
    id: UUID
    provider_id: int
    provider_name: str
    claimant_user_id: UUID
    claimant_email: str
    status: ClaimStatus
    proof_type: Optional[str]
    submitted_notes: Optional[str]
    reviewed_at: Optional[datetime]


class AdminProviderClaimListResponse(PaginatedResponse):
    """Paginated claim list for admin."""
    items: list[AdminProviderClaimListItem]


class AdminProviderClaimDetailResponse(ResponseSchema):
    """Full claim request details for admin review."""
    id: UUID
    provider_id: int
    provider_name: str
    claimant_user_id: UUID
    claimant_email: str
    claimant_name: Optional[str]
    status: ClaimStatus
    proof_type: Optional[str]
    proof_payload: Optional[dict[str, Any]]
    submitted_notes: Optional[str]
    admin_review_notes: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]


class AdminProviderClaimApproveRequest(BaseSchema):
    """Approve provider claim request."""
    membership_role: str = "owner"  # owner, editor, etc.
    admin_notes: Optional[str] = Field(None, max_length=1000)


class AdminProviderClaimApproveResponse(BaseSchema):
    """Approve claim response."""
    claim_id: UUID
    provider_id: int
    claimant_user_id: UUID
    new_membership_id: UUID
    approved_at: datetime


class AdminProviderClaimRejectRequest(BaseSchema):
    """Reject provider claim request."""
    reason: str = Field(..., min_length=5, max_length=1000)


class AdminProviderClaimRejectResponse(BaseSchema):
    """Reject claim response."""
    claim_id: UUID
    provider_id: int
    claimant_user_id: UUID
    rejected_at: datetime
    reason: str


# === Admin Tier Evaluation Requests ===

class AdminTierRequestListParams(PaginationParams):
    """Query parameters for admin tier request list."""
    status: Optional[TierEvaluationStatus] = None
    provider_id: Optional[int] = None


class AdminTierRequestListItem(ResponseSchema):
    """Tier evaluation request list item."""
    id: UUID
    provider_id: int
    provider_name: str
    requested_by_user_id: UUID
    requested_by_email: str
    current_tier: Optional[str]
    status: TierEvaluationStatus
    reviewed_at: Optional[datetime]
    new_tier: Optional[str]


class AdminTierRequestListResponse(PaginatedResponse):
    """Paginated tier request list."""
    items: list[AdminTierRequestListItem]


class AdminTierRequestDetailResponse(ResponseSchema):
    """Full tier evaluation request details."""
    id: UUID
    provider_id: int
    provider_name: str
    requested_by_user_id: UUID
    requested_by_email: str
    current_tier: Optional[str]
    requested_reason: Optional[str]
    supporting_payload: Optional[dict[str, Any]]
    status: TierEvaluationStatus
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    new_tier: Optional[str]


class AdminTierRequestApproveRequest(BaseSchema):
    """Approve tier upgrade request."""
    new_tier: str = Field(..., pattern="^[A-E]$")
    review_notes: Optional[str] = Field(None, max_length=1000)


class AdminTierRequestApproveResponse(BaseSchema):
    """Approve tier request response."""
    request_id: UUID
    provider_id: int
    old_tier: Optional[str]
    new_tier: str
    approved_at: datetime


class AdminTierRequestRejectRequest(BaseSchema):
    """Reject tier upgrade request."""
    review_notes: str = Field(..., min_length=5, max_length=1000)


class AdminTierRequestRejectResponse(BaseSchema):
    """Reject tier request response."""
    request_id: UUID
    provider_id: int
    rejected_at: datetime
    reason: str


# === Admin Payments ===

class AdminPaymentListParams(PaginationParams):
    """Query parameters for admin payment list."""
    status: Optional[str] = None
    purpose: Optional[str] = None
    provider_name: Optional[str] = None  # stripe, paypal
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class AdminPaymentListItem(ResponseSchema):
    """Payment list item for admin."""
    id: UUID
    provider_name: str
    external_payment_id: Optional[str]
    purpose: str
    amount: float
    currency: str
    payment_status: str
    initiated_by_user_id: Optional[UUID]
    initiated_at: datetime
    confirmed_at: Optional[datetime]


class AdminPaymentListResponse(PaginatedResponse):
    """Paginated payment list."""
    items: list[AdminPaymentListItem]


# === Admin Webhooks ===

class AdminWebhookListParams(PaginationParams):
    """Query parameters for admin webhook list."""
    provider_name: Optional[str] = None
    event_type: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class AdminWebhookListItem(ResponseSchema):
    """Webhook event list item."""
    id: UUID
    provider_name: str
    external_event_id: str
    event_type: str
    processing_status: str
    received_at: datetime
    processed_at: Optional[datetime]
    retry_count: int


class AdminWebhookListResponse(PaginatedResponse):
    """Paginated webhook list."""
    items: list[AdminWebhookListItem]


class AdminWebhookDetailResponse(ResponseSchema):
    """Full webhook event details."""
    id: UUID
    provider_name: str
    external_event_id: str
    event_type: str
    payload: dict[str, Any]
    signature_verified: bool
    processing_status: str
    received_at: datetime
    processed_at: Optional[datetime]
    error_message: Optional[str]
    retry_count: int


class AdminWebhookReplayResponse(BaseSchema):
    """Webhook replay response."""
    webhook_id: UUID
    previous_status: str
    new_status: str
    replayed_at: datetime


# === Admin Ads ===

class AdminAdListParams(PaginationParams):
    """Query parameters for admin ad list."""
    status: Optional[str] = None
    page_type: Optional[str] = None
    advertiser_email: Optional[str] = None


class AdminAdListItem(ResponseSchema):
    """Ad list item for admin."""
    id: UUID
    ad_slot_id: Optional[UUID]
    page_type: Optional[str]
    advertiser_user_id: UUID
    advertiser_email: str
    provider_id: Optional[int]
    title: str
    ad_status: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]


class AdminAdListResponse(PaginatedResponse):
    """Paginated ad list."""
    items: list[AdminAdListItem]


class AdminAdPauseRequest(BaseSchema):
    """Pause advertisement request."""
    reason: Optional[str] = Field(None, max_length=500)


class AdminAdPauseResponse(BaseSchema):
    """Pause advertisement response."""
    ad_id: UUID
    previous_status: str
    new_status: str
    paused_at: datetime


# === Admin User Management ===

class AdminUserSuspendRequest(BaseSchema):
    """Suspend user account."""
    reason: str = Field(..., min_length=5, max_length=1000)
    duration_days: Optional[int] = Field(None, ge=1, le=365)


class AdminUserSuspendResponse(BaseSchema):
    """Suspend user response."""
    user_id: UUID
    suspended_at: datetime
    suspended_until: Optional[datetime]
    reason: str


# === Admin Audit Logs ===

class AdminAuditLogListParams(PaginationParams):
    """Query parameters for audit log list."""
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    action: Optional[str] = None
    actor_user_id: Optional[UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


class AdminAuditLogListItem(ResponseSchema):
    """Audit log entry."""
    id: UUID
    actor_user_id: Optional[UUID]
    actor_email: Optional[str]
    entity_type: str
    entity_id: str
    action: str
    before_state: Optional[dict[str, Any]]
    after_state: Optional[dict[str, Any]]
    ip_address: Optional[str]


class AdminAuditLogListResponse(PaginatedResponse):
    """Paginated audit log."""
    items: list[AdminAuditLogListItem]


# === System Configuration (Admin Settings) ===

class SystemConfigRequest(BaseSchema):
    """Request body for saving API keys and service credentials to database."""
    # AI / Search
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    openai_llm_model: Optional[str] = None
    openai_embedding_model: Optional[str] = None
    # Payments
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    # Storage
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    aws_s3_bucket: Optional[str] = None
    # Email
    resend_api_key: Optional[str] = None
    resend_from_email: Optional[str] = None
    # Document signing
    signrequest_api_key: Optional[str] = None
    signwell_api_key: Optional[str] = None
    signwell_template_id: Optional[str] = None


class SystemConfigResponse(BaseSchema):
    """Response after saving config values."""
    status: str
    keys_saved: list[str]
    message: str
