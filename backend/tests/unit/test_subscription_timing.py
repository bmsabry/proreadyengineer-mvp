"""Subscriptions must end as advertised.

Covers:
  * campaign-accept grants a real 3-month PROVIDER_ANNUAL ($1000 tier) subscription
    that the RFQ-unlock gate honours;
  * the daily expiry job cancels ACTIVE subs past their period end (beyond grace),
    while leaving renewed (future-dated), in-grace, and NULL-end subs active.

Self-contained SQLite — runs anywhere incl. CI.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import TextClause
from pgvector.sqlalchemy import Vector

from app.models.base import Base
from app.models.enums import CampaignStatus, InviteStatus, SubscriptionStatus, SubscriptionType


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


async def _make_campaign_invite(db_session, *, duration_days=90, slots=10, token="ctok"):
    from app.models.campaign import ProviderCampaign, ProviderCampaignInvite
    from app.models.provider import Provider
    from app.models.user import User

    admin = User(id=uuid.uuid4(), email=f"a_{uuid.uuid4().hex[:6]}@t.com",
                 password_hash="x", first_name="A", last_name="D", roles=["admin"])
    user = User(id=uuid.uuid4(), email=f"p_{uuid.uuid4().hex[:6]}@firm.com",
                password_hash="x", first_name="P", last_name="R", roles=[])
    provider = Provider(name="Firm", firm_name="Firm", email_addresses=["p@firm.com"])
    db_session.add_all([admin, user, provider])
    await db_session.flush()
    campaign = ProviderCampaign(
        id=uuid.uuid4(), name="C", email_subject="S", email_body_html="",
        founding_slots_total=slots, founding_duration_days=duration_days,
        batch_size_per_day=10, status=CampaignStatus.ACTIVE, created_by=admin.id,
    )
    db_session.add(campaign)
    await db_session.flush()
    invite = ProviderCampaignInvite(
        id=uuid.uuid4(), campaign_id=campaign.id, provider_id=provider.id,
        invite_token=token, status=InviteStatus.SENT,
    )
    db_session.add(invite)
    await db_session.commit()
    return user, provider, campaign, invite


@pytest.mark.asyncio
async def test_redeem_grants_3month_annual_tier(db_session):
    from app.services.campaign_service import redeem_campaign_invite, FOUNDING_SUBSCRIPTION_MARKER
    from app.api.endpoints.rfqs import _provider_has_annual_subscription
    from app.models.payment import Subscription

    user, provider, campaign, invite = await _make_campaign_invite(db_session, duration_days=90)

    pid = await redeem_campaign_invite(db_session, token="ctok", user_id=user.id)
    assert pid == provider.id

    sub = (await db_session.execute(
        select(Subscription).where(Subscription.provider_id == provider.id)
    )).scalar_one()
    assert sub.subscription_type == SubscriptionType.PROVIDER_ANNUAL
    assert sub.subscription_status == SubscriptionStatus.ACTIVE
    assert sub.provider_name == FOUNDING_SUBSCRIPTION_MARKER
    # ~90 days out (3 months), not a full year
    days = (sub.current_period_end - sub.current_period_start).days
    assert 89 <= days <= 91

    await db_session.refresh(invite)
    await db_session.refresh(campaign)
    assert invite.status == InviteStatus.REGISTERED
    assert campaign.founding_slots_claimed == 1

    # The $1000-tier benefit is real: unlock gate sees an active annual sub.
    assert await _provider_has_annual_subscription(provider.id, db_session) is True


@pytest.mark.asyncio
async def test_redeem_is_idempotent(db_session):
    from app.services.campaign_service import redeem_campaign_invite
    from app.models.payment import Subscription

    user, provider, campaign, invite = await _make_campaign_invite(db_session)
    await redeem_campaign_invite(db_session, token="ctok", user_id=user.id)
    await redeem_campaign_invite(db_session, token="ctok", user_id=user.id)

    subs = (await db_session.execute(
        select(Subscription).where(Subscription.provider_id == provider.id)
    )).scalars().all()
    assert len(subs) == 1
    await db_session.refresh(campaign)
    assert campaign.founding_slots_claimed == 1


@pytest.mark.asyncio
async def test_redeem_unknown_token_returns_none(db_session):
    from app.services.campaign_service import redeem_campaign_invite
    assert await redeem_campaign_invite(db_session, token="not-a-campaign", user_id=uuid.uuid4()) is None


def _mk_sub(period_end):
    from app.models.payment import Subscription
    return Subscription(
        id=uuid.uuid4(),
        provider_name="stripe",
        subscription_type=SubscriptionType.PROVIDER_ANNUAL,
        subscription_status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.now(timezone.utc) - timedelta(days=400),
        current_period_end=period_end,
    )


@pytest.mark.asyncio
async def test_expire_due_subscriptions(db_session):
    from app.tasks.maintenance import expire_due_subscriptions

    now = datetime.now(timezone.utc)
    s_past = _mk_sub(now - timedelta(days=2))    # lapsed beyond grace -> cancel
    s_future = _mk_sub(now + timedelta(days=30))  # renewed -> stays
    s_grace = _mk_sub(now - timedelta(hours=1))   # within 1-day grace -> stays
    s_null = _mk_sub(None)                         # unknown end -> stays
    db_session.add_all([s_past, s_future, s_grace, s_null])
    await db_session.commit()

    cancelled = await expire_due_subscriptions(db_session, now=now)
    assert cancelled == 1

    for s in (s_past, s_future, s_grace, s_null):
        await db_session.refresh(s)
    assert s_past.subscription_status == SubscriptionStatus.CANCELLED
    assert s_past.cancelled_at is not None
    assert s_future.subscription_status == SubscriptionStatus.ACTIVE
    assert s_grace.subscription_status == SubscriptionStatus.ACTIVE
    assert s_null.subscription_status == SubscriptionStatus.ACTIVE
