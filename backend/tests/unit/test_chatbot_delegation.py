"""LLM4 chatbot + LLM3 delegation logic (help_service.answer_question).

asyncio_mode=auto, so no decorator needed.
"""
from app.services import help_service


def _cfgs(monkeypatch, llm3_key="k3"):
    async def fake_chat_cfg(db):
        return {"api_key": "k4", "model": "llm4-model", "base": "http://llm4"}

    async def fake_doc_cfg(db):
        return {"api_key": llm3_key, "model": "llm3-model", "base": "http://llm3"}

    monkeypatch.setattr(help_service, "_get_chat_llm_config", fake_chat_cfg)
    monkeypatch.setattr(help_service, "_get_llm3_config", fake_doc_cfg)


async def test_normal_question_answered_by_llm4_only(monkeypatch):
    _cfgs(monkeypatch)
    calls = []

    async def fake_call(cfg, messages, *, max_tokens=600, temperature=0.3):
        calls.append(cfg["model"])
        return {"reply": "Go to the Search page and enter your needs.",
                "model": cfg["model"], "latency_ms": 5}

    monkeypatch.setattr(help_service, "_call_llm", fake_call)
    res = await help_service.answer_question(
        db=None, user=None, history=[], user_message="How do I search for a firm?")

    assert res["delegated"] is False
    assert res["model"] == "llm4-model"
    assert calls == ["llm4-model"]  # LLM3 never touched on a normal turn
    assert "Search page" in res["reply"]


async def test_delegates_to_llm3_on_directive(monkeypatch):
    _cfgs(monkeypatch)
    calls = []

    async def fake_call(cfg, messages, *, max_tokens=600, temperature=0.3):
        calls.append(cfg["model"])
        if cfg["model"] == "llm4-model":
            return {"reply": "DELEGATE: summarise the quote the user received",
                    "model": "llm4-model", "latency_ms": 4}
        return {"reply": "The quote totals $5,000 for 3 line items.",
                "model": "llm3-model", "latency_ms": 9}

    monkeypatch.setattr(help_service, "_call_llm", fake_call)
    res = await help_service.answer_question(
        db=None, user=None, history=[],
        user_message="Can you read the quote I received and summarise it?")

    assert res["delegated"] is True
    assert res["model"] == "llm3-model"          # final answer came from LLM3
    assert calls == ["llm4-model", "llm3-model"]  # LLM4 decided, LLM3 executed
    assert "5,000" in res["reply"]


async def test_delegation_graceful_when_llm3_unconfigured(monkeypatch):
    _cfgs(monkeypatch, llm3_key="")  # LLM3 has no key
    calls = []

    async def fake_call(cfg, messages, *, max_tokens=600, temperature=0.3):
        calls.append(cfg["model"])
        return {"reply": "DELEGATE: analyse the attached image",
                "model": "llm4-model", "latency_ms": 4}

    monkeypatch.setattr(help_service, "_call_llm", fake_call)
    res = await help_service.answer_question(
        db=None, user=None, history=[], user_message="What does this diagram show?")

    assert res["delegated"] is True
    assert res["error"] == "llm3_not_configured"
    assert calls == ["llm4-model"]  # LLM3 not called because unconfigured
    assert "analyse" in res["reply"].lower() or "analysis" in res["reply"].lower()
