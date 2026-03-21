from __future__ import annotations
"""Authentication service with JWT tokens, password hashing, and refresh token management."""

import hashlib
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


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password.

    Returns:
        str: Bcrypt hashed password.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: Plain text password.
        password_hash: Stored bcrypt hash.

    Returns:
        bool: True if password matches.
    """
    password_bytes = password.encode("utf-8")
    hash_bytes = password_hash.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hash_bytes)


def create_access_token(user_id: uuid.UUID) -> str:
    """Create a short-lived JWT access token.

    Args:
        user_id: User's UUID.

    Returns:
        str: JWT access token, expires in 15 minutes.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a long-lived JWT refresh token.

    Args:
        user_id: User's UUID.

    Returns:
        str: JWT refresh token, expires in 7 days.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string.

    Returns:
        dict: Decoded token payload.

    Raises:
        jwt.ExpiredSignatureError: If token is expired.
        jwt.InvalidTokenError: If token is invalid.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def _hash_token(token: str) -> str:
    """Hash a token for secure storage.

    Args:
        token: Raw token string.

    Returns:
        str: SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> Optional[User]:
    """Authenticate user by email and password.

    Args:
        db: Database session.
        email: User's email address.
        password: Plain text password.

    Returns:
        User | None: Authenticated user or None if invalid.
    """
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    if not user:
        return None

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        return None

    if not verify_password(password, user.password_hash):
        # Increment failed login count
        user.failed_login_count += 1

        # Lock account after 5 failed attempts (15 minutes)
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)

        await db.commit()
        return None

    # Reset failed login count on success
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    return user


async def register_user(
    db: AsyncSession, data: UserRegisterRequest
) -> User:
    """Register a new user account.

    Args:
        db: Database session.
        data: Registration request data.

    Returns:
        User: Created user.

    Raises:
        ValueError: If email already exists.
    """
    # Check for existing user
    result = await db.execute(select(User).where(User.email == data.email.lower()))
    if result.scalar_one_or_none():
        raise ValueError("Email already exists")

    # Create user
    user = User(
        email=data.email.lower(),
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        full_name=data.full_name,
        business_name=data.business_name,
        roles=list(data.roles) if data.roles else ["customer"],  # Use requested role or default to customer
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


async def create_refresh_token_record(
    db: AsyncSession,
    user_id: uuid.UUID,
    token: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RefreshToken:
    """Create a server-side refresh token record.

    Args:
        db: Database session.
        user_id: User's UUID.
        token: Raw JWT refresh token.
        ip: Client IP address.
        user_agent: Client user agent.

    Returns:
        RefreshToken: Created refresh token record.
    """
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
    """Rotate a refresh token (token rotation security).

    Args:
        db: Database session.
        old_token: Previous refresh token.
        new_token: New refresh token.

    Returns:
        RefreshToken: New refresh token record.

    Raises:
        ValueError: If old token is invalid, expired, or revoked.
    """
    old_hash = _hash_token(old_token)

    # Find old token
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    old_record = result.scalar_one_or_none()

    if not old_record:
        raise ValueError("Invalid refresh token")

    if old_record.revoked_at:
        raise ValueError("Token already revoked")

    if old_record.expires_at < datetime.now(timezone.utc):
        raise ValueError("Token expired")

    # Create new token record
    new_record = await create_refresh_token_record(
        db,
        user_id=old_record.user_id,
        token=new_token,
    )

    # Revoke old token and link to new one
    old_record.revoked_at = datetime.now(timezone.utc)
    old_record.replaced_by_token_id = new_record.id

    await db.commit()

    return new_record


async def revoke_all_user_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Revoke all refresh tokens for a user (logout all sessions).

    Args:
        db: Database session.
        user_id: User's UUID.
    """
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


async def create_password_reset_token(
    db: AsyncSession, user_id: uuid.UUID, ip: Optional[str] = None
) -> str:
    """Create a password reset token.

    Args:
        db: Database session.
        user_id: User's UUID.
        ip: Client IP address.

    Returns:
        str: Raw password reset token (1-hour expiry).
    """
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_ip=ip,
    )

    db.add(reset_token)
    await db.commit()

    return token




async def generate_password_reset_token(
    db: AsyncSession, user_id: uuid.UUID, ip: Optional[str] = None
) -> str:
    """Generate a password reset token for a user.

    Args:
        db: Database session.
        user_id: User's UUID.
        ip: Client IP address.

    Returns:
        str: Raw password reset token.
    """
    from app.models.user import PasswordResetToken

    # Generate random token
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)

    # Create token record
    reset_token = PasswordResetToken(
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
    """Verify a password reset token.

    Args:
        db: Database session.
        token: Raw reset token.

    Returns:
        PasswordResetToken | None: Token record if valid and unused.
    """
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
    """Reset user password using a reset token.

    Args:
        db: Database session.
        token: Raw reset token.
        new_password: New plain text password.

    Returns:
        bool: True if password was reset successfully.
    """
    reset_record = await verify_password_reset_token(db, token)
    if not reset_record:
        return False

    # Update password
    user = await db.get(User, reset_record.user_id)
    if not user:
        return False

    user.password_hash = hash_password(new_password)
    reset_record.used_at = datetime.now(timezone.utc)

    # Revoke all sessions for security
    await revoke_all_user_tokens(db, user.id)

    await db.commit()
    return True

def create_invite_token(rfq_id: str, provider_id: int, dispatch_id: str, sent_to_email: str) -> str:
    """Create a signed JWT invite token for provider teaser email links. Expires in 7 days."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": "invite",
        "rfq_id": str(rfq_id),
        "provider_id": provider_id,
        "dispatch_id": str(dispatch_id),
        "sent_to_email": sent_to_email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def verify_invite_token(token: str) -> Optional[dict]:
    """Verify and decode an invite token. Returns payload dict or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("sub") != "invite":
            return None
        return payload
    except Exception:
        return None
