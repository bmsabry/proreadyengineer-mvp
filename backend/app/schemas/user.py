"""User request and response schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema, ResponseSchema


class UserCreateRequest(BaseSchema):
    """Create user request (internal/admin use)."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    roles: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseSchema):
    """Update user profile request."""
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None


class UserRoleUpdateRequest(BaseSchema):
    """Update user roles (admin only)."""
    roles: list[str]
    is_super_admin: Optional[bool] = None
    can_review_claims: Optional[bool] = None
    can_moderate_providers: Optional[bool] = None
    can_moderate_ads: Optional[bool] = None
    can_manage_refunds: Optional[bool] = None
    can_override_rfq_status: Optional[bool] = None
    can_review_tier_requests: Optional[bool] = None


class UserResponse(BaseSchema):
    """User profile response."""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    roles: list[str]
    is_super_admin: bool = False
    can_review_claims: bool = False
    can_moderate_providers: bool = False
    can_moderate_ads: bool = False
    can_manage_refunds: bool = False
    can_override_rfq_status: bool = False
    can_review_tier_requests: bool = False
    failed_login_count: int = 0
    locked_until: Optional[datetime] = None
    monthly_search_count: int = 0
    search_count_reset_at: Optional[datetime] = None
    email_verified: bool = True
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserListResponse(BaseSchema):
    """User list item (admin view)."""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    roles: list[str]
    is_super_admin: bool
    monthly_search_count: int
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UserSearchQuotaResponse(BaseSchema):
    """User search quota information."""
    monthly_search_count: int
    search_count_reset_at: Optional[datetime]
    remaining_searches: int
    tier: str  # anonymous, registered_free, tier_1, tier_2
    tier_limit: int
