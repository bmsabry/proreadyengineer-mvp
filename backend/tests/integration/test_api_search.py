"""Integration tests for search API endpoints.

Tests public search, file uploads, and quota enforcement.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.models import SearchRequest, IPUsageTracking


@pytest.mark.integration
class TestSearchQuery:
    """Tests for POST /search/query endpoint."""

    def test_search_anonymous_success(self, client, mock_openai):
        """Test anonymous search returns results."""
        with patch("app.api.endpoints.search.search_providers") as mock_search:
            mock_search.return_value = [
                {
                    "provider": MagicMock(
                        id=1,
                        name="Test Provider",
                        primary_specialty="Mechanical Engineering",
                        business_description="Test description",
                        business_evaluation_tier="A",
                    ),
                    "composite_score": 85,
                    "specialty_score": 20,
                    "capabilities_score": 40,
                    "tier_score": 25,
                }
            ]
            
            response = client.post(
                "/api/v1/search/query",
                json={"query": "mechanical engineering FEA"},
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "remaining_searches" in data

    def test_search_authenticated_success(self, client, customer_user, mock_openai):
        """Test authenticated search with user context."""
        # Login
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.search.search_providers") as mock_search:
            mock_search.return_value = []
            
            response = client.post(
                "/api/v1/search/query",
                json={"query": "need ANSYS simulation"},
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert data["remaining_searches"] == 9  # Started with 10

    def test_search_empty_query(self, client):
        """Test search with empty query."""
        response = client.post(
            "/api/v1/search/query",
            json={"query": ""},
        )
        
        assert response.status_code == 422

    def test_search_quota_exceeded_anonymous(self, client, db_session):
        """Test anonymous search quota enforcement."""
        # Use up quota
        for i in range(3):
            with patch("app.api.endpoints.search.search_providers") as mock_search:
                mock_search.return_value = []
                client.post(
                    "/api/v1/search/query",
                    json={"query": f"test {i}"},
                    headers={"X-Forwarded-For": "192.168.1.1"},
                )
        
        # 4th search should fail
        with patch("app.api.endpoints.search.search_providers") as mock_search:
            mock_search.return_value = []
            response = client.post(
                "/api/v1/search/query",
                json={"query": "exceeded"},
                headers={"X-Forwarded-For": "192.168.1.1"},
            )
        
        assert response.status_code == 429

    def test_search_results_contain_required_fields(self, client, mock_openai):
        """Test search results include all required provider fields."""
        with patch("app.api.endpoints.search.search_providers") as mock_search:
            mock_search.return_value = [
                {
                    "provider": MagicMock(
                        id=1,
                        name="Provider Inc",
                        primary_specialty="Civil Engineering",
                        business_description="Description here",
                        business_evaluation_tier="B",
                        capabilities=["FEA", "CAD"],
                        software_tools=["ANSYS"],
                    ),
                    "composite_score": 75,
                    "specialty_score": 20,
                    "capabilities_score": 35,
                    "tier_score": 20,
                }
            ]
            
            response = client.post(
                "/api/v1/search/query",
                json={"query": "civil engineering"},
            )
        
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) > 0
        
        result = results[0]
        assert "id" in result
        assert "name" in result
        assert "primary_specialty" in result
        assert "composite_score" in result


@pytest.mark.integration
class TestSearchUpload:
    """Tests for search file upload endpoints."""

    def test_upload_initiate_success(self, client, mock_s3_client):
        """Test successful upload URL generation."""
        with patch("app.api.endpoints.search.settings") as mock_settings:
            mock_settings.AWS_ACCESS_KEY_ID = "test"
            mock_settings.AWS_SECRET_ACCESS_KEY = "test"
            mock_settings.AWS_S3_BUCKET = "bucket"
            
            response = client.post(
                "/api/v1/search/upload/initiate",
                json={
                    "file_name": "specs.pdf",
                    "file_type": "application/pdf",
                    "file_size": 1024000,
                },
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "fields" in data
        assert "key" in data

    def test_upload_initiate_invalid_type(self, client):
        """Test upload with invalid file type."""
        response = client.post(
            "/api/v1/search/upload/initiate",
            json={
                "file_name": "malware.exe",
                "file_type": "application/x-executable",
                "file_size": 1024000,
            },
        )
        
        assert response.status_code == 400

    def test_upload_initiate_too_large(self, client):
        """Test upload with file exceeding size limit."""
        response = client.post(
            "/api/v1/search/upload/initiate",
            json={
                "file_name": "huge.pdf",
                "file_type": "application/pdf",
                "file_size": 50 * 1024 * 1024,  # 50MB
            },
        )
        
        assert response.status_code == 400

    def test_upload_complete_success(self, client, db_session):
        """Test successful upload completion."""
        response = client.post(
            "/api/v1/search/upload/complete",
            json={
                "key": "uploads/search/test_file.pdf",
                "original_filename": "specs.pdf",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "search_id" in data
        assert data["status"] == "processing"
