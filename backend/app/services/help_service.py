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
_MEMORY_PREFIX = "MEMORY:"  # one-line self-note the assistant persists across sessions


_PROVIDER_PROFILE_COACH = (
    "PROVIDER PROFILE \u2014 HELP THEM GET MATCHED:\n"
    "- If the account section above includes the user's FIRM PROFILE snapshot, assess completeness "
    "SPECIFICALLY from it: say roughly how complete it is and name the exact empty/thin fields and "
    "what to add \u2014 do not say you cannot see their fields, and do not give only generic guidance.\n"
    "- WHENEVER you point out missing or thin fields, DO NOT stop at listing them. PROACTIVELY OFFER, in the same reply, to fill them FOR them: tell them they can upload a capability statement, brochure, line card, or past-project write-up (the paperclip in this chat) and you will pull the details into their profile, OR they can just tell you the details in chat and you will add them. Make this offer every time you identify gaps \u2014 do not wait to be asked.\n"

    "- Providers receive RFQs based on how well their profile reflects what they actually do. The "
    "more SPECIFIC and COMPLETE their profile, the more \u2014 and more relevant \u2014 RFQs reach "
    "them. Frame it exactly that way. NEVER explain or speculate about HOW the matching/ranking works "
    "internally (no talk of scores, weights, embeddings, or which field counts most) \u2014 just coach "
    "them to a rich, accurate profile because it helps THEM win the right work.\n"
    "- When a provider wants help with their profile (or clearly has a thin one), coach them to fill "
    "these with concrete, technical specifics (not vague marketing):\n"
    "  \u2022 Capabilities \u2014 engineering services they perform (e.g. 'FEA structural analysis', "
    "'HVAC load calculations', 'pressure-vessel design to ASME VIII').\n"
    "  \u2022 Specialties / industries served (e.g. 'oil & gas', 'data-center cooling', 'medical devices').\n"
    "  \u2022 Software & tools (SolidWorks, ANSYS Fluent, Creo), equipment, certifications (ISO 9001, "
    "ASME stamps, PE licensure), notable clients.\n"
    "  \u2022 Notable Projects \u2014 the most valuable. For EACH past project, ONE clear sentence: what "
    "they did + the method/approach + the outcome/purpose. Coach them to add several, specific and "
    "factual. OFFER TO DRAFT these from what they tell you, for them to review.\n"
    "- OFFER THE UPLOAD: tell them they can attach a capability statement, brochure, line card, or "
    "past-project write-ups (the paperclip in this chat) and you will pull the details into their "
    "profile. If they have staged such documents and ask you to update/improve their profile, end your "
    "reply with: PROPOSE_ACTION: update_profile_from_docs|<any>|Update your firm profile from the "
    "uploaded document(s)  (no file keys \u2014 the server uses the staged uploads; it MERGES with their "
    "- CONVERSATIONAL FILL: if the provider just TELLS you specific things to add (a capability, tool, certification, or a project), you may apply it directly. Confirm what you'll add, then end your reply with two lines: a PROPOSE_ACTION line 'update_profile_from_chat|<any>|<short summary>' AND a companion 'PROFILE_DATA: {json}' line whose JSON has ONLY these keys you are adding (lists for capabilities / specialties / software_tools / equipment / certifications / proven_experience_notable_projects; strings for team_summary / primary_specialty). Put ONLY their real, stated details \u2014 never invent. It merges additively and removes nothing; they confirm before it saves.\n"
    "existing profile and removes nothing; they review afterward). Saving requires Professional / founding "
    "membership \u2014 if they cannot edit yet, point them to /provider/upgrade.\n\n"
)


def _build_system_prompt(manual: str, user: Optional[User], roles: List[str], account_context: str = "", autonomous: bool = False, is_admin: bool = False, page: Optional[str] = None) -> str:
    role_str = "anonymous"
    if user is not None:
        role_str = ",".join(roles) or "authenticated"
    return (
        "You are the ProMechDirectory AI Assistant. You help users with (1) how the "
        "ProMechDirectory website works — using the MANUAL below as the source of truth — and "
        "(2) general MECHANICAL ENGINEERING questions, since this is a mechanical-engineering "
        "services directory.\n\n"
        "GROUND RULES (non-negotiable):\n"
        "- IN SCOPE: anything about the ProMechDirectory platform, and general mechanical / "
        "engineering topics (design, materials, manufacturing, FEA/CFD, thermodynamics, "
        "tolerances, standards, CAD, etc.). For platform facts, rely on the MANUAL; for "
        "engineering questions, answer helpfully and accurately, note key assumptions, and add "
        "a brief caveat that it's general information, not a stamped professional engineering "
        "judgement.\n"
        "- OUT OF SCOPE: topics unrelated to the platform or to engineering (politics, general "
        "trivia, other products, coding help, etc.) — politely decline and offer to help with "
        "the platform or an engineering question instead. Still never give legal, financial, or "
        "medical advice, and never give specific safety-critical engineering sign-off (e.g. "
        "'this pressure vessel is safe to operate') — give general guidance and recommend a "
        "qualified, licensed engineer for anything safety-critical or code-stamped.\n"
        "- Never take actions on the user's behalf. You cannot submit, cancel, pay, or "
        "modify anything. If a user asks you to do something, tell them which page and "
        "button to use.\n"
        "- You have a LIVE, COMPREHENSIVE snapshot of THIS signed-in user's own account below: "
        "their identity, subscription, all their RFQ/quote counts and metrics (e.g. RFQs "
        "received, quotes submitted, accepted, pending decisions, not selected, NDAs signed, "
        "win rate, searches used, member-since) and their action items. ANSWER ANY question "
        "about their own account directly and specifically from these numbers — do not deflect "
        "to 'check your dashboard' when the figure is right here. When they ask what to do next, "
        "give a short PRIORITIZED list from their ACTION ITEMS with the exact page/button.\n"
        "- If a specific figure genuinely is not in the snapshot, say so plainly and point to the "
        "page that shows it — don't guess or invent a number.\n"
        "- This snapshot is ONLY ever this one signed-in user's data. Never mention, infer, or "
        "compare another user's data — you do not have it.\n"
        "- MEMORY: when the user EXPLICITLY asks you to remember something about them, or states a "
        "durable preference (e.g. \"I usually work in SI units\", \"my budgets are around $5k\", "
        "\"always remind me to attach drawings\"), acknowledge it and add ONE line at the very END of "
        "your reply: " + _MEMORY_PREFIX + " <concise note in third person>. To forget, use "
        + _MEMORY_PREFIX + " CLEAR. Only store the user's OWN preferences/context — never another "
        "party's data, secrets, or payment details. Anything under REMEMBERED above is what you already "
        "know about them; use it naturally.\n"
        "- COMPARING QUOTES: if the snapshot lists \"Quotes you have received\" on the user's RFQ(s), "
        "you MAY compare them and recommend which looks strongest — reason ONLY over the price, "
        "turnaround, scope, and assumptions shown, and explain the trade-offs plainly. CRITICAL: the "
        "quotes are anonymized as \"Quote 1/2/3\"; you do NOT know and must NEVER name, guess, or "
        "describe which provider/firm submitted any quote, nor anything about providers on the platform "
        "or what they are good at — that information belongs to other parties and revealing it is "
        "prohibited. Remind the user that provider identities are revealed only when they accept a quote.\n"
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
        + (_PROVIDER_PROFILE_COACH if "provider" in roles else "")
        + ("ACTIONS — AUTONOMOUS MODE IS ON for this user:\n"
           "- You may PROPOSE these actions on the user's OWN records, and they will be EXECUTED "
           "immediately (the user enabled autonomous mode and accepted the risk): "
           "mark_contacted / undo_mark_contacted (a quote_id), accept_quote (a quote_id), "
           "withdraw_quote (a quote_id), cancel_rfq (an RFQ id). Propose with a line at the very "
           "END of your reply:\n"
           "  " + _ACTION_PREFIX + " <type>|<id>|<short human summary>\n"
           "- Only act when the user clearly asks for it, and only on ids from their account "
           "section above. Tell them what you did in plain language.\n"
           "- DOCUMENT WORKFLOWS: if the user staged uploaded documents (listed under UPLOADED "
           "DOCUMENTS above) and asks you to create an RFQ from them, or (as a provider) to quote "
           "from them, propose 'create_rfq_from_docs|<any>|...', 'submit_quote_from_docs|<rfq_id>|...', or (provider) 'update_profile_from_docs|<any>|...'. Do NOT put file keys in the line — the server "
           "uses the staged uploads automatically. For create_rfq_from_docs you may also write a "
           "concise project_description — include ONLY the technical scope, requirements, and deliverables. NEVER include the customer's name, company, email, phone, address, dates, reference numbers, or any letterhead/cover-page contact block; the platform keeps customer identity private from providers. The RFQ is created as a DRAFT for the user to submit.\n"
           "- You STILL must NOT pay any fee or sign/countersign an NDA — those are never "
           "automated. Guide the user through them and link the page; the user clicks.\n\n"
           if autonomous else
           "ACTIONS YOU CAN DO FOR THE USER (confirm-then-execute):\n"
           "- You may PROPOSE exactly one safe, reversible action: marking an accepted RFQ as "
           "'customer contacted' (or undoing it). Only for the quote_ids listed under 'Accepted "
           "RFQs you can mark contacted' in this user's account section above. To propose it, add "
           "a line at the very END of your reply:\n"
           "  " + _ACTION_PREFIX + " mark_contacted|<quote_id>|Mark <who> as contacted\n"
           "  (or 'undo_mark_contacted|<quote_id>|...'). Briefly tell the user you'll mark it once "
           "they confirm — they will see a Confirm button. NEVER claim it's done yourself.\n"
           "- DOCUMENT WORKFLOWS: if the user staged uploaded documents and asks you to create an "
           "RFQ from them (customer) or quote from them (provider), you may PROPOSE "
           "'create_rfq_from_docs|<any>|...', 'submit_quote_from_docs|<rfq_id>|...', or (provider) 'update_profile_from_docs|<any>|...' (no file keys "
           "in the line — the server uses the staged uploads). The user confirms before it runs.\n"
           "- You CANNOT and must NOT pay, sign an NDA, accept a quote, cancel, delete, change "
           "settings, or send messages. For those, explain the steps and give a navigation link; "
           "the user does it themselves.\n\n")
        + (("ADMIN ACTIONS (you are talking to an ADMIN):\n"
            "- On a support ticket page (/admin/support/<id>) you CAN directly act on THIS ticket. "
            "The exact on-screen buttons are: **Resolve** (green), **Escalate**, **Archive**, "
            "**Mark Spam**. When the admin asks to close/resolve/escalate/archive/mark-spam the "
            "ticket, DO IT — end your reply with one line:\n"
            "  " + _ACTION_PREFIX + " resolve_ticket|<any>|Resolve this ticket\n"
            "  (types: resolve_ticket, escalate_ticket, archive_ticket, mark_ticket_spam). You do "
            "NOT need a ticket id in the line — the server uses the ticket from the current page. "
            "These run immediately for admins (no separate Autonomous toggle needed). Tell the "
            "admin plainly what you did. The button to close a ticket is literally 'Resolve'.\n\n")
           if is_admin else "")
        + "DELEGATION (very important):\n"
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
        + ((
            "=== REMEMBERED ABOUT THIS USER (notes they asked you to keep; this user only) ===\n"
            + (getattr(user, "assistant_memory", None) or "")
            + "\n=== END REMEMBERED ===\n\n"
        ) if getattr(user, "assistant_memory", None) else "")
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
    # Fallback so a turn is NEVER counted as $0 just because the provider omitted usage:
    # estimate tokens from text length (~4 chars/token). Real usage is preferred when present.
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    if pt is None:
        pt = max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)
    if ct is None:
        ct = max(1, len(reply) // 4)
    return {
        "reply": reply,
        "model": cfg["model"],
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": usage.get("total_tokens") or (pt + ct),
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


# Mechanical-engineering vocabulary. A query hitting any of these is treated as in-domain
# even if it doesn't match the platform manual (the manual is about the website, not
# engineering theory), so the scope-gate won't wrongly refuse a legitimate eng question.
_ENG_HINTS = (
    "engineer", "mechanic", "material", "steel", "aluminum", "aluminium", "alloy",
    "stress", "strain", "fatigue", "load", "torque", "bearing", "gear", "shaft",
    "weld", "machining", "cnc", "tolerance", "gd&t", "fea", "cfd", "thermo", "heat",
    "fluid", "pressure", "vessel", "pump", "valve", "actuator", "hvac", "combustion",
    "turbine", "casting", "injection mold", "3d print", "additive", "cad", "solidwork",
    "ansys", "beam", "moment", "deflection", "yield", "modulus", "viscosity", "flow rate",
    "bolt", "fastener", "spring", "vibration", "rpm", "horsepower", "kw", "newton",
    "pascal", "psi", "fea ", "simulation", "design for manufactur", "dfm", "tolerancing",
    "corrosion", "lubric", "gearbox", "piston", "cylinder", "manifold", "heat exchanger",
)


def _looks_engineering(msg: str) -> bool:
    m = (msg or "").lower()
    return any(h in m for h in _ENG_HINTS)


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


# Confirm-then-execute actions the model may PROPOSE (never execute). The model
# emits, on its own line:  PROPOSE_ACTION: <type>|<quote_id>|<human summary>
# The backend returns it as an inert proposal; the user must click Confirm, which
# is the only thing that triggers the hardened /help/action executor.
_ACTION_PREFIX = "PROPOSE_ACTION:"
_PROFILE_DATA_PREFIX = "PROFILE_DATA:"  # optional companion JSON line for update_profile_from_chat
_PROPOSABLE_ACTIONS = {"mark_contacted", "undo_mark_contacted",
                       "accept_quote", "cancel_rfq", "withdraw_quote",
                       "create_rfq_from_docs", "submit_quote_from_docs",
                       "update_profile_from_docs", "update_profile_from_chat",
                       "resolve_ticket", "escalate_ticket", "archive_ticket", "mark_ticket_spam"}
# Actions that need an rfq_id rather than a quote_id.
_RFQ_ID_ACTIONS = {"cancel_rfq"}


def _extract_action(reply: str):
    """Return (clean_reply, action_or_None). action = {type, quote_id, summary[, profile_updates]}."""
    if not reply or _ACTION_PREFIX not in reply:
        return reply, None
    kept, action, profile_data = [], None, None
    for ln in reply.splitlines():
        st = ln.strip()
        if action is None and st.upper().startswith(_ACTION_PREFIX):
            payload = ln.split(":", 1)[1] if ":" in ln else ""
            parts = [p.strip() for p in payload.split("|")]
            atype = parts[0] if parts else ""
            if atype in _PROPOSABLE_ACTIONS and len(parts) >= 2 and parts[1]:
                action = {
                    "type": atype,
                    "quote_id": parts[1][:64],
                    "summary": (parts[2] if len(parts) >= 3 else atype)[:140],
                }
            # whether valid or not, drop the control line from the visible reply
        elif st.upper().startswith(_PROFILE_DATA_PREFIX):
            try:
                import json as _json
                raw = ln.split(":", 1)[1] if ":" in ln else ""
                pd = _json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
                if isinstance(pd, dict):
                    profile_data = pd
            except Exception:
                pass
            # drop the control line from the visible reply
        else:
            kept.append(ln)
    if action and profile_data and action.get("type") == "update_profile_from_chat":
        action["profile_updates"] = profile_data
    return "\n".join(kept).strip(), action


def _extract_memory(reply: str):
    """Pull a trailing MEMORY: line out of the reply. Returns (clean_reply, note|None).
    note == "CLEAR" means wipe stored memory."""
    if not reply or _MEMORY_PREFIX not in reply:
        return reply, None
    kept, note = [], None
    for ln in reply.splitlines():
        if note is None and ln.strip().upper().startswith(_MEMORY_PREFIX):
            note = (ln.split(":", 1)[1].strip() if ":" in ln else "")
        else:
            kept.append(ln)
    return "\n".join(kept).strip(), (note or None)


async def _persist_memory(db: AsyncSession, user: Optional[User], note: Optional[str]) -> None:
    """Append a short self-note to the user's assistant_memory (or CLEAR it).
    Scoped to this user only; capped to the most recent ~1500 chars."""
    if user is None or note is None:
        return
    try:
        from sqlalchemy import update as _update
        from app.models.user import User as _User
        if note.strip().upper() == "CLEAR":
            newval = None
        else:
            existing = (getattr(user, "assistant_memory", None) or "").strip()
            line = note.strip()[:300]
            if existing and line.lower() in existing.lower():
                return  # already remembered; avoid duplicates
            combined = (existing + "\n" + line).strip() if existing else line
            newval = combined[-1500:]
        await db.execute(_update(_User).where(_User.id == user.id).values(assistant_memory=newval))
        await db.commit()
        try:
            user.assistant_memory = newval
        except Exception:
            pass
    except Exception as exc:
        logger.warning("[help_service] memory persist failed: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass


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

# Default token prices in USD per 1K tokens. Set to Google Gemini 2.5 Flash
# ($0.30 / 1M input, $2.50 / 1M output as of 2026). Admins can override per model via
# runtime-config CHAT_LLM_PRICING (JSON: {"model": {"in": x_per_1k, "out": y_per_1k}}).
_DEFAULT_PRICE_PER_1K = {"in": 0.0003, "out": 0.0025}

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


import re as _re


def _ticket_id_from_page(page: Optional[str]) -> Optional[str]:
    """Extract a support-ticket UUID from an /admin/support/<id> page path."""
    if not page:
        return None
    m = _re.search(r"/admin/support/([0-9a-fA-F-]{8,})", page)
    return m.group(1) if m else None


async def _maybe_autoexecute(db, user, action, attachments=None, page=None):
    """Auto-execute a proposed action when allowed, else return None (inert confirm).

    Fires when EITHER the user has autonomous mode ON, OR the action is an admin action
    and the user is an admin (admins are privileged operators — they don't need the
    consumer consent flag to operate their own support queue). The flag/role are read
    fresh each turn so the hard-stop takes effect immediately. Failures degrade to a
    normal confirm proposal rather than breaking the chat.
    """
    if not action or user is None:
        return None
    from app.services.help_actions import execute_action, ALL_ACTIONS, ADMIN_ACTIONS
    atype = action.get("type")
    if atype not in ALL_ACTIONS:
        return None
    autonomous = bool(getattr(user, "agent_autonomous_enabled", False))
    is_admin = "admin" in (user.roles or [])
    # Admin ticket actions auto-run for admins; everything else needs autonomous mode.
    if not (autonomous or (atype in ADMIN_ACTIONS and is_admin)):
        return None
    try:
        _id = action.get("quote_id")
        params = {"quote_id": _id, "rfq_id": _id, "attachments": attachments or [],
                  "ticket_id": _ticket_id_from_page(page),
                  "profile_updates": action.get("profile_updates")}
        res = await execute_action(db, user, atype, params, autonomous)
        return {"executed": True, "type": atype, "message": res.get("message"), "link": res.get("link")}
    except Exception as exc:
        logger.info("[help_service] auto execute failed (%s); leaving as proposal", exc)
        return None


async def answer_question(
    db: AsyncSession,
    user: Optional[User],
    history: List[Dict[str, Any]],
    user_message: str,
    page: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
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

    # Attachments staged via /help/upload: expose excerpts + keys so the model can use
    # them in a doc-driven workflow action. The file KEYS are authoritative here (server
    # validates them); the model only references them.
    atts = attachments or []
    if atts:
        lines = ["UPLOADED DOCUMENTS the user staged for you (use ONLY these for doc actions):"]
        for a in atts[:5]:
            ex = (a.get("excerpt") or "").strip().replace("\n", " ")[:600]
            lines.append(f"- key={a.get('key')} filename={a.get('filename')} :: {ex}")
        account_ctx = (account_ctx + "\n\n" + "\n".join(lines)).strip() if account_ctx else "\n".join(lines)

    # RAG: ground on the most relevant manual chunks (falls back to full manual).
    grounding, max_sim = await _get_grounding(db, user_message)

    # Scope-gate: clearly off-topic question -> refuse cheaply, no LLM call.
    # Account-related questions or any staged upload bypass the gate.
    if (max_sim is not None and max_sim < _SCOPE_MIN_SIM
            and not _looks_account_related(user_message)
            and not _looks_engineering(user_message)
            and not atts):
        logger.info("[help_service] scope-gate refused (sim=%.3f) msg=%r", max_sim, user_message[:80])
        return {
            "reply": (
                "I can help with the ProMechDirectory platform (RFQs, quotes, NDAs, "
                "subscriptions, search, your account) and with general mechanical-engineering "
                "questions. That one looks outside both — could you rephrase it around the "
                "platform or an engineering topic?"
            ),
            "error": "out_of_scope",
            "cost_usd": 0.0,
        }

    _autonomous = bool(getattr(user, "agent_autonomous_enabled", False)) if user else False
    _is_admin = bool(user and "admin" in (user.roles or []))
    system_prompt = _build_system_prompt(grounding, user, roles, account_context=account_ctx, autonomous=_autonomous, is_admin=_is_admin, page=page)

    safe_history = _sanitize_history(history)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(safe_history)
    if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
        messages.append({"role": "user", "content": user_message})

    res = await _call_llm(chat_cfg, messages, max_tokens=4000, temperature=0.3)
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
        res3 = await _call_llm(doc_cfg, spec_messages, max_tokens=4000, temperature=0.2)
        cost3 = _estimate_cost(res3.get("model"), res3.get("prompt_tokens"), res3.get("completion_tokens"), rt_cfg)
        if res3.get("error"):
            return {"reply": "", "error": res3["error"], "model": res3.get("model"),
                    "delegated": True, "latency_ms": res3.get("latency_ms"), "cost_usd": round(cost4 + cost3, 6)}
        clean3, action3 = _extract_action((res3.get("reply") or "").strip())
        clean3, links3 = _extract_links(clean3)
        auto3 = await _maybe_autoexecute(db, user, action3, attachments, page=page)
        return {
            "reply": clean3,
            "links": links3,
            "action": None if auto3 else action3,
            "action_result": auto3,
            "model": res3.get("model"),
            "delegated": True,
            "prompt_tokens": res3.get("prompt_tokens"),
            "completion_tokens": res3.get("completion_tokens"),
            "total_tokens": res3.get("total_tokens"),
            "latency_ms": res3.get("latency_ms"),
            "cost_usd": round(cost4 + cost3, 6),
        }

    # --- Normal LLM4 answer ---
    clean, action = _extract_action(reply)
    clean, links = _extract_links(clean)
    clean, _mem_note = _extract_memory(clean)
    await _persist_memory(db, user, _mem_note)
    auto = await _maybe_autoexecute(db, user, action, attachments, page=page)
    return {
        "reply": clean,
        "links": links,
        "action": None if auto else action,
        "action_result": auto,
        "model": res.get("model"),
        "delegated": False,
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
        "total_tokens": res.get("total_tokens"),
        "latency_ms": res.get("latency_ms"),
        "cost_usd": cost4,
    }


# ---------------------------------------------------------------------------
# Streaming (additive). The non-streaming answer_question above is the proven
# path and is intentionally left untouched. This streaming path mirrors its
# happy-case prep, and for ANY non-happy condition (no message, attachments,
# budget cap, missing key, out-of-scope, or a DELEGATE handoff) it yields a
# ("fallback", None) sentinel so the caller transparently falls back to the
# non-streaming /help/chat endpoint — guaranteeing identical behaviour there.
# ---------------------------------------------------------------------------

# Control lines the model emits at the END of a reply that must never be shown.
_CONTROL_PREFIXES = (
    _ACTION_PREFIX.upper(), _LINK_PREFIX.upper(), _MEMORY_PREFIX.upper(),
    _PROFILE_DATA_PREFIX.upper(), _DELEGATE_PREFIX.upper(),
)


def _is_control_line(line: str) -> bool:
    st = line.strip().upper()
    return any(st.startswith(p) for p in _CONTROL_PREFIXES)


async def _call_llm_stream(cfg, messages, *, max_tokens: int = 4000, temperature: float = 0.3):
    """Async generator over an OpenAI-compatible streaming chat-completion.
    Yields ("delta", text), ("usage", dict), or ("error", message)."""
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    import json as _json
    url = f"{str(cfg['base']).rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", "replace")[:300]
                    yield ("error", f"llm_http_{resp.status_code}: {body}")
                    return
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data)
                    except Exception:
                        continue
                    ch = obj.get("choices") or []
                    if ch:
                        txt = (ch[0].get("delta") or {}).get("content")
                        if txt:
                            yield ("delta", txt)
                    if obj.get("usage"):
                        yield ("usage", obj["usage"])
    except Exception as exc:
        yield ("error", f"llm_stream_failed: {exc}")


async def answer_question_stream(
    db: AsyncSession,
    user: Optional[User],
    history: List[Dict[str, Any]],
    user_message: str,
    page: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
):
    """Async generator yielding ("token", text), then a single ("meta", dict),
    OR ("fallback", None) to defer to the non-streaming path."""
    user_message = (user_message or "").strip()[:_MAX_USER_MESSAGE_CHARS]
    atts = attachments or []
    if not user_message or atts:
        yield ("fallback", None); return

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
        if await _user_month_cost(db, user.id) >= budget:
            yield ("fallback", None); return

    chat_cfg = await _get_chat_llm_config(db)
    if not chat_cfg["api_key"]:
        yield ("fallback", None); return

    roles = list(user.roles or []) if user else []
    account_ctx = ""
    if user is not None:
        try:
            from app.services.help_context import build_account_context, render_account_context
            _snap = await build_account_context(db, user)
            account_ctx = render_account_context(_snap, page=page)
        except Exception as exc:
            logger.info("[help_service] (stream) account context failed: %s", exc)

    grounding, max_sim = await _get_grounding(db, user_message)
    if (max_sim is not None and max_sim < _SCOPE_MIN_SIM
            and not _looks_account_related(user_message)
            and not _looks_engineering(user_message)):
        yield ("fallback", None); return

    _autonomous = bool(getattr(user, "agent_autonomous_enabled", False)) if user else False
    system_prompt = _build_system_prompt(grounding, user, roles, account_context=account_ctx,
                                         autonomous=_autonomous, is_admin=is_admin, page=page)
    safe_history = _sanitize_history(history)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(safe_history)
    if not safe_history or safe_history[-1]["role"] != "user" or safe_history[-1]["content"] != user_message:
        messages.append({"role": "user", "content": user_message})

    t0 = time.time()
    full = ""
    flushed = 0
    decided = False  # whether we've ruled out a DELEGATE handoff
    usage: Dict[str, Any] = {}
    stream_error: Optional[str] = None

    async for kind, val in _call_llm_stream(chat_cfg, messages, max_tokens=4000, temperature=0.3):
        if kind == "usage":
            usage = val or {}
            continue
        if kind == "error":
            stream_error = val
            break
        # kind == "delta"
        full += val
        if not decided:
            stripped = full.lstrip()
            if len(stripped) >= len(_DELEGATE_PREFIX):
                if stripped.upper().startswith(_DELEGATE_PREFIX):
                    yield ("fallback", None); return  # hand off to JSON path
                decided = True
            else:
                continue  # too short to tell yet; keep buffering
        # Flush completed, non-control lines (hold the in-progress last line).
        lines = full.split("\n")
        complete = lines[:-1]
        visible_parts = []
        for ln in complete:
            if _is_control_line(ln):
                break
            visible_parts.append(ln)
        visible = "\n".join(visible_parts)
        if len(visible) > flushed:
            yield ("token", visible[flushed:])
            flushed = len(visible)

    # If the stream errored before we emitted anything, fall back cleanly.
    if stream_error and flushed == 0 and not full.strip():
        yield ("fallback", None); return

    # Flush any remaining safe text (the final in-progress line if not control).
    if not stream_error:
        final_lines = []
        for ln in full.split("\n"):
            if _is_control_line(ln):
                break
            final_lines.append(ln)
        final_visible = "\n".join(final_lines)
        if len(final_visible) > flushed:
            yield ("token", final_visible[flushed:])
            flushed = len(final_visible)

    reply = full.strip()
    latency_ms = int((time.time() - t0) * 1000)
    pt = usage.get("prompt_tokens") or max(1, sum(len(str(m.get("content", ""))) for m in messages) // 4)
    ct = usage.get("completion_tokens") or max(1, len(reply) // 4)
    cost4 = _estimate_cost(chat_cfg.get("model"), pt, ct, rt_cfg)

    # Post-process the FULL text exactly like the non-streaming path.
    clean, action = _extract_action(reply)
    clean, links = _extract_links(clean)
    clean, _mem_note = _extract_memory(clean)
    await _persist_memory(db, user, _mem_note)
    auto = await _maybe_autoexecute(db, user, action, atts, page=page)

    yield ("meta", {
        "reply": clean,
        "links": links,
        "action": None if auto else action,
        "action_result": auto,
        "model": chat_cfg.get("model"),
        "delegated": False,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": usage.get("total_tokens") or (pt + ct),
        "latency_ms": latency_ms,
        "cost_usd": cost4,
        "error": stream_error,
    })
