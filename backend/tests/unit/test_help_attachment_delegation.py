"""The AI assistant must forward staged document text to the LLM3 specialist
when LLM4 delegates a document-analysis turn. Regression test for the bug where
LLM3 received no document content and kept asking the user to 'upload the file'.
"""
import pytest
import app.services.help_service as hs


@pytest.mark.asyncio
async def test_delegated_doc_analysis_receives_attachment_text(monkeypatch):
    captured = {"llm3_messages": None}

    async def fake_grounding(db, msg):
        return ("", 1.0)  # high similarity -> scope-gate passes

    async def fake_chat_cfg(db):
        return {"api_key": "x", "model": "llm4"}

    async def fake_llm3_cfg(db):
        return {"api_key": "x", "model": "llm3"}

    calls = {"n": 0}

    async def fake_call_llm(cfg, messages, max_tokens=0, temperature=0.0):
        calls["n"] += 1
        if calls["n"] == 1:
            # LLM4 decides this needs the document specialist
            return {"reply": "DELEGATE: assess RFQ completeness", "model": "llm4",
                    "prompt_tokens": 1, "completion_tokens": 1}
        # LLM3 turn — capture what it actually received
        captured["llm3_messages"] = messages
        return {"reply": "The RFQ covers valve sizing but lacks material spec.",
                "model": "llm3", "prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(hs, "_get_grounding", fake_grounding)
    monkeypatch.setattr(hs, "_get_chat_llm_config", fake_chat_cfg)
    monkeypatch.setattr(hs, "_get_llm3_config", fake_llm3_cfg)
    monkeypatch.setattr(hs, "_call_llm", fake_call_llm)

    unique = "BadgerControlValve2inchCv316SS150psi"
    out = await hs.answer_question(
        db=None,
        user=None,
        history=[],
        user_message="is this attached document enough for this RFQ?",
        attachments=[{"key": "assistant-uploads/u/abc/RFQ.pdf",
                      "filename": "RFQ_Badger_Control_Valve.pdf",
                      "excerpt": f"{unique} — needs Cv, body material, pressure rating."}],
    )

    assert out.get("delegated") is True
    # The document text MUST have reached the LLM3 specialist.
    blob = "\n".join(m["content"] for m in captured["llm3_messages"])
    assert unique in blob, "LLM3 did not receive the staged document text"
    assert "valve sizing" in out["reply"].lower() or "material" in out["reply"].lower()
