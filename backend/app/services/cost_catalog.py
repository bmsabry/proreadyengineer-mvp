"""Operating-cost pricing catalog for the admin Operating Cost panel.

Goal: make money in/out transparent. Prices are read LIVE from runtime config
(admin-editable, takes effect instantly) and fall back to hardcoded static values
when config is missing or unreachable (e.g. mid-deploy / no network). This keeps the
$/token math accurate without a fragile runtime web-scrape of vendor pricing pages.

Update prices in Admin -> Settings (LLM_PRICING JSON) when a vendor changes them.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Static fallback: USD per 1,000 tokens {in, out}. Verified against vendor pricing
# 2026-05. Keys are matched case-insensitively as substrings of the model name, so
# "gemini-2.5-flash", "models/gemini-2.5-flash-001" etc. all resolve.
STATIC_PRICES_PER_1K: Dict[str, Dict[str, float]] = {
    # Google Gemini (Developer API)
    "gemini-2.5-flash-lite": {"in": 0.0001, "out": 0.0004},
    "gemini-2.5-flash":      {"in": 0.0003, "out": 0.0025},
    "gemini-2.5-pro":        {"in": 0.00125, "out": 0.010},
    "gemini-1.5-flash":      {"in": 0.000075, "out": 0.0003},
    "gemini-1.5-pro":        {"in": 0.00125, "out": 0.005},
    # OpenAI
    "gpt-4o-mini":           {"in": 0.00015, "out": 0.0006},
    "gpt-4o":                {"in": 0.0025, "out": 0.010},
    "gpt-4.1-mini":          {"in": 0.0004, "out": 0.0016},
    # DeepInfra / open models (approx)
    "deepseek":              {"in": 0.00027, "out": 0.0011},
    "kimi":                  {"in": 0.00057, "out": 0.0023},
    "moonshot":              {"in": 0.00057, "out": 0.0023},
    "mistral":               {"in": 0.00010, "out": 0.0003},
    "llama":                 {"in": 0.00009, "out": 0.0003},
    # Embeddings (per 1K tokens; output side unused -> 0)
    "bge-large":             {"in": 0.00001, "out": 0.0},
    "text-embedding-3-small":{"in": 0.00002, "out": 0.0},
    "text-embedding-3-large":{"in": 0.00013, "out": 0.0},
    "bge":                   {"in": 0.00001, "out": 0.0},
}

# Final fallback if a model matches nothing above (use a mid cheap-model price).
_GENERIC = {"in": 0.0003, "out": 0.0025}


def _runtime_prices(rt_cfg: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Parse the admin-editable LLM_PRICING JSON from runtime config, if present.

    Expected shape: {"model-substring": {"in": <per-1k>, "out": <per-1k>}, ...}
    """
    if not rt_cfg:
        return {}
    raw = rt_cfg.get("LLM_PRICING") or rt_cfg.get("llm_pricing") or rt_cfg.get("CHAT_LLM_PRICING")
    if not raw:
        return {}
    try:
        table = json.loads(raw) if isinstance(raw, str) else raw
        out: Dict[str, Dict[str, float]] = {}
        if isinstance(table, dict):
            for k, v in table.items():
                if isinstance(v, dict) and ("in" in v or "out" in v):
                    out[str(k).lower()] = {"in": float(v.get("in", 0.0)), "out": float(v.get("out", 0.0))}
        return out
    except Exception as exc:
        logger.info("[cost_catalog] bad LLM_PRICING config, using static fallback: %s", exc)
        return {}


def price_for_model(model: Optional[str], rt_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Resolve {in, out} per-1K price for a model name.

    Order: exact runtime override -> substring runtime override -> substring static ->
    generic fallback. Always returns a usable dict (never raises).
    """
    name = (model or "").strip().lower()
    runtime = _runtime_prices(rt_cfg)
    # exact then substring against runtime overrides
    if name in runtime:
        return runtime[name]
    for key, val in runtime.items():
        if key and key in name:
            return val
    # substring against static catalog (longest key first = most specific)
    for key in sorted(STATIC_PRICES_PER_1K.keys(), key=len, reverse=True):
        if key in name:
            return STATIC_PRICES_PER_1K[key]
    return dict(_GENERIC)


def cost_for_tokens(model: Optional[str], prompt_tokens, completion_tokens,
                    rt_cfg: Optional[Dict[str, Any]] = None) -> float:
    """USD cost for a given model + token usage."""
    p = price_for_model(model, rt_cfg)
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)
    return round((pt / 1000.0) * p["in"] + (ct / 1000.0) * p["out"], 6)
