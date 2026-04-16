"""Integration tests for authentication API endpoints.

Tests registration, login, token refresh, logout, and password reset endpoints.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import User, RefreshToken, PasswordResetToken
from app.services.auth_service import hash_password, verify_password
from app.core.config import settings


@pytest.mark.integration
class TestAuthRegister:
    """Tests for POST /auth/register endpoint."""

    def test_register_success(self, client, db_session):
        """Test successful user registration."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@test.com",
                "password": "securepassword123",
                "first_name": "New",
                "last_name": "User",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "newuser@test.com"
        assert "id" in data["user"]
        assert "customer" in data["user"]["roles"]
        assert "password" not in data["user"]
        assert "access_token" in data
        assert "refresh_token" in data

    def test_register_email_normalized(self, client, db_session):
        """Test that email is normalized to lowercase."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "MiXeD@Email.COM",
                "password": "password123",
            },
        )
        
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "mixed@email.com"

    def test_register_duplicate_email(self, client, db_session, customer_user):
        """Test registration with duplicate email returns error."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"].lower()

    def test_register_password_too_short(self, client):
        """Test registration with short password fails."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "shortpass@test.com",
                "password": "12345",
            },
        )
        
        assert response.status_code == 422

    def test_register_missing_email(self, client):
        """Test registration without email fails."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "password": "password123",
            },
        )
        
        assert response.status_code == 422


@pytest.mark.integration
class TestAuthLogin:
    """Tests for POST /auth/login endpoint."""

    def test_login_success(self, client, db_session, customer_user):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        
        # Check cookies
        assert "access_token" in [c.name for c in response.cookies.jar]
        assert "refresh_token" in [c.name for c in response.cookies.jar]

    def test_login_invalid_password(self, client, db_session, customer_user):
        """Test login with wrong password."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "wrongpassword",
            },
        )
        
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client):
        """Test login with non-existent email."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@test.com",
                "password": "password123",
            },
        )
        
        assert response.status_code == 401

    def test_login_account_locked(self, client, db_session, customer_user):
        """Test login to locked account fails."""
        # Lock the account
        customer_user.failed_login_count = 5
        customer_user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db_session.commit()
        
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        assert response.status_code == 403
        assert "locked" in response.json()["detail"].lower()


@pytest.mark.integration
class TestAuthRefresh:
    """Tests for POST /auth/refresh endpoint."""

    def test_refresh_success(self, client, db_session, customer_user):
        """Test successful token refresh."""
        # Login first
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        assert login_response.status_code == 200
        
        # Refresh token
        refresh_response = client.post("/api/v1/auth/refresh")
        
        assert refresh_response.status_code == 200
        data = refresh_response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_without_token(self, client):
        """Test refresh without cookie fails."""
        response = client.post("/api/v1/auth/refresh")
        
        assert response.status_code == 401


@pytest.mark.integration
class TestAuthLogout:
    """Tests for POST /auth/logout endpoint."""

    def test_logout_success(self, client, db_session, customer_user):
        """Test successful logout."""
        # Login first
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        # Logout
        response = client.post("/api/v1/auth/logout")
        
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"
        
        # Verify tokens are cleared from cookies
        assert response.cookies.get("access_token") is None or response.cookies.get("access_token") == ""

    def test_logout_all_sessions(self, client, db_session, customer_user):
        """Test logout from all sessions."""
        # Login first
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        # Logout all
        response = client.post("/api/v1/auth/logout-all")
        
        assert response.status_code == 200
        assert "all sessions" in response.json()["message"].lower()


@pytest.mark.integration
class TestAuthPasswordReset:
    """Tests for password reset endpoints."""

    def test_forgot_password_success(self, client, db_session, customer_user):
        """Test successful forgot password request."""
        response = client.post(
            "/api/v1/auth/password/forgot",
            json={"email": "customer@test.com"},
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "If email exists, reset link sent"

    def test_forgot_password_nonexistent_email(self, client):
        """Test forgot password with non-existent email."""
        response = client.post(
            "/api/v1/auth/password/forgot",
            json={"email": "nonexistent@test.com"},
        )
        
        # Should return same message for security
        assert response.status_code == 200
        assert response.json()["message"] == "If email exists, reset link sent"

    async def test_reset_password_success(self, client, db_session, customer_user):
        """Test successful password reset."""
        # Create reset token
        from app.services.auth_service import create_password_reset_token
        token = await create_password_reset_token(db_session, customer_user.id, ip="127.0.0.1")
        
        response = client.post(
            "/api/v1/auth/password/reset",
            json={
                "token": token,
                "new_password": "newpassword456",
            },
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Password reset successful"
        
        # Verify password changed
        await db_session.refresh(customer_user)
        assert verify_password("newpassword456", customer_user.password_hash)

    def test_reset_password_invalid_token(self, client):
        """Test reset with invalid token fails."""
        response = client.post(
            "/api/v1/auth/password/reset",
            json={
                "token": "invalid_token_123",
                "new_password": "newpassword",
            },
        )
        
        assert response.status_code == 400


@pytest.mark.integration
class TestAuthMe:
    """Tests for GET /auth/me endpoint."""

    def test_get_me_authenticated(self, client, db_session, customer_user):
        """Test getting current user info when authenticated."""
        # Login first
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "customer@test.com",
                "password": "password123",
            },
        )
        
        # Get me
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "customer@test.com"
        assert "customer" in data["roles"]

    def test_get_me_unauthenticated(self, client):
        """Test getting current user info when not authenticated."""
        response = client.get("/api/v1/auth/me")
        
        assert response.status_code == 401
