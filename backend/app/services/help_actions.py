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

SAFE_ACTIONS = {"mark_contacted", "undo_mark_contacted"}
AUTONOMOUS_ACTIONS = {"accept_quote", "cancel_rfq", "withdraw_quote"}
ALL_ACTIONS = SAFE_ACTIONS | AUTONOMOUS_ACTIONS

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
    if action_type in AUTONOMOUS_ACTIONS and not autonomous_enabled:
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

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported action.")
