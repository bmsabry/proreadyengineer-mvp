"""Centralized, authorization-enforcing executor for AI-assistant actions.

ONE place where the assistant's actions are authorized and run, shared by the
confirm-then-execute path and the autonomous path. Hard rules baked in here:

- Two tiers of executable action:
    SAFE_ACTIONS       — reversible, low-stakes (mark/undo contacted). Allowed via the
                         confirm-then-execute flow for any subscriber.
    AUTONOMOUS_ACTIONS — consequential but non-financial, on the user's OWN records
                         (accept quote, cancel RFQ, withdraw quote). Allowed only when
                         the user has explicitly enabled autonomous mode.
- PAYMENTS and NDA E-SIGNING are NEVER executable here, regardless of any flag or
  consent. They are deliberately absent from every allowlist. The assistant guides
  the user through them; the human performs the final click.
- Every action re-checks resource ownership server-side (it never trusts the caller's
  framing or a model-supplied id) and writes an AuditLog.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

SAFE_ACTIONS = {"mark_contacted", "undo_mark_contacted", "update_profile_from_docs", "update_profile_from_chat"}
AUTONOMOUS_ACTIONS = {"accept_quote", "cancel_rfq", "withdraw_quote",
                      "create_rfq_from_docs", "submit_quote_from_docs"}
# Admin-only support-ticket actions. Gated on the admin role (admins are already
# privileged operators); they do NOT require the consumer autonomous-consent flag.
ADMIN_ACTIONS = {"resolve_ticket", "escalate_ticket", "archive_ticket", "mark_ticket_spam"}
ALL_ACTIONS = SAFE_ACTIONS | AUTONOMOUS_ACTIONS | ADMIN_ACTIONS

# Explicitly forbidden forever — payments and legal e-signature are never agent-executed.
FORBIDDEN_ACTIONS = {
    "pay", "pay_unlock", "pay_nda_fee", "subscribe", "purchase",
    "sign_nda", "countersign_nda", "esign",
}


async def _audit(db: AsyncSession, user: User, entity_type: str, entity_id: str,
                 action: str, autonomous: bool) -> None:
    try:
        from app.models.admin import AuditLog
        db.add(AuditLog(
            actor_user_id=user.id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=f"assistant_{action}",
            extra_data={"via": "help_assistant", "autonomous": autonomous},
        ))
        await db.commit()
    except Exception as exc:
        logger.warning("[help_actions] audit failed: %s", exc)
        await db.rollback()


def _validate_attachments(user, attachments):
    """Keep only attachments whose S3 key is under THIS user's assistant-uploads prefix.

    This is the core defense: file keys come from the staged-upload response, never from
    the LLM. Even if the model echoes a key, anything not under assistant-uploads/<user_id>/
    is dropped — so a user can never attach another user's file, and a malicious document
    cannot smuggle in a foreign key.
    """
    if not attachments or not isinstance(attachments, list):
        return []
    prefix = f"assistant-uploads/{user.id}/"
    out = []
    for a in attachments:
        if not isinstance(a, dict):
            continue
        key = str(a.get("key") or "")
        if key.startswith(prefix) and "://" not in key and ".." not in key:
            out.append({
                "key": key,
                "filename": str(a.get("filename") or "document")[:200],
                "mime": str(a.get("mime") or "application/octet-stream")[:100],
                "size_bytes": a.get("size_bytes") or 0,
                "excerpt": str(a.get("excerpt") or "")[:4000],
            })
    return out[:5]


# --- PII scrubbing for document-derived, counterparty-visible text -----------
# RFQ descriptions and quote notes built from an uploaded document are shown to
# the OTHER party (RFQ desc -> providers; quote notes -> customer). The platform
# never exposes either party's identity/contact, so any contact block carried in
# from a letterhead/cover page must be stripped at the source before it is saved.
import re as _re_pii

_EMAIL_RE_PII = _re_pii.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE_PII = _re_pii.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
_URL_RE_PII = _re_pii.compile(r"https?://\S+|www\.\S+", _re_pii.IGNORECASE)
# Whole lines that are an identity/contact field -> dropped (value captured for inline scrub).
_CONTACT_LINE_RE = _re_pii.compile(
    r"^\s*(?P<label>customer name|customer|client name|client|company name|company|"
    r"contact name|contact|prepared by|prepared for|submitted by|requested by|"
    r"requested for|attention|attn|address|mailing address|e-?mail|email|"
    r"phone|telephone|tel|fax|mobile|cell|website|web|date|name)\s*[:\-]\s*(?P<value>.*)$",
    _re_pii.IGNORECASE,
)
# Section headers like "CUSTOMER INFORMATION" / "CONTACT DETAILS" -> dropped.
_CONTACT_HEADER_RE = _re_pii.compile(
    r"^\s*(customer|client|contact|vendor|buyer|requester)\s+(information|details|info)\s*:?\s*$",
    _re_pii.IGNORECASE,
)
# Page markers and the document's own reference number -> noise to drop.
_PAGE_MARK_RE = _re_pii.compile(r"Page\s*\d+\s*/\s*\d+", _re_pii.IGNORECASE)
_REF_NUM_RE = _re_pii.compile(r"\bRFQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", _re_pii.IGNORECASE)
# Labels whose VALUE is a name/company we must also scrub from inline prose.
_NAME_LABELS = {"customer name", "customer", "client name", "client", "company name",
                "company", "contact name", "contact", "prepared by", "submitted by",
                "requested by", "requested for", "attention", "attn", "name"}


def _scrub_pii(text: str, user=None) -> str:
    """Remove identity/contact info from counterparty-visible, doc-derived text.

    Drops contact lines and section headers, redacts emails/phones/URLs/page-markers,
    and — crucially — captures the customer/company NAME from the document's own
    contact block and redacts it from the inline prose too (the doc often repeats the
    company name in the overview), plus the acting user's own profile identifiers.
    Defensive backstop to the prompt/summarizer — must not rely on the model.
    """
    if not text:
        return text
    kept = []
    name_tokens = set()
    for ln in text.splitlines():
        if _CONTACT_HEADER_RE.match(ln):
            continue
        m = _CONTACT_LINE_RE.match(ln)
        if m:
            label = (m.group("label") or "").strip().lower()
            value = (m.group("value") or "").strip()
            if label in _NAME_LABELS and value:
                v = _EMAIL_RE_PII.sub("", value)
                v = _PHONE_RE_PII.sub("", v).strip(" ,;:-")
                if len(v) >= 3:
                    name_tokens.add(v)
                for tok in _re_pii.split(r"[\s,/]+", v):
                    tok = tok.strip(".,;:()-")
                    if len(tok) >= 3 and (any(c.isdigit() for c in tok) or tok[:1].isupper()):
                        name_tokens.add(tok)
            continue
        kept.append(ln)
    text = "\n".join(kept)
    text = _EMAIL_RE_PII.sub("[redacted]", text)
    text = _URL_RE_PII.sub("[redacted]", text)
    text = _PHONE_RE_PII.sub("[redacted]", text)
    text = _PAGE_MARK_RE.sub("", text)
    text = _REF_NUM_RE.sub("", text)
    if user is not None:
        for attr in ("full_name", "business_name", "first_name", "last_name", "email"):
            val = getattr(user, attr, None)
            if isinstance(val, str) and len(val.strip()) >= 3:
                name_tokens.add(val.strip())
    for tok in sorted(name_tokens, key=len, reverse=True):
        if len(tok) >= 3:
            text = _re_pii.sub(r"\b" + _re_pii.escape(tok) + r"\b", "[redacted]", text,
                               flags=_re_pii.IGNORECASE)
    text = _re_pii.sub(r"[ \t]{2,}", " ", text)
    text = _re_pii.sub(r"\n{3,}", "\n\n", text).strip()
    return text


async def _summarize_rfq_from_docs(db, doc_text):
    """Rewrite an uploaded RFQ document into a clean, provider-facing project
    description: technical scope only, no identity/contact, lightly structured.
    Best-effort; returns None on any failure so the caller can fall back."""
    if not (doc_text or "").strip():
        return None
    try:
        from openai import AsyncOpenAI
        from app.services.config_service import get_runtime_config
        cfg = await get_runtime_config(db)
        api_key = cfg.get("DOC_LLM_API_KEY") or cfg.get("CHAT_LLM_API_KEY") or cfg.get("OPENAI_API_KEY")
        api_base = cfg.get("DOC_LLM_API_BASE") or cfg.get("CHAT_LLM_API_BASE") or cfg.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
        model = cfg.get("DOC_LLM_MODEL") or cfg.get("CHAT_LLM_MODEL") or cfg.get("OPENAI_LLM_MODEL") or "gpt-4o-mini"
        if not api_key:
            return None
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        sys = (
            "You turn an uploaded engineering RFQ document into a clean project description "
            "for service providers to read. Output ONLY the description text (no preamble).\n"
            "RULES:\n"
            "- Include the technical scope, requirements, standards, and deliverables.\n"
            "- EXCLUDE all identity/contact info: customer or company names, people, emails, "
            "phones, addresses, dates, reference numbers, letterhead, and page markers. Refer "
            "to the buyer generically as 'the customer'.\n"
            "- Structure it readably: a short overview paragraph, then clear sections with "
            "concise bullet lines (use '- ' for bullets). Keep it faithful; do not invent."
        )
        resp = await client.chat.completions.create(
            model=model, temperature=0.2,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": doc_text[:8000]}],
        )
        out = (resp.choices[0].message.content or "").strip()
        return out[:9000] if len(out) >= 40 else None
    except Exception as exc:
        logger.info("[help_actions] rfq summary failed: %s", exc)
        return None

async def _extract_quote_fields(db, doc_text: str) -> Dict[str, Any]:
    """Best-effort LLM extraction of quote fields from a quote document. Returns a dict with
    price_min/price_max (Decimal|None), turnaround/scope/assumptions (str|None). Never raises.
    """
    result: Dict[str, Any] = {}
    if not (doc_text or "").strip():
        return result
    try:
        import json
        from decimal import Decimal, InvalidOperation
        from openai import AsyncOpenAI
        from app.services.config_service import get_runtime_config
        cfg = await get_runtime_config(db)
        api_key = cfg.get("DOC_LLM_API_KEY") or cfg.get("CHAT_LLM_API_KEY") or cfg.get("OPENAI_API_KEY")
        api_base = cfg.get("DOC_LLM_API_BASE") or cfg.get("CHAT_LLM_API_BASE") or cfg.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
        model = cfg.get("DOC_LLM_MODEL") or cfg.get("CHAT_LLM_MODEL") or cfg.get("OPENAI_LLM_MODEL") or "gpt-4o-mini"
        if not api_key:
            return result
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        sys = ("Extract quote fields from this engineering quote document. Return ONLY JSON with keys: "
               "price_min (number or null), price_max (number or null), turnaround (string or null), "
               "scope (string or null), assumptions (string or null). Use null when unsure; never invent a price.")
        resp = await client.chat.completions.create(
            model=model, temperature=0.1,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": doc_text[:6000]}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        def _dec(v):
            try:
                return Decimal(str(v)) if v is not None and str(v).strip() != "" else None
            except (InvalidOperation, ValueError):
                return None
        result["price_min"] = _dec(data.get("price_min"))
        result["price_max"] = _dec(data.get("price_max")) or result.get("price_min")
        for k in ("turnaround", "scope", "assumptions"):
            v = data.get(k)
            result[k] = (str(v)[:1900] if v else None)
    except Exception as exc:
        logger.info("[help_actions] quote extraction failed: %s", exc)
    return result


PROFILE_LIST_FIELDS = (
    "capabilities", "specialties", "software_tools", "equipment",
    "certifications", "notable_clients", "proven_experience_notable_projects",
)
PROFILE_SCALAR_FIELDS = ("team_summary", "primary_specialty")


def _merge_profile_fields(existing: Dict[str, Any], extracted: Dict[str, Any]):
    """Additively merge extracted profile data into existing values.

    List fields are unioned (case-insensitive dedup, existing entries kept first, capped);
    scalar fields are filled ONLY when currently empty. Never removes or overwrites data.
    Returns (merged_values, changed_field_set).
    """
    merged: Dict[str, Any] = {}
    changed = set()
    for fld in PROFILE_LIST_FIELDS:
        cur = existing.get(fld) or []
        cur = [str(x).strip() for x in cur if str(x).strip()] if isinstance(cur, list) else []
        new = extracted.get(fld) or []
        new = [str(x).strip() for x in new if str(x).strip()] if isinstance(new, list) else []
        if not new:
            continue
        out = list(cur)
        seen = {x.lower() for x in cur}
        for x in new:
            if x.lower() not in seen:
                out.append(x)
                seen.add(x.lower())
        cap = 30 if fld == "proven_experience_notable_projects" else 40
        out = out[:cap]
        if out != cur:
            merged[fld] = out
            changed.add(fld)
    for fld in PROFILE_SCALAR_FIELDS:
        cur = existing.get(fld)
        cur = cur.strip() if isinstance(cur, str) else ""
        new = extracted.get(fld)
        new = new.strip() if isinstance(new, str) else ""
        if new and not cur:
            merged[fld] = new[:2000]
            changed.add(fld)
    return merged, changed


async def _extract_profile_fields(db, doc_text: str) -> Dict[str, Any]:
    """Best-effort LLM extraction of a firm's profile from its own marketing/capability
    documents. Returns a dict of the profile list/scalar fields. Never raises."""
    result: Dict[str, Any] = {}
    if not (doc_text or "").strip():
        return result
    try:
        import json
        from openai import AsyncOpenAI
        from app.services.config_service import get_runtime_config
        cfg = await get_runtime_config(db)
        api_key = cfg.get("DOC_LLM_API_KEY") or cfg.get("CHAT_LLM_API_KEY") or cfg.get("OPENAI_API_KEY")
        api_base = cfg.get("DOC_LLM_API_BASE") or cfg.get("CHAT_LLM_API_BASE") or cfg.get("OPENAI_API_BASE") or "https://api.openai.com/v1"
        model = cfg.get("DOC_LLM_MODEL") or cfg.get("CHAT_LLM_MODEL") or cfg.get("OPENAI_LLM_MODEL") or "gpt-4o-mini"
        if not api_key:
            return result
        client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        sys = (
            "You extract a mechanical-engineering FIRM's profile from its own marketing / capability "
            "documents (brochure, capability statement, line card, project write-ups). Return ONLY JSON "
            "with these keys; use [] or null when the document does not support it; NEVER invent:\n"
            "- capabilities: specific engineering services performed (e.g. \"FEA structural analysis\", \"HVAC load calculations\")\n"
            "- specialties: focus areas / industries served (e.g. \"oil & gas\", \"data-center cooling\")\n"
            "- software_tools: named CAD/CAE/PLM tools (e.g. \"SolidWorks\", \"ANSYS Fluent\")\n"
            "- equipment: in-house equipment / machinery\n"
            "- certifications: e.g. \"ISO 9001\", \"ASME U-stamp\", \"PE-licensed\"\n"
            "- notable_clients: named clients, only if explicitly named\n"
            "- proven_experience_notable_projects: for EACH project/case study write EXACTLY ONE factual sentence: "
            "(1) what engineering service was performed (2) the method/approach used (3) the outcome/purpose. One item per project.\n"
            "- team_summary: one short paragraph on the team/expertise, or null\n"
            "- primary_specialty: a single one-line description of the firm's main specialty, or null\n"
            "Be factual and technical; extract only what the document supports."
        )
        resp = await client.chat.completions.create(
            model=model, temperature=0.1,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": doc_text[:8000]}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        for fld in PROFILE_LIST_FIELDS:
            v = data.get(fld)
            if isinstance(v, list):
                vals = [str(x).strip() for x in v if str(x).strip()]
                if vals:
                    result[fld] = vals[:40]
        for fld in PROFILE_SCALAR_FIELDS:
            v = data.get(fld)
            if isinstance(v, str) and v.strip():
                result[fld] = v.strip()
    except Exception as exc:
        logger.info("[help_actions] profile extraction failed: %s", exc)
    return result


def _validate_profile_updates(raw) -> Dict[str, Any]:
    """Sanitize an LLM-proposed profile-update dict down to known fields + safe types.
    List fields -> list[str] (trimmed, capped); scalar fields -> str. Drops everything else,
    so the model can never set an arbitrary column or inject a non-profile value."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for fld in PROFILE_LIST_FIELDS:
        v = raw.get(fld)
        if isinstance(v, list):
            vals = [str(x).strip() for x in v if str(x).strip()][:40]
            if vals:
                out[fld] = vals
    for fld in PROFILE_SCALAR_FIELDS:
        v = raw.get(fld)
        if isinstance(v, str) and v.strip():
            out[fld] = v.strip()[:2000]
    return out


async def _apply_profile_updates(db, user, extracted: Dict[str, Any], autonomous_enabled: bool, source: str) -> Dict[str, Any]:
    """Shared, authorization-enforcing write of profile additions (used by the doc and chat paths).

    Resolves the caller's OWN provider, enforces the full-profile-edit gate, ADDITIVELY merges
    (never removes), re-embeds, and audit-logs. Raises HTTPException on bad/unauthorized input.
    """
    from sqlalchemy import select
    from app.models.provider import ProviderMembership, Provider
    from app.api.endpoints.providers import _provider_can_edit_profile, EMBEDDING_FIELDS
    membership = (await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == user.id)
    )).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No provider firm is linked to your account.")
    provider = (await db.execute(
        select(Provider).where(Provider.id == membership.provider_id)
    )).scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider record not found.")
    if not await _provider_can_edit_profile(provider, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Improving your full profile is part of Professional / founding membership. Upgrade at /provider/upgrade, then I can do this for you.")
    existing = {fld: getattr(provider, fld, None) for fld in (PROFILE_LIST_FIELDS + PROFILE_SCALAR_FIELDS)}
    merged, changed = _merge_profile_fields(existing, extracted)
    if not changed:
        return {"ok": True, "message": "Those details are already in your profile \u2014 nothing new to add.",
                "link": {"href": "/provider/profile", "label": "Review your profile"}}
    embedding_changed = False
    for fld in changed:
        setattr(provider, fld, merged[fld])
        if fld in EMBEDDING_FIELDS:
            embedding_changed = True
    await db.commit()
    if embedding_changed:
        try:
            from app.tasks.search_tasks import generate_provider_embedding_async
            await generate_provider_embedding_async(str(provider.id))
        except Exception as exc:
            logger.warning("[help_actions] re-embed after profile update failed: %s", exc)
    await _audit(db, user, "provider", str(provider.id), "update_profile", autonomous_enabled)
    list_added = ", ".join(
        "%d %s" % (len(extracted[fld]), fld.replace("proven_experience_", "").replace("_", " "))
        for fld in changed if isinstance(extracted.get(fld), list) and extracted.get(fld)
    )
    scalar_added = ", ".join(fld.replace("_", " ") for fld in changed if fld in PROFILE_SCALAR_FIELDS)
    added = "; ".join(p for p in (list_added, scalar_added) if p) or "new details"
    return {"ok": True, "provider_id": str(provider.id),
            "message": ("I updated your firm profile from " + source + " \u2014 added " + added +
                        ". I merged it with what you already had (nothing removed), so please review and refine anything."),
            "link": {"href": "/provider/profile", "label": "Review your updated profile"}}


async def execute_action(
    db: AsyncSession,
    user: User,
    action_type: str,
    params: Dict[str, Any],
    autonomous_enabled: bool,
) -> Dict[str, Any]:
    """Authorize + execute one assistant action. Returns {ok, message}.

    Raises HTTPException(400/403/404) on bad/unauthorized requests.
    """
    action_type = (action_type or "").strip()
    params = params or {}

    if action_type in FORBIDDEN_ACTIONS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="That action must be completed by you directly; the assistant cannot do payments or NDA signing.")
    if action_type not in ALL_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Action not allowed: {action_type}")
    _is_admin = bool(user and "admin" in (user.roles or []))
    if action_type in ADMIN_ACTIONS and not _is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required for this action.")
    if action_type in AUTONOMOUS_ACTIONS and not autonomous_enabled and not _is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This action requires Autonomous mode, which is off. Enable it (with consent) or do it yourself.")

    # ---- SAFE: mark / undo contacted ----
    if action_type in ("mark_contacted", "undo_mark_contacted"):
        from app.api.endpoints.quotes import set_quote_contacted
        quote_id = params.get("quote_id")
        if not quote_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing quote_id.")
        contacted = action_type == "mark_contacted"
        await set_quote_contacted(db, user, quote_id, contacted)
        await _audit(db, user, "quote", quote_id, action_type, autonomous_enabled)
        return {"ok": True, "message": (
            "Marked that accepted RFQ as contacted — moved to your closed list."
            if contacted else "Moved that RFQ back to your active accepted list.")}

    # ---- AUTONOMOUS: accept quote (customer) ----
    if action_type == "accept_quote":
        from app.services.rfq_service import accept_quote
        quote_id = params.get("quote_id")
        if not quote_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing quote_id.")
        try:
            quote_uuid = _uuid.UUID(str(quote_id))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote id")
        try:
            await accept_quote(db, quote_uuid, user)  # enforces ownership + state
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        await _audit(db, user, "quote", quote_id, "accept_quote", autonomous_enabled)
        return {"ok": True, "message": "Quote accepted — the provider has been notified and their contact details are revealed to you."}

    # ---- AUTONOMOUS: cancel RFQ (customer) ----
    if action_type == "cancel_rfq":
        from sqlalchemy import select
        from datetime import datetime
        from app.models.rfq import RFQ
        from app.models.enums import RfqStatus
        rfq_id = params.get("rfq_id")
        if not rfq_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing rfq_id.")
        rfq = (await db.execute(select(RFQ).where(RFQ.id == rfq_id))).scalar_one_or_none()
        if not rfq:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
        if rfq.customer_user_id != user.id and "admin" not in (user.roles or []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        cur = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status or "")
        if cur == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is already cancelled")
        if rfq.is_closed and cur not in ("quote_limit_reached",):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is already closed")
        rfq.rfq_status = RfqStatus.CANCELLED
        rfq.closed_at = datetime.utcnow()
        await db.commit()
        await _audit(db, user, "rfq", rfq_id, "cancel_rfq", autonomous_enabled)
        return {"ok": True, "message": "RFQ cancelled."}

    # ---- AUTONOMOUS: withdraw quote (provider) ----
    if action_type == "withdraw_quote":
        from sqlalchemy import select
        from app.models.quote import Quote
        from app.models.provider import ProviderMembership
        quote_id = params.get("quote_id")
        if not quote_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing quote_id.")
        quote = (await db.execute(select(Quote).where(Quote.id == quote_id))).scalar_one_or_none()
        if not quote:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
        owns = (await db.execute(select(ProviderMembership).where(
            ProviderMembership.provider_id == quote.provider_id,
            ProviderMembership.user_id == user.id,
        ))).scalar_one_or_none()
        if not owns:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        quote.quote_status = "withdrawn"
        await db.commit()
        await _audit(db, user, "quote", quote_id, "withdraw_quote", autonomous_enabled)
        return {"ok": True, "message": "Quote withdrawn."}

    # ---- AUTONOMOUS: create an RFQ (draft) from staged documents (customer) ----
    if action_type == "create_rfq_from_docs":
        attachments = _validate_attachments(user, params.get("attachments"))
        if not attachments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid uploaded documents to use.")
        from app.schemas.rfq import RFQCreateRequest
        from app.services.rfq_service import create_rfq
        from app.models.rfq import RFQFile
        # Project description: the model-synthesized summary if provided, else stitched
        # from the documents' extracted text. Either way it's the user's OWN data.
        # Source text: the model's draft if it wrote one, else the documents' text.
        _doc_text = ("\n\n".join(a.get("excerpt", "") for a in attachments)).strip()
        _model_desc = (params.get("project_description") or "").strip()
        _source = _model_desc if len(_model_desc) >= 40 else _doc_text
        if len(_source) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The document(s) had too little readable text to build an RFQ. Please add a short description.")
        # Rewrite into a clean, structured, provider-facing description (no identity),
        # falling back to the raw source if the summarizer is unavailable.
        desc = await _summarize_rfq_from_docs(db, _source) or _source
        # Defense in depth: strip any identity/contact the model left in (cover-page
        # name/company often repeats in the prose), plus page markers.
        desc = _scrub_pii(desc, user)
        if len(desc) < 10:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="After removing contact details the document had too little technical content to build an RFQ. Please add a short scope description.")
        req = RFQCreateRequest(
            customer_email=user.email,
            business_name=(params.get("business_name") or user.business_name or None),
            contact_name=(params.get("contact_name") or user.full_name or None),
            project_description=desc,
            urgency=None,
            tollgate_phases=[],
        )
        rfq = await create_rfq(db, req, user)
        # Attach the staged files to the RFQ.
        import uuid as _u
        from datetime import datetime as _dt
        for a in attachments:
            db.add(RFQFile(
                id=_u.uuid4(), rfq_id=rfq.id, s3_key=a["key"],
                original_filename=a.get("filename") or "document",
                mime_type=a.get("mime") or "application/octet-stream",
                file_size_bytes=int(a.get("size_bytes") or 0),
                uploaded_by_user_id=user.id, created_at=_dt.utcnow(),
            ))
        await db.commit()
        await _audit(db, user, "rfq", str(rfq.id), "create_rfq_from_docs", autonomous_enabled)
        return {"ok": True, "rfq_id": str(rfq.id),
                "message": "I created a draft RFQ with your document(s) attached. Review the details and submit it when ready — submitting starts matching (and, if you require an NDA, the $10 fee, which you complete yourself).",
                "link": {"href": f"/customer/rfq/{rfq.id}", "label": "Review & submit the draft RFQ"}}

    # ---- AUTONOMOUS: submit a quote from staged documents (provider) ----
    if action_type == "submit_quote_from_docs":
        rfq_id = params.get("rfq_id")
        if not rfq_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing rfq_id.")
        attachments = _validate_attachments(user, params.get("attachments"))
        if not attachments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid uploaded quote document to use.")
        try:
            rfq_uuid = _uuid.UUID(str(rfq_id))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid rfq id")
        from sqlalchemy import select
        from app.models.provider import ProviderMembership
        membership = (await db.execute(
            select(ProviderMembership).where(ProviderMembership.user_id == user.id)
        )).scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No provider firm linked to your account.")
        doc_text = "\n\n".join(a.get("excerpt", "") for a in attachments).strip()
        fields = await _extract_quote_fields(db, doc_text)
        from app.schemas.quote import QuoteCreateRequest
        from app.services.rfq_service import submit_quote
        primary = attachments[0]
        # Strip the provider's own identity/contact from customer-visible quote text.
        _scope_src = fields.get("scope") or (doc_text[:1900] or None)
        req = QuoteCreateRequest(
            rough_price_min=fields.get("price_min"),
            rough_price_max=fields.get("price_max"),
            currency="USD",
            turnaround_estimate_text=fields.get("turnaround"),
            assumptions_text=_scrub_pii(fields.get("assumptions") or "", user) or None,
            scope_notes=_scrub_pii(_scope_src or "", user) or None,
            document_s3_key=primary["key"],
            document_filename=primary.get("filename"),
        )
        try:
            quote = await submit_quote(db=db, data=req, rfq_id=rfq_uuid, provider_id=membership.provider_id, user=user)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        await _audit(db, user, "quote", str(quote.id), "submit_quote_from_docs", autonomous_enabled)
        note = "" if fields.get("price_min") is not None else " I left the price blank because I couldn't read it confidently — set it before it's final if needed."
        return {"ok": True, "quote_id": str(quote.id),
                "message": "I submitted your quote from the document, with the file attached." + note,
                "link": {"href": f"/provider/rfq/{rfq_id}", "label": "Review the submitted quote"}}

    # ---- ADMIN: support-ticket actions (admin role only) ----
    if action_type in ("resolve_ticket", "escalate_ticket", "archive_ticket", "mark_ticket_spam"):
        from sqlalchemy import select
        from datetime import datetime, timezone
        from app.models.support import SupportTicket
        from app.models.enums import SupportTicketStatus
        from app.services.support_service import _emit_event, escalate_ticket as _escalate
        ticket_id = params.get("ticket_id")
        if not ticket_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing ticket_id (open the ticket page).")
        try:
            tid = _uuid.UUID(str(ticket_id))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ticket id.")
        ticket = (await db.execute(select(SupportTicket).where(SupportTicket.id == tid))).scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found.")
        old_status = ticket.status

        if action_type == "resolve_ticket":
            ticket.status = SupportTicketStatus.RESOLVED.value
            ticket.resolved_at = datetime.now(timezone.utc)
            await _emit_event(ticket, "status_change", db, actor_user_id=user.id,
                              payload={"from": old_status, "to": ticket.status, "via": "ai_assistant"})
            await db.commit()
            msg = "Ticket resolved."
        elif action_type == "archive_ticket":
            ticket.status = SupportTicketStatus.ARCHIVED.value
            await _emit_event(ticket, "status_change", db, actor_user_id=user.id,
                              payload={"from": old_status, "to": ticket.status, "via": "ai_assistant"})
            await db.commit()
            msg = "Ticket archived."
        elif action_type == "mark_ticket_spam":
            ticket.is_spam = True
            ticket.status = SupportTicketStatus.SPAM.value
            await _emit_event(ticket, "spam_flagged", db, actor_user_id=user.id,
                              payload={"from": old_status, "via": "ai_assistant"})
            await db.commit()
            msg = "Ticket marked as spam and closed."
        else:  # escalate_ticket
            await _escalate(ticket, (params.get("reason") or "Escalated via AI assistant"), db, actor_user_id=user.id)
            await db.commit()
            msg = "Ticket escalated."

        await _audit(db, user, "support_ticket", str(tid), action_type, autonomous_enabled)
        return {"ok": True, "message": msg, "link": {"href": f"/admin/support/{tid}", "label": "View the ticket"}}

    # ---- SAFE: update the provider's firm profile from staged documents ----
    if action_type == "update_profile_from_docs":
        attachments = _validate_attachments(user, params.get("attachments"))
        if not attachments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid uploaded documents to use. Attach a brochure or capability statement first.")
        from sqlalchemy import select
        from app.models.provider import ProviderMembership, Provider
        from app.api.endpoints.providers import _provider_can_edit_profile, EMBEDDING_FIELDS
        membership = (await db.execute(
            select(ProviderMembership).where(ProviderMembership.user_id == user.id)
        )).scalar_one_or_none()
        if not membership:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No provider firm is linked to your account.")
        provider = (await db.execute(
            select(Provider).where(Provider.id == membership.provider_id)
        )).scalar_one_or_none()
        if not provider:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider record not found.")
        if not await _provider_can_edit_profile(provider, db):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Improving your full profile is part of Professional / founding membership. Upgrade at /provider/upgrade, then I can do this for you.")
        doc_text = "\n\n".join(a.get("excerpt", "") for a in attachments).strip()
        extracted = await _extract_profile_fields(db, doc_text)
        if not extracted:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="I could not read enough from the document(s) to update your profile. Try a clearer capability statement or brochure.")
        existing = {fld: getattr(provider, fld, None) for fld in (PROFILE_LIST_FIELDS + PROFILE_SCALAR_FIELDS)}
        merged, changed = _merge_profile_fields(existing, extracted)
        if not changed:
            return {"ok": True, "message": "Your profile already covers what was in those documents \u2014 nothing new to add.",
                    "link": {"href": "/provider/profile", "label": "Review your profile"}}
        embedding_changed = False
        for fld in changed:
            setattr(provider, fld, merged[fld])
            if fld in EMBEDDING_FIELDS:
                embedding_changed = True
        await db.commit()
        if embedding_changed:
            try:
                from app.tasks.search_tasks import generate_provider_embedding_async
                await generate_provider_embedding_async(str(provider.id))
            except Exception as exc:
                logger.warning("[help_actions] re-embed after profile update failed: %s", exc)
        await _audit(db, user, "provider", str(provider.id), "update_profile_from_docs", autonomous_enabled)
        added = ", ".join(
            "%d %s" % (len(extracted[fld]), fld.replace("proven_experience_", "").replace("_", " "))
            for fld in changed if isinstance(extracted.get(fld), list) and extracted.get(fld)
        )
        return {"ok": True, "provider_id": str(provider.id),
                "message": ("I updated your firm profile from the document(s) \u2014 added " + (added or "new details") +
                            ". I merged it with what you already had (nothing removed), so please review and refine anything."),
                "link": {"href": "/provider/profile", "label": "Review your updated profile"}}

    # ---- SAFE: update the provider's firm profile from what they told the assistant in chat ----
    if action_type == "update_profile_from_chat":
        updates = _validate_profile_updates(params.get("profile_updates"))
        if not updates:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="I did not capture specific profile details to add. Tell me exactly what to add (a capability, tool, certification, or a project).")
        return await _apply_profile_updates(db, user, updates, autonomous_enabled, source="what you told me")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported action.")
