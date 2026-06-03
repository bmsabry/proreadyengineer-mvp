"""Unit tests for the RFQ completeness gate (free vs paid attempt budgets).

The LLM evaluation and runtime config are monkeypatched so these tests are
deterministic and require no DB/LLM — they exercise the gate decision logic only.
"""
import pytest
import app.services.rfq_quality_service as q


class _FakeRFQ:
    def __init__(self):
        self.id = "rfq-test"
        self.business_name = "Acme"
        self.quality_attempts = 0
        self.quality_blocked = False


class _FakeDB:
    async def commit(self):
        return None
    async def rollback(self):
        return None


@pytest.fixture(autouse=True)
def _patch_cfg(monkeypatch):
    async def _cfg(db):
        return {"enabled": True, "block": 45, "warn": 70, "max_free": 2, "max_paid": 5}
    monkeypatch.setattr(q, "_gate_cfg", _cfg)
    # Never actually send a support email in tests.
    async def _noop(db, rfq, ev):
        return None
    monkeypatch.setattr(q, "_notify_support_incomplete_rfq", _noop)


def _patch_verdict(monkeypatch, verdict, score=30):
    async def _ev(db, rfq):
        return {"verdict": verdict, "score": score,
                "missing": ["dimensions", "tolerances"], "suggestions": ["add specs"],
                "summary": "needs work"}
    monkeypatch.setattr(q, "evaluate_rfq", _ev)


@pytest.mark.asyncio
async def test_ready_passes(monkeypatch):
    _patch_verdict(monkeypatch, q.READY, score=90)
    out = await q.gate_rfq_for_dispatch(_FakeDB(), _FakeRFQ(), is_subscriber=False)
    assert out["ok"] is True


@pytest.mark.asyncio
async def test_borderline_warns_but_allows(monkeypatch):
    _patch_verdict(monkeypatch, q.BORDERLINE, score=60)
    out = await q.gate_rfq_for_dispatch(_FakeDB(), _FakeRFQ(), is_subscriber=False)
    assert out["ok"] is True and "warning" in out


@pytest.mark.asyncio
async def test_free_user_terminal_block_at_second_attempt(monkeypatch):
    _patch_verdict(monkeypatch, q.INCOMPLETE)
    rfq = _FakeRFQ()
    db = _FakeDB()
    # 1st incomplete attempt -> soft block, not terminal
    out1 = await q.gate_rfq_for_dispatch(db, rfq, is_subscriber=False)
    assert out1["ok"] is False and out1["terminal"] is False
    assert out1["reason"] == "rfq_incomplete" and out1["attempts_max"] == 2
    assert out1["ai_help"] is False  # free user -> no AI assist offer
    # 2nd incomplete attempt -> terminal block
    out2 = await q.gate_rfq_for_dispatch(db, rfq, is_subscriber=False)
    assert out2["ok"] is False and out2["terminal"] is True
    assert out2["reason"] == "rfq_terminally_blocked"
    assert rfq.quality_blocked is True


@pytest.mark.asyncio
async def test_subscriber_escalates_to_support_at_fifth_attempt(monkeypatch):
    _patch_verdict(monkeypatch, q.INCOMPLETE)
    rfq = _FakeRFQ()
    db = _FakeDB()
    # attempts 1..4 -> soft block, AI assist offered, never terminal
    for i in range(1, 5):
        out = await q.gate_rfq_for_dispatch(db, rfq, is_subscriber=True)
        assert out["ok"] is False and out["terminal"] is False, f"attempt {i}"
        assert out["attempts_max"] == 5 and out["ai_help"] is True
    # 5th attempt -> support escalation (not a hard "not industry standard" block)
    out5 = await q.gate_rfq_for_dispatch(db, rfq, is_subscriber=True)
    assert out5["ok"] is False and out5["terminal"] is True
    assert out5["reason"] == "rfq_support_escalated"
    assert rfq.quality_blocked is True


@pytest.mark.asyncio
async def test_already_blocked_message_differs_by_tier(monkeypatch):
    _patch_verdict(monkeypatch, q.READY)  # verdict irrelevant; blocked short-circuits
    rfq = _FakeRFQ()
    rfq.quality_blocked = True
    free = await q.gate_rfq_for_dispatch(_FakeDB(), rfq, is_subscriber=False)
    paid = await q.gate_rfq_for_dispatch(_FakeDB(), rfq, is_subscriber=True)
    assert free["reason"] == "rfq_terminally_blocked"
    assert paid["reason"] == "rfq_support_escalated"


@pytest.mark.asyncio
async def test_disabled_gate_is_fail_open(monkeypatch):
    async def _cfg(db):
        return {"enabled": False, "block": 45, "warn": 70, "max_free": 2, "max_paid": 5}
    monkeypatch.setattr(q, "_gate_cfg", _cfg)
    _patch_verdict(monkeypatch, q.INCOMPLETE)
    out = await q.gate_rfq_for_dispatch(_FakeDB(), _FakeRFQ(), is_subscriber=False)
    assert out["ok"] is True
