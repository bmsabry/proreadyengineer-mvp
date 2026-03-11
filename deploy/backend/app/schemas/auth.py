"""Authentication request and response schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.user import UserResponse
from app.schemas.base import BaseSchema, ResponseSchema


class UserRegisterRequest(BaseSchema):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    full_name: Optional[str] = None
    business_name: Optional[str] = None


class UserLoginRequest(BaseSchema):
    """User login request."""
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenPairResponse(BaseSchema):
    """Token pair response (access token details)."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes
    user: UserResponse


class RefreshTokenRequest(BaseSchema):
    """Token refresh request (cookies handle the actual refresh token)."""
    pass


class PasswordForgotRequest(BaseSchema):
    """Password reset request."""
    email: EmailStr


class PasswordResetRequest(BaseSchema):
    """Password reset confirmation."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetResponse(BaseSchema):
    """Password reset response."""
    success: bool
    message: str


class LogoutResponse(BaseSchema):
    """Logout response."""
    success: bool
    message: str



class LoginResponse(BaseSchema):
    """Login response with tokens and user info."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    user: UserResponse


class RegisterResponse(BaseSchema):
    """Registration response with tokens and user info."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900
    user: UserResponse
    message: str = "Registration successful"

class AuthMeResponse(ResponseSchema):
    """Current user profile response."""
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    roles: list[str]
    is_super_admin: bool
    can_review_claims: bool
    can_moderate_providers: bool
    can_moderate_ads: bool
    can_manage_refunds: bool
    can_override_rfq_status: bool
    can_review_tier_requests: bool
    last_login_at: Optional[datetime]
    monthly_search_count: int
    search_count_reset_at: Optional[datetime]


# Rebuild models to resolve forward references
RegisterResponse.model_rebuild()
LoginResponse.model_rebuild()
