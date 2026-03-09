"""Integration tests for RFQ API endpoints.

Tests RFQ creation, submission, file uploads, NDA checkout, and status retrieval.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestCreateRFQ:
    """Tests for POST /rfqs endpoint."""

    def test_create_rfq_anonymous(self, client):
        """Test creating RFQ as guest."""
        response = client.post(
            "/api/v1/rfqs",
            json={
                "customer_email": "guest@test.com",
                "business_name": "Guest Corp",
                "contact_name": "Guest User",
                "project_description": "Need structural analysis",
                "urgency": "High",
                "tollgate_phases": ["TG1", "TG3"],
                "nda_required": False,
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["customer_email"] == "guest@test.com"
        assert data["rfq_status"] == "draft"
        assert "id" in data

    def test_create_rfq_authenticated(self, client, customer_user):
        """Test creating RFQ as authenticated user."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        response = client.post(
            "/api/v1/rfqs",
            json={
                "customer_email": "customer@test.com",
                "business_name": "Customer Corp",
                "contact_name": "Customer User",
                "project_description": "Need FEA simulation",
                "urgency": "Medium",
                "tollgate_phases": ["TG0"],
                "nda_required": True,
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["customer_user_id"] is not None
        assert data["nda_required"] is True

    def test_create_rfq_missing_required_fields(self, client):
        """Test creating RFQ without required fields fails."""
        response = client.post(
            "/api/v1/rfqs",
            json={
                "customer_email": "test@test.com",
                # Missing other required fields
            },
        )
        
        assert response.status_code == 422


@pytest.mark.integration
class TestGetRFQ:
    """Tests for GET /rfqs/{id} endpoint."""

    def test_get_rfq_owner(self, client, db_session, customer_user):
        """Test owner can get their RFQ."""
        from tests.fixtures.factories import create_test_rfq
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(db_session, customer_id=customer_user.id)
        
        response = client.get(f"/api/v1/rfqs/{rfq.id}")
        
        assert response.status_code == 200
        assert response.json()["id"] == str(rfq.id)

    def test_get_rfq_not_found(self, client, customer_user):
        """Test getting non-existent RFQ."""
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        import uuid
        response = client.get(f"/api/v1/rfqs/{uuid.uuid4()}")
        
        assert response.status_code == 404


@pytest.mark.integration
class TestRFQUpload:
    """Tests for RFQ file upload endpoints."""

    def test_upload_initiate_success(self, client, customer_user, mock_s3_client):
        """Test initiating file upload."""
        from tests.fixtures.factories import create_test_rfq
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        with patch("app.api.endpoints.rfqs.settings") as mock_settings:
            mock_settings.AWS_ACCESS_KEY_ID = "test"
            mock_settings.AWS_SECRET_ACCESS_KEY = "test"
            mock_settings.AWS_S3_BUCKET = "bucket"
            
            response = client.post(
                f"/api/v1/rfqs/{uuid.uuid4()}/files/initiate",
                json={
                    "file_name": "specs.pdf",
                    "file_type": "application/pdf",
                    "file_size": 1024000,
                },
            )
        
        assert response.status_code == 200
        assert "url" in response.json()


@pytest.mark.integration
class TestRFQNDA:
    """Tests for RFQ NDA endpoints."""

    def test_nda_checkout_requires_login(self, client):
        """Test NDA checkout requires authentication."""
        import uuid
        response = client.post(f"/api/v1/rfqs/{uuid.uuid4()}/nda/checkout")
        
        assert response.status_code == 401

    def test_nda_checkout_success(self, client, customer_user, mock_stripe):
        """Test NDA checkout creates payment intent."""
        from tests.fixtures.factories import create_test_rfq
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(
            client.app.state.db,
            customer_id=customer_user.id,
            rfq_status="draft",
            nda_required=True,
        )
        
        with patch("app.api.endpoints.rfqs.settings") as mock_settings:
            mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
            
            response = client.post(f"/api/v1/rfqs/{rfq.id}/nda/checkout")
        
        assert response.status_code == 200
        data = response.json()
        assert "client_secret" in data
        assert data["amount"] == 500  # $5.00


@pytest.mark.integration
class TestRFQSubmit:
    """Tests for POST /rfqs/{id}/submit endpoint."""

    def test_submit_rfq_success(self, client, customer_user, mock_openai):
        """Test submitting an RFQ."""
        from tests.fixtures.factories import create_test_rfq
        import uuid
        
        client.post(
            "/api/v1/auth/login",
            data={"username": "customer@test.com", "password": "testpassword123"},
        )
        
        rfq = create_test_rfq(
            client.app.state.db,
            customer_id=customer_user.id,
            rfq_status="draft",
        )
        
        with patch("app.api.endpoints.rfqs.search_providers") as mock_search:
            mock_search.return_value = []
            
            response = client.post(f"/api/v1/rfqs/{rfq.id}/submit")
        
        assert response.status_code == 200
        assert response.json()["rfq_status"] == "open_for_dispatch"
