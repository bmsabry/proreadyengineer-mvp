"""Phase 1 chatbot helpers: chunking, cosine, cost estimate, scope threshold.
Pure functions only (no DB / network). asyncio_mode=auto.
"""
from app.services import help_service as H


def test_chunk_manual_splits_on_headers():
    md = "intro text\n\n## Section A\nbody a\n\n### Sub B\nbody b\n\n## Section C\nbody c"
    chunks = H._chunk_manual(md)
    assert len(chunks) == 4  # preamble + A + Sub B + C
    assert chunks[1].startswith("## Section A")
    assert any("Section C" in c for c in chunks)


def test_chunk_manual_handles_empty_or_missing():
    assert H._chunk_manual("NO_MANUAL_AVAILABLE...") == ["NO_MANUAL_AVAILABLE..."]


def test_cosine_basics():
    assert H._cosine([1, 0], [1, 0]) == 1.0
    assert H._cosine([1, 0], [0, 1]) == 0.0
    assert abs(H._cosine([1, 1], [1, 1]) - 1.0) < 1e-9
    assert H._cosine([], [1]) == 0.0  # mismatched/empty -> 0


def test_estimate_cost_uses_defaults():
    # 2000 prompt + 500 completion tokens at default $0.0003/$0.0010 per 1K
    c = H._estimate_cost("some-model", 2000, 500, {})
    assert abs(c - (2.0 * 0.0003 + 0.5 * 0.0010)) < 1e-9  # 0.0011


def test_estimate_cost_respects_runtime_override():
    rt = {"CHAT_LLM_PRICING": '{"m": {"in": 0.001, "out": 0.002}}'}
    c = H._estimate_cost("m", 1000, 1000, rt)
    assert abs(c - (0.001 + 0.002)) < 1e-9


def test_scope_threshold_is_conservative():
    # A clearly-unrelated query should fall below the gate; relevant stays above.
    assert H._SCOPE_MIN_SIM <= 0.25  # conservative to avoid false refusals


def test_price_for_model_falls_back_to_default():
    p = H._price_for_model("unknown-model", {})
    assert p == H._DEFAULT_PRICE_PER_1K
