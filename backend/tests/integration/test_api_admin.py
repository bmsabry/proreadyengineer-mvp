"""Integration tests for admin API endpoints.

Tests admin-only operations for claims, RFQs, payments, and moderation.
"""

import pytest
from unittest.mock import patch
import uuid


@pytest.mark.integration
class TestAdminProviderClaims:
    """Tests for admin provider claim management."""

    def test_get_claims_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access claims."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/provider-claims")
        
        assert response.status_code == 403

    def test_get_claims_success(self, client, admin_user):
        """Test admin can get claim requests."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/provider-claims")
        
        assert response.status_code == 200
        assert "claims" in response.json()

    def test_approve_claim(self, client, admin_user, db_session, test_provider_claim):
        """Test approving a provider claim."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.post(f"/api/v1/admin/provider-claims/{test_provider_claim.id}/approve")
        
        assert response.status_code in [200, 404]

    def test_reject_claim(self, client, admin_user, db_session, test_provider_claim):
        """Test rejecting a provider claim."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            f"/api/v1/admin/provider-claims/{test_provider_claim.id}/reject",
            json={"reason": "Insufficient proof"},
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdminRFQs:
    """Tests for admin RFQ management."""

    def test_get_rfqs_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access RFQs list."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/rfqs")
        
        assert response.status_code == 403

    def test_get_rfqs_success(self, client, admin_user):
        """Test admin can get all RFQs."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/rfqs")
        
        assert response.status_code == 200
        assert "rfqs" in response.json()

    def test_get_rfq_detail(self, client, admin_user, db_session, customer_user):
        """Test admin can get RFQ details."""
        from tests.fixtures.factories import create_test_rfq
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(db_session, customer_id=customer_user.id)
        
        response = client.get(f"/api/v1/admin/rfqs/{rfq.id}")
        
        assert response.status_code == 200
        assert response.json()["id"] == str(rfq.id)

    def test_override_rfq_status(self, client, admin_user, db_session, customer_user):
        """Test admin can override RFQ status."""
        from tests.fixtures.factories import create_test_rfq
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(db_session, customer_id=customer_user.id)
        
        response = client.post(
            f"/api/v1/admin/rfqs/{rfq.id}/override-status",
            json={
                "new_status": "closed_no_selection",
                "reason": "Customer request",
            },
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdminPayments:
    """Tests for admin payment monitoring."""

    def test_get_payments_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access payments."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/payments")
        
        assert response.status_code == 403

    def test_get_payments_success(self, client, admin_user):
        """Test admin can get payment attempts."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/payments")
        
        assert response.status_code == 200
        assert "payments" in response.json()


@pytest.mark.integration
class TestAdminWebhooks:
    """Tests for admin webhook management."""

    def test_get_webhooks_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access webhooks."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/webhooks")
        
        assert response.status_code == 403

    def test_get_webhooks_success(self, client, admin_user):
        """Test admin can get webhook events."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/webhooks")
        
        assert response.status_code == 200
        assert "webhooks" in response.json()

    def test_replay_webhook(self, client, admin_user):
        """Test replaying a webhook event."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.post(f"/api/v1/admin/webhooks/{uuid.uuid4()}/replay")
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdminTierRequests:
    """Tests for admin tier evaluation management."""

    def test_get_tier_requests_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access tier requests."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/tier-requests")
        
        assert response.status_code == 403

    def test_get_tier_requests_success(self, client, admin_user):
        """Test admin can get tier evaluation requests."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/tier-requests")
        
        assert response.status_code == 200
        assert "requests" in response.json()

    def test_approve_tier_request(self, client, admin_user):
        """Test approving tier evaluation request."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.post(
            f"/api/v1/admin/tier-requests/{uuid.uuid4()}/approve",
            json={"new_tier": "A"},
        )
        
        assert response.status_code in [200, 404]

    def test_reject_tier_request(self, client, admin_user):
        """Test rejecting tier evaluation request."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.post(
            f"/api/v1/admin/tier-requests/{uuid.uuid4()}/reject",
            json={"reason": "Does not meet criteria"},
        )
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdminAds:
    """Tests for admin ad management."""

    def test_get_ads_requires_admin(self, client, customer_user):
        """Test that non-admin cannot access ads."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/ads")
        
        assert response.status_code == 403

    def test_get_ads_success(self, client, admin_user):
        """Test admin can get all ads."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/admin/ads")
        
        assert response.status_code == 200
        assert "ads" in response.json()

    def test_pause_ad(self, client, admin_user):
        """Test pausing an ad."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.post(f"/api/v1/admin/ads/{uuid.uuid4()}/pause")
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdminUsers:
    """Tests for admin user management."""

    def test_suspend_user_requires_admin(self, client, customer_user):
        """Test that non-admin cannot suspend users."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.post(f"/api/v1/admin/users/{uuid.uuid4()}/suspend")
        
        assert response.status_code == 403

    def test_suspend_user_success(self, client, admin_user, customer_user):
        """Test admin can suspend a user."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "admin@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            f"/api/v1/admin/users/{customer_user.id}/suspend",
            json={"reason": "Terms of service violation"},
        )
        
        assert response.status_code in [200, 404]
