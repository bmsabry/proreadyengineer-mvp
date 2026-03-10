"""Unit tests for RFQ lifecycle service.

Tests RFQ creation, submission, matching, dispatch, unlock with concurrency safety.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.services.rfq_service import (
    create_rfq,
    get_rfq,
    submit_rfq,
    create_dispatch_batch,
    dispatch_teaser_batch,
    get_rfq_matches,
    unlock_rfq,
    submit_quote,
    get_rfq,
    accept_quote,
)
from app.models import (
    RFQ,
    RFQFile,
    RFQMatch,
    RFQDispatch,
    RFQDispatchBatch,
    RFQUnlock,
    Quote,
    QuoteStatus,
    RfqStatus,
    UnlockStatus,
    DispatchStatus,
    NdaStatus,
)
from app.schemas.rfq import RFQCreateRequest
from app.schemas.quote import QuoteCreateRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateRFQ:
    """Tests for RFQ creation."""

    async def test_create_rfq_with_user(self, db_session, customer_user):
        """Test creating RFQ with authenticated user."""
        data = RFQCreateRequest(
            customer_email="customer@test.com",
            business_name="Test Corp",
            contact_name="John Doe",
            project_description="Need FEA analysis",
            urgency="High",
            tollgate_phases=["TG1", "TG3"],
            nda_required=False,
        )
        
        rfq = await create_rfq(db_session, data, customer_user)
        
        assert rfq.customer_user_id == customer_user.id
        assert rfq.customer_email == "customer@test.com"
        assert rfq.business_name == "Test Corp"
        assert rfq.rfq_status == RfqStatus.DRAFT
        assert rfq.quote_count == 0
        assert rfq.is_closed is False

    async def test_create_rfq_without_user(self, db_session):
        """Test creating RFQ as guest."""
        data = RFQCreateRequest(
            customer_email="guest@test.com",
            business_name="Guest Corp",
            contact_name="Jane Doe",
            project_description="Need prototyping",
            urgency="Medium",
            tollgate_phases=["TG1"],
            nda_required=True,
        )
        
        rfq = await create_rfq(db_session, data, None)
        
        assert rfq.customer_user_id is None
        assert rfq.customer_email == "guest@test.com"
        assert rfq.nda_required is True
        assert rfq.rfq_status == RfqStatus.DRAFT

    async def test_create_rfq_preserves_all_fields(self, db_session, customer_user):
        """Test that all RFQ fields are preserved."""
        data = RFQCreateRequest(
            customer_email="test@test.com",
            business_name="Business Name",
            contact_name="Contact Name",
            project_description="Project Description",
            urgency="Low",
            tollgate_phases=["TG0", "TG1", "TG3"],
            nda_required=True,
        )
        
        rfq = await create_rfq(db_session, data, customer_user)
        
        assert rfq.project_description == "Project Description"
        assert rfq.urgency == "Low"
        assert rfq.tollgate_phases == ["TG0", "TG1", "TG3"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetRFQ:
    """Tests for retrieving RFQ."""

    async def test_get_rfq_exists(self, db_session, customer_user):
        """Test getting existing RFQ."""
        from tests.fixtures.factories import create_test_rfq
        
        created_rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        
        retrieved_rfq = await get_rfq(db_session, created_rfq.id)
        
        assert retrieved_rfq is not None
        assert retrieved_rfq.id == created_rfq.id
        assert retrieved_rfq.customer_email == created_rfq.customer_email

    async def test_get_rfq_not_found(self, db_session):
        """Test getting non-existent RFQ returns None."""
        rfq = await get_rfq(db_session, uuid.uuid4())
        
        assert rfq is None

    async def test_get_rfq_loads_relationships(self, db_session, customer_user):
        """Test that get_rfq loads related data."""
        from tests.fixtures.factories import create_test_rfq, create_test_rfq_file
        
        rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        
        # Add a file
        await create_test_rfq_file(db_session, rfq.id, uploaded_by_user_id=customer_user.id)
        
        retrieved = await get_rfq(db_session, rfq.id)
        
        assert retrieved is not None
        assert len(retrieved.files) == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubmitRFQ:
    """Tests for RFQ submission and matching."""

    async def test_submit_rfq_triggers_nda_flow(self, db_session, customer_user):
        """Test that NDA-required RFQ enters NDA flow."""
        from tests.fixtures.factories import create_test_rfq
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.DRAFT,
            nda_required=True,
        )
        
        await submit_rfq(db_session, rfq.id, None)
        
        await db_session.refresh(rfq)
        assert rfq.rfq_status == RfqStatus.AWAITING_NDA_PAYMENT

    async def test_submit_rfq_moves_to_dispatch(self, db_session, customer_user):
        """Test non-NDA RFQ moves to dispatch state."""
        from tests.fixtures.factories import create_test_rfq
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.DRAFT,
            nda_required=False,
        )
        
        # Mock search_providers to avoid OpenAI calls
        with patch("app.services.rfq_service.search_providers") as mock_search:
            mock_search.return_value = []
            
            await submit_rfq(db_session, rfq.id, None)
        
        await db_session.refresh(rfq)
        assert rfq.rfq_status == RfqStatus.OPEN_FOR_DISPATCH
        assert rfq.submitted_at is not None

    async def test_submit_rfq_creates_matches(self, db_session, customer_user):
        """Test that submit creates RFQ matches."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.DRAFT,
            nda_required=False,
        )
        
        # Create provider
        provider = await create_test_provider(db_session, name="Match Provider")
        
        # Mock search results
        mock_result = {
            "provider": provider,
            "composite_score": 85,
            "specialty_score": 20,
            "capabilities_score": 40,
            "tier_score": 25,
            "scoring_inputs": {},
        }
        
        with patch("app.services.rfq_service.search_providers") as mock_search:
            mock_search.return_value = [mock_result]
            
            await submit_rfq(db_session, rfq.id, None)
        
        # Check matches were created
        result = await db_session.execute(
            select(RFQMatch).where(RFQMatch.rfq_id == rfq.id)
        )
        matches = result.scalars().all()
        
        assert len(matches) == 1
        assert matches[0].provider_id == provider.id
        assert matches[0].composite_score == 85

    async def test_submit_rfq_not_found_raises(self, db_session):
        """Test submitting non-existent RFQ raises error."""
        with pytest.raises(ValueError, match="RFQ not found"):
            await submit_rfq(db_session, uuid.uuid4(), None)

    async def test_submit_rfq_wrong_status_raises(self, db_session, customer_user):
        """Test submitting already-submitted RFQ raises error."""
        from tests.fixtures.factories import create_test_rfq
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.SUBMITTED,
        )
        
        with pytest.raises(ValueError, match="RFQ is not in draft status"):
            await submit_rfq(db_session, rfq.id, None)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDispatchBatch:
    """Tests for RFQ dispatch batching."""

    async def test_create_dispatch_batch(self, db_session, customer_user):
        """Test creating a dispatch batch."""
        from tests.fixtures.factories import create_test_rfq
        from app.core.config import settings
        
        rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        
        with patch.object(settings, "RFQ_DISPATCH_BATCH_INTERVAL_HOURS", 24):
            batch = await create_dispatch_batch(db_session, rfq.id, batch_number=2)
        
        assert batch.rfq_id == rfq.id
        assert batch.batch_number == 2
        assert batch.scheduled_for > datetime.utcnow()
        assert batch.status == "pending"

    async def test_dispatch_teaser_batch(self, db_session, customer_user):
        """Test dispatching teaser batch."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider, create_test_rfq_match
        from app.core.config import settings
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.OPEN_FOR_DISPATCH,
        )
        
        # Create batch
        batch = await create_dispatch_batch(db_session, rfq.id, batch_number=1)
        
        # Create provider and match
        provider = await create_test_provider(
            db_session,
            email_addresses=["provider@test.com"],
        )
        match = await create_test_rfq_match(db_session, rfq.id, provider.id, rank_position=1)
        
        with patch.object(settings, "RFQ_DISPATCH_BATCH_SIZE", 5):
            dispatches = await dispatch_teaser_batch(db_session, rfq.id, 1, None)
        
        assert len(dispatches) == 1
        assert dispatches[0].provider_id == provider.id
        assert dispatches[0].email_target == "provider@test.com"

    async def test_dispatch_stops_when_closed(self, db_session, customer_user):
        """Test dispatch stops when RFQ is closed."""
        from tests.fixtures.factories import create_test_rfq
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.CLOSED_NO_SELECTION,
            is_closed=True,
        )
        
        batch = await create_dispatch_batch(db_session, rfq.id, batch_number=1)
        
        dispatches = await dispatch_teaser_batch(db_session, rfq.id, 1, None)
        
        assert len(dispatches) == 0

    async def test_dispatch_stops_when_quote_limit_reached(self, db_session, customer_user):
        """Test dispatch stops when quote limit reached."""
        from tests.fixtures.factories import create_test_rfq
        from app.core.config import settings
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.QUOTE_LIMIT_REACHED,
            quote_count=settings.RFQ_MAX_QUOTES,
        )
        
        batch = await create_dispatch_batch(db_session, rfq.id, batch_number=1)
        
        dispatches = await dispatch_teaser_batch(db_session, rfq.id, 1, None)
        
        assert len(dispatches) == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestUnlockRFQ:
    """Tests for RFQ unlock with concurrency safety."""

    async def test_unlock_rfq_success(self, db_session, customer_user, provider_user):
        """Test successful RFQ unlock."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider,
            create_test_provider_membership, create_test_payment_attempt
        )
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.OPEN_FOR_UNLOCK,
            quote_count=0,
        )
        
        provider = await create_test_provider(db_session)
        await create_test_provider_membership(db_session, provider.id, provider_user.id)
        
        payment = await create_test_payment_attempt(
            db_session,
            purpose="rfq_unlock",
            payment_status="completed",
        )
        
        unlock = await unlock_rfq(
            db_session,
            rfq.id,
            provider.id,
            provider_user.id,
            payment.id,
        )
        
        assert unlock is not None
        assert unlock.rfq_id == rfq.id
        assert unlock.provider_id == provider.id
        assert unlock.unlock_status == UnlockStatus.UNLOCKED
        
        # Check quote count incremented
        await db_session.refresh(rfq)
        assert rfq.quote_count == 1

    async def test_unlock_rfq_fails_when_closed(self, db_session, customer_user, provider_user):
        """Test unlock fails when RFQ is closed."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.CLOSED_NO_SELECTION,
            is_closed=True,
        )
        
        provider = await create_test_provider(db_session)
        
        with pytest.raises(ValueError, match="RFQ is not available"):
            await unlock_rfq(db_session, rfq.id, provider.id, provider_user.id, uuid.uuid4())

    async def test_unlock_rfq_fails_when_quote_limit_reached(self, db_session, customer_user, provider_user):
        """Test unlock fails when quote limit reached."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        from app.core.config import settings
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.QUOTE_LIMIT_REACHED,
            quote_count=settings.RFQ_MAX_QUOTES,
        )
        
        provider = await create_test_provider(db_session)
        
        with pytest.raises(ValueError, match="Quote limit reached"):
            await unlock_rfq(db_session, rfq.id, provider.id, provider_user.id, uuid.uuid4())

    async def test_unlock_rfq_duplicate_blocked(self, db_session, customer_user, provider_user):
        """Test duplicate unlock for same provider is blocked."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider,
            create_test_provider_membership
        )
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.OPEN_FOR_UNLOCK,
        )
        
        provider = await create_test_provider(db_session)
        await create_test_provider_membership(db_session, provider.id, provider_user.id)
        
        # First unlock
        await unlock_rfq(db_session, rfq.id, provider.id, provider_user.id, uuid.uuid4())
        
        # Duplicate should fail
        with pytest.raises(ValueError, match="already unlocked"):
            await unlock_rfq(db_session, rfq.id, provider.id, provider_user.id, uuid.uuid4())


@pytest.mark.unit
@pytest.mark.asyncio
class TestQuoteManagement:
    """Tests for quote creation and management."""

    async def test_submit_quote(self, db_session, customer_user, provider_user):
        """Test creating a quote."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider
        
        rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        provider = await create_test_provider(db_session)
        
        data = QuoteCreateRequest(
            rough_price_min=10000,
            rough_price_max=25000,
            currency="USD",
            turnaround_estimate_text="4-6 weeks",
            assumptions_text="Standard materials",
            scope_notes="Full scope pending",
        )
        
        quote = await submit_quote(
            db_session,
            rfq.id,
            provider.id,
            provider_user.id,
            data,
        )
        
        assert quote.rfq_id == rfq.id
        assert quote.provider_id == provider.id
        assert quote.submitter_user_id == provider_user.id
        assert quote.quote_status == QuoteStatus.DRAFT
        assert quote.rough_price_min == 10000
        assert quote.rough_price_max == 25000

    async def test_get_rfq(self, db_session, customer_user, provider_user):
        """Test retrieving quotes for an RFQ."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider, create_test_quote
        )
        
        rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        provider = await create_test_provider(db_session)
        
        # Create multiple quotes
        for i in range(3):
            await create_test_quote(
                db_session,
                rfq.id,
                provider.id,
                provider_user.id,
                quote_status=QuoteStatus.SUBMITTED,
            )
        
        quotes = await get_rfq(db_session, rfq.id)
        
        assert len(quotes) == 3

    async def test_accept_quote(self, db_session, customer_user, provider_user):
        """Test accepting a quote."""
        from tests.fixtures.factories import (
            create_test_rfq, create_test_provider, create_test_quote
        )
        
        rfq = await create_test_rfq(
            db_session,
            customer_id=customer_user.id,
            rfq_status=RfqStatus.OPEN_FOR_UNLOCK,
        )
        provider = await create_test_provider(db_session)
        quote = await create_test_quote(
            db_session,
            rfq.id,
            provider.id,
            provider_user.id,
            quote_status=QuoteStatus.SUBMITTED,
        )
        
        accepted_quote = await accept_quote(db_session, quote.id, customer_user.id)
        
        assert accepted_quote.quote_status == QuoteStatus.ACCEPTED
        
        # Check RFQ updated
        await db_session.refresh(rfq)
        assert rfq.selected_provider_id == provider.id
        assert rfq.rfq_status == RfqStatus.CUSTOMER_SELECTED_PROVIDER

    async def test_accept_quote_wrong_customer(self, db_session, customer_user, provider_user):
        """Test that wrong customer cannot accept quote."""
        from tests.fixtures.factories import create_test_rfq, create_test_provider, create_test_quote
        from tests.fixtures.factories import create_customer
        
        rfq = await create_test_rfq(db_session, customer_id=customer_user.id)
        provider = await create_test_provider(db_session)
        quote = await create_test_quote(
            db_session,
            rfq.id,
            provider.id,
            provider_user.id,
        )
        
        # Different customer tries to accept
        other_customer = await create_customer(db_session)
        
        with pytest.raises(ValueError, match="not authorized"):
            await accept_quote(db_session, quote.id, other_customer.id)
