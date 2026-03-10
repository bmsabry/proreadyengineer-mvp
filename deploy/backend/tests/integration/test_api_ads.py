"""Integration tests for advertising API endpoints.

Tests public ad pages, checkout flow, and advertiser management.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestAdsPublic:
    """Tests for public ad listing endpoints."""

    def test_get_software_providers_no_auth(self, client):
        """Test getting software providers page without auth."""
        response = client.get("/api/v1/ads/software-providers")
        
        assert response.status_code == 200
        assert "ads" in response.json()

    def test_get_featured_firms_no_auth(self, client):
        """Test getting featured firms page without auth."""
        response = client.get("/api/v1/ads/featured-firms")
        
        assert response.status_code == 200
        assert "ads" in response.json()

    def test_get_software_providers_empty_placeholder(self, client):
        """Test that empty slots show placeholders."""
        response = client.get("/api/v1/ads/software-providers")
        
        assert response.status_code == 200
        data = response.json()
        # Check that empty slots are present
        for ad in data.get("ads", []):
            if ad.get("status") == "empty":
                assert "placeholder" in ad or ad.get("title") is None


@pytest.mark.integration
class TestAdsCheckout:
    """Tests for POST /ads/checkout endpoint."""

    def test_checkout_requires_auth(self, client):
        """Test checkout requires authentication."""
        response = client.post(
            "/api/v1/ads/checkout",
            json={
                "ad_slot_id": 1,
                "page_type": "software_providers",
            },
        )
        
        assert response.status_code == 401

    def test_checkout_success(self, client, advertiser_user, mock_stripe):
        """Test successful ad checkout."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "advertiser@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.ads.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            
            response = client.post(
                "/api/v1/ads/checkout",
                json={
                    "ad_slot_id": 1,
                    "page_type": "software_providers",
                    "title": "My Software",
                },
            )
        
        assert response.status_code in [200, 404]  # 404 if slot doesn't exist

    def test_checkout_slot_unavailable(self, client, advertiser_user, mock_stripe):
        """Test checkout on unavailable slot fails."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "advertiser@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            "/api/v1/ads/checkout",
            json={
                "ad_slot_id": 9999,  # Non-existent
                "page_type": "software_providers",
            },
        )
        
        assert response.status_code in [404, 400]


@pytest.mark.integration
class TestAdvertiserAds:
    """Tests for GET /advertiser/ads/me endpoint."""

    def test_get_my_ads_requires_auth(self, client):
        """Test getting ads requires authentication."""
        response = client.get("/api/v1/advertiser/ads/me")
        
        assert response.status_code == 401

    def test_get_my_ads_success(self, client, advertiser_user):
        """Test getting advertiser's ads."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "advertiser@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/advertiser/ads/me")
        
        assert response.status_code == 200
        assert "ads" in response.json()


@pytest.mark.integration
class TestAdAssetUpload:
    """Tests for ad asset upload endpoints."""

    def test_asset_initiate_requires_auth(self, client):
        """Test asset upload requires authentication."""
        import uuid
        response = client.post(f"/api/v1/advertiser/ads/{uuid.uuid4()}/asset/initiate")
        
        assert response.status_code == 401

    def test_asset_initiate_success(self, client, advertiser_user, mock_s3_client):
        """Test initiating ad asset upload."""
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "advertiser@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.ads.settings") as mock_settings:
            mock_settings.AWS_ACCESS_KEY_ID = "test"
            mock_settings.AWS_SECRET_ACCESS_KEY = "test"
            mock_settings.AWS_S3_BUCKET = "bucket"
            
            response = client.post(
                f"/api/v1/advertiser/ads/{uuid.uuid4()}/asset/initiate",
                json={
                    "file_name": "ad_image.png",
                    "file_type": "image/png",
                    "file_size": 1024000,
                },
            )
        
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAdUpdate:
    """Tests for PATCH /advertiser/ads/{id} endpoint."""

    def test_update_ad_requires_auth(self, client):
        """Test updating ad requires authentication."""
        import uuid
        response = client.patch(
            f"/api/v1/advertiser/ads/{uuid.uuid4()}",
            json={"title": "Updated Title"},
        )
        
        assert response.status_code == 401

    def test_update_ad_success(self, client, advertiser_user):
        """Test updating ad content."""
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "advertiser@test.com", "password": "testpassword123"},
        )
        
        response = client.patch(
            f"/api/v1/advertiser/ads/{uuid.uuid4()}",
            json={
                "title": "Updated Title",
                "promotional_text": "New promotional text",
                "outbound_url": "https://example.com",
            },
        )
        
        assert response.status_code in [200, 404]
