"""Fast, self-contained tests for pure helpers (no DB / network)."""
import uuid

import pytest


class TestPaymentIdempotencyKey:
    def test_deterministic_same_inputs(self):
        from app.services.payment_service import _create_idempotency_key
        u, r = uuid.uuid4(), uuid.uuid4()
        assert _create_idempotency_key("rfq_unlock", u, r) == _create_idempotency_key("rfq_unlock", u, r)

    def test_differs_by_purpose_and_entity(self):
        from app.services.payment_service import _create_idempotency_key
        u, r = uuid.uuid4(), uuid.uuid4()
        assert _create_idempotency_key("rfq_unlock", u, r) != _create_idempotency_key("nda_fee", u, r)
        assert _create_idempotency_key("rfq_unlock", u, r) != _create_idempotency_key("rfq_unlock", u, uuid.uuid4())


class TestSearchQuotaConstants:
    def test_free_and_paid_limits(self):
        # Free limit must match the value advertised in-app and on the admin screen.
        from app.services.search_service import FREE_SEARCH_LIMIT, PAID_SEARCH_LIMIT
        assert FREE_SEARCH_LIMIT == 10
        assert PAID_SEARCH_LIMIT == 100
