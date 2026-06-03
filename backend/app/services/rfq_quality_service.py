"""RFQ completeness gate.

Before an RFQ is dispatched to providers (who PAY to unlock it), an LLM (LLM3, the
document-analysis specialist) evaluates whether the RFQ contains enough for a competent
engineering firm to scope and quote it. Calibrated to the project's tollgate/maturity and
to any attached specs.

Design principles:
- FAIL-OPEN: if the gate is disabled, the LLM is unavailable, or evaluation errors, the RFQ is
  allowed through. The gate improves lead quality; it must NEVER break submission.
- Block only genuinely-incomplete RFQs; WARN (allow) borderline ones — RFQ volume is scarce.
- After RFQ_QUALITY_MAX_ATTEMPTS incomplete attempts, the RFQ is terminally blocked.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

READY = "ready"
BORDERLINE = "borderline"
INCOMPLETE = "incomplete"

_MAX_DESC_CHARS = 6000
_MAX_FILE_CHARS = 1500
_MAX_FILES = 3
_MAX_ATTACH_TOTAL = 5000

_SYSTEM = (
    "You are an engineering RFQ (Request for Quotation) completeness reviewer for a marketplace that "
    "connects companies with engineering service FIRMS. A provider will PAY to unlock this RFQ and quote "
    "it, so it must contain enough for a competent engineering firm to scope and price the work.\n\n"
    "Evaluate the RFQ below and decide how complete it is. CALIBRATE to the project's tollgate/maturity: "
    "early-stage (idea / feasibility) RFQs legitimately need less detail; detailed-design or analysis RFQs "
    "need real specifications. If files/specs are attached, treat their content as part of the RFQ and be "
    "lenient about brevity in the description.\n\n"
    "A reasonably complete RFQ usually conveys: (1) a clear objective/problem and the outcome wanted; "
    "(2) the part/system/scope and what work is requested; (3) the deliverable(s) expected (analysis, CAD, "
    "drawings, report, calculations); (4) key conditions/constraints WHERE APPLICABLE (loads, pressures, "
    "temperatures, environment, materials, applicable codes/standards); (5) acceptance criteria or definition "
    "of success where applicable; (6) units if quantitative. Not every item is required for every project — "
    "judge whether a competent firm could ACTUALLY scope and quote it.\n\n"
    "Be LENIENT. Only give a low score if the RFQ is genuinely too vague to quote (e.g. one line, no real "
    "scope, 'design something', spam, or empty). Do NOT nitpick well-formed RFQs.\n\n"
    "Return ONLY a JSON object and nothing else:\n"
    '{"score": <integer 0-100, how ready a competent firm is to scope/quote this>, '
    '"missing": [{"item": "<short label>", "why": "<one sentence>"}], '
    '"suggestions": ["<one concrete thing to add>"], '
    '"summary": "<one sentence overall>"}\n'
    "Keep missing to the 5 most important gaps and suggestions to at most 4, each concrete and actionable."
)


async def _gate_cfg(db: AsyncSession) -> Dict[str, Any]:
    from app.core.config import settings
    rt: Dict[str, Any] = {}
    try:
        from app.services.config_service import get_runtime_config
        rt = await get_runtime_config(db) or {}
    except Exception:
        rt = {}

    def _int(key: str, default: int) -> int:
        v = rt.get(key)
        try:
            return int(v) if v not in (None, "") else int(default)
        except (TypeError, ValueError):
            return int(default)

    enabled_raw = rt.get("RFQ_QUALITY_GATE_ENABLED")
    if enabled_raw is None:
        enabled = bool(getattr(settings, "RFQ_QUALITY_GATE_ENABLED", True))
    else:
        enabled = str(enabled_raw).strip().lower() not in ("false", "0", "no", "off", "")
    return {
        "enabled": enabled,
        "block": _int("RFQ_QUALITY_BLOCK_THRESHOLD", getattr(settings, "RFQ_QUALITY_BLOCK_THRESHOLD", 45)),
        "warn": _int("RFQ_QUALITY_WARN_THRESHOLD", getattr(settings, "RFQ_QUALITY_WARN_THRESHOLD", 70)),
        "max_free": _int("RFQ_QUALITY_MAX_ATTEMPTS_FREE", getattr(settings, "RFQ_QUALITY_MAX_ATTEMPTS_FREE", 2)),
        "max_paid": _int("RFQ_QUALITY_MAX_ATTEMPTS_PAID", getattr(settings, "RFQ_QUALITY_MAX_ATTEMPTS_PAID", 5)),
    }


def _build_content(rfq, files) -> str:
    parts: List[str] = []
    title = getattr(rfq, "title", None) or getattr(rfq, "business_name", None) or ""
    if title:
        parts.append(f"TITLE: {str(title)[:200]}")
    tg = getattr(rfq, "tollgate_phases", None)
    if tg:
        parts.append(f"TOLLGATE / maturity: {tg}")
    urg = getattr(rfq, "urgency", None)
    if urg:
        parts.append(f"DEADLINE / urgency: {urg}")
    parts.append(f"NDA required: {'yes' if getattr(rfq, 'nda_required', False) else 'no'}")
    desc = (getattr(rfq, "project_description", None) or "").strip()
    parts.append("DESCRIPTION:\n" + (desc[:_MAX_DESC_CHARS] if desc else "(none provided)"))

    attach_lines: List[str] = []
    total = 0
    shown = 0
    for f in (files or []):
        if shown >= _MAX_FILES or total >= _MAX_ATTACH_TOTAL:
            break
        name = getattr(f, "original_filename", None) or "file"
        txt = (getattr(f, "extracted_text", None) or "").strip()
        if txt:
            excerpt = txt[:_MAX_FILE_CHARS]
            total += len(excerpt)
            attach_lines.append(f"- {name}:\n{excerpt}")
        else:
            attach_lines.append(f"- {name}: [non-text / drawing / CAD file — contents not readable here]")
        shown += 1
    n_files = len(files or [])
    if n_files:
        parts.append(f"ATTACHMENTS ({n_files} total; showing up to {_MAX_FILES}):\n" + "\n".join(attach_lines))
    return "\n\n".join(parts)


def _parse_verdict(reply: str) -> Optional[Dict[str, Any]]:
    if not reply:
        return None
    try:
        start = reply.find("{")
        end = reply.rfind("}")
        if start < 0 or end <= start:
            return None
        obj = json.loads(reply[start:end + 1])
        if not isinstance(obj, dict):
            return None
        score = obj.get("score")
        score = int(score) if isinstance(score, (int, float)) else 50
        score = max(0, min(100, score))
        missing = obj.get("missing") or []
        clean_missing = []
        for m in missing[:5]:
            if isinstance(m, dict):
                clean_missing.append({"item": str(m.get("item", ""))[:120], "why": str(m.get("why", ""))[:240]})
            elif isinstance(m, str):
                clean_missing.append({"item": m[:120], "why": ""})
        suggestions = [str(x)[:240] for x in (obj.get("suggestions") or [])[:4] if str(x).strip()]
        summary = str(obj.get("summary", ""))[:300]
        return {"score": score, "missing": clean_missing, "suggestions": suggestions, "summary": summary}
    except Exception:
        return None


async def evaluate_rfq(db: AsyncSession, rfq) -> Dict[str, Any]:
    """Evaluate one RFQ. Returns {verdict, score, missing, suggestions, summary, enabled, error?}.
    FAIL-OPEN: returns verdict=ready on any disabled/unavailable/error condition."""
    cfg = await _gate_cfg(db)
    if not cfg["enabled"]:
        return {"verdict": READY, "score": 100, "missing": [], "suggestions": [], "summary": "", "enabled": False}

    from app.models.rfq import RFQFile
    try:
        files = (await db.execute(select(RFQFile).where(RFQFile.rfq_id == rfq.id))).scalars().all()
    except Exception:
        files = []

    content = _build_content(rfq, files)

    try:
        from app.services.help_service import _get_llm3_config, _call_llm
        doc_cfg = await _get_llm3_config(db)
        if not doc_cfg.get("api_key"):
            logger.info("[rfq_quality] LLM3 not configured — fail-open (allow)")
            return {"verdict": READY, "score": 100, "missing": [], "suggestions": [], "summary": "",
                    "enabled": True, "error": "llm3_not_configured"}
        messages = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": content}]
        res = await _call_llm(doc_cfg, messages, max_tokens=700, temperature=0.1)
        if res.get("error"):
            logger.warning("[rfq_quality] LLM error — fail-open: %s", res.get("error"))
            return {"verdict": READY, "score": 100, "missing": [], "suggestions": [], "summary": "",
                    "enabled": True, "error": res.get("error")}
        parsed = _parse_verdict(res.get("reply") or "")
        if parsed is None:
            logger.warning("[rfq_quality] unparseable verdict — fail-open")
            return {"verdict": READY, "score": 100, "missing": [], "suggestions": [], "summary": "",
                    "enabled": True, "error": "parse_failed"}
        score = parsed["score"]
        if score < cfg["block"]:
            verdict = INCOMPLETE
        elif score < cfg["warn"]:
            verdict = BORDERLINE
        else:
            verdict = READY
        return {"verdict": verdict, "score": score, "missing": parsed["missing"],
                "suggestions": parsed["suggestions"], "summary": parsed["summary"], "enabled": True}
    except Exception as exc:
        logger.warning("[rfq_quality] evaluation failed — fail-open: %s", exc)
        return {"verdict": READY, "score": 100, "missing": [], "suggestions": [], "summary": "",
                "enabled": True, "error": str(exc)}


def _terminal_message(is_subscriber: bool) -> str:
    """Message shown when an RFQ is terminally blocked (free users, 2-strike rule)."""
    return ("This RFQ doesn't meet the completeness standard engineering firms expect, after multiple "
            "attempts, so it can't be sent to providers. Please create a new RFQ with the missing details. "
            "Tip: a Search subscription unlocks an AI assistant that can complete an RFQ for you "
            "from a spec sheet or a few details.")


def _support_message() -> str:
    """Message shown when a subscriber's RFQ is escalated to our team for help."""
    return ("We've tried a few times to get this RFQ ready and it still needs work, so we've handed it to "
            "our team. Someone will reach out to help you finish it. You can also email us at "
            "info@promechdirectory.com.")


async def _notify_support_incomplete_rfq(db: AsyncSession, rfq, ev: Dict[str, Any]) -> None:
    """Best-effort: alert our team that a subscriber's RFQ needs hands-on help. Never raises."""
    try:
        from app.core.config import settings
        from app.services.email_service import _send_email_now
        to = settings.ADMIN_EMAIL or settings.FROM_EMAIL
        if not to:
            return
        missing = "; ".join(str(m) for m in (ev.get("missing") or [])[:8]) or "(none reported)"
        rid = getattr(rfq, "id", "?")
        biz = getattr(rfq, "business_name", "") or ""
        score = ev.get("score")
        text = (
            f"A subscriber's RFQ has hit the AI-completion limit and needs manual help.\n\n"
            f"RFQ ID: {rid}\n"
            f"Customer/business: {biz}\n"
            f"Completeness score: {score}\n"
            f"Still-missing items: {missing}\n\n"
            f"Please reach out to the customer to help finish this RFQ."
        )
        await _send_email_now(
            to=[to],
            subject=f"[Action] Subscriber RFQ needs manual help — {rid}",
            html_content=None,
            text_content=text,
            db=db,
            is_admin_alert=True,
        )
    except Exception:
        logger.warning("Failed to send support escalation for incomplete RFQ", exc_info=True)


async def gate_rfq_for_dispatch(db: AsyncSession, rfq, is_subscriber: bool) -> Dict[str, Any]:
    """Gate an RFQ before it is charged/dispatched.

    Returns a dict with key 'ok':
      - ok=True  -> proceed (ready, or borderline with an optional non-blocking 'warning')
      - ok=False -> block (incomplete with gaps, or terminal after too many attempts)
    """
    cfg = await _gate_cfg(db)
    if not cfg["enabled"]:
        return {"ok": True}

    # Per-tier attempt budget: free users get a hard 2-strike block; subscribers get
    # more chances and a hand-off to our team (no "not industry standard" dead-end).
    max_attempts = cfg["max_paid"] if is_subscriber else cfg["max_free"]

    if getattr(rfq, "quality_blocked", False):
        if is_subscriber:
            return {"ok": False, "terminal": True, "reason": "rfq_support_escalated",
                    "message": _support_message()}
        return {"ok": False, "terminal": True, "reason": "rfq_terminally_blocked",
                "message": _terminal_message(is_subscriber)}

    ev = await evaluate_rfq(db, rfq)
    verdict = ev["verdict"]

    if verdict == READY:
        return {"ok": True}

    if verdict == BORDERLINE:
        return {"ok": True, "warning": {"missing": ev["missing"], "suggestions": ev["suggestions"],
                                        "summary": ev["summary"], "score": ev["score"]}}

    # INCOMPLETE — count an attempt; at the per-tier limit, free users are terminally
    # blocked while subscribers are escalated to support.
    rfq.quality_attempts = int(getattr(rfq, "quality_attempts", 0) or 0) + 1
    at_limit = rfq.quality_attempts >= max_attempts
    if at_limit:
        rfq.quality_blocked = True
    try:
        await db.commit()
    except Exception:
        await db.rollback()

    if at_limit and is_subscriber:
        await _notify_support_incomplete_rfq(db, rfq, ev)
        return {"ok": False, "terminal": True, "reason": "rfq_support_escalated",
                "message": _support_message(), "missing": ev["missing"]}
    if at_limit:
        return {"ok": False, "terminal": True, "reason": "rfq_terminally_blocked",
                "message": _terminal_message(is_subscriber), "missing": ev["missing"]}
    return {"ok": False, "terminal": False, "reason": "rfq_incomplete",
            "missing": ev["missing"], "suggestions": ev["suggestions"], "summary": ev["summary"],
            "score": ev["score"], "attempts_used": rfq.quality_attempts,
            "attempts_max": max_attempts, "ai_help": bool(is_subscriber)}


async def is_search_subscriber(db: AsyncSession, user) -> bool:
    """True if the user has an active customer Search subscription (which also grants the AI assistant)."""
    if user is None:
        return False
    try:
        from app.models.payment import Subscription
        res = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.subscription_status == "active",
                Subscription.subscription_type.in_(["search_tier_1", "search_tier_2"]),
            ).limit(1)
        )
        return res.scalar_one_or_none() is not None
    except Exception:
        return False
