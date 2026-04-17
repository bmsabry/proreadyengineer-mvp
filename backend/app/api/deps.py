"""API dependencies for authentication, authorization, and rate limiting."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

# Security scheme for bearer tokens
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate JWT token and return current user.

    Checks for token in:
    1. Authorization header (Bearer token)
    2. httpOnly cookie (access_token)
    """
    token = None

    # Try Authorization header first
    if credentials:
        token = credentials.credentials
    else:
        # Try cookie
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    # Get user from database
    result = await db.execute(
        select(User).where(User.id == UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user and verify account is not locked."""
    # Check if account is locked
    # TODO: Implement lock check with timestamps

    return current_user


def require_role(*roles):
    """
    Dependency factory to require specific roles.
    Accepts both require_role("admin") and require_role(["admin"]) patterns.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
    """
    # Flatten any list/tuple arguments so both calling patterns work
    flat_roles = []
    for r in roles:
        if isinstance(r, (list, tuple)):
            flat_roles.extend(r)
        else:
            flat_roles.append(str(r))

    async def role_checker(user: User = Depends(get_current_active_user)) -> User:
        if not any(role in (user.roles or []) for role in flat_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(flat_roles)}",
            )
        return user
    return role_checker


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise None.
    Used for endpoints that work for both authenticated and anonymous users.
    """
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


# Common role dependencies
require_admin = require_role("admin")
require_customer = require_role("customer")
require_provider = require_role("provider")
require_advertiser = require_role("advertiser")
require_customer_or_provider = require_role("customer", "provider")


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


# Alias for compatibility with endpoint imports
get_current_user_optional = get_optional_user

def reject_provider_only(current_user):
    """
    Raise 403 if the current user is a provider who is NOT also a customer or admin.
    Anonymous (None) users are allowed. Customer/admin users are allowed.
    Used to gate customer-only actions (RFQ submission, project search) so providers
    cannot shop the marketplace using their provider account.
    """
    if current_user is None:
        return
    roles = set(current_user.roles or [])
    is_provider = "provider" in roles
    is_customer_or_admin = "customer" in roles or "admin" in roles
    if is_provider and not is_customer_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provider accounts cannot submit RFQs or search for firms. Please use a customer account.",
        )

