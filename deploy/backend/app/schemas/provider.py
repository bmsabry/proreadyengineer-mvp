"""Provider request and response schemas."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# Membership enums as Literals
MembershipRole = Literal["owner", "editor", "billing_manager", "viewer"]
MembershipStatus = Literal["active", "inactive", "pending"]
ClaimStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
TierEvaluationStatus = Literal["pending", "approved", "rejected", "cancelled"]


# === Provider Public Schemas (minimal, safe for public) ===

class ProviderPublicResponse(ResponseSchema):
    """Provider public profile - minimal info for search results."""
    id: int
    firm_name: str
    primary_specialty: Optional[str]
    secondary_specialties: Optional[list[str]]
    business_description: Optional[str]
    capabilities: Optional[list[str]]
    tier: Optional[str]  # A, B, C, D, E
    city: Optional[str]
    state: Optional[str]
    website: Optional[str]
    certifications: Optional[list[str]]
    notable_clients: Optional[list[str]]
    software_tools: Optional[list[str]]


class ProviderSearchResult(BaseSchema):
    """Provider in search results with match explanation."""
    provider_id: int
    name: str
    firm_name: str
    tier: Optional[str]
    primary_specialty: Optional[str]
    score: int = Field(..., ge=0, le=100)  # Composite 0-100 score
    explanation: str  # Grounded explanation of why this provider matches
    capabilities: Optional[list[str]]
    city: Optional[str]
    state: Optional[str]


# === Provider Claim Schemas ===

class ProviderClaimSearchRequest(BaseSchema):
    """Search for provider to claim."""
    firm_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class ProviderClaimSearchResult(BaseSchema):
    """Matching providers for claim search."""
    provider_id: int
    firm_name: str
    city: Optional[str]
    state: Optional[str]
    primary_specialty: Optional[str]
    claimable: bool  # Whether this provider has no existing claim


class ProviderClaimCreateRequest(BaseSchema):
    """Submit claim request for a provider."""
    provider_id: int
    proof_type: str = Field(..., max_length=100)  # e.g., "domain_verification", "business_license"
    proof_payload: dict[str, Any]  # Flexible proof data
    submitted_notes: Optional[str] = Field(None, max_length=2000)


class ProviderClaimResponse(ResponseSchema):
    """Claim request status."""
    id: UUID
    provider_id: int
    provider_name: str
    claimant_user_id: UUID
    status: ClaimStatus
    proof_type: Optional[str]
    submitted_notes: Optional[str]
    admin_review_notes: Optional[str]
    reviewed_at: Optional[datetime]
    created_at: datetime


# === Provider Membership Schemas ===

class ProviderMembershipCreateRequest(BaseSchema):
    """Add member to provider (admin/owner only)."""
    user_id: UUID
    membership_role: MembershipRole


class ProviderMembershipResponse(ResponseSchema):
    """Provider membership details."""
    id: UUID
    provider_id: int
    user_id: UUID
    user_email: Optional[str]
    user_name: Optional[str]
    membership_role: MembershipRole
    status: MembershipStatus
    created_at: datetime


# === Provider Profile Schemas (for subscribed providers) ===

class ProviderProfileCreateRequest(BaseSchema):
    """Create new provider profile (if not in seeded database)."""
    firm_name: str = Field(..., max_length=200)
    primary_specialty: Optional[str] = Field(None, max_length=200)
    secondary_specialties: Optional[list[str]] = None
    business_description: Optional[str] = Field(None, max_length=5000)
    capabilities: Optional[list[str]] = None
    specialties: Optional[list[str]] = None
    software_tools: Optional[list[str]] = None
    notable_clients: Optional[list[str]] = None
    certifications: Optional[list[str]] = None
    email_addresses: Optional[list[str]] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)


class ProviderProfileUpdateRequest(BaseSchema):
    """Update provider profile (editors and owners)."""
    firm_name: Optional[str] = Field(None, max_length=200)
    primary_specialty: Optional[str] = Field(None, max_length=200)
    secondary_specialties: Optional[list[str]] = None
    business_description: Optional[str] = Field(None, max_length=5000)
    capabilities: Optional[list[str]] = None
    specialties: Optional[list[str]] = None
    software_tools: Optional[list[str]] = None
    notable_clients: Optional[list[str]] = None
    certifications: Optional[list[str]] = None
    email_addresses: Optional[list[str]] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)


class ProviderProfileResponse(ResponseSchema):
    """Full provider profile response (for owners/editors)."""
    id: int
    firm_name: str
    primary_specialty: Optional[str]
    secondary_specialties: Optional[list[str]]
    business_description: Optional[str]
    capabilities: Optional[list[str]]
    specialties: Optional[list[str]]
    software_tools: Optional[list[str]]
    notable_clients: Optional[list[str]]
    certifications: Optional[list[str]]
    email_addresses: Optional[list[str]]
    phone: Optional[str]
    website: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    tier: Optional[str]
    claim_status: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    embedding_generated_at: Optional[datetime]
    memberships: list[ProviderMembershipResponse]


# === Tier Evaluation Schemas ===

class TierEvaluationCreateRequest(BaseSchema):
    """Request tier evaluation/rank up."""
    requested_reason: str = Field(..., min_length=10, max_length=2000)
    supporting_payload: Optional[dict[str, Any]] = None  # URLs to portfolios, case studies, etc.


class TierEvaluationResponse(ResponseSchema):
    """Tier evaluation request status."""
    id: UUID
    provider_id: int
    current_tier: Optional[str]
    requested_reason: Optional[str]
    status: TierEvaluationStatus
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    new_tier: Optional[str]
    created_at: datetime


class TierEvaluationAdminResponse(ResponseSchema):
    """Full tier evaluation for admin review."""
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
    created_at: datetime



# === Provider Update Schema ===

class ProviderUpdateRequest(BaseSchema):
    """Provider profile update request."""
    firm_name: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)
    primary_specialty: Optional[str] = Field(None, max_length=255)
    secondary_specialties: Optional[list[str]] = None
    business_description: Optional[str] = None
    capabilities: Optional[list[str]] = None
    specialties: Optional[list[str]] = None
    software_tools: Optional[list[str]] = None
    notable_clients: Optional[list[str]] = None
    certifications: Optional[list[str]] = None


# === Provider Membership Schemas ===

class ProviderMembershipResponse(BaseSchema):
    """Provider membership response."""
    id: UUID
    provider_id: int
    user_id: UUID
    membership_role: str
    status: str
    created_at: datetime


# === Provider Claim Schemas ===

class ProviderClaimRequest(BaseSchema):
    """Request to claim a provider record."""
    provider_id: int
    proof_type: str = Field(..., description="Type of proof provided")
    proof_payload: dict = Field(default_factory=dict)
    submitted_notes: Optional[str] = None


class ProviderClaimResponse(BaseSchema):
    """Provider claim response."""
    id: UUID
    provider_id: int
    claimant_user_id: UUID
    status: str
    created_at: datetime
    message: str = "Claim submitted successfully"


# Aliases for endpoint compatibility
ProviderResponse = ProviderPublicResponse



class ProviderResponse(BaseSchema):
    """Full provider response with all fields."""
    id: int
    name: str
    business_name: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    primary_specialty: Optional[str] = None
    secondary_specialties: list = []
    business_description: Optional[str] = None
    capabilities: list = []
    specialties: list = []
    software_tools: list = []
    notable_clients: list = []
    email_addresses: list = []
    certifications: list = []
    tier: str = "D"
    is_claimed: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
