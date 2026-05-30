import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.user import User
from app.models.rfq import RFQ, RFQUnlock, RFQDispatch, RFQDispatchBatch
from app.models.provider import Provider, ProviderMembership
from app.models.payment import Subscription
from app.models.enums import RfqStatus, UnlockStatus, MembershipRole, MembershipStatus
from app.services.auth_service import hash_password
from app.api.endpoints.rfqs import get_unlock_status


async def _setup(db, *, nda_required, annual, customer_signed=False):
    cust = User(email=f"cust_{uuid.uuid4().hex[:6]}@t.com", password_hash=hash_password("pw"),
                first_name="Jane", last_name="Buyer", business_name="Acme Buyer LLC",
                state="Texas", phone="+1 555-123-9999", roles=["customer"])
    prov_user = User(email=f"prov_{uuid.uuid4().hex[:6]}@t.com", password_hash=hash_password("pw"),
                     first_name="John", last_name="Smith", roles=["provider"])
    db.add_all([cust, prov_user]); await db.commit(); await db.refresh(cust); await db.refresh(prov_user)

    prov = Provider(name="Smith Engineering", firm_name="Smith Engineering Inc")
    db.add(prov); await db.commit(); await db.refresh(prov)
    mem = ProviderMembership(provider_id=prov.id, user_id=prov_user.id, membership_role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE)
    db.add(mem)

    rfq = RFQ(customer_user_id=cust.id, customer_email=cust.email, business_name="Acme Buyer LLC",
              contact_name="Jane Buyer", project_description="Valve sizing.", urgency="Intermediate",
              nda_required=nda_required, rfq_status=RfqStatus.OPEN_FOR_UNLOCK)
    db.add(rfq); await db.commit(); await db.refresh(rfq)

    from datetime import datetime as _dt
    batch = RFQDispatchBatch(rfq_id=rfq.id, batch_number=1, scheduled_for=_dt.utcnow())
    db.add(batch); await db.commit(); await db.refresh(batch)
    db.add(RFQDispatch(rfq_id=rfq.id, provider_id=prov.id, batch_id=batch.id, dispatch_status="sent"))
    db.add(RFQUnlock(rfq_id=rfq.id, provider_id=prov.id, unlock_status=UnlockStatus.UNLOCKED,
                     unlocked_by_user_id=prov_user.id))
    if annual:
        db.add(Subscription(user_id=prov_user.id, provider_id=prov.id,
                            subscription_type="provider_annual", subscription_status="active", provider_name="stripe"))
    await db.commit()
    return prov_user, rfq


@pytest.mark.asyncio
async def test_annual_non_nda_sees_contact(db_session):
    prov_user, rfq = await _setup(db_session, nda_required=False, annual=True)
    out = await get_unlock_status(rfq.id, db_session, prov_user)
    assert out["is_annual_subscriber"] is True
    assert out["contact_locked_reason"] is None
    cc = out["customer_contact"]
    assert cc and cc["email"] == rfq.customer_email
    assert cc["company"] == "Acme Buyer LLC"
    assert cc["name"] == "Jane Buyer"
    assert cc["state"] == "Texas"
    assert cc["phone"] == "+1 555-123-9999"


@pytest.mark.asyncio
async def test_annual_nda_unsigned_is_locked(db_session):
    prov_user, rfq = await _setup(db_session, nda_required=True, annual=True)
    out = await get_unlock_status(rfq.id, db_session, prov_user)
    assert out["is_annual_subscriber"] is True
    assert out["customer_contact"] is None
    assert out["contact_locked_reason"] == "nda_required"


@pytest.mark.asyncio
async def test_non_annual_gets_no_contact(db_session):
    prov_user, rfq = await _setup(db_session, nda_required=False, annual=False)
    out = await get_unlock_status(rfq.id, db_session, prov_user)
    assert out["is_annual_subscriber"] is False
    assert out["customer_contact"] is None
    assert out["contact_locked_reason"] is None
