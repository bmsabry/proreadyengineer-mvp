"""Monthly free-NDA allowance logic (5/month for paid customers).

Tests the pure decision helper compute_nda_credit_grant + the pricing constants.
asyncio_mode=auto.
"""
from datetime import datetime, timezone, timedelta
from app.api.endpoints.rfqs import compute_nda_credit_grant
from app.core.config import settings

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


def test_first_credit_of_month_is_granted():
    grant, used, remaining = compute_nda_credit_grant(0, None, NOW, 5)
    assert grant is True and used == 1 and remaining == 4


def test_fifth_credit_granted_then_exhausted():
    # used=4 -> grant the 5th, none remaining
    grant, used, remaining = compute_nda_credit_grant(4, NOW, NOW, 5)
    assert grant is True and used == 5 and remaining == 0
    # used=5 -> no grant (must pay)
    grant2, used2, remaining2 = compute_nda_credit_grant(5, NOW, NOW, 5)
    assert grant2 is False and used2 == 5 and remaining2 == 0


def test_counter_resets_on_new_calendar_month():
    last_month = NOW - timedelta(days=40)  # April
    # Was exhausted last month, but it's a new month now -> granted again.
    grant, used, remaining = compute_nda_credit_grant(5, last_month, NOW, 5)
    assert grant is True and used == 1 and remaining == 4


def test_same_month_does_not_reset():
    earlier_same_month = datetime(2026, 5, 2, tzinfo=timezone.utc)
    grant, used, remaining = compute_nda_credit_grant(5, earlier_same_month, NOW, 5)
    assert grant is False and used == 5


def test_pricing_constants_are_correct():
    assert settings.SEARCH_TIER_1_PRICE == 5000      # $50/mo
    assert settings.SEARCH_ANNUAL_PRICE == 50000     # $500/yr
    assert settings.NDA_FREE_CREDITS_PER_MONTH == 5
    assert settings.RFQ_UNLOCK_PRICE == 5000         # $50 unlock unchanged
    assert settings.NDA_FEE_PRICE == 1000            # $10 NDA fee unchanged
