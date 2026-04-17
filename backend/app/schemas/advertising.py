"""Advertising request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import Field, HttpUrl

from app.schemas.base import BaseSchema, ResponseSchema


# Ad enums as Literals
AdStatus = Literal[
    "empty", "processing", "pending_review", "reserved_checkout_pending",
    "active", "paused", "cancelled", "expired", "rejected",
]


# === Ad Slots ===

class AdSlotResponse(BaseSchema):
    """Ad slot inventory response."""
    id: UUID
    page_type: str  # software-providers, featured-firms
    slot_name: str
    slot_position: int
    status: str  # available, reserved, occupied
    current_price: float = 50.00  # Monthly price


# === Advertisements ===

class AdvertisementCreateRequest(BaseSchema):
    """Create advertisement checkout."""
    ad_slot_id: UUID
    provider_id: Optional[int] = None  # Link to provider if applicable
    payment_provider: str = Field(default="stripe", pattern="^(stripe|paypal)$")


class AdvertisementUpdateRequest(BaseSchema):
    """Update advertisement content."""
    title: Optional[str] = Field(None, max_length=100)
    promotional_text: Optional[str] = Field(None, max_length=500)
    outbound_url: Optional[str] = Field(None, max_length=500)
    optional_price_text: Optional[str] = Field(None, max_length=100)


class AdvertisementResponse(ResponseSchema):
    """Advertisement response."""
    id: UUID
    ad_slot_id: Optional[UUID] = None
    advertiser_user_id: UUID
    provider_id: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    page_type: Optional[str] = None
    title: str
    promotional_text: Optional[str] = None
    outbound_url: Optional[str] = None
    image_s3_key: Optional[str] = None
    optional_price_text: Optional[str] = None
    ad_status: AdStatus
    llm_extracted_content: Optional[Dict[str, Any]] = None
    source_website_url: Optional[str] = None
    uploaded_materials_s3_keys: Optional[List[str]] = None
    click_count: int = 0
    impression_count: int = 0
    admin_review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class AdvertisementPublicResponse(BaseSchema):
    """Advertisement as shown on public pages."""
    id: UUID
    title: str
    promotional_text: Optional[str] = None
    outbound_url: Optional[str] = None
    image_url: Optional[str] = None  # Presigned S3 URL
    optional_price_text: Optional[str] = None
    provider_id: Optional[int] = None
    page_type: Optional[str] = None
    llm_extracted_content: Optional[Dict[str, Any]] = None
    click_count: int = 0
    impression_count: int = 0


class AdvertisementListResponse(BaseSchema):
    """List of advertisements for an advertiser."""
    advertisements: list[AdvertisementResponse]
    active_count: int
    total_spend: float


class SoftwareProvidersAdsResponse(BaseSchema):
    """Paginated response for software-providers ad page."""
    advertisements: list[AdvertisementPublicResponse]
    total: int
    page: int
    page_size: int


class FeaturedFirmsAdsResponse(BaseSchema):
    """Paginated response for featured-firms ad page."""
    advertisements: list[AdvertisementPublicResponse]
    total: int
    page: int
    page_size: int


# === Ad Submission (new workflow) ===

class AdSubmissionRequest(BaseSchema):
    """Submit ad for creation — provider uploads materials + optional website."""
    page_type: str = Field(..., pattern="^(software-providers|featured-firms)$")
    website_url: Optional[str] = Field(None, max_length=500)
    description_text: Optional[str] = Field(
        None, max_length=10000,
        description="Freeform text from brochures, flyers, or descriptions"
    )
    outbound_url: Optional[str] = Field(
        None, max_length=500,
        description="Where ad clicks redirect (firm website or product page)"
    )
    uploaded_material_keys: Optional[List[str]] = Field(
        None,
        description="S3 keys of uploaded brochure/flyer files"
    )


class AdSubmissionResponse(BaseSchema):
    """Response after ad is submitted for review."""
    ad_id: UUID
    ad_status: str
    title: str
    promotional_text: Optional[str] = None
    llm_extracted_content: Optional[Dict[str, Any]] = None
    message: str


# === Ad Search ===

class AdSearchRequest(BaseSchema):
    """Search ads with LLM-powered reordering."""
    query: str = Field(..., min_length=1, max_length=500)
    page_type: Optional[str] = Field(None, pattern="^(software-providers|featured-firms)$")


class AdSearchResponse(BaseSchema):
    """Search results for ads."""
    query: str
    advertisements: list[AdvertisementPublicResponse]
    total_count: int


# === Ad Asset Upload ===

class AdAssetUploadInitiateRequest(BaseSchema):
    """Request presigned URL for ad material upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., gt=0, le=10485760)  # 10MB max


class AdAssetUploadInitiateResponse(BaseSchema):
    """Presigned URL for ad material upload."""
    upload_url: str
    fields: Dict[str, str]
    s3_key: str


class AdAssetUploadCompleteRequest(BaseSchema):
    """Confirm ad material upload."""
    s3_key: str


class AdAssetUploadCompleteResponse(BaseSchema):
    """Response after confirming ad material upload."""
    s3_key: str
    message: str = "Upload confirmed"


# === Ad Creation (legacy) ===

class AdCreateRequest(BaseSchema):
    """Create a new advertisement (legacy — use AdSubmissionRequest)."""
    ad_slot_id: UUID
    title: str = Field(..., max_length=100)
    promotional_text: str = Field(..., max_length=500)
    outbound_url: str = Field(..., max_length=500)
    optional_price_text: Optional[str] = Field(None, max_length=100)


class AdCheckoutRequest(BaseSchema):
    """Initiate ad slot checkout."""
    ad_slot_id: UUID


class AdCheckoutResponse(BaseSchema):
    """Ad checkout session response."""
    checkout_session_id: str
    checkout_url: str


class AdUpdateRequest(BaseSchema):
    """Update ad configuration."""
    title: Optional[str] = Field(None, max_length=100)
    promotional_text: Optional[str] = Field(None, max_length=500)
    outbound_url: Optional[str] = Field(None, max_length=500)
    optional_price_text: Optional[str] = Field(None, max_length=100)
    image_s3_key: Optional[str] = None


# === Admin Ad Review ===

class AdminAdReviewRequest(BaseSchema):
    """Admin reviews an ad submission."""
    action: str = Field(..., pattern="^(approve|reject)$")
    notes: Optional[str] = Field(None, max_length=1000)


class AdminAdReviewResponse(BaseSchema):
    """Response after admin review."""
    ad_id: UUID
    ad_status: str
    reviewed_at: datetime
    message: str


# === Admin Ad Create ===

class AdminAdCreateRequest(BaseSchema):
    """Admin creates an ad for a registered provider."""
    provider_id: int = Field(..., description="ID of the registered provider")
    page_type: str = Field(..., pattern="^(software-providers|featured-firms)$")
    website_url: Optional[str] = Field(None, max_length=500)
    description_text: Optional[str] = Field(None, max_length=10000)
    outbound_url: Optional[str] = Field(None, max_length=500)


class AdminAdEditRequest(BaseSchema):
    """Admin edits any ad field."""
    title: Optional[str] = Field(None, max_length=200)
    promotional_text: Optional[str] = Field(None, max_length=2000)
    outbound_url: Optional[str] = Field(None, max_length=500)
    optional_price_text: Optional[str] = Field(None, max_length=100)
    page_type: Optional[str] = Field(None, pattern="^(software-providers|featured-firms)$")
    ad_status: Optional[str] = Field(None)
    image_s3_key: Optional[str] = None
    admin_review_notes: Optional[str] = Field(None, max_length=2000)


# === Click Tracking ===

class AdClickRequest(BaseSchema):
    """Record an ad click."""
    ad_id: UUID
