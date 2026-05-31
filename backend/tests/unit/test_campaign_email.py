"""Tests for campaign email deliverability shell + unsubscribe + AI draft.

Self-contained (SQLite, no DB service required) so it runs anywhere incl. CI.
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import TextClause
from pgvector.sqlalchemy import Vector

from app.services.campaign_email import (
    body_to_html,
    html_to_text,
    wrap_campaign_email,
    build_unsubscribe_headers,
)
from app.models.base import Base


@compiles(Vector, "sqlite")
def _render_vector_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "BLOB"


@compiles(TextClause, "sqlite")
def _render_text_sqlite(element, compiler, **kw):  # noqa: ANN001
    t = element.text.strip().lower()
    return {"now()": "CURRENT_TIMESTAMP", "false": "0", "true": "1"}.get(t, element.text)


# ---- pure email-shell helpers ----------------------------------------------

def test_body_to_html_wraps_paragraphs():
    out = body_to_html("Hello there.\n\nClaim your spot today.")
    assert out.count("<p") == 2
    assert "Hello there." in out


def test_body_to_html_passes_through_existing_html():
    src = "<p>Already HTML</p>"
    assert body_to_html(src) == src


def test_wrap_campaign_email_has_footer_and_unsubscribe():
    html = wrap_campaign_email(
        "<p>Body</p>",
        unsubscribe_url="https://api.example.com/api/v1/campaigns/unsubscribe/tok123",
        preheader="A preheader",
    )
    assert "tok123" in html
    assert "Unsubscribe" in html
    assert "ProMechDirectory" in html


def test_html_to_text_strips_tags():
    txt = html_to_text("<p>Hello <a href='x'>world</a></p>")
    assert "<" not in txt
    assert "Hello" in txt and "world" in txt


def test_build_unsubscribe_headers_rfc8058():
    h = build_unsubscribe_headers("https://x/unsub/tok", mailto="unsub@x.com")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "https://x/unsub/tok" in h["List-Unsubscribe"]
    assert "mailto:unsub@x.com" in h["List-Unsubscribe"]


# ---- self-contained app + DB fixtures --------------------------------------

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
async def app_client(db_session):
    from main import app as fastapi_app
    from app.db.session import get_db

    async def _override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    fastapi_app.dependency_overrides.clear()


async def _make_invite(db_session, status):
    from app.models.campaign import ProviderCampaign, ProviderCampaignInvite
    from app.models.provider import Provider
    from app.models.user import User
    from app.models.enums import CampaignStatus

    admin = User(
        id=uuid.uuid4(), email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="x", first_name="A", last_name="D", roles=["admin"],
    )
    db_session.add(admin)
    await db_session.flush()
    provider = Provider(name="Test Firm", firm_name="Test Firm", email_addresses=["t@firm.com"])
    db_session.add(provider)
    await db_session.flush()
    campaign = ProviderCampaign(
        id=uuid.uuid4(), name="C", email_subject="S", email_body_html="",
        founding_slots_total=10, founding_duration_days=30, batch_size_per_day=10,
        status=CampaignStatus.ACTIVE, created_by=admin.id,
    )
    db_session.add(campaign)
    await db_session.flush()
    token = f"tok-{uuid.uuid4().hex[:8]}"
    invite = ProviderCampaignInvite(
        id=uuid.uuid4(), campaign_id=campaign.id, provider_id=provider.id,
        invite_token=token, status=status,
    )
    db_session.add(invite)
    await db_session.commit()
    return invite, token


@pytest.mark.asyncio
async def test_unsubscribe_one_click_flips_status(app_client, db_session):
    from app.models.enums import InviteStatus
    invite, token = await _make_invite(db_session, InviteStatus.SENT)

    resp = await app_client.post(f"/api/v1/campaigns/unsubscribe/{token}")
    assert resp.status_code == 200
    assert resp.json()["unsubscribed"] is True

    await db_session.refresh(invite)
    assert invite.status == InviteStatus.UNSUBSCRIBED


@pytest.mark.asyncio
async def test_unsubscribe_browser_get_returns_html(app_client, db_session):
    from app.models.enums import InviteStatus
    _, token = await _make_invite(db_session, InviteStatus.SENT)

    resp = await app_client.get(f"/api/v1/campaigns/unsubscribe/{token}")
    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()


@pytest.mark.asyncio
async def test_unsubscribe_unknown_token_is_safe(app_client):
    resp = await app_client.post("/api/v1/campaigns/unsubscribe/does-not-exist")
    assert resp.status_code == 200
    assert resp.json()["unsubscribed"] is False


@pytest.mark.asyncio
async def test_draft_email_returns_subject_and_body(app_client):
    """The draft endpoint parses the LLM JSON into subject + body (admin only)."""
    from main import app as fastapi_app
    from app.api.deps import get_current_active_user
    from app.models.user import User
    import app.services.help_service as hs

    admin = User(
        email="admin@test.com", password_hash="x",
        first_name="A", last_name="D", roles=["admin"],
    )

    async def _override_user():
        return admin

    async def _fake_call_llm(cfg, messages, **kw):
        return {
            "reply": '{"subject": "Join ProMechDirectory", "body": "Hi {{firm_name}}, claim your spot: {{invite_link}}"}',
            "model": "fake", "total_tokens": 42,
        }

    async def _fake_cfg(db):
        return {"api_key": "k", "model": "fake", "base": "http://x"}

    fastapi_app.dependency_overrides[get_current_active_user] = _override_user
    orig_call, orig_cfg = hs._call_llm, hs._get_chat_llm_config
    hs._call_llm, hs._get_chat_llm_config = _fake_call_llm, _fake_cfg
    try:
        resp = await app_client.post(
            "/api/v1/admin/campaigns/draft-email",
            json={"brief": "Invite engineering firms to join for free."},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["subject"] == "Join ProMechDirectory"
        assert "{{firm_name}}" in data["body"]
    finally:
        hs._call_llm, hs._get_chat_llm_config = orig_call, orig_cfg
        fastapi_app.dependency_overrides.pop(get_current_active_user, None)
