"""Regression tests for NDA-RFQ dispatch (root-cause fix).

Bug: an NDA-required RFQ got stranded in `awaiting_customer_signature` and never
dispatched to providers, because the NDA fee handlers moved it out of `draft`
while `submit` only ran from `draft`.

Invariant locked in here:
  An NDA-required RFQ MUST dispatch when submitted, regardless of whether the
  customer NDA signature has been collected. The signature is gathered later
  (provider-triggered) and must NEVER block dispatch.

`submit_rfq` must:
  * dispatch from ANY pre-dispatch state (draft, submitted, awaiting_nda_payment,
    awaiting_customer_signature);
  * be idempotent (re-submit must not duplicate matches or raise);
  * be a no-op once already dispatching/open/closed.

Self-contained: builds a minimal SQLite schema (the app is Postgres-native, but
these tests need no DB service so they run anywhere, including CI).
"""
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import TextClause
from pgvector.sqlalchemy import Vector

from app.services.rfq_service import submit_rfq
from app.models import RFQ, RFQMatch, User, Provider
from app.models.base import Base
from app.models.enums import RfqStatus
from app.services.auth_service import hash_password


# --- Render Postgres-only DDL on SQLite so the needed tables build ----------
@compiles(Vector, "sqlite")
def _render_vector_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "BLOB"


@compiles(TextClause, "sqlite")
def _render_text_sqlite(element, compiler, **kw):  # noqa: ANN001
    t = element.text.strip().lower()
    return {"now()": "CURRENT_TIMESTAMP", "false": "0", "true": "1"}.get(t, element.text)




@pytest_asyncio.fixture
async def db_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'t.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def customer_user(db_session):
    u = User(
        email=f"cust_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("pw"),
        first_name="Test",
        last_name="Customer",
        roles=["customer"],
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


_PRE_DISPATCH_STATES = {
    RfqStatus.DRAFT,
    RfqStatus.SUBMITTED,
    RfqStatus.AWAITING_NDA_PAYMENT,
    RfqStatus.AWAITING_CUSTOMER_SIGNATURE,
}


def _fake_result(provider):
    class _R:
        pass
    r = _R()
    r.provider = provider
    r.score = 85.0
    r.specialty_score = 20.0
    r.capabilities_score = 40.0
    r.tier_score = 25.0
    return r


async def _make_rfq(db, customer_id, status, nda):
    rfq = RFQ(
        customer_user_id=customer_id,
        customer_email="c@test.com",
        business_name="Acme",
        contact_name="Jane",
        project_description="Need structural analysis for an aerospace bracket.",
        urgency="High",
        nda_required=nda,
        rfq_status=status,
    )
    db.add(rfq)
    await db.commit()
    await db.refresh(rfq)
    return rfq


async def _match_count(db, rfq_id):
    return (await db.execute(
        select(func.count()).select_from(RFQMatch).where(RFQMatch.rfq_id == rfq_id)
    )).scalar() or 0


@pytest.mark.asyncio
async def test_nda_rfq_stuck_in_awaiting_signature_still_dispatches(db_session, customer_user):
    """THE regression: NDA RFQ parked in awaiting_customer_signature must dispatch."""
    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.AWAITING_CUSTOMER_SIGNATURE, True)
    with patch("app.services.search_service.search_providers") as m:
        m.return_value = ([], {})
        await submit_rfq(db_session, rfq.id)
        m.assert_called()  # proceeded PAST the guard (did not bail on NDA status)
    await db_session.refresh(rfq)
    assert rfq.rfq_status not in _PRE_DISPATCH_STATES  # escaped the trap
    assert rfq.submitted_at is not None


@pytest.mark.asyncio
async def test_nda_rfq_from_awaiting_nda_payment_dispatches(db_session, customer_user):
    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.AWAITING_NDA_PAYMENT, True)
    with patch("app.services.search_service.search_providers") as m:
        m.return_value = ([], {})
        await submit_rfq(db_session, rfq.id)
        m.assert_called()
    await db_session.refresh(rfq)
    assert rfq.rfq_status not in _PRE_DISPATCH_STATES


@pytest.mark.asyncio
async def test_non_nda_rfq_still_dispatches_from_draft(db_session, customer_user):
    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.DRAFT, False)
    with patch("app.services.search_service.search_providers") as m:
        m.return_value = ([], {})
        await submit_rfq(db_session, rfq.id)
        m.assert_called()
    await db_session.refresh(rfq)
    assert rfq.rfq_status not in _PRE_DISPATCH_STATES


@pytest.mark.asyncio
async def test_submit_creates_matches_once_then_idempotent(db_session, customer_user):
    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.AWAITING_CUSTOMER_SIGNATURE, True)
    provider = Provider(name="Idempotent Co", firm_name="Idempotent Co")
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    with patch("app.services.search_service.search_providers") as m:
        m.return_value = ([_fake_result(provider)], {})
        await submit_rfq(db_session, rfq.id)
        assert await _match_count(db_session, rfq.id) == 1
        # Re-submit: now OPEN_FOR_DISPATCH -> no-op, no duplicate matches.
        await submit_rfq(db_session, rfq.id)
        assert await _match_count(db_session, rfq.id) == 1


@pytest.mark.asyncio
async def test_submit_already_open_is_noop(db_session, customer_user):
    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.OPEN_FOR_UNLOCK, True)
    with patch("app.services.search_service.search_providers") as m:
        m.return_value = ([], {})
        await submit_rfq(db_session, rfq.id)
        m.assert_not_called()
    await db_session.refresh(rfq)
    assert rfq.rfq_status == RfqStatus.OPEN_FOR_UNLOCK


@pytest.mark.asyncio
async def test_submit_missing_rfq_raises(db_session):
    with pytest.raises(ValueError, match="RFQ not found"):
        await submit_rfq(db_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_mutual_nda_webhook_distinguishes_signers(db_session, customer_user):
    """Webhook must record customer vs provider signatures separately on a mutual
    NDA, and mark fully_signed only once BOTH parties have signed."""
    from app.models.nda import RFQNDA
    from app.services.nda_service import handle_signwell_webhook

    rfq = await _make_rfq(db_session, customer_user.id, RfqStatus.OPEN_FOR_UNLOCK, True)
    provider = Provider(name="Webhook Co", firm_name="Webhook Co")
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)

    nda = RFQNDA(
        rfq_id=rfq.id,
        provider_id=provider.id,
        customer_user_id=customer_user.id,
        signrequest_document_id="DOC-MUTUAL-1",
        nda_status="pending_signatures",
    )
    db_session.add(nda)
    await db_session.commit()

    # Provider signs first (a non-customer email) -> only provider recorded.
    await handle_signwell_webhook(
        "document_signer_completed",
        {"data": {"object": {"id": "DOC-MUTUAL-1"}}, "signer": {"email": "provider@firm.com"}},
        db_session,
    )
    await db_session.refresh(nda)
    assert nda.provider_signed_at is not None
    assert nda.customer_signed_at is None  # NOT both yet

    # Customer countersigns -> now fully signed.
    await handle_signwell_webhook(
        "document_signer_completed",
        {"data": {"object": {"id": "DOC-MUTUAL-1"}}, "signer": {"email": customer_user.email}},
        db_session,
    )
    await db_session.refresh(nda)
    assert nda.customer_signed_at is not None
    assert nda.fully_signed_at is not None
    assert str(nda.nda_status).endswith("fully_signed")
