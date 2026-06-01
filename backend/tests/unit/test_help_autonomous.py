"""Autonomous-mode safety: executor allowlists + consent gating. asyncio_mode=auto."""
import pytest
from app.services import help_actions as HA
from app.services import help_service as HS


class _FakeUser:
    def __init__(self, roles=None, autonomous=False):
        import uuid
        self.id = uuid.uuid4()
        self.roles = roles or ["customer"]
        self.agent_autonomous_enabled = autonomous


def test_action_allowlists_are_exactly_as_expected():
    assert HA.SAFE_ACTIONS == {"mark_contacted", "undo_mark_contacted", "update_profile_from_docs", "update_profile_from_chat"}
    assert HA.AUTONOMOUS_ACTIONS == {"accept_quote", "cancel_rfq", "withdraw_quote",
                                    "create_rfq_from_docs", "submit_quote_from_docs"}
    # Payments and NDA signing must NEVER be executable.
    for forbidden in ["pay", "pay_unlock", "pay_nda_fee", "subscribe", "sign_nda", "countersign_nda", "esign"]:
        assert forbidden not in HA.ALL_ACTIONS
        assert forbidden in HA.FORBIDDEN_ACTIONS


async def test_autonomous_action_rejected_when_disabled():
    user = _FakeUser(autonomous=False)
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=user, action_type="accept_quote",
                                params={"quote_id": "x"}, autonomous_enabled=False)
    # 403 — needs autonomous mode
    assert getattr(ei.value, "status_code", None) == 403


async def test_forbidden_action_always_blocked_even_with_autonomy():
    user = _FakeUser(autonomous=True)
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=user, action_type="pay_unlock",
                                params={}, autonomous_enabled=True)
    assert getattr(ei.value, "status_code", None) == 403


async def test_unknown_action_blocked():
    user = _FakeUser(autonomous=True)
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=user, action_type="launch_missiles",
                                params={}, autonomous_enabled=True)
    assert getattr(ei.value, "status_code", None) == 400


def test_proposable_set_includes_autonomous_actions():
    # The model may PROPOSE these; execution is still gated server-side.
    for a in ["mark_contacted", "undo_mark_contacted", "accept_quote", "cancel_rfq", "withdraw_quote"]:
        assert a in HS._PROPOSABLE_ACTIONS
