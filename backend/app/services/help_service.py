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


def _build_system_prompt(manual: str, user: Optional[User], roles: List[str]) -> str:
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
        "- Never mention another user's data. You have no access to it.\n"
        "- Never give legal, financial, medical, or engineering advice, even if asked.\n"
        "- If the manual doesn't contain the answer, say so and point the user to the "
        "Contact page. Do not invent prices, SLAs, policies, or features.\n"
        "- Keep answers short and practical. Prefer bullet points for steps.\n"
        "- Be warm and professional.\n\n"
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
        "=== MANUAL (authoritative) ===\n"
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


async def answer_question(
    db: AsyncSession,
    user: Optional[User],
    history: List[Dict[str, Any]],
    user_message: str,
) -> Dict[str, Any]:
    user_message = (user_message or "").strip()[:_MAX_USER_MESSAGE_CHARS]
    if not user_message:
        return {"reply": "", "error": "empty_message"}

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
        }

    manual = _load_manual()
    roles = list(user.roles or []) if user else []
    system_prompt = _build_system_prompt(manual, user, roles)

    safe_history = _sanitize_history(history)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(safe_history)
    if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
        messages.append({"role": "user", "content": user_message})

    res = await _call_llm(chat_cfg, messages, max_tokens=600, temperature=0.3)
    if res.get("error"):
        return {"reply": "", "error": res["error"],
                "model": res.get("model"), "latency_ms": res.get("latency_ms")}

    reply = (res.get("reply") or "").strip()

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
            }
        spec_prompt = _build_specialist_prompt(manual, user, roles)
        spec_messages: List[Dict[str, str]] = [{"role": "system", "content": spec_prompt}]
        spec_messages.extend(safe_history)
        if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
            spec_messages.append({"role": "user", "content": user_message})
        if focus:
            spec_messages.append({"role": "system", "content": f"Specialist focus: {focus}"})
        res3 = await _call_llm(doc_cfg, spec_messages, max_tokens=900, temperature=0.2)
        if res3.get("error"):
            return {"reply": "", "error": res3["error"], "model": res3.get("model"),
                    "delegated": True, "latency_ms": res3.get("latency_ms")}
        return {
            "reply": (res3.get("reply") or "").strip(),
            "model": res3.get("model"),
            "delegated": True,
            "prompt_tokens": res3.get("prompt_tokens"),
            "completion_tokens": res3.get("completion_tokens"),
            "total_tokens": res3.get("total_tokens"),
            "latency_ms": res3.get("latency_ms"),
        }

    # --- Normal LLM4 answer ---
    return {
        "reply": reply,
        "model": res.get("model"),
        "delegated": False,
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
        "total_tokens": res.get("total_tokens"),
        "latency_ms": res.get("latency_ms"),
    }
