"""NDA signing flow request and response schemas."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# NDA enums as Literals
NdaStatus = Literal[
    "not_required", "payment_pending", "customer_signature_pending",
    "provider_signature_pending", "fully_signed", "failed", "cancelled"
]


# === NDA Checkout/Initiate ===

class NDACheckoutRequest(BaseSchema):
    """Initiate NDA payment and signing flow."""
    rfq_id: UUID


class NDACheckoutResponse(BaseSchema):
    """NDA checkout session response."""
    rfq_id: UUID
    checkout_url: str  # Stripe/PayPal checkout URL
    payment_intent_id: Optional[str]
    amount: float = 5.00
    currency: str = "USD"
    nda_status: NdaStatus


# === NDA Response ===

class NDAResponse(ResponseSchema):
    """NDA signing record response."""
    id: UUID
    rfq_id: UUID
    provider_id: Optional[int]
    customer_user_id: Optional[UUID]
    nda_status: NdaStatus
    signrequest_document_id: Optional[str]
    signrequest_template_id: Optional[str]
    signed_pdf_s3_key: Optional[str]
    audit_trail_s3_key: Optional[str]
    customer_signed_at: Optional[datetime]
    provider_signed_at: Optional[datetime]
    fully_signed_at: Optional[datetime]


class NDACustomerStatusResponse(BaseSchema):
    """NDA status for customer."""
    rfq_id: UUID
    nda_required: bool
    nda_status: NdaStatus
    customer_signed: bool
    signed_pdf_url: Optional[str]  # Presigned S3 URL
    audit_trail_url: Optional[str]
    signing_url: Optional[str]  # SignRequest embedded signing URL


class NDAProviderStatusResponse(BaseSchema):
    """NDA status for provider (may need to sign independently)."""
    rfq_id: UUID
    provider_id: int
    nda_required: bool
    nda_status: NdaStatus
    provider_signed: bool
    customer_signed: bool
    signing_url: Optional[str]  # SignRequest embedded signing URL
    signed_pdf_url: Optional[str]


class NDASigningCompleteRequest(BaseSchema):
    """Notify that signing is complete (webhook or manual check)."""
    signrequest_document_id: str


class NDASigningCompleteResponse(BaseSchema):
    """NDA signing completion response."""
    nda_id: UUID
    rfq_id: UUID
    nda_status: NdaStatus
    fully_signed: bool
    signed_pdf_url: Optional[str]
    audit_trail_url: Optional[str]
