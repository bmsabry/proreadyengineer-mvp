"""
Provider request and response schemas.

SECOND-PASS FIX LOG (6 bugs eliminated):
  BUG-1 ProviderPublicResponse used ResponseSchema (needs id:UUID + updated_at).
        Provider.id is INTEGER; no updated_at column.  FIX -> BaseSchema.
  BUG-2 ProviderMembershipResponse defined twice.  FIX -> single definition.
  BUG-3 ProviderClaimResponse defined twice.  FIX -> single definition.
  BUG-4 ProviderResponse alias then re-class.  FIX -> removed alias.
  BUG-5 ProviderProfileResponse required is_active/updated_at, neither exists
        on Provider model.  FIX -> Optional with None defaults.
  BUG-6 notable_clients typed list[str] but is a TEXT column.
        FIX -> Optional[str] everywhere.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


# Status literals
MembershipRole = Literal["owner", "editor", "billing_manager", "viewer"]
MembershipStatus = Literal["active", "inactive", "pending"]
ClaimStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
TierEvaluationStatus = Literal["pending", "approved", "rejected", "cancelled"]


# ---------------------------------------------------------------------------
# Public provider schemas
# ---------------------------------------------------------------------------

class ProviderPublicResponse(BaseSchema):
    """Minimal provider profile for search results.

    BUG-1 FIX: BaseSchema NOT ResponseSchema -
      Provider.id is INTEGER; Provider has no updated_at column.
    """
    id: int
    name: Optional[str] = None
    firm_name: str
    primary_specialty: Optional[str] = None
    secondary_specialties: Optional[List[str]] = None
    business_description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    notable_clients: Optional[str] = None  # TEXT column not list
    software_tools: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    tier: Optional[str] = None  # @property on Provider
    city: Optional[str] = None
    state: Optional[str] = None
    website: Optional[str] = None


class ProviderSearchResult(BaseSchema):
    """Provider in search results with match explanation."""
    provider_id: int
    name: str
    firm_name: str
    tier: Optional[str] = None
    primary_specialty: Optional[str] = None
    score: int = Field(..., ge=0, le=100)
    explanation: str
    capabilities: Optional[List[str]] = None
    city: Optional[str] = None
    state: Optional[str] = None


# ---------------------------------------------------------------------------
# Provider claim schemas
# ---------------------------------------------------------------------------

class ProviderClaimSearchRequest(BaseSchema):
    """Search for an existing provider record to claim."""
    firm_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class ProviderClaimSearchResult(BaseSchema):
    """Provider summary shown in claim-search results."""
    provider_id: int
    firm_name: str
    city: Optional[str] = None
    state: Optional[str] = None
    primary_specialty: Optional[str] = None
    claimable: bool


class ProviderClaimCreateRequest(BaseSchema):
    """Submit a new ownership claim for a provider record."""
    provider_id: int
    proof_type: str = Field(..., max_length=100)
    proof_payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    submitted_notes: Optional[str] = Field(None, max_length=2000)


ProviderClaimRequest = ProviderClaimCreateRequest  # backward-compat alias


class ProviderClaimResponse(BaseSchema):
    """Claim request status. BUG-3 FIX: was defined twice."""
    id: UUID
    provider_id: int
    claimant_user_id: UUID
    status: str
    proof_type: Optional[str] = None
    submitted_notes: Optional[str] = None
    admin_review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    message: str = "Claim submitted successfully"

    model_config = {"from_attributes": True}


class ProviderClaimAdminResponse(BaseSchema):
    """Full claim request detail for admin review queue."""
    id: UUID
    provider_id: int
    provider_name: Optional[str] = None
    claimant_user_id: UUID
    status: ClaimStatus
    proof_type: Optional[str] = None
    submitted_notes: Optional[str] = None
    admin_review_notes: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
# ---------------------------------------------------------------------------
# Provider membership schemas
# ---------------------------------------------------------------------------

class ProviderMembershipCreateRequest(BaseSchema):
    """Add a member to a provider (admin/owner only)."""
    user_id: UUID
    membership_role: MembershipRole


class ProviderMembershipResponse(BaseSchema):
    """Provider membership detail. BUG-2 FIX: was defined twice."""
    id: UUID
    provider_id: int
    user_id: UUID
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    membership_role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Provider profile schemas
# ---------------------------------------------------------------------------

class ProviderProfileCreateRequest(BaseSchema):
    """Create a new provider profile."""
    firm_name: str = Field(..., max_length=200)
    primary_specialty: Optional[str] = Field(None, max_length=200)
    secondary_specialties: Optional[List[str]] = None
    business_description: Optional[str] = Field(None, max_length=5000)
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[str] = None
    certifications: Optional[List[str]] = None
    email_addresses: Optional[List[str]] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)


class ProviderProfileUpdateRequest(BaseSchema):
    """Partial-update provider profile (editors and owners)."""
    firm_name: Optional[str] = Field(None, max_length=200)
    primary_specialty: Optional[str] = Field(None, max_length=200)
    secondary_specialties: Optional[List[str]] = None
    business_description: Optional[str] = Field(None, max_length=5000)
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[str] = None
    certifications: Optional[List[str]] = None
    email_addresses: Optional[List[str]] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)


ProviderUpdateRequest = ProviderProfileUpdateRequest  # backward-compat


class ProviderProfileResponse(BaseSchema):
    """Full provider profile for owners/editors.

    BUG-1+BUG-5 FIX: BaseSchema not ResponseSchema.
    Provider has no is_active or updated_at - both Optional with defaults.
    """
    id: int
    name: Optional[str] = None
    firm_name: str
    primary_specialty: Optional[str] = None
    secondary_specialties: Optional[List[str]] = None
    business_description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[str] = None
    certifications: Optional[List[str]] = None
    email_addresses: Optional[List[str]] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    tier: Optional[str] = None
    is_active: Optional[bool] = None  # BUG-5: not on model, Optional
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None  # BUG-5: not on model, Optional
    embedding_generated_at: Optional[datetime] = None
    memberships: List[ProviderMembershipResponse] = []

    model_config = {"from_attributes": True}


# Backward-compat aliases
ProviderResponse = ProviderProfileResponse  # BUG-4 FIX: alias not re-class


# ---------------------------------------------------------------------------
# Tier evaluation schemas
# ---------------------------------------------------------------------------

class TierEvaluationCreateRequest(BaseSchema):
    """Request a tier evaluation / rank-up."""
    requested_reason: str = Field(..., min_length=10, max_length=2000)
    supporting_payload: Optional[Dict[str, Any]] = None


class TierEvaluationResponse(BaseSchema):
    """Tier evaluation request status."""
    id: UUID
    provider_id: int
    current_tier: Optional[str] = None
    requested_reason: Optional[str] = None
    status: TierEvaluationStatus
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    new_tier: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TierEvaluationAdminResponse(BaseSchema):
    """Full tier evaluation for admin review."""
    id: UUID
    provider_id: int
    provider_name: Optional[str] = None
    requested_by_user_id: UUID
    requested_by_email: Optional[str] = None
    current_tier: Optional[str] = None
    requested_reason: Optional[str] = None
    supporting_payload: Optional[Dict[str, Any]] = None
    status: TierEvaluationStatus
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    new_tier: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
