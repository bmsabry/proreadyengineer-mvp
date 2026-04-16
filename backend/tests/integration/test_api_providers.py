"""Integration tests for provider API endpoints.

Tests public provider viewing, claim requests, and profile management.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestProviderPublic:
    """Tests for GET /providers/{id}/public endpoint."""

    def test_get_provider_public_success(self, client, db_session, test_provider):
        """Test getting public provider info."""
        response = client.get(f"/api/v1/providers/{test_provider.id}/public")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_provider.id
        assert data["name"] == test_provider.name
        assert data["primary_specialty"] == test_provider.primary_specialty

    def test_get_provider_public_not_found(self, client):
        """Test getting non-existent provider."""
        response = client.get("/api/v1/providers/99999/public")
        
        assert response.status_code == 404


@pytest.mark.integration
class TestProviderClaimSearch:
    """Tests for POST /providers/claim-search endpoint."""

    def test_claim_search_success(self, client, db_session, test_provider):
        """Test searching for providers to claim."""
        with patch("app.api.endpoints.providers.search_providers") as mock_search:
            mock_search.return_value = [
                {"provider": test_provider, "composite_score": 90}
            ]
            
            response = client.post(
                "/api/v1/providers/claim-search",
                json={"query": "Test Provider"},
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


@pytest.mark.integration
class TestProviderClaims:
    """Tests for provider claim endpoints."""

    def test_create_claim_request_success(self, client, db_session, provider_user, test_provider):
        """Test creating a provider claim request."""
        # Login as provider user
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            "/api/v1/provider-claims",
            json={
                "provider_id": test_provider.id,
                "proof_type": "email_domain",
                "proof_payload": {"email": f"admin@{test_provider.email_addresses[0].split('@')[1]}"},
                "submitted_notes": "I own this company",
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["provider_id"] == test_provider.id
        assert data["status"] == "pending"

    def test_create_claim_request_unauthenticated(self, client, test_provider):
        """Test claim request without authentication fails."""
        response = client.post(
            "/api/v1/provider-claims",
            json={
                "provider_id": test_provider.id,
                "proof_type": "email_domain",
                "proof_payload": {},
            },
        )
        
        assert response.status_code == 401

    def test_get_my_claims(self, client, db_session, provider_user, test_provider):
        """Test getting user's claim requests."""
        # Login and create a claim
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        client.post(
            "/api/v1/provider-claims",
            json={
                "provider_id": test_provider.id,
                "proof_type": "email_domain",
                "proof_payload": {},
            },
        )
        
        response = client.get("/api/v1/provider-claims/me")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


@pytest.mark.integration
class TestProviderProfile:
    """Tests for provider profile endpoints."""

    def test_get_profile_success(self, client, db_session, provider_user, test_provider, test_provider_membership):
        """Test getting provider profile."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.get("/api/v1/provider/profile")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_provider.id

    def test_update_profile_success(self, client, db_session, provider_user, test_provider, test_provider_membership):
        """Test updating provider profile."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.patch(
            "/api/v1/provider/profile",
            json={
                "business_description": "Updated description",
                "primary_specialty": "Updated Specialty",
            },
        )
        
        assert response.status_code == 200
        assert response.json()["business_description"] == "Updated description"

    def test_request_rank_up(self, client, db_session, provider_user, test_provider, test_provider_membership):
        """Test submitting rank up request."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "provider@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            "/api/v1/provider/profile/request-rank-up",
            json={
                "requested_reason": "We have expanded our capabilities",
                "supporting_payload": {"new_certifications": ["ISO 9001"]},
            },
        )
        
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
