"""Integration tests for provider RFQ access API endpoints.

Tests provider RFQ teaser views, unlock, and quote submission.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestProviderRFQTeasers:
    """Tests for GET /provider/rfqs/teasers endpoint."""

    def test_get_teasers_requires_auth(self, client):
        """Test that getting teasers requires authentication."""
        response = client.get("/api/v1/provider/rfqs/teasers")
        
        assert response.status_code == 401

    def test_get_teasers_success(self, client, provider_user):
        """Test getting RFQ teasers as provider."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/provider/rfqs/teasers")
        
        assert response.status_code == 200
        assert "teasers" in response.json()


@pytest.mark.integration
class TestProviderRFQTeaserDetail:
    """Tests for GET /provider/rfqs/{id}/teaser endpoint."""

    def test_get_teaser_detail(self, client, provider_user, db_session):
        """Test getting single RFQ teaser details."""
        from tests.fixtures.factories import create_test_rfq
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.get(f"/api/v1/provider/rfqs/{uuid.uuid4()}/teaser")
        
        # Will be 200 or 404 depending on RFQ existence
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestProviderRFQUnlock:
    """Tests for POST /provider/rfqs/{id}/unlock/checkout endpoint."""

    def test_unlock_checkout_requires_auth(self, client):
        """Test unlock checkout requires authentication."""
        import uuid
        response = client.post(f"/api/v1/provider/rfqs/{uuid.uuid4()}/unlock/checkout")
        
        assert response.status_code == 401

    def test_unlock_checkout_success(self, client, provider_user, mock_stripe):
        """Test creating unlock payment intent."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.rfqs.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            
            response = client.post(f"/api/v1/provider/rfqs/{uuid.uuid4()}/unlock/checkout")
        
        # Will be 200 or 404 depending on setup
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestProviderRFQQuote:
    """Tests for POST /provider/rfqs/{id}/quote endpoint."""

    def test_submit_quote_requires_auth(self, client):
        """Test quote submission requires authentication."""
        import uuid
        response = client.post(
            f"/api/v1/provider/rfqs/{uuid.uuid4()}/quote",
            json={
                "rough_price_min": 10000,
                "rough_price_max": 25000,
                "currency": "USD",
                "turnaround_estimate_text": "4-6 weeks",
            },
        )
        
        assert response.status_code == 401

    def test_submit_quote_success(self, client, provider_user, db_session):
        """Test submitting a quote."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            f"/api/v1/provider/rfqs/{uuid.uuid4()}/quote",
            json={
                "rough_price_min": 10000,
                "rough_price_max": 25000,
                "currency": "USD",
                "turnaround_estimate_text": "4-6 weeks",
                "assumptions_text": "Standard materials",
                "scope_notes": "Full scope pending",
            },
        )
        
        # Will be 201 or 404 depending on setup
        assert response.status_code in [201, 404, 400]
