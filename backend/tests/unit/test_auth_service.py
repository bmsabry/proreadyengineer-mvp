"""Unit tests for authentication service.

Tests password hashing, JWT token creation/validation, refresh token rotation,
user authentication, and password reset flows.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import jwt
import pytest
from freezegun import freeze_time
from sqlalchemy import select

from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    authenticate_user,
    register_user,
    create_refresh_token_record,
    rotate_refresh_token,
    revoke_all_user_tokens,
    create_password_reset_token,
    verify_password_reset_token,
    reset_password,
)
from app.models import User, RefreshToken, PasswordResetToken
from app.schemas.auth import UserRegisterRequest


@pytest.mark.unit
class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a valid bcrypt hash."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert isinstance(hashed, str)
        assert hashed.startswith("$")
        assert len(hashed) > 50  # bcrypt hashes are long

    def test_hash_password_different_salts(self):
        """Test that hashing same password twice gives different hashes."""
        password = "testpassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2  # Different salts
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "testpassword123"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with wrong password."""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_unicode(self):
        """Test password verification with unicode characters."""
        password = "пароль123密码"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True


@pytest.mark.unit
class TestJWTAccessToken:
    """Tests for JWT access token creation and validation."""

    def test_create_access_token_returns_string(self):
        """Test that create_access_token returns a valid JWT string."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        
        assert isinstance(token, str)
        assert "." in token  # JWT format: header.payload.signature

    def test_create_access_token_contains_correct_claims(self):
        """Test that access token contains expected claims."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        
        decoded = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_signature": False})
        
        assert decoded["sub"] == str(user_id)
        assert decoded["type"] == "access"
        assert "iat" in decoded
        assert "exp" in decoded
        assert "jti" in decoded

    @freeze_time("2024-01-01 12:00:00")
    def test_create_access_token_expiration(self):
        """Test that access token has correct expiration time (15 minutes)."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        
        decoded = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_signature": False})
        
        iat = datetime.utcfromtimestamp(decoded["iat"])
        exp = datetime.utcfromtimestamp(decoded["exp"])
        
        assert iat == datetime(2024, 1, 1, 12, 0, 0)
        assert exp == datetime(2024, 1, 1, 12, 15, 0)  # 15 minutes later

    def test_decode_token_valid(self):
        """Test decoding a valid token."""
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        
        # Patch settings for test
        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.SECRET_KEY = "test-secret"
            mock_settings.ALGORITHM = "HS256"
            decoded = decode_token(token)
        
        assert decoded["sub"] == str(user_id)
        assert decoded["type"] == "access"

    def test_decode_token_expired(self):
        """Test that decoding an expired token raises error."""
        # Create a token that's already expired
        with freeze_time("2024-01-01 12:00:00"):
            user_id = uuid.uuid4()
            with patch("app.services.auth_service.settings") as mock_settings:
                mock_settings.SECRET_KEY = "test-secret"
                mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 0  # Expires immediately
                mock_settings.ALGORITHM = "HS256"
                token = create_access_token(user_id)
        
        # Try to decode after expiration
        with freeze_time("2024-01-01 13:00:00"):
            with patch("app.services.auth_service.settings") as mock_settings:
                mock_settings.SECRET_KEY = "test-secret"
                mock_settings.ALGORITHM = "HS256"
                with pytest.raises(jwt.ExpiredSignatureError):
                    decode_token(token)


@pytest.mark.unit
class TestJWTRefreshToken:
    """Tests for JWT refresh token creation and validation."""

    def test_create_refresh_token_returns_string(self):
        """Test that create_refresh_token returns a valid JWT string."""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        
        assert isinstance(token, str)
        assert "." in token

    def test_create_refresh_token_contains_correct_claims(self):
        """Test that refresh token contains expected claims."""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        
        decoded = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_signature": False})
        
        assert decoded["sub"] == str(user_id)
        assert decoded["type"] == "refresh"
        assert "iat" in decoded
        assert "exp" in decoded
        assert "jti" in decoded

    @freeze_time("2024-01-01 12:00:00")
    def test_create_refresh_token_expiration(self):
        """Test that refresh token has correct expiration time (7 days)."""
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        
        decoded = jwt.decode(token, "test-secret", algorithms=["HS256"], options={"verify_signature": False})
        
        iat = datetime.utcfromtimestamp(decoded["iat"])
        exp = datetime.utcfromtimestamp(decoded["exp"])
        
        assert iat == datetime(2024, 1, 1, 12, 0, 0)
        assert exp == datetime(2024, 1, 8, 12, 0, 0)  # 7 days later


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserAuthentication:
    """Tests for user authentication."""

    async def test_authenticate_user_success(self, db_session, customer_user):
        """Test successful user authentication."""
        user = await authenticate_user(db_session, "customer@test.com", "testpassword123")
        
        assert user is not None
        assert user.id == customer_user.id
        assert user.failed_login_count == 0  # Reset on success
        assert user.last_login_at is not None

    async def test_authenticate_user_wrong_password(self, db_session, customer_user):
        """Test authentication with wrong password increments failed count."""
        user = await authenticate_user(db_session, "customer@test.com", "wrongpassword")
        
        assert user is None
        
        # Refresh user from DB to check failed count
        result = await db_session.execute(select(User).where(User.id == customer_user.id))
        refreshed_user = result.scalar_one()
        assert refreshed_user.failed_login_count == 1

    async def test_authenticate_user_nonexistent_email(self, db_session):
        """Test authentication with non-existent email."""
        user = await authenticate_user(db_session, "nonexistent@test.com", "password123")
        
        assert user is None

    async def test_authenticate_user_locked_account(self, db_session, customer_user):
        """Test authentication with locked account."""
        # Lock the account
        customer_user.failed_login_count = 5
        customer_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        await db_session.commit()
        
        user = await authenticate_user(db_session, "customer@test.com", "testpassword123")
        
        assert user is None

    async def test_authenticate_user_locks_after_5_attempts(self, db_session, customer_user):
        """Test that account locks after 5 failed attempts."""
        # 4 failed attempts
        for _ in range(4):
            await authenticate_user(db_session, "customer@test.com", "wrongpassword")
        
        result = await db_session.execute(select(User).where(User.id == customer_user.id))
        user = result.scalar_one()
        assert user.failed_login_count == 4
        assert user.locked_until is None
        
        # 5th failed attempt
        await authenticate_user(db_session, "customer@test.com", "wrongpassword")
        
        result = await db_session.execute(select(User).where(User.id == customer_user.id))
        user = result.scalar_one()
        assert user.failed_login_count == 5
        assert user.locked_until is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestUserRegistration:
    """Tests for user registration."""

    async def test_register_user_success(self, db_session):
        """Test successful user registration."""
        data = UserRegisterRequest(
            email="newuser@test.com",
            password="securepassword123",
            first_name="New",
            last_name="User",
        )
        
        user = await register_user(db_session, data)
        
        assert user.email == "newuser@test.com"
        assert user.first_name == "New"
        assert user.last_name == "User"
        assert "customer" in user.roles
        assert verify_password("securepassword123", user.password_hash)

    async def test_register_user_email_normalized(self, db_session):
        """Test that email is normalized to lowercase."""
        data = UserRegisterRequest(
            email="MiXeD@Email.COM",
            password="securepassword123",
        )
        
        user = await register_user(db_session, data)
        
        assert user.email == "mixed@email.com"

    async def test_register_user_duplicate_email(self, db_session, customer_user):
        """Test registration with duplicate email raises error."""
        data = UserRegisterRequest(
            email="customer@test.com",
            password="password123",
        )
        
        with pytest.raises(ValueError, match="Email already registered"):
            await register_user(db_session, data)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRefreshTokenManagement:
    """Tests for refresh token creation and rotation."""

    async def test_create_refresh_token_record(self, db_session, customer_user):
        """Test creating a refresh token record."""
        token = "test_refresh_token_123"
        
        record = await create_refresh_token_record(
            db_session,
            customer_user.id,
            token,
            ip="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )
        
        assert record.user_id == customer_user.id
        assert record.token_hash is not None
        assert record.expires_at > datetime.utcnow()
        assert record.created_ip == "192.168.1.1"
        assert record.user_agent == "TestBrowser/1.0"
        assert record.revoked_at is None

    async def test_rotate_refresh_token_success(self, db_session, customer_user):
        """Test successful token rotation."""
        old_token = "old_token_123"
        new_token = "new_token_456"
        
        # Create initial token
        old_record = await create_refresh_token_record(
            db_session, customer_user.id, old_token
        )
        
        # Rotate
        new_record = await rotate_refresh_token(db_session, old_token, new_token)
        
        assert new_record.user_id == customer_user.id
        
        # Check old token is revoked
        await db_session.refresh(old_record)
        assert old_record.revoked_at is not None
        assert old_record.replaced_by_token_id == new_record.id

    async def test_rotate_refresh_token_invalid(self, db_session):
        """Test rotation with invalid token raises error."""
        with pytest.raises(ValueError, match="Invalid refresh token"):
            await rotate_refresh_token(db_session, "invalid_token", "new_token")

    async def test_rotate_refresh_token_revoked(self, db_session, customer_user):
        """Test rotation with already revoked token raises error."""
        old_token = "old_token_123"
        
        # Create and revoke
        record = await create_refresh_token_record(
            db_session, customer_user.id, old_token
        )
        record.revoked_at = datetime.utcnow()
        await db_session.commit()
        
        with pytest.raises(ValueError, match="Token already revoked"):
            await rotate_refresh_token(db_session, old_token, "new_token")

    async def test_revoke_all_user_tokens(self, db_session, customer_user):
        """Test revoking all tokens for a user."""
        # Create multiple tokens
        for i in range(3):
            await create_refresh_token_record(db_session, customer_user.id, f"token_{i}")
        
        await revoke_all_user_tokens(db_session, customer_user.id)
        
        # Check all revoked
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == customer_user.id)
        )
        tokens = result.scalars().all()
        
        assert len(tokens) == 3
        for token in tokens:
            assert token.revoked_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
class TestPasswordReset:
    """Tests for password reset flow."""

    async def test_create_password_reset_token(self, db_session, customer_user):
        """Test creating a password reset token."""
        token = await create_password_reset_token(
            db_session, customer_user.id, ip="192.168.1.1"
        )
        
        assert isinstance(token, str)
        assert len(token) > 20
        
        # Verify record created
        result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == customer_user.id)
        )
        record = result.scalar_one()
        
        assert record.token_hash is not None
        assert record.expires_at > datetime.utcnow()
        assert record.created_ip == "192.168.1.1"
        assert record.used_at is None

    async def test_verify_password_reset_token_valid(self, db_session, customer_user):
        """Test verifying a valid reset token."""
        token = await create_password_reset_token(db_session, customer_user.id)
        
        record = await verify_password_reset_token(db_session, token)
        
        assert record is not None
        assert record.user_id == customer_user.id

    async def test_verify_password_reset_token_invalid(self, db_session):
        """Test verifying an invalid reset token."""
        record = await verify_password_reset_token(db_session, "invalid_token")
        
        assert record is None

    async def test_verify_password_reset_token_used(self, db_session, customer_user):
        """Test that used tokens cannot be verified."""
        token = await create_password_reset_token(db_session, customer_user.id)
        
        # Mark as used
        result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == customer_user.id)
        )
        record = result.scalar_one()
        record.used_at = datetime.utcnow()
        await db_session.commit()
        
        # Try to verify
        verified = await verify_password_reset_token(db_session, token)
        assert verified is None

    async def test_verify_password_reset_token_expired(self, db_session, customer_user):
        """Test that expired tokens cannot be verified."""
        token = await create_password_reset_token(db_session, customer_user.id)
        
        # Make it expired
        result = await db_session.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == customer_user.id)
        )
        record = result.scalar_one()
        record.expires_at = datetime.utcnow() - timedelta(hours=2)
        await db_session.commit()
        
        # Try to verify
        verified = await verify_password_reset_token(db_session, token)
        assert verified is None

    async def test_reset_password_success(self, db_session, customer_user):
        """Test successful password reset."""
        old_hash = customer_user.password_hash
        token = await create_password_reset_token(db_session, customer_user.id)
        
        success = await reset_password(db_session, token, "newpassword456")
        
        assert success is True
        
        # Verify password changed
        await db_session.refresh(customer_user)
        assert customer_user.password_hash != old_hash
        assert verify_password("newpassword456", customer_user.password_hash)

    async def test_reset_password_invalid_token(self, db_session):
        """Test reset with invalid token returns False."""
        success = await reset_password(db_session, "invalid_token", "newpassword")
        
        assert success is False

    async def test_reset_password_revokes_all_sessions(self, db_session, customer_user):
        """Test that password reset revokes all sessions."""
        # Create a session
        await create_refresh_token_record(db_session, customer_user.id, "session_token")
        
        token = await create_password_reset_token(db_session, customer_user.id)
        await reset_password(db_session, token, "newpassword456")
        
        # Check session revoked
        result = await db_session.execute(
            select(RefreshToken).where(RefreshToken.user_id == customer_user.id)
        )
        session = result.scalar_one()
        assert session.revoked_at is not None
