"""Advertising request and response schemas."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field, HttpUrl

from app.schemas.base import BaseSchema, ResponseSchema


# Ad enums as Literals
AdStatus = Literal["empty", "reserved_checkout_pending", "active", "paused", "cancelled", "expired"]


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
    ad_slot_id: Optional[UUID]
    advertiser_user_id: UUID
    provider_id: Optional[int]
    stripe_subscription_id: Optional[str]
    title: str
    promotional_text: Optional[str]
    outbound_url: Optional[str]
    image_s3_key: Optional[str]
    optional_price_text: Optional[str]
    ad_status: AdStatus
    started_at: Optional[datetime]
    ended_at: Optional[datetime]


class AdvertisementPublicResponse(BaseSchema):
    """Advertisement as shown on public pages."""
    id: UUID
    title: str
    promotional_text: Optional[str]
    outbound_url: Optional[str]
    image_url: Optional[str]  # Presigned S3 URL
    optional_price_text: Optional[str]


class AdvertisementListResponse(BaseSchema):
    """List of advertisements for an advertiser."""
    advertisements: list[AdvertisementResponse]
    active_count: int
    total_spend: float


# === Ad Asset Upload ===

class AdAssetUploadInitiateRequest(BaseSchema):
    """Request presigned URL for ad image upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., pattern="^(image/jpeg|image/png|image/webp)$")
    file_size_bytes: int = Field(..., gt=0, le=5242880)  # 5MB max


class AdAssetUploadInitiateResponse(BaseSchema):
    """Presigned URL for ad image upload."""
    upload_id: UUID
    presigned_url: str
    s3_key: str
    expires_in_seconds: int


class AdAssetUploadCompleteRequest(BaseSchema):
    """Confirm ad image upload."""
    upload_id: UUID


class AdAssetUploadCompleteResponse(BaseSchema):
    """Ad image upload confirmation."""
    ad_id: UUID
    image_s3_key: str
    image_url: str  # Presigned URL
    ad_status: AdStatus


# === Public Ad Pages ===

class SoftwareProvidersAdsResponse(BaseSchema):
    """Software providers page ads."""
    ads: list[AdvertisementPublicResponse]
    placeholder_count: int
    purchase_url: str


class FeaturedFirmsAdsResponse(BaseSchema):
    """Featured firms page ads."""
    ads: list[AdvertisementPublicResponse]
    placeholder_count: int
    purchase_url: str
    disclaimer: str = "Featured firms allow direct customer access outside the RFQ flow."



# === Ad Creation ===

class AdCreateRequest(BaseSchema):
    """Create a new advertisement."""
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


class AdAssetUploadInitiateRequest(BaseSchema):
    """Request presigned URL for ad image upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., gt=0, le=5242880)  # 5MB max


class AdAssetUploadCompleteRequest(BaseSchema):
    """Confirm ad image upload."""
    upload_id: UUID


class AdUpdateRequest(BaseSchema):
    """Update ad configuration."""
    title: Optional[str] = Field(None, max_length=100)
    promotional_text: Optional[str] = Field(None, max_length=500)
    outbound_url: Optional[str] = Field(None, max_length=500)
    optional_price_text: Optional[str] = Field(None, max_length=100)
    image_s3_key: Optional[str] = None
