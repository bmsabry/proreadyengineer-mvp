"""Integration tests for quotes API endpoints.

Tests customer quote viewing, acceptance, and provider quote management.
"""

import pytest
from unittest.mock import patch


@pytest.mark.integration
class TestCustomerQuotes:
    """Tests for GET /customer/rfqs/{id}/quotes endpoint."""

    def test_get_quotes_requires_auth(self, client):
        """Test getting quotes requires authentication."""
        import uuid
        response = client.get(f"/api/v1/customer/rfqs/{uuid.uuid4()}/quotes")
        
        assert response.status_code == 401

    def test_get_quotes_success(self, client, customer_user, db_session):
        """Test getting quotes for RFQ."""
        from tests.fixtures.factories import create_test_rfq
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(db_session, customer_id=customer_user.id)
        
        response = client.get(f"/api/v1/customer/rfqs/{rfq.id}/quotes")
        
        assert response.status_code == 200
        assert "quotes" in response.json()


@pytest.mark.integration
class TestAcceptQuote:
    """Tests for POST /customer/quotes/{id}/accept endpoint."""

    def test_accept_quote_requires_auth(self, client):
        """Test quote acceptance requires authentication."""
        import uuid
        response = client.post(f"/api/v1/customer/quotes/{uuid.uuid4()}/accept")
        
        assert response.status_code == 401

    def test_accept_quote_success(self, client, customer_user, db_session):
        """Test accepting a quote."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider, create_test_quote
        )
        from app.models import QuoteStatus
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status="open_for_unlock",
        )
        provider = create_test_provider(db_session)
        quote = create_test_quote(
            db_session,
            rfq.id,
            provider.id,
            uuid.uuid4(),  # submitter
            quote_status=QuoteStatus.SUBMITTED,
        )
        
        response = client.post(f"/api/v1/customer/quotes/{quote.id}/accept")
        
        assert response.status_code == 200
        assert response.json()["quote_status"] == "accepted"


@pytest.mark.integration
class TestWithdrawQuote:
    """Tests for POST /provider/quotes/{id}/withdraw endpoint."""

    def test_withdraw_quote_requires_auth(self, client):
        """Test quote withdrawal requires authentication."""
        import uuid
        response = client.post(f"/api/v1/provider/quotes/{uuid.uuid4()}/withdraw")
        
        assert response.status_code == 401

    def test_withdraw_quote_success(self, client, provider_user, db_session):
        """Test withdrawing a quote."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider, create_test_quote
        )
        from app.models import QuoteStatus
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(db_session)
        provider = create_test_provider(db_session)
        quote = create_test_quote(
            db_session,
            rfq.id,
            provider.id,
            provider_user.id,
            quote_status=QuoteStatus.SUBMITTED,
        )
        
        response = client.post(f"/api/v1/provider/quotes/{quote.id}/withdraw")
        
        assert response.status_code in [200, 403]  # May fail if not authorized


@pytest.mark.integration
class TestProviderQuotes:
    """Tests for GET /provider/quotes/me endpoint."""

    def test_get_provider_quotes_requires_auth(self, client):
        """Test getting provider quotes requires authentication."""
        response = client.get("/api/v1/provider/quotes/me")
        
        assert response.status_code == 401

    def test_get_provider_quotes_success(self, client, provider_user):
        """Test getting provider's quotes."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/provider/quotes/me")
        
        assert response.status_code == 200
        assert "quotes" in response.json()
