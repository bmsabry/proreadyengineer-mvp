"""Quote request and response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# Quote enums as Literals
QuoteStatus = Literal["draft", "submitted", "withdrawn", "customer_viewed", "shortlisted", "accepted", "not_selected", "expired"]


# === Quote Create/Submit ===

class QuoteCreateRequest(BaseSchema):
    """Create quote draft."""
    rough_price_min: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    rough_price_max: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    currency: str = Field(default="USD", max_length=3)
    turnaround_estimate_text: Optional[str] = Field(None, max_length=500)
    assumptions_text: Optional[str] = Field(None, max_length=2000)
    scope_notes: Optional[str] = Field(None, max_length=2000)
    # Optional uploaded document reference
    document_s3_key: Optional[str] = Field(None, description="S3 key of uploaded quote document")
    document_filename: Optional[str] = Field(None, description="Original filename of uploaded document")


class QuoteSubmitRequest(BaseSchema):
    """Submit quote (immutable after submission)."""
    rough_price_min: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    rough_price_max: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    currency: str = Field(default="USD", max_length=3)
    turnaround_estimate_text: Optional[str] = Field(None, max_length=500)
    assumptions_text: Optional[str] = Field(None, max_length=2000)
    scope_notes: Optional[str] = Field(None, max_length=2000)
    # Optional uploaded document reference
    document_s3_key: Optional[str] = Field(None)
    document_filename: Optional[str] = Field(None)


class QuoteFileCreateRequest(BaseSchema):
    """Attach file to quote."""
    s3_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int


# === Document Extraction ===

class QuoteDocExtractResponse(BaseSchema):
    """Result of LLM extraction from an uploaded quote document."""
    s3_key: str
    original_filename: str
    extracted_fields: dict
    # Pre-filled suggestions
    rough_price_min: Optional[Decimal] = None
    rough_price_max: Optional[Decimal] = None
    currency: str = "USD"
    turnaround_estimate_text: Optional[str] = None
    assumptions_text: Optional[str] = None
    scope_notes: Optional[str] = None
    raw_extraction: Optional[str] = None


# === Quote Response ===

class QuoteFileResponse(ResponseSchema):
    """Quote file details."""
    id: UUID
    quote_id: UUID
    original_filename: str
    mime_type: str
    file_size_bytes: int


class QuoteProviderInfo(BaseSchema):
    """Provider info visible to customer (limited until accepted)."""
    provider_id: int
    provider_name: str
    firm_name: str
    primary_specialty: Optional[str]
    # Contact fields - only populated for accepted quotes
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None


class QuoteResponse(ResponseSchema):
    """Quote response (full details)."""
    id: UUID
    rfq_id: UUID
    provider_id: int
    submitter_user_id: UUID
    quote_status: QuoteStatus
    rough_price_min: Optional[Decimal]
    rough_price_max: Optional[Decimal]
    currency: str
    turnaround_estimate_text: Optional[str]
    assumptions_text: Optional[str]
    scope_notes: Optional[str]
    submitted_at: Optional[datetime]
    customer_viewed_at: Optional[datetime]
    # Document attachment (revealed to customer only on acceptance)
    document_s3_key: Optional[str] = None
    document_filename: Optional[str] = None
    # Customer contact info - only populated for accepted quotes (provider view)
    customer_contact_name: Optional[str] = None
    customer_company: Optional[str] = None
    customer_email: Optional[str] = None


class QuoteForCustomerResponse(QuoteResponse):
    """Quote as seen by customer."""
    provider: QuoteProviderInfo
    files: list[QuoteFileResponse]
    # Document download URL (only populated for accepted quotes)
    document_download_url: Optional[str] = None


class QuoteForProviderResponse(QuoteResponse):
    """Quote as seen by provider (no sensitive customer data)."""
    files: list[QuoteFileResponse]


class QuoteListResponse(BaseSchema):
    """List of quotes for an RFQ (customer view)."""
    quotes: list[QuoteForCustomerResponse]
    rfq_id: UUID
    can_accept: bool  # RFQ is open and quote count < 5
    disclaimer: str = "Quotes are rough, non-binding, order-of-magnitude estimates. Refined final estimate will follow direct engagement."


class QuoteAcceptRequest(BaseSchema):
    """Accept a quote."""
    pass  # Action only


class QuoteAcceptResponse(BaseSchema):
    """Quote acceptance response - includes provider contact info revealed on acceptance."""
    success: bool
    message: str
    rfq_id: UUID
    selected_quote_id: UUID
    selected_provider_id: int
    provider_contact_revealed: bool = True
    # Provider contact details (revealed upon acceptance)
    provider_name: Optional[str] = None
    provider_email: Optional[str] = None
    provider_phone: Optional[str] = None
    provider_website: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_address: Optional[str] = None


class QuoteWithdrawRequest(BaseSchema):
    """Withdraw a submitted quote."""
    reason: Optional[str] = Field(None, max_length=500)


class QuoteWithdrawResponse(BaseSchema):
    """Quote withdrawal response."""
    success: bool
    message: str
    quote_id: UUID
    new_status: QuoteStatus
