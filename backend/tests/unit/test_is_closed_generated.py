import os as _os
import pytest as _pytest

# These tests exercise PostgreSQL-only behaviour (GENERATED columns / Postgres semantics).
# The unit-test harness runs on in-memory SQLite, so skip there and run only when a real
# Postgres TEST DATABASE is provided. This keeps CI green while preserving the tests.
_DB = (_os.environ.get("TEST_DATABASE_URL") or _os.environ.get("DATABASE_URL") or "").lower()
pytestmark = _pytest.mark.skipif(
    "postgresql" not in _DB and "postgres" not in _DB,
    reason="Requires PostgreSQL (GENERATED column / PG-specific behaviour); SQLite harness skips.",
)

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
