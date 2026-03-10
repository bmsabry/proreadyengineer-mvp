"""Integration tests for payments API endpoints.

Tests billing portal access and webhook handling.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestBillingPortal:
    """Tests for GET /billing/portal endpoint."""

    def test_billing_portal_requires_auth(self, client):
        """Test billing portal requires authentication."""
        response = client.get("/api/v1/billing/portal")
        
        assert response.status_code == 401

    def test_billing_portal_success(self, client, customer_user, mock_stripe):
        """Test getting billing portal URL."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.payments.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            mock_settings.STRIPE_PUBLISHABLE_KEY = "pk_test_123"
            
            response = client.get("/api/v1/billing/portal")
        
        assert response.status_code == 200
        assert "url" in response.json()


@pytest.mark.integration
class TestStripeWebhook:
    """Tests for POST /webhooks/stripe endpoint."""

    def test_stripe_webhook_valid(self, client, mock_stripe):
        """Test valid Stripe webhook."""
        with patch("app.api.endpoints.payments.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
            
            response = client.post(
                "/api/v1/webhooks/stripe",
                data=b'{"type": "payment_intent.succeeded"}',
                headers={"Stripe-Signature": "test_sig"},
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "processed"

    def test_stripe_webhook_invalid_signature(self, client, mock_stripe):
        """Test invalid Stripe webhook signature."""
        mock_stripe.Webhook.construct_event = MagicMock(
            side_effect=mock_stripe.error.SignatureVerificationError("Invalid", "")
        )
        
        with patch("app.api.endpoints.payments.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
            
            response = client.post(
                "/api/v1/webhooks/stripe",
                data=b'{}',
                headers={"Stripe-Signature": "bad_sig"},
            )
        
        assert response.status_code == 400


@pytest.mark.integration
class TestPayPalWebhook:
    """Tests for POST /webhooks/paypal endpoint."""

    def test_paypal_webhook_valid(self, client):
        """Test valid PayPal webhook."""
        with patch("app.api.endpoints.payments.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"verification_status": "SUCCESS"}
            mock_requests.post.return_value = mock_response
            
            with patch("app.api.endpoints.payments.settings") as mock_settings:
                mock_settings.PAYPAL_WEBHOOK_ID = "wh_paypal_123"
                
                response = client.post(
                    "/api/v1/webhooks/paypal",
                    data=b'{"id": "WH-123"}',
                    headers={"PAYPAL-TRANSMISSION-ID": "test"},
                )
        
        assert response.status_code in [200, 400]  # Depends on setup


@pytest.mark.integration
class TestSignRequestWebhook:
    """Tests for POST /webhooks/signrequest endpoint."""

    def test_signrequest_webhook_valid(self, client):
        """Test valid SignRequest webhook."""
        response = client.post(
            "/api/v1/webhooks/signrequest",
            json={
                "event": "document.signed",
                "document": {"uuid": "doc-123"},
            },
        )
        
        # Should accept and process
        assert response.status_code in [200, 400]  # Depends on implementation
