"""Phase 2 personalization: account snapshot renderer + account-intent detection.
Pure functions (no DB). asyncio_mode=auto.
"""
from app.services.help_context import render_account_context
from app.services import help_service as H


def test_render_includes_identity_subscription_and_actions():
    ctx = {
        "name": "Bassam", "company": "Bassam LLC", "roles": ["customer"],
        "subscription": "search_tier_1", "subscription_renews": "2026-06-30",
        "rfqs": {"total": 4, "open": 2, "open_with_quotes": 1},
        "nda_free_credits_remaining": 3,
        "actions": ["2 NDA(s) are awaiting your signature — countersign so the provider can quote."],
    }
    out = render_account_context(ctx, page="/customer/dashboard")
    assert "Bassam" in out and "Bassam LLC" in out
    assert "search_tier_1" in out
    assert "ACTION ITEMS" in out and "NDA(s) are awaiting" in out
    assert "4 total" in out and "Your RFQs" in out
    assert "/customer/dashboard" in out


def test_render_empty_context_is_blank():
    assert render_account_context({}) == ""


def test_render_no_actions_message():
    out = render_account_context({"roles": ["provider"], "subscription": None, "actions": []})
    assert "No outstanding action items" in out
    assert "free account" in out.lower()


def test_account_intent_detection():
    assert H._looks_account_related("what should I do next?")
    assert H._looks_account_related("how many quotes do I have")
    assert H._looks_account_related("when does my subscription renew")
    assert not H._looks_account_related("what is the capital of France")


def test_render_provider_metrics_and_identity():
    ctx = {
        "name": "Acme Eng", "company": "Acme", "roles": ["provider"],
        "email": "p@acme.com", "member_since": "2025-01-01", "subscription": "provider_annual",
        "provider_metrics": {"rfqs_received": 17, "quotes_submitted": 23, "accepted": 5,
                             "pending_decisions": 6, "not_selected": 2, "ndas_signed": 9, "win_rate_pct": 22},
        "actions": [],
    }
    out = render_account_context(ctx)
    assert "RFQs received 17" in out
    assert "quotes submitted 23" in out
    assert "win rate 22%" in out
    assert "NDAs signed 9" in out
    assert "Member since 2025-01-01" in out


def test_render_customer_rfq_breakdown():
    ctx = {
        "name": "Bob", "roles": ["customer"], "subscription": None,
        "rfqs": {"total": 4, "open": 2, "open_with_quotes": 1, "quoted": 3,
                 "provider_selected": 1, "cancelled": 0, "total_quotes_received": 7},
        "search_used_this_month": 3, "actions": [],
    }
    out = render_account_context(ctx)
    assert "4 total" in out and "7 quotes received in total" in out
    assert "Searches used this month: 3" in out
