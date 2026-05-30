"""Per-user account snapshot for the AI Help Assistant (Phase 2 personalization).

Builds a COMPACT, user-scoped summary of the signed-in user's live state — their
subscription, counts, and prioritized "action required" items — which is injected
into the chatbot prompt so it can answer "what should I do next?" and questions
about the user's own RFQs/quotes/NDAs. Read-only and scoped to this user; it never
contains another user's data. Every query is defensive: a failure degrades to a
partial/empty snapshot and never breaks the chat.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)

_CLOSED = {"quote_limit_reached", "customer_selected_provider", "closed_no_selection", "cancelled"}


def _status_str(v) -> str:
    return v.value if hasattr(v, "value") else str(v or "")


async def build_account_context(db: AsyncSession, user: Optional[User]) -> Dict[str, Any]:
    """Return a compact dict snapshot of the user's account + pending actions."""
    if user is None:
        return {}
    roles = list(user.roles or [])
    ctx: Dict[str, Any] = {
        "name": user.full_name or None,
        "company": user.business_name or None,
        "roles": roles,
        "actions": [],   # prioritized "do this next" strings
    }

    # --- Active subscription (customer search or provider annual) ---
    try:
        from app.models.payment import Subscription
        sub = (await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.subscription_status == "active",
            ).order_by(Subscription.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if sub:
            ctx["subscription"] = _status_str(sub.subscription_type)
            ctx["subscription_renews"] = sub.current_period_end.date().isoformat() if sub.current_period_end else None
        else:
            ctx["subscription"] = None
    except Exception as exc:
        logger.info("[help_context] subscription lookup failed: %s", exc)

    if "customer" in roles or not roles:
        await _customer_context(db, user, ctx)
    if "provider" in roles:
        await _provider_context(db, user, ctx)
    return ctx


async def _customer_context(db: AsyncSession, user: User, ctx: Dict[str, Any]) -> None:
    from app.models.rfq import RFQ
    from app.models.nda import RFQNDA
    try:
        rows = (await db.execute(
            select(RFQ.rfq_status, RFQ.quote_count, RFQ.is_closed).where(RFQ.customer_user_id == user.id)
        )).all()
        total = len(rows)
        open_with_quotes = sum(1 for st, qc, closed in rows if (qc or 0) > 0 and not closed)
        open_rfqs = sum(1 for st, qc, closed in rows if not closed)
        ctx["rfqs"] = {"total": total, "open": open_rfqs, "open_with_quotes": open_with_quotes}
        if open_with_quotes:
            ctx["actions"].append(
                f"You have {open_with_quotes} open RFQ(s) with quotes to review — open the RFQ to compare and accept a quote."
            )
    except Exception as exc:
        logger.info("[help_context] customer rfq counts failed: %s", exc)

    # NDAs awaiting the customer's countersignature, on OPEN RFQs only.
    try:
        awaiting = (await db.execute(
            select(func.count()).select_from(RFQNDA).join(RFQ, RFQ.id == RFQNDA.rfq_id).where(
                RFQNDA.customer_user_id == user.id,
                RFQNDA.provider_signed_at.isnot(None),
                RFQNDA.customer_signed_at.is_(None),
                RFQ.is_closed.is_(False),
            )
        )).scalar() or 0
        if awaiting:
            ctx["actions"].insert(0,
                f"{awaiting} NDA(s) are awaiting your signature — countersign so the provider can see your full project and quote.")
    except Exception as exc:
        logger.info("[help_context] customer NDA await failed: %s", exc)

    # Search quota + NDA credits (best-effort; columns may be absent on old rows).
    try:
        from app.core.config import settings
        limit_free = getattr(settings, "REGISTERED_SEARCH_LIMIT_PER_MONTH", 5)
        used = getattr(user, "monthly_search_count", 0) or 0
        ctx["search_used_this_month"] = used
        if ctx.get("subscription") in ("search_tier_1", "search_tier_2"):
            ctx["nda_free_credits_remaining"] = max(0, getattr(settings, "NDA_FREE_CREDITS_PER_MONTH", 5) - (getattr(user, "monthly_nda_credits_used", 0) or 0))
    except Exception:
        pass


async def _provider_context(db: AsyncSession, user: User, ctx: Dict[str, Any]) -> None:
    from app.models.provider import ProviderMembership
    from app.models.quote import Quote
    from app.models.nda import RFQNDA
    from app.models.rfq import RFQ
    try:
        membership = (await db.execute(
            select(ProviderMembership).where(ProviderMembership.user_id == user.id)
        )).scalar_one_or_none()
        if not membership:
            return
        pid = membership.provider_id
    except Exception as exc:
        logger.info("[help_context] provider membership failed: %s", exc)
        return

    # Accepted quotes where the customer hasn't been marked contacted yet.
    try:
        to_contact = (await db.execute(
            select(func.count()).select_from(Quote).where(
                Quote.provider_id == pid,
                Quote.quote_status == "accepted",
                Quote.provider_contacted_at.is_(None),
            )
        )).scalar() or 0
        if to_contact:
            ctx["actions"].insert(0,
                f"{to_contact} customer(s) accepted your quote and are waiting for you to reach out — see Accepted RFQs.")
    except Exception as exc:
        logger.info("[help_context] provider accepted failed: %s", exc)

    # NDAs awaiting THIS provider's signature on still-open RFQs.
    try:
        nda_pending = (await db.execute(
            select(func.count()).select_from(RFQNDA).join(RFQ, RFQ.id == RFQNDA.rfq_id).where(
                RFQNDA.provider_id == pid,
                RFQNDA.provider_signed_at.is_(None),
                RFQ.is_closed.is_(False),
            )
        )).scalar() or 0
        if nda_pending:
            ctx["actions"].append(
                f"{nda_pending} RFQ(s) need you to sign the NDA before you can read the full project.")
    except Exception as exc:
        logger.info("[help_context] provider nda failed: %s", exc)


def render_account_context(ctx: Dict[str, Any], page: Optional[str] = None) -> str:
    """Render the snapshot into a compact prompt block. Empty string if nothing useful."""
    if not ctx:
        return ""
    lines: List[str] = []
    who = ctx.get("name") or "the user"
    roles = ", ".join(ctx.get("roles") or []) or "user"
    line = f"Account: {who}"
    if ctx.get("company"):
        line += f" ({ctx['company']})"
    line += f"; role(s): {roles}."
    lines.append(line)

    sub = ctx.get("subscription")
    if sub:
        s = f"Subscription: {sub}"
        if ctx.get("subscription_renews"):
            s += f" (period ends {ctx['subscription_renews']})"
        lines.append(s + ".")
    else:
        lines.append("Subscription: none (free account).")

    if "rfqs" in ctx:
        r = ctx["rfqs"]
        lines.append(f"RFQs: {r.get('total',0)} total, {r.get('open',0)} open, {r.get('open_with_quotes',0)} with quotes to review.")
    if ctx.get("nda_free_credits_remaining") is not None:
        lines.append(f"Free NDA credits left this month: {ctx['nda_free_credits_remaining']}.")

    actions = ctx.get("actions") or []
    if actions:
        lines.append("ACTION ITEMS (most important first):")
        for a in actions[:6]:
            lines.append(f"- {a}")
    else:
        lines.append("No outstanding action items right now.")

    if page:
        lines.append(f"The user is currently on the page: {page}")
    return "\n".join(lines)
