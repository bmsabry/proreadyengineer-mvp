from __future__ import annotations
# Authentication service with JWT tokens, password hashing, and refresh token management.

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import PasswordResetToken, RefreshToken, User
from app.schemas.auth import UserRegisterRequest


# ---------------------------------------------------------------------------
# Password strength validation
# ---------------------------------------------------------------------------

def validate_password_strength(password: str) -> None:
    msg = (
        "Password must be at least 12 characters and include uppercase, "
        "lowercase, number, and special character"
    )
    if not password or len(password) < 12:
        raise ValueError(msg)
    if not re.search(r'[A-Z]', password):
        raise ValueError(msg)
    if not re.search(r'[a-z]', password):
        raise ValueError(msg)
    if not re.search(r'\d', password):
        raise ValueError(msg)
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:',./<>?\\]", password):
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode('utf-8')
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'type': 'access',
        'iat': now,
        'exp': now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        'jti': secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user_id),
        'type': 'refresh',
        'iat': now,
        'exp': now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        'jti': secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> Optional[User]:
    import logging
    _log = logging.getLogger(__name__)

    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        return None

    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return None

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1

        if user.failed_login_count == 5:
            try:
                from app.services.email_service import send_security_alert_email
                await send_security_alert_email(user.email, db=db)
            except Exception as alert_err:
                _log.warning('Failed to send security alert email to %s: %s', user.email, alert_err)

        if user.failed_login_count >= 10:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
            _log.warning('Account locked for %s after %d failed attempts', user.email, user.failed_login_count)

        await db.commit()
        return None

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return user


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

async def register_user(
    db: AsyncSession, data: UserRegisterRequest
) -> User:
    validate_password_strength(data.password)

    result = await db.execute(select(User).where(User.email == data.email.lower()))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        existing_roles = set(existing_user.roles or [])
        requested_roles = set(list(data.roles) if data.roles else ['customer'])
        # Hard block: prevent provider-customer dual role on same email
        if 'provider' in existing_roles and 'customer' in requested_roles and 'provider' not in requested_roles:
            raise ValueError(
                'This email is already registered as a provider account. '
                'Please log in to your provider account, or use a different email to create a customer account.'
            )
        if 'customer' in existing_roles and 'provider' in requested_roles and 'customer' not in requested_roles:
            raise ValueError(
                'This email is already registered as a customer account. '
                'Please log in to your customer account, or use a different email to create a provider account.'
            )
        raise ValueError('An account with this email already exists. Please log in or use a different email.')

    email_verified: bool = not settings.REQUIRE_EMAIL_VERIFICATION
    email_verify_token_hash: Optional[str] = None
    email_verify_token_expires_at: Optional[datetime] = None
    raw_verify_token: Optional[str] = None

    if settings.REQUIRE_EMAIL_VERIFICATION:
        raw_verify_token = secrets.token_urlsafe(32)
        email_verify_token_hash = _hash_token(raw_verify_token)
        email_verify_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        full_name=data.full_name,
        business_name=data.business_name or getattr(data, 'company_name', None),
        entity_type=data.entity_type,
        state=data.state or None,
        roles=list(data.roles) if data.roles else ['customer'],
        email_verified=email_verified,
        email_verify_token_hash=email_verify_token_hash,
        email_verify_token_expires_at=email_verify_token_expires_at,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    if settings.REQUIRE_EMAIL_VERIFICATION and raw_verify_token:
        try:
            from app.services.email_service import send_email_verification
            await send_email_verification(user.email, raw_verify_token, db=db)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning('Failed to send verification email to %s: %s', user.email, e)

    return user


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

async def verify_email_token(
    db: AsyncSession, token: str
) -> Optional[User]:
    token_hash = _hash_token(token)
    result = await db.execute(
        select(User).where(
            User.email_verify_token_hash == token_hash,
            User.email_verified.is_(False),
            User.email_verify_token_expires_at > datetime.now(timezone.utc),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.email_verified = True
    user.email_verify_token_hash = None
    user.email_verify_token_expires_at = None
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Refresh token management
# ---------------------------------------------------------------------------

async def create_refresh_token_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    token: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RefreshToken:
    token_hash = _hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_ip=ip,
        user_agent=user_agent,
    )
    db.add(refresh_token)
    await db.commit()
    await db.refresh(refresh_token)
    return refresh_token


async def rotate_refresh_token(
    db: AsyncSession, old_token: str, new_token: str
) -> RefreshToken:
    old_hash = _hash_token(old_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == old_hash))
    old_record = result.scalar_one_or_none()
    if not old_record:
        raise ValueError('Invalid refresh token')
    if old_record.revoked_at:
        raise ValueError('Token already revoked')
    if old_record.expires_at < datetime.now(timezone.utc):
        raise ValueError('Token expired')
    new_record = await create_refresh_token_record(db, user_id=old_record.user_id, token=new_token)
    old_record.revoked_at = datetime.now(timezone.utc)
    old_record.replaced_by_token_id = new_record.id
    await db.commit()
    return new_record


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    tokens = result.scalars().all()
    for token in tokens:
        token.revoked_at = datetime.now(timezone.utc)
    await db.commit()


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

async def create_password_reset_token(
    db: AsyncSession, user_id: uuid.UUID, ip: Optional[str] = None
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    reset_token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_ip=ip,
    )
    db.add(reset_token)
    await db.commit()
    return token


async def generate_password_reset_token(
    db: AsyncSession, user_id: uuid.UUID, ip: Optional[str] = None
) -> str:
    from app.models.user import PasswordResetToken as _PRT
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    reset_token = _PRT(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_ip=ip,
    )
    db.add(reset_token)
    await db.commit()
    return token


async def verify_password_reset_token(
    db: AsyncSession, token: str
) -> Optional[PasswordResetToken]:
    token_hash = _hash_token(token)
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def reset_password(
    db: AsyncSession, token: str, new_password: str
) -> bool:
    validate_password_strength(new_password)
    reset_record = await verify_password_reset_token(db, token)
    if not reset_record:
        return False
    user = await db.get(User, reset_record.user_id)
    if not user:
        return False
    user.password_hash = hash_password(new_password)
    reset_record.used_at = datetime.now(timezone.utc)
    await revoke_all_user_tokens(db, user.id)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Invite tokens
# ---------------------------------------------------------------------------

def create_invite_token(
    rfq_id: str,
    provider_id: int,
    dispatch_id: str,
    sent_to_email: str,
    firm_name: Optional[str] = None,
    phone: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    has_existing_account: bool = False,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {
        'sub': 'invite',
        'rfq_id': str(rfq_id),
        'provider_id': provider_id,
        'dispatch_id': str(dispatch_id),
        'sent_to_email': sent_to_email,
        'exp': expire,
        'firm_name': firm_name or '',
        'phone': phone or '',
        'city': city or '',
        'state': state or '',
        'has_existing_account': has_existing_account,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def verify_invite_token(token: str) -> Optional[dict]:
    import logging
    _log = logging.getLogger(__name__)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        if payload.get('sub') != 'invite':
            _log.warning('verify_invite_token: sub mismatch')
            return None
        return payload
    except jwt.ExpiredSignatureError:
        _log.warning('verify_invite_token: token EXPIRED')
        return None
    except jwt.InvalidTokenError as e:
        _log.error('verify_invite_token: invalid token - %s', str(e))
        return None
    except Exception as e:
        _log.error('verify_invite_token: unexpected error - %s', str(e))
        return None
