import pytest
from sqlalchemy import select
from app.models.rfq import RFQ
from app.models.enums import RfqStatus


@pytest.mark.asyncio
async def test_is_closed_is_generated_from_status(db_session):
    # Open RFQ -> is_closed False, computed by the DB (we never set it)
    r = RFQ(customer_email="x@y.com", project_description="d", rfq_status=RfqStatus.OPEN_FOR_UNLOCK)
    db_session.add(r)
    await db_session.commit()
    fresh = (await db_session.execute(
        select(RFQ).where(RFQ.id == r.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert fresh.is_closed is False

    # Flip status to a closed one -> is_closed follows automatically, no is_closed write
    fresh.rfq_status = RfqStatus.CANCELLED
    await db_session.commit()
    again = (await db_session.execute(
        select(RFQ).where(RFQ.id == r.id).execution_options(populate_existing=True)
    )).scalar_one()
    assert again.is_closed is True
