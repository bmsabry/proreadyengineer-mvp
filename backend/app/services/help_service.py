"""AI Help Assistant service.

Default chatbot brain is LLM4 (CHAT_LLM_*) - a cheap/fast model that answers
general platform questions. When a turn requires analysing an image or reading a
specific document's contents, LLM4 emits a "DELEGATE:" directive and the request
is handed to LLM3 (DOC_LLM_*), the more capable (and more expensive) specialist.
Both use the runtime-config-first read pattern. Grounded on
docs/help/proreadyengineer_manual.md. Subscription gate included.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import SubscriptionStatus, SubscriptionType
from app.models.payment import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)

_CHATBOT_ACCESS_TYPES = {
    SubscriptionType.SEARCH_TIER_1,
    SubscriptionType.SEARCH_TIER_2,
    SubscriptionType.PROVIDER_PROFILE,
    SubscriptionType.PROVIDER_ANNUAL,
}
_ACTIVE_STATUSES = {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}

_MANUAL_PATHS = [
    Path(__file__).resolve().parent.parent.parent.parent / "docs" / "help" / "proreadyengineer_manual.md",
    Path("docs/help/proreadyengineer_manual.md"),
    Path("../docs/help/proreadyengineer_manual.md"),
]

_MANUAL_CACHE: Optional[str] = None
_MANUAL_LOADED_AT: float = 0.0
_MANUAL_TTL_SEC = 300


def _load_manual() -> str:
    global _MANUAL_CACHE, _MANUAL_LOADED_AT
    now = time.time()
    if _MANUAL_CACHE is not None and (now - _MANUAL_LOADED_AT) < _MANUAL_TTL_SEC:
        return _MANUAL_CACHE
    for p in _MANUAL_PATHS:
        try:
            if p.exists():
                txt = p.read_text(encoding="utf-8")
                _MANUAL_CACHE = txt
                _MANUAL_LOADED_AT = now
                logger.info("[help_service] Loaded manual from %s (%d chars)", p, len(txt))
                return txt
        except Exception as e:
            logger.warning("[help_service] Could not read %s: %s", p, e)
    logger.error("[help_service] Manual not found on any candidate path")
    _MANUAL_CACHE = (
        "NO_MANUAL_AVAILABLE. Tell the user the help system is temporarily "
        "unavailable and they should contact support via the Contact page."
    )
    _MANUAL_LOADED_AT = now
    return _MANUAL_CACHE


async def user_has_chatbot_access(db: AsyncSession, user: Optional[User]) -> Tuple[bool, str]:
    if user is None:
        return False, "not_authenticated"
    roles = set(user.roles or [])
    if "admin" in roles:
        return True, "admin"
    types_values = [t.value for t in _CHATBOT_ACCESS_TYPES]
    statuses_values = [s.value for s in _ACTIVE_STATUSES]
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.subscription_type.in_(types_values),
            Subscription.subscription_status.in_(statuses_values),
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True, "paid_subscription"
    return False, "no_active_subscription"


_DELEGATE_PREFIX = "DELEGATE:"


def _build_system_prompt(manual: str, user: Optional[User], roles: List[str], account_context: str = "") -> str:
    role_str = "anonymous"
    if user is not None:
        role_str = ",".join(roles) or "authenticated"
    return (
        "You are the ProMechDirectory AI Help Assistant. Your only job is to help users "
        "understand how the ProMechDirectory website works, using the MANUAL below as the "
        "source of truth.\n\n"
        "GROUND RULES (non-negotiable):\n"
        "- Answer only questions about the ProMechDirectory platform. If the user asks "
        "about anything else (legal advice, engineering advice, general knowledge, code, "
        "other products), politely decline and offer to help with the platform instead.\n"
        "- Never take actions on the user's behalf. You cannot submit, cancel, pay, or "
        "modify anything. If a user asks you to do something, tell them which page and "
        "button to use.\n"
        "- You have a LIVE snapshot of THIS signed-in user's own account below (their "
        "subscription, RFQ/quote counts, and action items). Use it to answer questions about "
        "their own account and, when they ask what to do next, give a short PRIORITIZED list "
        "from their ACTION ITEMS with the exact page/button to use.\n"
        "- Never mention or infer another user's data. You only ever have this user's own.\n"
        "- Never give legal, financial, medical, or engineering advice, even if asked.\n"
        "- If the manual doesn't contain the answer, say so and point the user to the "
        "Contact page. Do not invent prices, SLAs, policies, or features.\n"
        "- Keep answers short and practical. Prefer bullet points for steps.\n"
        "- Be warm and professional.\n\n"
        "NAVIGATION & DRAFTING:\n"
        "- When it helps the user act, point them to the exact page and, at the VERY END of "
        "your reply, add one line listing up to 3 in-app links to render as buttons:\n"
        "  " + _LINK_PREFIX + " /path|Short label ;; /path2|Short label2\n"
        "  Use ONLY these real paths: /customer/dashboard, /customer/rfq/new, /customer/quotes, "
        "/customer/all-rfqs, /customer/profile, /billing, /search, /provider/dashboard, "
        "/provider/rfqs, /provider/accepted-rfqs, /provider/upgrade, /provider/profile, "
        "/provider/advertise, /help, /contact. Pick links that match the user's role and need. "
        "Never invent a path; omit the line if none fit.\n"
        "- If the user asks you to draft something (an RFQ description, a message to a customer/"
        "provider), write a clear, concise draft they can copy and edit, then point them with a "
        "link to where they submit it. You prepare drafts; the user reviews and submits.\n\n"
        "DELEGATION (very important):\n"
        "- You are a fast, cost-effective model. You CANNOT look at images and you CANNOT "
        "read or analyse the contents of a specific document (such as a Quote or an RFQ the "
        "user received, or any attached/pasted file). A more capable specialist model "
        "handles those.\n"
        "- If, and ONLY if, answering the user's latest request requires analysing an image "
        "or reading/analysing the actual contents of a specific document, you MUST NOT "
        "answer it yourself. Instead reply with EXACTLY one line and nothing else:\n"
        "  " + _DELEGATE_PREFIX + " <one concise sentence describing what the specialist should analyse or answer>\n"
        "- For everything else - how the platform works, navigation, pricing/policies from "
        "the manual, account/subscription questions, general guidance - answer normally "
        "yourself. Do NOT delegate ordinary questions.\n\n"
        f"USER CONTEXT: the user is signed in with role(s) = {role_str}. Tailor examples "
        "to their role when helpful.\n\n"
        + (("=== THIS USER'S ACCOUNT (live, authoritative for their own data) ===\n" + account_context + "\n=== END ACCOUNT ===\n\n") if account_context else "")
        + "=== MANUAL (authoritative) ===\n"
        f"{manual}\n"
        "=== END MANUAL ==="
    )


def _build_specialist_prompt(manual: str, user: Optional[User], roles: List[str]) -> str:
    """System prompt for LLM3 (the document / image analysis specialist)."""
    role_str = "anonymous"
    if user is not None:
        role_str = ",".join(roles) or "authenticated"
    return (
        "You are the ProMechDirectory document & image analysis specialist. The fast "
        "assistant handed this conversation to you because the user's request needs you to "
        "read or analyse the actual contents of a document or an image.\n\n"
        "RULES:\n"
        "- Analyse only the document text or image content present in this conversation, "
        "plus the platform MANUAL below for context. \n"
        "- If the conversation does not actually contain the document/image content needed "
        "to answer (only a reference to it), say so plainly and tell the user how to provide "
        "it (e.g. open the specific Quote/RFQ and paste the relevant text), then stop.\n"
        "- Never give legal, financial, medical, or engineering advice, and never invent "
        "facts, prices, or policies.\n"
        "- Never reveal or reference another user's data.\n"
        "- Be accurate, concrete, and concise.\n\n"
        f"USER CONTEXT: role(s) = {role_str}.\n\n"
        "=== MANUAL (context only) ===\n"
        f"{manual}\n"
        "=== END MANUAL ==="
    )


async def _get_llm3_config(db: AsyncSession) -> Dict[str, Optional[str]]:
    from app.services.config_service import get_runtime_config
    rt_cfg = await get_runtime_config(db)
    api_key = (
        rt_cfg.get("DOC_LLM_API_KEY") or rt_cfg.get("doc_llm_api_key")
        or rt_cfg.get("OPENAI_API_KEY") or rt_cfg.get("openai_api_key")
        or getattr(settings, "DOC_LLM_API_KEY", None)
        or getattr(settings, "OPENAI_API_KEY", None)
    )
    model = (
        rt_cfg.get("DOC_LLM_MODEL") or rt_cfg.get("doc_llm_model")
        or rt_cfg.get("OPENAI_LLM_MODEL") or rt_cfg.get("openai_llm_model")
        or getattr(settings, "DOC_LLM_MODEL", None)
        or getattr(settings, "OPENAI_LLM_MODEL", "gpt-4o-mini")
    )
    base = (
        rt_cfg.get("DOC_LLM_API_BASE") or rt_cfg.get("doc_llm_api_base")
        or rt_cfg.get("OPENAI_API_BASE") or rt_cfg.get("openai_api_base")
        or getattr(settings, "DOC_LLM_API_BASE", None)
        or getattr(settings, "OPENAI_API_BASE", None)
        or "https://api.openai.com/v1"
    )
    return {"api_key": api_key, "model": model, "base": base}


async def _get_chat_llm_config(db: AsyncSession) -> Dict[str, Optional[str]]:
    """LLM4 (CHAT_LLM_*) - the default chatbot model.

    Falls back to LLM3 (DOC_LLM_*) then LLM1 (OPENAI_*) so the chatbot keeps
    working even if LLM4 has not been configured yet.
    """
    from app.services.config_service import get_runtime_config
    rt_cfg = await get_runtime_config(db)
    api_key = (
        rt_cfg.get("CHAT_LLM_API_KEY") or rt_cfg.get("chat_llm_api_key")
        or rt_cfg.get("DOC_LLM_API_KEY") or rt_cfg.get("doc_llm_api_key")
        or rt_cfg.get("OPENAI_API_KEY") or rt_cfg.get("openai_api_key")
        or getattr(settings, "DOC_LLM_API_KEY", None)
        or getattr(settings, "OPENAI_API_KEY", None)
    )
    model = (
        rt_cfg.get("CHAT_LLM_MODEL") or rt_cfg.get("chat_llm_model")
        or rt_cfg.get("DOC_LLM_MODEL") or rt_cfg.get("doc_llm_model")
        or rt_cfg.get("OPENAI_LLM_MODEL") or rt_cfg.get("openai_llm_model")
        or getattr(settings, "OPENAI_LLM_MODEL", "gpt-4o-mini")
    )
    base = (
        rt_cfg.get("CHAT_LLM_API_BASE") or rt_cfg.get("chat_llm_api_base")
        or rt_cfg.get("DOC_LLM_API_BASE") or rt_cfg.get("doc_llm_api_base")
        or rt_cfg.get("OPENAI_API_BASE") or rt_cfg.get("openai_api_base")
        or getattr(settings, "OPENAI_API_BASE", None)
        or "https://api.openai.com/v1"
    )
    return {"api_key": api_key, "model": model, "base": base}


async def _call_llm(
    cfg: Dict[str, Optional[str]],
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 600,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Single OpenAI-compatible chat-completion call. Returns reply/usage/error."""
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    url = f"{str(cfg['base']).rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except Exception as exc:
        logger.exception("[help_service] LLM request failed: %s", exc)
        return {"reply": "", "error": f"llm_request_failed: {exc}", "model": cfg["model"]}
    latency_ms = int((time.time() - t0) * 1000)
    if resp.status_code >= 400:
        body = resp.text[:400]
        logger.warning("[help_service] LLM non-2xx: %s %s", resp.status_code, body)
        return {"reply": "", "error": f"llm_http_{resp.status_code}: {body}",
                "latency_ms": latency_ms, "model": cfg["model"]}
    try:
        data = resp.json()
        reply = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
    except Exception as exc:
        logger.exception("[help_service] Unparseable LLM response: %s", exc)
        return {"reply": "", "error": f"llm_parse_failed: {exc}",
                "latency_ms": latency_ms, "model": cfg["model"]}
    return {
        "reply": reply,
        "model": cfg["model"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "latency_ms": latency_ms,
    }


_MAX_USER_MESSAGE_CHARS = 2000
_MAX_HISTORY_TURNS = 10


_ACCOUNT_HINTS = (
    "my ", "what should i", "what do i", "next", "pending", "waiting", "to do",
    "todo", "action", "status of", "subscription", "renew", "quote", "rfq", "nda",
    "credits", "remaining", "account", "plan", "do i have", "how many",
)


def _looks_account_related(msg: str) -> bool:
    m = (msg or "").lower()
    return any(h in m for h in _ACCOUNT_HINTS)


# Navigation: the model may end a reply with a line like
#   SUGGESTED_LINKS: /customer/rfq/new|Submit a new RFQ ;; /customer/quotes|Review quotes
# We parse it into validated INTERNAL links the widget renders as buttons.
_LINK_PREFIX = "SUGGESTED_LINKS:"
_ALLOWED_LINK_PREFIXES = (
    "/customer", "/provider", "/billing", "/search", "/help", "/contact",
    "/advertise", "/featured-firms", "/software-providers", "/providers",
    "/profile", "/login", "/register",
)


def _is_safe_internal_path(href: str) -> bool:
    href = (href or "").strip()
    if not href.startswith("/") or href.startswith("//"):
        return False
    if "://" in href or "\\" in href or " " in href:
        return False
    seg = "/" + href.lstrip("/").split("/", 1)[0]
    return any(href == p or href.startswith(p + "/") or seg == p for p in _ALLOWED_LINK_PREFIXES)


def _extract_links(reply: str):
    """Return (clean_reply, links[]). links = [{href,label}] validated internal-only, max 3."""
    if not reply or _LINK_PREFIX not in reply:
        return reply, []
    lines = reply.splitlines()
    kept, links = [], []
    for ln in lines:
        if ln.strip().upper().startswith(_LINK_PREFIX):
            payload = ln.split(":", 1)[1] if ":" in ln else ""
            for entry in payload.split(";;"):
                entry = entry.strip()
                if not entry:
                    continue
                if "|" in entry:
                    href, label = entry.split("|", 1)
                else:
                    href, label = entry, entry
                href, label = href.strip(), label.strip()[:60]
                if _is_safe_internal_path(href) and len(links) < 3:
                    links.append({"href": href, "label": label or href})
        else:
            kept.append(ln)
    return "\n".join(kept).strip(), links


def _sanitize_history(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not isinstance(history, list):
        return []
    out: List[Dict[str, str]] = []
    for item in history[-_MAX_HISTORY_TURNS:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "") or "")[:_MAX_USER_MESSAGE_CHARS]
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content})
    return out


# ---------------------------------------------------------------------------
# Phase 1: RAG retrieval, scope-gate, and per-user budget metering.
# ---------------------------------------------------------------------------
import hashlib as _hashlib
import math as _math

_RAG_TOP_K = 4
# Conservative: only refuse when the best matching manual chunk is clearly unrelated,
# to avoid wrongly refusing a paying user. Tunable.
_SCOPE_MIN_SIM = 0.20

# Default token prices (USD per 1K tokens). Cheap models (DeepSeek V4 Flash,
# gpt-4o-mini class) are well under these; admins can override per model via the
# runtime-config key CHAT_LLM_PRICING (JSON: {"model": {"in": x, "out": y}, ...}).
_DEFAULT_PRICE_PER_1K = {"in": 0.0003, "out": 0.0010}

# In-memory chunk + embedding cache, keyed by a hash of the manual text.
_CHUNK_CACHE: Dict[str, List[str]] = {}
_CHUNK_EMB_CACHE: Dict[str, List[List[float]]] = {}


def _chunk_manual(manual: str) -> List[str]:
    """Split the manual into self-contained chunks at ## / ### headers."""
    import re
    if not manual or manual.startswith("NO_MANUAL_AVAILABLE"):
        return [manual or ""]
    parts = re.split(r"(?m)^(?=#{2,3}\s)", manual)
    chunks = [p.strip() for p in parts if p.strip()]
    # Keep the leading preamble (before the first header) as its own chunk.
    return chunks or [manual]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = _math.sqrt(sum(x * x for x in a))
    nb = _math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _price_for_model(model: Optional[str], rt_cfg: Dict[str, Any]) -> Dict[str, float]:
    """Resolve (in, out) per-1K price for a model from runtime config or defaults."""
    pricing_raw = (rt_cfg or {}).get("CHAT_LLM_PRICING") or (rt_cfg or {}).get("chat_llm_pricing")
    if pricing_raw:
        try:
            import json as _json
            table = _json.loads(pricing_raw) if isinstance(pricing_raw, str) else pricing_raw
            if isinstance(table, dict) and model in table:
                e = table[model]
                return {"in": float(e.get("in", _DEFAULT_PRICE_PER_1K["in"])),
                        "out": float(e.get("out", _DEFAULT_PRICE_PER_1K["out"]))}
        except Exception:
            pass
    return dict(_DEFAULT_PRICE_PER_1K)


def _estimate_cost(model: Optional[str], prompt_tokens, completion_tokens, rt_cfg: Dict[str, Any]) -> float:
    p = _price_for_model(model, rt_cfg)
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)
    return round((pt / 1000.0) * p["in"] + (ct / 1000.0) * p["out"], 6)


async def _user_month_cost(db: AsyncSession, user_id) -> float:
    """Sum this user's assistant cost for the current calendar month (USD)."""
    if user_id is None:
        return 0.0
    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from app.models.help_chat import HelpChatLog
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    try:
        total = (await db.execute(
            select(func.coalesce(func.sum(HelpChatLog.cost_usd), 0.0)).where(
                HelpChatLog.user_id == user_id,
                HelpChatLog.created_at >= month_start,
            )
        )).scalar()
        return float(total or 0.0)
    except Exception as exc:
        logger.warning("[help_service] month-cost lookup failed: %s", exc)
        return 0.0


async def _embed_text(text: str, db: AsyncSession) -> Optional[List[float]]:
    """Embed one string via the shared search embedding stack. None on failure."""
    try:
        from app.services.config_service import get_runtime_config
        from app.services.search_service import generate_embedding
        rt = await get_runtime_config(db)
        return await generate_embedding(text, runtime_config=rt)
    except Exception as exc:
        logger.info("[help_service] embedding unavailable, RAG disabled this turn: %s", exc)
        return None


async def _get_grounding(db: AsyncSession, query: str) -> Tuple[str, Optional[float]]:
    """Return (context_text, max_similarity).

    Retrieves the top-K most relevant manual chunks for the query. Falls back to
    the FULL manual (and max_similarity=None) whenever embeddings are unavailable,
    so the assistant never breaks because of the RAG layer.
    """
    manual = _load_manual()
    key = _hashlib.sha1(manual.encode("utf-8")).hexdigest()
    chunks = _CHUNK_CACHE.get(key)
    if chunks is None:
        chunks = _chunk_manual(manual)
        _CHUNK_CACHE[key] = chunks
    embs = _CHUNK_EMB_CACHE.get(key)
    if embs is None:
        import asyncio
        results = await asyncio.gather(*[_embed_text(c, db) for c in chunks])
        if any(r is None for r in results):
            return manual, None  # embeddings unavailable -> full-manual fallback
        embs = results  # type: ignore
        _CHUNK_EMB_CACHE[key] = embs  # type: ignore
    q_emb = await _embed_text(query, db)
    if q_emb is None:
        return manual, None
    sims = [(_cosine(q_emb, e), i) for i, e in enumerate(embs)]
    sims.sort(reverse=True)
    max_sim = sims[0][0] if sims else None
    top_idx = sorted(i for _, i in sims[:_RAG_TOP_K])
    context = "\n\n".join(chunks[i] for i in top_idx)
    return context, max_sim


async def answer_question(
    db: AsyncSession,
    user: Optional[User],
    history: List[Dict[str, Any]],
    user_message: str,
    page: Optional[str] = None,
) -> Dict[str, Any]:
    user_message = (user_message or "").strip()[:_MAX_USER_MESSAGE_CHARS]
    if not user_message:
        return {"reply": "", "error": "empty_message"}

    # --- Per-user monthly budget pre-flight (admins exempt) ---
    from app.core.config import settings as _settings
    rt_cfg: Dict[str, Any] = {}
    try:
        from app.services.config_service import get_runtime_config
        rt_cfg = await get_runtime_config(db)
    except Exception:
        rt_cfg = {}
    budget = float(getattr(_settings, "CHATBOT_MONTHLY_BUDGET_USD", 15.0))
    is_admin = bool(user and "admin" in (user.roles or []))
    if user is not None and not is_admin:
        spent = await _user_month_cost(db, user.id)
        if spent >= budget:
            logger.info("[help_service] budget cap hit user=%s spent=%.4f", user.id, spent)
            return {
                "reply": (
                    f"You've reached this month's AI Assistant usage limit (about ${budget:.0f}). "
                    "It resets on the 1st of next month. If you need a higher limit, contact us "
                    "via the Contact page and we'll be happy to raise it."
                ),
                "error": "budget_exceeded",
                "cost_usd": 0.0,
            }

    # --- LLM4 (default, cost-effective chatbot brain) ---
    chat_cfg = await _get_chat_llm_config(db)
    if not chat_cfg["api_key"]:
        logger.error("[help_service] No chatbot LLM (LLM4/LLM3) key configured")
        return {
            "reply": (
                "The AI Help Assistant is temporarily unavailable. "
                "Please check the Contact page for support."
            ),
            "error": "llm_not_configured",
            "cost_usd": 0.0,
        }

    roles = list(user.roles or []) if user else []
    # Personalization: compact, user-scoped account snapshot + action items.
    account_ctx = ""
    if user is not None:
        try:
            from app.services.help_context import build_account_context, render_account_context
            _snap = await build_account_context(db, user)
            account_ctx = render_account_context(_snap, page=page)
        except Exception as exc:
            logger.info("[help_service] account context failed: %s", exc)
            account_ctx = ""

    # RAG: ground on the most relevant manual chunks (falls back to full manual).
    grounding, max_sim = await _get_grounding(db, user_message)

    # Scope-gate: clearly off-topic question -> refuse cheaply, no LLM call.
    # Account-related questions ("what should I do next", "my quotes") bypass the gate.
    if max_sim is not None and max_sim < _SCOPE_MIN_SIM and not _looks_account_related(user_message):
        logger.info("[help_service] scope-gate refused (sim=%.3f) msg=%r", max_sim, user_message[:80])
        return {
            "reply": (
                "I can only help with the ProMechDirectory platform — things like RFQs, quotes, "
                "unlocking, NDAs, subscriptions, search, and your account. Could you rephrase your "
                "question about the platform?"
            ),
            "error": "out_of_scope",
            "cost_usd": 0.0,
        }

    system_prompt = _build_system_prompt(grounding, user, roles, account_context=account_ctx)

    safe_history = _sanitize_history(history)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(safe_history)
    if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
        messages.append({"role": "user", "content": user_message})

    res = await _call_llm(chat_cfg, messages, max_tokens=600, temperature=0.3)
    if res.get("error"):
        return {"reply": "", "error": res["error"],
                "model": res.get("model"), "latency_ms": res.get("latency_ms"), "cost_usd": 0.0}

    reply = (res.get("reply") or "").strip()
    cost4 = _estimate_cost(res.get("model"), res.get("prompt_tokens"), res.get("completion_tokens"), rt_cfg)

    # --- Delegation: LLM4 asked the LLM3 specialist to handle this turn ---
    if reply.upper().startswith(_DELEGATE_PREFIX):
        focus = reply.split(":", 1)[1].strip() if ":" in reply else ""
        logger.info("[help_service] LLM4 delegated to LLM3. focus=%r", focus[:160])
        doc_cfg = await _get_llm3_config(db)
        if not doc_cfg["api_key"]:
            logger.warning("[help_service] Delegation requested but LLM3 not configured")
            return {
                "reply": (
                    "I'd need to analyse that document or image to answer, but the "
                    "document-analysis service isn't available right now. Please try "
                    "again later or reach out via the Contact page."
                ),
                "model": chat_cfg["model"],
                "error": "llm3_not_configured",
                "delegated": True,
                "latency_ms": res.get("latency_ms"),
                "cost_usd": cost4,
            }
        spec_prompt = _build_specialist_prompt(grounding, user, roles)
        spec_messages: List[Dict[str, str]] = [{"role": "system", "content": spec_prompt}]
        spec_messages.extend(safe_history)
        if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
            spec_messages.append({"role": "user", "content": user_message})
        if focus:
            spec_messages.append({"role": "system", "content": f"Specialist focus: {focus}"})
        res3 = await _call_llm(doc_cfg, spec_messages, max_tokens=900, temperature=0.2)
        cost3 = _estimate_cost(res3.get("model"), res3.get("prompt_tokens"), res3.get("completion_tokens"), rt_cfg)
        if res3.get("error"):
            return {"reply": "", "error": res3["error"], "model": res3.get("model"),
                    "delegated": True, "latency_ms": res3.get("latency_ms"), "cost_usd": round(cost4 + cost3, 6)}
        clean3, links3 = _extract_links((res3.get("reply") or "").strip())
        return {
            "reply": clean3,
            "links": links3,
            "model": res3.get("model"),
            "delegated": True,
            "prompt_tokens": res3.get("prompt_tokens"),
            "completion_tokens": res3.get("completion_tokens"),
            "total_tokens": res3.get("total_tokens"),
            "latency_ms": res3.get("latency_ms"),
            "cost_usd": round(cost4 + cost3, 6),
        }

    # --- Normal LLM4 answer ---
    clean, links = _extract_links(reply)
    return {
        "reply": clean,
        "links": links,
        "model": res.get("model"),
        "delegated": False,
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
        "total_tokens": res.get("total_tokens"),
        "latency_ms": res.get("latency_ms"),
        "cost_usd": cost4,
    }
