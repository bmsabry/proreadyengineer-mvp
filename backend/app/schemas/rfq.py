"""RFQ request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# Enums as Literals
RfqStatus = Literal[
    "draft", "submitted", "awaiting_nda_payment", "awaiting_customer_signature",
    "open_for_dispatch", "dispatching", "open_for_unlock", "quote_limit_reached",
    "customer_selected_provider", "closed_no_selection", "cancelled"
]
DispatchStatus = Literal["pending", "sent", "opened", "clicked", "responded", "failed"]
UnlockStatus = Literal["pending", "completed", "expired", "refunded"]


# === RFQ Create/Update ===

class RFQCreateRequest(BaseSchema):
    """Create new RFQ draft."""
    customer_email: str = Field(..., max_length=255)
    business_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    project_description: str = Field(..., min_length=10, max_length=10000)
    urgency: Optional[str] = Field(None, pattern="^(High|Intermediate|Low)$")
    tollgate_phases: list[str] = Field(default_factory=list)  # TG0, TG1, TG3, TG4, TG6, All, Don't Know
    nda_required: bool = False
    document_s3_key: Optional[str] = Field(None, description="S3 key of primary document uploaded during search (backward-compat)")
    document_s3_keys: Optional[list[dict]] = Field(None, description="List of {filename, s3_key, is_cad} for multi-file uploads")
    document_extracted_text: Optional[str] = Field(None, description="Extracted text from uploaded document(s) when S3 is not available")


class RFQUpdateRequest(BaseSchema):
    """Update RFQ draft."""
    business_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    project_description: Optional[str] = Field(None, min_length=10, max_length=10000)
    urgency: Optional[str] = Field(None, pattern="^(High|Intermediate|Low)$")
    tollgate_phases: Optional[list[str]] = None
    nda_required: Optional[bool] = None


class RFQSubmitRequest(BaseSchema):
    """Submit RFQ for matching and dispatch."""
    pass  # Just the action, no body needed


# === RFQ Files (defined here so RFQResponse can reference it) ===

class RFQFileResponse(ResponseSchema):
    """RFQ file details."""
    id: UUID
    rfq_id: UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    extracted_text: Optional[str]
    download_url: Optional[str] = None

# === RFQ Response ===

class RFQResponse(ResponseSchema):
    """RFQ details response."""
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
    submitted_at: Optional[datetime]
    closed_at: Optional[datetime]
    files: list[RFQFileResponse] = []


class RFQStatusResponse(BaseSchema):
    """RFQ status summary."""
    rfq_id: UUID
    status: RfqStatus
    quote_count: int
    quote_limit: int = 5
    is_closed: bool
    dispatched_providers_count: int
    unlocks_count: int
    next_dispatch_at: Optional[datetime]


# === RFQ Files ===

class RFQFileCreateRequest(BaseSchema):
    """Add file to RFQ."""
    s3_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int




class RFQFileUploadInitiateResponse(BaseSchema):
    """Presigned URL for RFQ file upload."""
    file_id: UUID
    presigned_url: str
    s3_key: str
    expires_in_seconds: int


# === RFQ Matches ===

class RFQMatchResponse(ResponseSchema):
    """RFQ match ranking snapshot."""
    id: UUID
    rfq_id: UUID
    provider_id: int
    provider_name: str
    rank_position: int
    composite_score: int  # 0-100
    specialty_score: int  # 0-25
    capabilities_score: int  # 0-50
    tier_score: int  # 0-25
    scoring_inputs: dict[str, Any]
    is_dispatched: bool
    dispatched_at: Optional[datetime]


# === RFQ Dispatches ===

class RFQDispatchBatchResponse(ResponseSchema):
    """RFQ dispatch batch details."""
    id: UUID
    rfq_id: UUID
    batch_number: int
    scheduled_for: datetime
    dispatched_at: Optional[datetime]
    status: str


class RFQDispatchResponse(ResponseSchema):
    """Individual provider dispatch record."""
    id: UUID
    rfq_id: UUID
    provider_id: int
    provider_name: str
    batch_id: Optional[UUID]
    dispatch_status: DispatchStatus
    teaser_email_sent_at: Optional[datetime]
    email_target: Optional[str]
    email_opened_at: Optional[datetime]
    teaser_link_clicked_at: Optional[datetime]


# === RFQ Unlocks (Provider side) ===

class RFQUnlockResponse(ResponseSchema):
    """RFQ unlock status."""
    id: UUID
    rfq_id: UUID
    provider_id: int
    unlock_status: UnlockStatus
    unlocked_at: Optional[datetime]
    expires_at: Optional[datetime]


class RFQUnlockStatusResponse(BaseSchema):
    """RFQ unlock status for provider."""
    rfq_id: UUID
    is_unlocked: bool
    unlock_status: Optional[UnlockStatus]
    can_unlock: bool
    unlock_price: Decimal = Decimal("10.00")
    currency: str = "USD"


class RFQTeaserResponse(BaseSchema):
    """RFQ teaser for provider (before unlock)."""
    rfq_id: UUID
    urgency: Optional[str]
    tollgate_phases: Optional[list[str]]
    project_summary: str  # Truncated description
    has_documents: bool
    dispatch_date: datetime
    is_closed: bool
    quote_limit_reached: bool
    current_quote_count: int


class RFQDetailForProviderResponse(RFQResponse):
    """Full RFQ details for unlocked providers."""
    files: list[RFQFileResponse]
    files_download_urls: list[str]  # Presigned URLs



# === RFQ File Upload ===

class RFQFileUploadInitiateRequest(BaseSchema):
    """Request presigned URL for RFQ file upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., gt=0, le=26214400)  # 25MB max


class RFQFileUploadInitiateResponse(BaseSchema):
    """Presigned upload URL response."""
    upload_id: UUID
    presigned_url: str
    s3_key: str
    expires_in_seconds: int


class RFQFileUploadCompleteRequest(BaseSchema):
    """Confirm RFQ file upload."""
    upload_id: UUID


class RFQFileUploadResponse(BaseSchema):
    """RFQ file upload completion response."""
    file_id: UUID
    rfq_id: UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int
    uploaded_at: datetime


# === NDA Checkout ===

class RFQNDACheckoutRequest(BaseSchema):
    """Initiate NDA payment/checkout."""
    pass


class RFQNDACheckoutResponse(BaseSchema):
    """NDA checkout session response."""
    checkout_session_id: str
    checkout_url: str


# Aliases for compatibility
RFQUploadInitiateRequest = RFQFileUploadInitiateRequest
RFQUploadInitiateResponse = RFQFileUploadInitiateResponse
RFQUploadCompleteRequest = RFQFileUploadCompleteRequest



# === Admin Override ===

class RFQStatusOverrideRequest(BaseSchema):
    """Admin override for RFQ status."""
    new_status: RfqStatus
    reason: str = Field(..., min_length=5, max_length=1000)
    admin_notes: Optional[str] = None


class RFQAdminResponse(ResponseSchema):
    """Admin view of RFQ with full details."""
    id: UUID
    customer_email: str
    business_name: Optional[str]
    project_description: str
    rfq_status: RfqStatus
    quote_count: int
    nda_required: bool
    is_closed: bool
    selected_provider_id: Optional[int]
    created_at: datetime
    submitted_at: Optional[datetime]
    closed_at: Optional[datetime]
