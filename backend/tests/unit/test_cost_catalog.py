"""Operating-cost catalog: live-config prices with static fallback. Pure. asyncio_mode=auto."""
from app.services import cost_catalog as CC


def test_static_gemini_flash_price():
    p = CC.price_for_model("gemini-2.5-flash", None)
    assert p == {"in": 0.0003, "out": 0.0025}


def test_substring_match_handles_prefixed_names():
    p = CC.price_for_model("models/gemini-2.5-flash-001", None)
    assert p["in"] == 0.0003 and p["out"] == 0.0025


def test_most_specific_static_key_wins():
    # 'gemini-2.5-flash-lite' must not be shadowed by 'gemini-2.5-flash'
    p = CC.price_for_model("gemini-2.5-flash-lite", None)
    assert p == {"in": 0.0001, "out": 0.0004}


def test_runtime_override_takes_precedence():
    rt = {"LLM_PRICING": '{"gemini-2.5-flash": {"in": 0.001, "out": 0.009}}'}
    p = CC.price_for_model("gemini-2.5-flash", rt)
    assert p == {"in": 0.001, "out": 0.009}


def test_unknown_model_uses_generic_fallback():
    assert CC.price_for_model("some-brand-new-model", None) == CC._GENERIC


def test_bad_runtime_json_falls_back_to_static():
    rt = {"LLM_PRICING": "{not valid json"}
    assert CC.price_for_model("gemini-2.5-flash", rt) == {"in": 0.0003, "out": 0.0025}


def test_cost_for_tokens_math():
    # 2000 in + 500 out on Flash
    c = CC.cost_for_tokens("gemini-2.5-flash", 2000, 500, None)
    assert abs(c - (2.0 * 0.0003 + 0.5 * 0.0025)) < 1e-9


def test_cost_for_tokens_handles_none():
    assert CC.cost_for_tokens("gemini-2.5-flash", None, None, None) == 0.0


def test_search_request_model_has_token_columns():
    # Guards the operating-cost 'actual' path: the columns it sums must exist.
    from app.models.search import SearchRequest
    for col in ("llm_prompt_tokens", "llm_completion_tokens", "llm_cost_usd"):
        assert hasattr(SearchRequest, col), f"SearchRequest missing {col}"
