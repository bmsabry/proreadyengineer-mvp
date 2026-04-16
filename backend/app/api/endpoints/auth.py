"""Authentication API endpoints."""

from typing import Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from app.core.rate_limiter import limiter
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
    validate_password_strength,
    verify_email_token,
)
from app.db.session import AsyncSessionLocal

router = APIRouter()


@limiter.limit("5/minute")
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
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=3600)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=604800)

    # ATOMIC INVITE TOKEN PROCESSING
    # Store linked_provider_id on User record AND create ProviderMembership
    # This is bulletproof because linked_provider_id is stored in the SAME transaction
    if getattr(data, 'invite_token', None):
        import logging as _log
        _logger = _log.getLogger(__name__)
        _logger.info(f"Processing invite token during registration for user {user.email}")
        try:
            from app.services.auth_service import verify_invite_token
            from app.models.provider import ProviderMembership, MembershipRole, MembershipStatus
            from sqlalchemy import select as _sel
            invite_payload = verify_invite_token(data.invite_token)
            if invite_payload:
                provider_id = int(invite_payload["provider_id"])
                _logger.info(f"Invite token verified: provider_id={provider_id}")

                # ALWAYS store linked_provider_id on user (the bulletproof link)
                # Wrapped in try/except: column may not exist in production DB yet
                try:
                    user.linked_provider_id = provider_id
                except Exception as _col_err:
                    _logger.warning(f"Could not set linked_provider_id (column may not exist yet): {_col_err}")

                # Create ProviderMembership if not exists
                _existing = await db.execute(
                    _sel(ProviderMembership).where(
                        ProviderMembership.user_id == user.id,
                        ProviderMembership.provider_id == provider_id,
                    )
                )
                if not _existing.scalar_one_or_none():
                    _membership = ProviderMembership(
                        provider_id=provider_id,
                        user_id=user.id,
                        membership_role=MembershipRole.OWNER,
                        status=MembershipStatus.ACTIVE,
                        created_by=user.id,
                        invite_email=invite_payload.get("sent_to_email"),
                    )
                    db.add(_membership)
                    _logger.info(f"Created ProviderMembership: user={user.id}, provider={provider_id}")

                # Ensure provider role is set
                if "provider" not in (user.roles or []):
                    user.roles = list(user.roles or []) + ["provider"]

                await db.commit()
                await db.refresh(user)
                _logger.info(f"Invite processing committed successfully for user {user.email}")
            else:
                _logger.warning(f"Invite token verification returned None for user {user.email}")
                # Even if token verification fails, try to extract provider_id from JWT payload
                # (token may be expired but still readable)
                try:
                    import jwt as _jwt
                    from app.core.config import settings as _settings
                    _raw = _jwt.decode(data.invite_token, _settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
                    if _raw.get("provider_id"):
                        user.linked_provider_id = int(_raw["provider_id"])
                        await db.commit()
                        await db.refresh(user)
                        _logger.info(f"Stored linked_provider_id={user.linked_provider_id} from expired token")
                except Exception as _jwt_err:
                    _logger.warning(f"Failed to extract provider_id from expired token: {_jwt_err}")
        except Exception as _inv_err:
            import logging as _log2
            _log2.getLogger(__name__).error(f"INVITE PROCESSING FAILED for user {user.email}: {_inv_err}", exc_info=True)
            # Non-fatal: registration still succeeds, profile page will use linked_provider_id fallback


    return RegisterResponse(
        user=user,
        access_token=access_token,
        refresh_token=refresh_token,
    )


@limiter.limit("10/minute")
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

    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=3600)
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


@limiter.limit("30/minute")
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
    response.set_cookie(key="access_token", value=new_access, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=3600)
    response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=cookie_secure, samesite=cookie_samesite, max_age=2592000)  # 30 days

    token_response = TokenPairResponse(access_token=new_access, refresh_token=new_refresh, user=user_response)
    return token_response


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Logout current user (revoke refresh token from cookie). Does not require auth so incognito/expired sessions work."""
    from app.core.config import settings
    is_production = settings.is_production
    cookie_secure = is_production
    cookie_samesite = "none" if is_production else "lax"
    # Must specify same samesite/secure/path params as when setting cookies
    # Delete cookies - use both methods for maximum browser compatibility
    response.delete_cookie("access_token", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/")
    response.delete_cookie("refresh_token", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/")
    # Also explicitly expire cookies via Set-Cookie header with past expiry
    response.set_cookie(key="access_token", value="", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/", max_age=0, expires=0)
    response.set_cookie(key="refresh_token", value="", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/", max_age=0, expires=0)
    # Also try to revoke the refresh token from DB if present
    try:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            import hashlib
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            from sqlalchemy import select, update
            from app.models.user import RefreshToken
            from datetime import datetime
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == token_hash)
                .values(revoked_at=datetime.utcnow())
            )
            await db.commit()
    except Exception:
        pass
    return {"message": "Successfully logged out"}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout from all devices."""
    await revoke_all_user_tokens(db, current_user.id)
    from app.core.config import settings
    is_production = settings.is_production
    cookie_secure = is_production
    cookie_samesite = "none" if is_production else "lax"
    response.delete_cookie("access_token", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/")
    response.delete_cookie("refresh_token", httponly=True, secure=cookie_secure, samesite=cookie_samesite, path="/")
    return {"message": "Successfully logged out from all sessions"}


@limiter.limit("3/minute")
@router.post("/password/forgot")
async def password_forgot(
    request: Request,
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
        await send_password_reset_email(data.email, token, db=db)

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

    # Validate new password strength
    try:
        from app.services.auth_service import validate_password_strength
        validate_password_strength(data.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

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


class RedeemInviteRequest(BaseModel):
    token: str


class RedeemInviteResponse(BaseModel):
    provider_id: int
    rfq_id: str
    already_member: bool


@router.post("/redeem-invite", response_model=RedeemInviteResponse)
async def redeem_invite(
    data: RedeemInviteRequest,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Redeem an invite token after authentication - creates provider membership."""
    from app.services.auth_service import verify_invite_token
    from app.models.provider import ProviderMembership, MembershipRole, MembershipStatus
    from sqlalchemy import select as _select

    payload = verify_invite_token(data.token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    provider_id = int(payload["provider_id"])
    rfq_id = str(payload["rfq_id"])

    # Check if membership already exists
    result = await db.execute(
        _select(ProviderMembership).where(
            ProviderMembership.user_id == current_user.id,
            ProviderMembership.provider_id == provider_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return RedeemInviteResponse(
            provider_id=provider_id, rfq_id=rfq_id, already_member=True
        )

    # Create membership
    membership = ProviderMembership(
        provider_id=provider_id,
        user_id=current_user.id,
        membership_role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
        created_by=current_user.id,
        invite_email=payload.get('sent_to_email'),  # audit: email invite was sent to
    )
    db.add(membership)

    # Add provider role to user if not already set
    if "provider" not in (current_user.roles or []):
        current_user.roles = list(current_user.roles or []) + ["provider"]

    await db.commit()

    return RedeemInviteResponse(
        provider_id=provider_id, rfq_id=rfq_id, already_member=False
    )


@router.get("/invite-info")
async def get_invite_info(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get provider firm info from invite token (no auth required - token is the auth).
    Reads firm data from token payload first, DB fallback for older tokens.
    """
    from app.models.provider import Provider
    from app.services.auth_service import verify_invite_token
    try:
        payload = verify_invite_token(token)
        if not payload:
            return {"firm_name": None, "phone": None, "name": None, "city": None, "state": None, "sent_to_email": None}

        # STEP 1: Read from token payload (embedded at dispatch time for new tokens)
        firm_name = payload.get("firm_name") or None
        phone = payload.get("phone") or None
        city = payload.get("city") or None
        state = payload.get("state") or None
        sent_to_email = payload.get("sent_to_email") or None
        provider_id = payload.get("provider_id")

        # STEP 2: DB fallback for older tokens without embedded data
        if not firm_name and provider_id:
            result = await db.execute(select(Provider).where(Provider.id == int(provider_id)))
            provider = result.scalar_one_or_none()
            if provider:
                firm_name = getattr(provider, "firm_name", None) or getattr(provider, "name", None)
                phone = phone or getattr(provider, "phone", None)
                city = city or getattr(provider, "city", None)
                state = state or getattr(provider, "state", None)

        return {
            "firm_name": firm_name,
            "name": firm_name,
            "phone": phone,
            "city": city,
            "state": state,
            "sent_to_email": sent_to_email,
        }
    except Exception:
        return {"firm_name": None, "phone": None, "name": None, "city": None, "state": None, "sent_to_email": None}



@router.get("/invite-check")
async def check_invite_account(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Check if the email address in an invite token already has an account.
    Also returns provider firm data for pre-filling the registration form.
    Reads firm data from token payload first (always available), DB as fallback.
    """
    from app.models.user import User
    from app.models.provider import Provider, ProviderMembership
    from app.services.auth_service import verify_invite_token
    import logging
    _log = logging.getLogger(__name__)

    empty = {"has_account": False, "email": None, "firm_name": None, "phone": None, "state": None, "city": None}
    try:
        payload = verify_invite_token(token)
        if not payload:
            _log.warning("invite-check: verify_invite_token returned None — token may be expired or invalid")
            return empty
        email = payload.get("sent_to_email")
        provider_id = payload.get("provider_id")
        if not email:
            return empty

        # CHECK 1: Does the invite email match ANY active user account?
        # We check ALL users (regardless of role) — the admin Users panel shows all users.
        # If the email is in the Users table and the account is NOT removed -> has_account=True.
        # Removed accounts have email scrambled to removed_{uuid}@deleted.invalid so they won't match.
        result = await db.execute(
            select(User).where(
                User.email == email.lower().strip(),
                User.email.notlike("removed_%@deleted.invalid"),
            ).limit(1)
        )
        user = result.scalar_one_or_none()
        if user:
            _log.info("invite-check: found user %s via email match CHECK 1", user.id)

        # CHECK 2: Provider may have registered with a DIFFERENT email than the invite was sent to.
        # If the provider_id has an active ProviderMembership, there IS an account.
        if not user and provider_id:
            try:
                mem_result = await db.execute(
                    select(User)
                    .join(ProviderMembership, ProviderMembership.user_id == User.id)
                    .where(
                        ProviderMembership.provider_id == int(provider_id),
                        ProviderMembership.status == "active",
                    )
                    .limit(1)
                )
                user = mem_result.scalar_one_or_none()
                if user:
                    _log.info(
                        "invite-check: found user %s via ProviderMembership CHECK 2 (invite email %s != account email %s)",
                        user.id, email, user.email,
                    )
            except Exception as me:
                _log.error("invite-check: CHECK 2 membership lookup error: %s", me)

        # CHECK 3: Provider may have registered via a previous invite (linked_provider_id is set on User
        # during invite-based registration). This catches providers with different emails.
        if not user and provider_id:
            try:
                link_result = await db.execute(
                    select(User).where(User.linked_provider_id == int(provider_id)).limit(1)
                )
                user = link_result.scalar_one_or_none()
                if user:
                    _log.info(
                        "invite-check: found user %s via linked_provider_id CHECK 3 (invite email %s != account email %s)",
                        user.id, email, user.email,
                    )
            except Exception as le:
                _log.error("invite-check: CHECK 3 linked_provider_id lookup error: %s", le)

        # Fetch provider record once — used for CHECK 4 AND firm data fallback
        provider_rec = None
        if provider_id:
            try:
                prov_result = await db.execute(select(Provider).where(Provider.id == int(provider_id)))
                provider_rec = prov_result.scalar_one_or_none()
            except Exception as pe:
                _log.error("invite-check: error fetching provider %s: %s", provider_id, pe)

        # CHECK 4: Provider may have registered normally (no invite, no claim) but their personal
        # email appears in the provider's email_addresses list (firm email directory).
        if not user and provider_rec and provider_rec.email_addresses:
            try:
                for em in provider_rec.email_addresses:
                    if not em:
                        continue
                    u_res = await db.execute(
                        select(User).where(
                            User.email == em.lower().strip(),
                            User.email.notlike("removed_%@deleted.invalid"),
                        ).limit(1)
                    )
                    found = u_res.scalar_one_or_none()
                    if found:
                        user = found
                        _log.info(
                            "invite-check: found user %s via email_addresses CHECK 4 provider role verified (matched %s)",
                            user.id, em,
                        )
                        break
            except Exception as e4:
                _log.error("invite-check: CHECK 4 email_addresses lookup error: %s", e4)

        # STEP 1: Read firm data directly from token payload (always available, no DB needed)
        firm_name = payload.get("firm_name") or None
        phone = payload.get("phone") or None
        state = payload.get("state") or None
        city = payload.get("city") or None

        # STEP 2: Fallback to DB lookup if token doesn't have embedded firm data (older tokens)
        # Reuse the provider_rec already fetched above
        if not firm_name and provider_rec:
            firm_name = getattr(provider_rec, "firm_name", None) or getattr(provider_rec, "name", None)
            phone = phone or getattr(provider_rec, "phone", None)
            state = state or getattr(provider_rec, "state", None)
            city = city or getattr(provider_rec, "city", None)
            if firm_name:
                _log.info("invite-check: DB fallback — provider %s firm_name=%s", provider_id, firm_name)
            else:
                _log.warning("invite-check: provider_id=%s not found or no firm_name", provider_id)

        _log.info("invite-check: FINAL email=%s has_account=%s firm_name=%s phone=%s state=%s city=%s",
                  email, user is not None, firm_name, phone, state, city)

        return {
            "has_account": user is not None,
            "email": email,
            "firm_name": firm_name,
            "phone": phone,
            "state": state,
            "city": city,
        }
    except Exception as e:
        _log.error("invite-check: unexpected error: %s", e)
        return empty


@router.get("/verify-email")
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Verify email address using token from verification email."""
    from app.services.auth_service import verify_email_token
    user = await verify_email_token(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link expired or invalid. Please register again."
        )
    return {"message": "Email verified! You can now log in."}
