"""Authentication API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user, get_client_ip
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    LogoutResponse,
    RegisterResponse,
    LoginResponse,
)
from app.schemas.user import UserResponse
from app.models.user import User
from app.services.auth_service import (
    register_user, authenticate_user,
    create_access_token, create_refresh_token,
    create_refresh_token_record, rotate_refresh_token,
    revoke_all_user_tokens, decode_token,
    generate_password_reset_token, verify_password_reset_token,
    hash_password,
)
from app.db.session import AsyncSessionLocal

router = APIRouter()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    response: Response,
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    try:
        user = await register_user(db, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    await create_refresh_token_record(
        db, user.id, refresh_token,
        get_client_ip(request), request.headers.get("user-agent", "")
    )

    from app.core.config import settings
    is_production = settings.is_production
    cookie_secure = is_production
    cookie_samesite = "none" if is_production else "lax"
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=900)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=604800)

    return RegisterResponse(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    data: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return tokens."""
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    await create_refresh_token_record(
        db, user.id, refresh_token,
        get_client_ip(request), request.headers.get("user-agent", "")
    )

    # Environment-aware cookie settings for cross-origin support
    from app.core.config import settings
    is_production = settings.is_production
    cookie_secure = is_production  # True in production (HTTPS), False in dev
    cookie_samesite = "none" if is_production else "lax"  # none required for cross-origin
    refresh_max_age = 2592000 if data.remember_me else 604800  # 30 days or 7 days

    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=900)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=refresh_max_age)

    from app.schemas.user import UserResponse
    user_response = UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=getattr(user, 'full_name', None),
        business_name=getattr(user, 'business_name', None),
        roles=user.roles or [],
        is_super_admin=user.is_super_admin,
        can_review_claims=user.can_review_claims,
        can_moderate_providers=user.can_moderate_providers,
        can_moderate_ads=user.can_moderate_ads,
        can_manage_refunds=user.can_manage_refunds,
        can_override_rfq_status=getattr(user, 'can_override_rfq_status', False),
        can_review_tier_requests=getattr(user, 'can_review_tier_requests', False),
        failed_login_count=getattr(user, 'failed_login_count', 0),
        locked_until=getattr(user, 'locked_until', None),
        monthly_search_count=getattr(user, 'monthly_search_count', 0),
        search_count_reset_at=getattr(user, 'search_count_reset_at', None),
        last_login_at=getattr(user, 'last_login_at', None),
    )
    return LoginResponse(user=user_response, access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token(
    request: Request,
    response: Response,
    data: Optional[RefreshTokenRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    # Get refresh token from cookie or request body
    refresh_token = None
    if data and hasattr(data, 'refresh_token') and data.refresh_token:
        refresh_token = data.refresh_token
    else:
        # Try to get from cookie
        refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token not found")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Get the user
    from sqlalchemy import select
    from app.models.user import User
    import uuid
    user_id = uuid.UUID(payload["sub"]) if isinstance(payload["sub"], str) else payload["sub"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)

    await rotate_refresh_token(db, refresh_token, new_refresh)

    # Build user response
    from app.schemas.user import UserResponse
    user_response = UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=getattr(user, 'full_name', None),
        business_name=getattr(user, 'business_name', None),
        roles=user.roles or [],
        is_super_admin=user.is_super_admin,
        can_review_claims=user.can_review_claims,
        can_moderate_providers=user.can_moderate_providers,
        can_moderate_ads=user.can_moderate_ads,
        can_manage_refunds=user.can_manage_refunds,
        can_override_rfq_status=getattr(user, 'can_override_rfq_status', False),
        can_review_tier_requests=getattr(user, 'can_review_tier_requests', False),
        failed_login_count=getattr(user, 'failed_login_count', 0),
        locked_until=getattr(user, 'locked_until', None),
        monthly_search_count=getattr(user, 'monthly_search_count', 0),
        search_count_reset_at=getattr(user, 'search_count_reset_at', None),
        last_login_at=getattr(user, 'last_login_at', None),
    )

    # Set updated cookies with environment-aware settings
    from app.core.config import settings
    is_production = settings.is_production
    cookie_secure = is_production
    cookie_samesite = "none" if is_production else "lax"
    # Preserve remember_me by checking existing cookie max-age (keep 30 days if previously set)
    response.set_cookie(key="access_token", value=new_access, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=900)
    response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=2592000)  # 30 days

    token_response = TokenPairResponse(access_token=new_access, refresh_token=new_refresh, user=user_response)
    return token_response


@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user (revoke refresh token from cookie)."""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout from all devices."""
    await revoke_all_user_tokens(db, current_user.id)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Successfully logged out from all sessions"}


@router.post("/password/forgot")
async def password_forgot(
    data: PasswordForgotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Request password reset email."""
    # Look up user by email
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user:
        token = await generate_password_reset_token(db, user.id)
        from app.services.email_service import send_password_reset_email
        await send_password_reset_email(data.email, token)

    # Always return success to prevent email enumeration
    return {"message": "If email exists, reset link sent"}


@router.post("/password/reset")
async def password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password with token."""
    # Verify token and get the token record
    token_record = await verify_password_reset_token(db, data.token)
    if not token_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    # Look up the user by token's user_id
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == token_record.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    # Update user's password
    user.password_hash = hash_password(data.new_password)

    # Mark token as used
    from datetime import datetime
    token_record.used_at = datetime.utcnow()

    await db.commit()

    await revoke_all_user_tokens(db, user.id)
    return {"message": "Password reset successful"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return current_user
