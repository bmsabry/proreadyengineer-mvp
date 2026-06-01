"""Admin API endpoints."""

import logging
import csv
import json
import secrets
import io
from datetime import datetime
import httpx
from typing import Any, Dict, List, Optional
import asyncio
from app.tasks.search_tasks import generate_provider_embedding_async

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.models.advertising import Advertisement
from app.models.payment import PaymentAttempt, WebhookEvent
from app.models.provider import Provider, ProviderMembership, ProviderClaimRequest
from app.models.admin import TierEvaluationRequest, AuditLog
from app.models.rfq import RFQ, RFQDispatch
from app.models.search import SearchRequest
from app.models.user import User
from app.schemas.advertising import AdvertisementResponse
from app.schemas.base import PagedResponse
from app.schemas.payment import PaymentAttemptResponse, WebhookEventResponse
from app.schemas.provider import ProviderResponse, TierEvaluationResponse
from app.schemas.rfq import RFQResponse, RFQStatusOverrideRequest
from app.schemas.user import UserResponse

router = APIRouter()


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Get system statistics for the admin dashboard."""
    db_stats: Dict[str, Any] = {
        "user_count": 0,
        "provider_count": 0,
        "rfq_count": 0,
        "providers_with_embeddings": 0,
        "total_searches": 0,
        "connection_ok": False,
    }

    try:
        r = await db.execute(select(func.count()).select_from(User))
        db_stats["user_count"] = r.scalar() or 0
        db_stats["connection_ok"] = True
    except Exception as exc:
        db_stats["user_count_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(Provider))
        db_stats["provider_count"] = r.scalar() or 0
    except Exception as exc:
        db_stats["provider_count_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(RFQ))
        db_stats["rfq_count"] = r.scalar() or 0
    except Exception as exc:
        db_stats["rfq_count_error"] = str(exc)

    try:
        r = await db.execute(
            text("SELECT COUNT(*) FROM providers WHERE embedding IS NOT NULL")
        )
        db_stats["providers_with_embeddings"] = r.scalar() or 0
    except Exception as exc:
        db_stats["providers_with_embeddings_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(SearchRequest))
        db_stats["total_searches"] = r.scalar() or 0
    except Exception as exc:
        db_stats["total_searches_error"] = str(exc)

    # Check each API key independently using a FRESH session to avoid transaction corruption.
    # Each key has its own try/except so one failure never affects others.
    # Checks DB config first (keys saved via admin UI), then falls back to env vars.
    async def _key_set(db_key: str, env_val: str = "") -> bool:
        """Return True if this key is configured in DB or environment."""
        # Check env var first - always reliable
        if env_val and env_val.strip() and env_val.strip() not in ("dummy-key", "your-key-here", "none", "null", ""):
            return True
        # Try DB with a completely fresh session - never reuse the stats session
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as fresh_db:
                r = await fresh_db.execute(
                    text("SELECT value FROM system_config WHERE key = :k AND value IS NOT NULL AND value != ''  LIMIT 1"),
                    {"k": db_key},
                )
                row = r.fetchone()
                if row and row[0] and str(row[0]).strip() not in ("dummy-key", "your-key-here", ""):
                    return True
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        return False

    api_keys: Dict[str, bool] = {
        "openai_configured": await _key_set(
            "DEEPINFRA_API_KEY",
            getattr(settings, "OPENAI_API_KEY", "") or "",
        ),
        "stripe_configured": await _key_set(
            "STRIPE_SECRET_KEY",
            getattr(settings, "STRIPE_SECRET_KEY", "") or "",
        ),
        "paypal_configured": await _key_set(
            "PAYPAL_CLIENT_ID",
            getattr(settings, "PAYPAL_CLIENT_ID", "") or "",
        ),
        "signwell_configured": await _key_set(
            "SIGNWELL_API_KEY",
            getattr(settings, "SIGNWELL_API_KEY", "") or "",
        ),
        "aws_s3_configured": await _key_set(
            "AWS_ACCESS_KEY_ID",
            getattr(settings, "AWS_ACCESS_KEY_ID", "") or "",
        ),
        "resend_configured": await _key_set(
            "RESEND_API_KEY",
            getattr(settings, "RESEND_API_KEY", "") or "",
        ),
    }

    return {
        "database": db_stats,
        "api_keys": api_keys,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/admin/status")
async def admin_status_alias(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Backward-compat alias for /admin/stats."""
    return await admin_stats(db=db, current_user=current_user)


@router.get("/admin/rfqs", response_model=PagedResponse[RFQResponse])
async def admin_list_rfqs(
    status: Optional[str] = None,
    since: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List all RFQs.

    When `since` (ISO timestamp) is provided (the 'Production' view), only RFQs
    created at/after it are returned, so pre-launch / sandbox test RFQs are hidden.
    The cutoff is the shared go-live marker (PAYMENTS_PRODUCTION_SINCE).
    """
    from sqlalchemy import select, func
    from app.models.rfq import RFQ

    query = select(RFQ).options(selectinload(RFQ.files))
    if status:
        query = query.where(RFQ.rfq_status == status)
    if since:
        try:
            _since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.where(RFQ.created_at >= _since_dt)
        except (ValueError, AttributeError):
            pass

    # Get total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Get paginated results - order by newest first
    result = await db.execute(query.order_by(RFQ.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    rfqs = result.scalars().all()

    return PagedResponse(
        items=[RFQResponse.from_orm(r) for r in rfqs],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size) if total else 1
    )


@router.get("/admin/rfqs/{rfq_id}", response_model=RFQResponse)
async def admin_get_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Get RFQ details."""
    from sqlalchemy import select
    from app.models.rfq import RFQ

    result = await db.execute(select(RFQ).options(selectinload(RFQ.files)).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    return RFQResponse.from_orm(rfq)


@router.post("/admin/rfqs/{rfq_id}/override-status")
async def admin_override_rfq_status(
    rfq_id: str,
    data: RFQStatusOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Override RFQ status."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.admin import AuditLog
    import uuid
    from datetime import datetime

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    old_status = rfq.rfq_status
    old_is_closed = rfq.is_closed
    rfq.rfq_status = data.new_status

    # For terminal statuses, always set is_closed=True so the dispatch scheduler
    # never picks up this RFQ again and sends more emails.
    _TERMINAL_STATUSES = {
        "cancelled", "closed_no_selection", "quote_limit_reached",
        "customer_selected_provider",
    }
    _new_status_str = data.new_status if isinstance(data.new_status, str) else str(data.new_status)
    if _new_status_str in _TERMINAL_STATUSES:
        # is_closed is synced from rfq_status by the model validator
        rfq.closed_at = rfq.closed_at or datetime.utcnow()
        logger.info(
            "admin_override_rfq_status: rfq=%s set is_closed=True for terminal status %s",
            rfq_id, _new_status_str,
        )

    # Commit the status change FIRST so the override always persists; the audit log is
    # best-effort and must never roll back the actual status change.
    _new_status_val = data.new_status.value if hasattr(data.new_status, "value") else str(data.new_status)

    # is_closed is a Postgres GENERATED ALWAYS (Computed) column. SQLAlchemy does NOT
    # refresh it on the in-memory ORM object after commit, and accessing rfq.is_closed
    # post-commit triggers a lazy reload that crashes the async session
    # (sqlalchemy.exc.MissingGreenlet). Compute the value in Python instead.
    new_is_closed = _new_status_str in {
        "quote_limit_reached", "customer_selected_provider",
        "closed_no_selection", "cancelled",
    }
    await db.commit()

    try:
        db.add(AuditLog(
            id=uuid.uuid4(),
            actor_user_id=current_user.id,
            entity_type="rfq",
            entity_id=rfq_id,
            action="status_override",
            before_state={"status": old_status.value if hasattr(old_status, 'value') else str(old_status), "is_closed": old_is_closed},
            after_state={"status": _new_status_val, "is_closed": new_is_closed},
            extra_data={"reason": data.reason},
            created_at=datetime.utcnow(),
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return {"message": f"RFQ status changed to {_new_status_val}", "rfq_id": rfq_id, "is_closed": new_is_closed}


@router.get("/admin/rfqs/{rfq_id}/dispatch-tracking")
async def admin_rfq_dispatch_tracking(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Get full dispatch tracking for an RFQ - all matched providers with status."""
    import uuid as _uuid
    from app.models.rfq import RFQMatch
    from app.models.quote import Quote

    try:
        rfq_uuid = _uuid.UUID(rfq_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid RFQ ID format")

    # Get RFQ
    rfq_result = await db.execute(select(RFQ).where(RFQ.id == rfq_uuid))
    rfq = rfq_result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Get ALL matches ordered by rank, joined with provider info
    matches_result = await db.execute(
        select(RFQMatch, Provider)
        .join(Provider, RFQMatch.provider_id == Provider.id)
        .where(RFQMatch.rfq_id == rfq_uuid)
        .order_by(RFQMatch.rank_position)
    )
    matches = matches_result.all()

    # Get all dispatches for this RFQ (keyed by provider_id)
    dispatches_result = await db.execute(
        select(RFQDispatch).where(RFQDispatch.rfq_id == rfq_uuid)
    )
    dispatches = {d.provider_id: d for d in dispatches_result.scalars().all()}

    # Get providers who submitted quotes (keyed by provider_id)
    quotes_result = await db.execute(
        select(Quote).where(Quote.rfq_id == rfq_uuid)
    )
    quoted_providers = {q.provider_id for q in quotes_result.scalars().all()}

    # Build provider list
    providers = []
    for match, provider in matches:
        dispatch = dispatches.get(match.provider_id)

        # Get provider email
        email = None
        if provider.email_addresses:
            if isinstance(provider.email_addresses, list) and provider.email_addresses:
                email = provider.email_addresses[0]
            elif isinstance(provider.email_addresses, str):
                email = provider.email_addresses

        # Determine display status
        if match.provider_id in quoted_providers:
            display_status = "quoted"
        elif dispatch:
            display_status = dispatch.dispatch_status.value if hasattr(dispatch.dispatch_status, 'value') else str(dispatch.dispatch_status)
        else:
            display_status = "pending"

        providers.append({
            "rank_position": match.rank_position,
            "provider_id": match.provider_id,
            "provider_name": provider.firm_name or provider.name,
            "city": provider.city,
            "state": provider.state,
            "tier": provider.tier,
            "composite_score": match.composite_score,
            "provider_email": email,
            "is_dispatched": match.is_dispatched,
            "dispatched_at": match.dispatched_at.isoformat() if match.dispatched_at else None,
            "dispatch_status": display_status,
            "email_target": dispatch.email_target if dispatch else None,
            "teaser_email_sent_at": dispatch.teaser_email_sent_at.isoformat() if dispatch and dispatch.teaser_email_sent_at else None,
            "submitted_quote": match.provider_id in quoted_providers,
            "is_accepted": match.provider_id == rfq.selected_provider_id,
        })

    return {
        "rfq_id": str(rfq.id),
        "rfq_status": rfq.rfq_status.value if hasattr(rfq.rfq_status, 'value') else str(rfq.rfq_status),
        "customer_email": rfq.customer_email,
        "business_name": rfq.business_name,
        "project_description": rfq.project_description,
        "urgency": rfq.urgency,
        "nda_required": rfq.nda_required,
        "quote_count": rfq.quote_count,
        "live_quote_count": sum(1 for p in providers if p["submitted_quote"]),
        "is_closed": rfq.is_closed,
        "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
        "total_matches": len(providers),
        "total_contacted": sum(1 for p in providers if p["is_dispatched"]),
        "total_quoted": sum(1 for p in providers if p["submitted_quote"]),
        "providers": providers,
    }




@router.post("/admin/rfqs/repair-quote-counts")
async def repair_rfq_quote_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Repair corrupted quote_count values and is_closed flags on all RFQs.

    Recalculates quote_count from the actual quotes table (submitted + accepted quotes only).
    Fixes is_closed if quote_count < RFQ_MAX_QUOTES and status is not explicitly closed.
    """
    from sqlalchemy import text
    from app.core.config import settings
    max_quotes = getattr(settings, "RFQ_MAX_QUOTES", 5)

    # Get all RFQs with their actual quote counts from the quotes table
    result = await db.execute(text("""
        SELECT 
            r.id,
            r.quote_count AS stored_count,
            r.is_closed,
            r.rfq_status,
            COALESCE(q.actual_count, 0) AS actual_count
        FROM rfqs r
        LEFT JOIN (
            SELECT rfq_id, COUNT(*) AS actual_count
            FROM quotes
            WHERE quote_status IN ('submitted', 'accepted')
            GROUP BY rfq_id
        ) q ON q.rfq_id = r.id
        WHERE r.quote_count != COALESCE(q.actual_count, 0)
           OR (r.is_closed = TRUE 
               AND COALESCE(q.actual_count, 0) < :max_quotes
               AND r.rfq_status NOT IN ('cancelled', 'closed_no_selection', 'customer_selected_provider'))
    """), {"max_quotes": max_quotes})

    rows = result.fetchall()
    repaired = []

    for row in rows:
        rfq_id, stored_count, is_closed, rfq_status, actual_count = row

        should_be_closed = actual_count >= max_quotes

        # Only reopen RFQs where closure was caused by quote_count corruption
        # Do NOT reopen explicitly closed/cancelled/selected RFQs
        safe_to_reopen = rfq_status not in (
            'cancelled', 'closed_no_selection', 'customer_selected_provider'
        )

        new_is_closed = should_be_closed or (is_closed and not safe_to_reopen)
        if is_closed and safe_to_reopen:
            new_is_closed = should_be_closed

        new_status = rfq_status
        if should_be_closed and rfq_status not in (
            'quote_limit_reached', 'cancelled', 'closed_no_selection', 'customer_selected_provider'
        ):
            new_status = 'quote_limit_reached'
        elif not should_be_closed and is_closed and safe_to_reopen and actual_count > 0:
            new_status = 'open_for_unlock'
        elif not should_be_closed and is_closed and safe_to_reopen and actual_count == 0:
            new_status = 'open_for_dispatch'

        await db.execute(text("""
            UPDATE rfqs 
            SET quote_count = :actual_count,
                rfq_status = :new_status
            WHERE id = :rfq_id
        """), {
            "actual_count": actual_count,
            "new_status": new_status,
            "rfq_id": str(rfq_id),
        })

        repaired.append({
            "rfq_id": str(rfq_id),
            "old_quote_count": stored_count,
            "new_quote_count": actual_count,
            "old_is_closed": is_closed,
            "new_is_closed": new_is_closed,
            "old_status": rfq_status,
            "new_status": new_status,
        })

    await db.commit()

    return {
        "repaired_count": len(repaired),
        "message": f"Repaired {len(repaired)} RFQ(s) with incorrect quote counts or closure flags",
        "details": repaired,
    }
@router.post("/admin/rfqs/{rfq_id}/terminate-dispatch")
async def admin_terminate_rfq_dispatch(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Terminate future dispatch for an RFQ (stop contacting new providers)."""
    from app.models.rfq import RfqStatus
    from datetime import timezone

    import uuid as _uuid
    try:
        rfq_uuid = _uuid.UUID(rfq_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid RFQ ID format")
    rfq_result = await db.execute(select(RFQ).where(RFQ.id == rfq_uuid))
    rfq = rfq_result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    if rfq.is_closed:
        raise HTTPException(status_code=400, detail="RFQ is already closed")

    old_status = rfq.rfq_status.value if hasattr(rfq.rfq_status, 'value') else str(rfq.rfq_status)

    rfq.rfq_status = RfqStatus.CANCELLED  # validator syncs is_closed
    rfq.closed_at = datetime.utcnow()

    # Audit log
    try:
        import uuid as _uuid
        audit = AuditLog(
            id=_uuid.uuid4(),
            actor_user_id=current_user.id,
            entity_type="rfq",
            entity_id=rfq_id,
            action="terminate_dispatch",
            before_state={"rfq_status": old_status, "is_closed": False},
            after_state={"rfq_status": "cancelled", "is_closed": True},
            extra_data={"admin_id": str(current_user.id)},
            created_at=datetime.utcnow(),
        )
        db.add(audit)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    await db.commit()
    return {"message": "RFQ dispatch terminated", "rfq_id": rfq_id}

@router.post("/admin/rfqs/{rfq_id}/force-dispatch")
async def admin_force_rfq_dispatch(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Force dispatch next batch for an RFQ immediately."""
    import uuid as _uuid
    from app.services.rfq_service import dispatch_next_batch
    try:
        rfq_uuid = _uuid.UUID(rfq_id)
        dispatched = await dispatch_next_batch(db, rfq_uuid)
        return {
            "status": "ok",
            "rfq_id": rfq_id,
            "providers_emailed": len(dispatched),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/admin/payments", response_model=PagedResponse[PaymentAttemptResponse])
async def admin_list_payments(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List payment attempts."""
    from sqlalchemy import select, func
    from app.models.payment import PaymentAttempt

    query = select(PaymentAttempt)
    if status:
        query = query.where(PaymentAttempt.payment_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(PaymentAttempt.created_at.desc()).offset((page - 1) * size).limit(size))
    payments = result.scalars().all()

    return PagedResponse(
        items=[PaymentAttemptResponse.from_orm(p) for p in payments],
        total=total,
        page=page,
        page_size=size,
        pages=max(1, (total + size - 1) // size) if total else 1
    )


@router.get("/admin/webhooks", response_model=PagedResponse[WebhookEventResponse])
async def admin_list_webhooks(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List webhook events."""
    from sqlalchemy import select, func
    from app.models.payment import WebhookEvent

    query = select(WebhookEvent)
    if provider:
        query = query.where(WebhookEvent.provider_name == provider)
    if status:
        query = query.where(WebhookEvent.processing_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(WebhookEvent.received_at.desc()).offset((page - 1) * size).limit(size))
    events = result.scalars().all()

    return PagedResponse(
        items=[WebhookEventResponse.from_orm(e) for e in events],
        total=total,
        page=page,
        page_size=size,
        pages=max(1, (total + size - 1) // size) if total else 1
    )


@router.post("/admin/webhooks/{event_id}/replay")
async def admin_replay_webhook(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Replay a webhook event."""
    from sqlalchemy import select
    from app.models.payment import WebhookEvent
    from app.services.payment_service import handle_stripe_webhook, handle_paypal_webhook

    result = await db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")

    # Replay based on provider
    if event.provider_name == "stripe":
        await handle_stripe_webhook(db, event.payload, "")
    elif event.provider_name == "paypal":
        await handle_paypal_webhook(db, event.payload)

    event.processing_status = "replayed"
    await db.commit()

    return {"message": "Webhook replayed", "event_id": event_id}


@router.get("/admin/tier-requests", response_model=PagedResponse[TierEvaluationResponse])
async def admin_list_tier_requests(
    status: Optional[str] = "pending",
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List tier evaluation requests."""
    from sqlalchemy import select, func
    from app.models.provider import TierEvaluationRequest

    query = select(TierEvaluationRequest)
    if status:
        query = query.where(TierEvaluationRequest.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(TierEvaluationRequest.created_at.desc()).offset((page - 1) * size).limit(size))
    requests = result.scalars().all()

    return PagedResponse(
        items=[TierEvaluationResponse.from_orm(r) for r in requests],
        total=total,
        page=page,
        page_size=size,
        pages=max(1, (total + size - 1) // size) if total else 1
    )


@router.post("/admin/tier-requests/{request_id}/approve")
async def admin_approve_tier_request(
    request_id: str,
    new_tier: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Approve tier evaluation request."""
    from sqlalchemy import select
    from app.models.provider import TierEvaluationRequest, Provider
    from datetime import datetime

    result = await db.execute(
        select(TierEvaluationRequest).where(TierEvaluationRequest.id == request_id)
    )
    tier_request = result.scalar_one_or_none()

    if not tier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    tier_request.status = "approved"
    tier_request.reviewed_by = current_user.id
    tier_request.reviewed_at = datetime.utcnow()
    tier_request.review_notes = notes

    # Update provider tier
    result = await db.execute(select(Provider).where(Provider.id == tier_request.provider_id))
    provider = result.scalar_one()
    provider.tier = new_tier

    await db.commit()

    return {"message": f"Tier upgraded to {new_tier}", "provider_id": str(provider.id)}


@router.post("/admin/tier-requests/{request_id}/reject")
async def admin_reject_tier_request(
    request_id: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Reject tier evaluation request."""
    from sqlalchemy import select
    from app.models.provider import TierEvaluationRequest
    from datetime import datetime

    result = await db.execute(
        select(TierEvaluationRequest).where(TierEvaluationRequest.id == request_id)
    )
    tier_request = result.scalar_one_or_none()

    if not tier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    tier_request.status = "rejected"
    tier_request.reviewed_by = current_user.id
    tier_request.reviewed_at = datetime.utcnow()
    tier_request.review_notes = notes

    await db.commit()

    return {"message": "Request rejected"}


@router.get("/admin/ads", response_model=PagedResponse[AdvertisementResponse])
async def admin_list_ads(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List all advertisements."""
    from sqlalchemy import select, func
    from app.models.advertising import Advertisement

    query = select(Advertisement)
    if status:
        query = query.where(Advertisement.ad_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(Advertisement.created_at.desc()).offset((page - 1) * size).limit(size))
    ads = result.scalars().all()

    return PagedResponse(
        items=[AdvertisementResponse.model_validate(a) for a in ads],
        total=total,
        page=page,
        page_size=size,
        pages=max(1, (total + size - 1) // size) if total else 1
    )


@router.post("/admin/ads/{ad_id}/pause")
async def admin_pause_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Pause an advertisement."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement, AdStatusEnum

    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()

    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")

    ad.ad_status = AdStatusEnum.PAUSED
    await db.commit()

    return {"message": "Ad paused", "ad_id": ad_id}




@router.get("/admin/users")
async def admin_list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    status: str = Query("active"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: List all users with pagination and optional search."""
    from sqlalchemy import select, func, or_
    from app.models.user import User
    from app.models.payment import Subscription

    query = select(User)
    count_query = select(func.count()).select_from(User)

    # Active vs Removed split: removed accounts are anonymized to removed_<id>@deleted.invalid
    removed_clause = User.email.like("removed_%")
    status_clause = removed_clause if status == "removed" else ~removed_clause
    query = query.where(status_clause)
    count_query = count_query.where(status_clause)

    if search:
        filter_clause = or_(
            User.email.ilike(f"%{search}%"),
            User.full_name.ilike(f"%{search}%"),
            User.business_name.ilike(f"%{search}%"),
        )
        query = query.where(filter_clause)
        count_query = count_query.where(filter_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(User.email).offset((page - 1) * size).limit(size)
    )
    users = result.scalars().all()

    # Get subscription info for each user
    user_ids = [u.id for u in users]
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id.in_(user_ids),
            Subscription.subscription_status == "active",
        )
    )
    subs = {str(s.user_id): s for s in sub_result.scalars().all()}

    items = []
    for u in users:
        sub = subs.get(str(u.id))
        items.append({
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "business_name": u.business_name,
            "roles": u.roles,
            "is_super_admin": u.is_super_admin,
            "monthly_search_count": u.monthly_search_count or 0,
            "search_count_reset_at": u.search_count_reset_at.isoformat() if u.search_count_reset_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "failed_login_count": u.failed_login_count or 0,
            "locked_until": u.locked_until.isoformat() if u.locked_until else None,
            "membership_type": sub.subscription_type if sub else "free",
            "subscription_status": sub.subscription_status if sub else None,
            "subscription_id": str(sub.id) if sub else None,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/admin/users/export.csv")
async def admin_export_users_csv(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Export all users to CSV with full account info and membership type."""
    from sqlalchemy import select
    from app.models.user import User
    from app.models.payment import Subscription

    result = await db.execute(select(User).order_by(User.email))
    users = result.scalars().all()

    sub_result = await db.execute(
        select(Subscription).where(Subscription.subscription_status == "active")
    )
    subs = {str(s.user_id): s for s in sub_result.scalars().all()}

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id", "email", "full_name", "business_name", "roles",
        "is_super_admin", "membership_type", "subscription_status",
        "monthly_search_count", "search_count_reset_at",
        "last_login_at", "failed_login_count", "locked_until",
    ])

    for u in users:
        sub = subs.get(str(u.id))
        writer.writerow([
            str(u.id),
            u.email,
            u.full_name or "",
            u.business_name or "",
            ",".join(u.roles) if u.roles else "",
            u.is_super_admin,
            sub.subscription_type if sub else "free",
            sub.subscription_status if sub else "none",
            u.monthly_search_count or 0,
            u.search_count_reset_at.isoformat() if u.search_count_reset_at else "",
            u.last_login_at.isoformat() if u.last_login_at else "",
            u.failed_login_count or 0,
            u.locked_until.isoformat() if u.locked_until else "",
        ])

    output.seek(0)
    filename = f"users_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/admin/users/{user_id}/reset-search-quota")
async def admin_reset_user_search_quota(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Reset a user's monthly search count to zero."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_count = user.monthly_search_count or 0
    user.monthly_search_count = 0
    user.search_count_reset_at = datetime.utcnow()
    await db.commit()

    return {
        "message": "Search quota reset successfully",
        "user_id": user_id,
        "old_count": old_count,
        "new_count": 0,
    }

@router.post("/admin/users/{user_id}/suspend")
async def admin_suspend_user(
    user_id: str,
    reason: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Suspend a user account."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    await db.commit()

    # Revoke all tokens
    from app.services.auth_service import revoke_all_user_tokens
    await revoke_all_user_tokens(db, user_id)

    return {"message": "User suspended", "user_id": user_id}


@router.post("/admin/users/{user_id}/remove")
async def admin_remove_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Anonymise a user account - scrambles credentials, frees the email.

    Historical data (RFQs, quotes, memberships) is preserved linked to the old
    user_id, but login credentials are destroyed and the original email is
    released so the person may re-register fresh.
    """
    import secrets as _secrets
    import uuid as _uuid
    from app.models.user import RefreshToken
    from sqlalchemy import select, update
    from datetime import timezone

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Guard: already removed
    if user.email and user.email.startswith("removed_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has already been removed",
        )

    original_email = user.email

    # Scramble credentials - frees the original email for re-registration
    user.email = f"removed_{user.id}@deleted.invalid"
    user.hashed_password = "REMOVED_" + _secrets.token_hex(32)
    user.is_active = False

    # Revoke all active refresh tokens
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .values(revoked_at=datetime.now(timezone.utc))
    )

    # Emit audit log (non-fatal)
    try:
        audit = AuditLog(
            id=_uuid.uuid4(),
            actor_user_id=current_user.id,
            entity_type="user",
            entity_id=user_id,
            action="remove_user",
            before_state={"email": original_email, "is_active": True},
            after_state={"email": user.email, "is_active": False},
            metadata={"removed_by": str(current_user.id)},
            created_at=datetime.utcnow(),
        )
        db.add(audit)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    await db.commit()

    return {"success": True, "message": "User removed", "user_id": user_id}


# ─── System Configuration Endpoints ──────────────────────────────────────────
from pydantic import BaseModel as _BaseModel, ConfigDict, field_validator
from app.services.config_service import get_runtime_config as _get_runtime_config
from app.services.config_service import save_config_values as _save_config_values


class SystemConfigRequest(_BaseModel):
    model_config = ConfigDict(extra='ignore')

    @field_validator('*', mode='before')
    @classmethod
    def coerce_to_str(cls, v):
        """Coerce any non-string value to string.
        Handles cases where settings object returns int (SMTP_PORT=587) or bool (SMTP_TLS=True).
        """
        if v is None:
            return None
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (int, float)):
            return str(v)
        return v
    # Extra AI/Search fields from frontend
    embedding_api_key: Optional[str] = None
    embedding_api_base: Optional[str] = None
    doc_llm_api_key: Optional[str] = None
    doc_llm_api_base: Optional[str] = None
    doc_llm_model: Optional[str] = None
    chat_llm_api_key: Optional[str] = None
    chat_llm_api_base: Optional[str] = None
    chat_llm_model: Optional[str] = None
    render_api_key: Optional[str] = None
    render_monthly_budget: Optional[str] = None
    llm_pricing: Optional[str] = None
    operating_cost_items: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    openai_llm_model: Optional[str] = None
    openai_embedding_model: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    aws_s3_bucket: Optional[str] = None
    resend_api_key: Optional[str] = None
    resend_from_email: Optional[str] = None
    # SMTP Email
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_tls: Optional[str] = None
    smtp_ssl: Optional[str] = None
    signrequest_api_key: Optional[str] = None
    signwell_api_key: Optional[str] = None
    signwell_template_id: Optional[str] = None
    # PayPal
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_mode: Optional[str] = None
    paypal_webhook_id: Optional[str] = None
    paypal_plan_search_tier1: Optional[str] = None
    paypal_plan_search_tier2: Optional[str] = None
    paypal_plan_provider_profile: Optional[str] = None
    paypal_plan_advertisement: Optional[str] = None
    # RFQ Communication
    rfq_batch_size: Optional[str] = None
    rfq_batch_interval_hours: Optional[str] = None
    rfq_closed_message: Optional[str] = None


def _mask(v: str) -> str:
    if not v or len(v) < 8:
        return ''
    return v[:4] + '•' * 16 + v[-4:]


@router.get("/admin/config")
async def get_system_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get current system configuration (secrets masked)."""
    config = await _get_runtime_config(db)

    # Query DB directly: only explicitly saved keys are "Set"
    db_keys: set = set()
    try:
        result = await db.execute(
            text("SELECT key FROM system_config WHERE value IS NOT NULL AND value != ''")
        )
        db_keys = {row[0] for row in result.fetchall()}
    except Exception as _exc:
        import logging as _l
        _l.getLogger("admin.config").warning(f"[CONFIG] db_keys query failed: {_exc}")
        try:
            await db.rollback()
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    def _is_set(key: str) -> bool:
        return key in db_keys

    def _mask(val: str) -> str:
        if not val:
            return ""
        return val[:4] + "*" * max(0, len(val) - 4)

    return {
        "openai_api_key": _mask(config.get("OPENAI_API_KEY", "")),
        "openai_api_key_set": _is_set("OPENAI_API_KEY"),
        "openai_api_base": config.get("OPENAI_API_BASE", ""),
        "openai_api_base_set": _is_set("OPENAI_API_BASE"),
        "openai_llm_model": config.get("OPENAI_LLM_MODEL", ""),
        "openai_llm_model_set": _is_set("OPENAI_LLM_MODEL"),
        "openai_embedding_model": config.get("OPENAI_EMBEDDING_MODEL", ""),
        "openai_embedding_model_set": _is_set("OPENAI_EMBEDDING_MODEL"),
        "embedding_api_key": _mask(config.get("EMBEDDING_API_KEY", "")),
        "embedding_api_key_set": _is_set("EMBEDDING_API_KEY"),
        "embedding_api_base": config.get("EMBEDDING_API_BASE", ""),
        "embedding_api_base_set": _is_set("EMBEDDING_API_BASE"),
        "doc_llm_api_key": _mask(config.get("DOC_LLM_API_KEY", "")),
        "doc_llm_api_key_set": _is_set("DOC_LLM_API_KEY"),
        "doc_llm_api_base": config.get("DOC_LLM_API_BASE", ""),
        "doc_llm_api_base_set": _is_set("DOC_LLM_API_BASE"),
        "doc_llm_model": config.get("DOC_LLM_MODEL", ""),
        "doc_llm_model_set": _is_set("DOC_LLM_MODEL"),
        "chat_llm_api_key": _mask(config.get("CHAT_LLM_API_KEY", "")),
        "chat_llm_api_key_set": _is_set("CHAT_LLM_API_KEY"),
        "chat_llm_api_base": config.get("CHAT_LLM_API_BASE", ""),
        "chat_llm_api_base_set": _is_set("CHAT_LLM_API_BASE"),
        "chat_llm_model": config.get("CHAT_LLM_MODEL", ""),
        "chat_llm_model_set": _is_set("CHAT_LLM_MODEL"),
        "render_api_key": _mask(config.get("RENDER_API_KEY", "")),
        "render_api_key_set": _is_set("RENDER_API_KEY"),
        "render_monthly_budget": config.get("RENDER_MONTHLY_BUDGET", ""),
        "render_monthly_budget_set": _is_set("RENDER_MONTHLY_BUDGET"),
        "llm_pricing": config.get("LLM_PRICING", ""),
        "llm_pricing_set": _is_set("LLM_PRICING"),
        "operating_cost_items": config.get("OPERATING_COST_ITEMS", ""),
        "operating_cost_items_set": _is_set("OPERATING_COST_ITEMS"),
        "stripe_secret_key": _mask(config.get("STRIPE_SECRET_KEY", "")),
        "stripe_secret_key_set": _is_set("STRIPE_SECRET_KEY"),
        "stripe_publishable_key": config.get("STRIPE_PUBLISHABLE_KEY", ""),
        "stripe_publishable_key_set": _is_set("STRIPE_PUBLISHABLE_KEY"),
        "aws_access_key_id": _mask(config.get("AWS_ACCESS_KEY_ID", "")),
        "aws_access_key_set": _is_set("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key_set": _is_set("AWS_SECRET_ACCESS_KEY"),
        "aws_region": config.get("AWS_REGION", ""),
        "aws_region_set": _is_set("AWS_REGION"),
        "aws_s3_bucket": config.get("AWS_S3_BUCKET", ""),
        "aws_s3_bucket_set": _is_set("AWS_S3_BUCKET"),
        "smtp_host": config.get("SMTP_HOST", ""),
        "smtp_host_set": _is_set("SMTP_HOST"),
        "smtp_port": config.get("SMTP_PORT", "587"),
        "smtp_user": config.get("SMTP_USER", ""),
        "smtp_user_set": _is_set("SMTP_USER"),
        "smtp_password": _mask(config.get("SMTP_PASSWORD", "")),
        "smtp_password_set": _is_set("SMTP_PASSWORD"),
        "smtp_tls": config.get("SMTP_TLS", "true"),
        "smtp_ssl": config.get("SMTP_SSL", "false"),
        "resend_api_key": _mask(config.get("RESEND_API_KEY", "")),
        "resend_api_key_set": _is_set("RESEND_API_KEY"),
        "resend_from_email": config.get("RESEND_FROM_EMAIL", ""),
        "resend_from_email_set": _is_set("RESEND_FROM_EMAIL"),
        "signrequest_api_key": _mask(config.get("SIGNREQUEST_API_KEY", "")),
        "signrequest_api_key_set": _is_set("SIGNREQUEST_API_KEY"),
        "signwell_api_key": _mask(config.get("SIGNWELL_API_KEY", "")),
        "signwell_api_key_set": _is_set("SIGNWELL_API_KEY"),
        "signwell_template_id": config.get("SIGNWELL_TEMPLATE_ID", ""),
        "signwell_template_id_set": _is_set("SIGNWELL_TEMPLATE_ID"),
        "rfq_batch_size": config.get("RFQ_BATCH_SIZE", "5"),
        "rfq_batch_size_set": _is_set("RFQ_BATCH_SIZE"),
        "rfq_batch_interval_hours": config.get("RFQ_BATCH_INTERVAL_HOURS", "24"),
        "rfq_batch_interval_hours_set": _is_set("RFQ_BATCH_INTERVAL_HOURS"),
        "rfq_closed_message": config.get("RFQ_CLOSED_MESSAGE", ""),
        "rfq_closed_message_set": _is_set("RFQ_CLOSED_MESSAGE"),
        "stripe_webhook_secret_set": _is_set("STRIPE_WEBHOOK_SECRET"),
        "paypal_configured": _is_set("PAYPAL_CLIENT_ID"),
        "paypal_mode": config.get("PAYPAL_MODE", ""),
        "paypal_mode_set": _is_set("PAYPAL_MODE"),
        "source": "db_or_env",
    }
@router.post("/admin/config")
async def save_system_config(
    data: SystemConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Save API keys and config to database for runtime use."""
    import logging
    _log = logging.getLogger("admin.config.save")
    try:
        _log.info(f"[SAVE] POST /admin/config from user {current_user.id}")
        config_map: dict = {}
        if data.openai_api_key:         config_map["OPENAI_API_KEY"]         = data.openai_api_key
        if data.openai_api_base:        config_map["OPENAI_API_BASE"]        = data.openai_api_base
        if data.openai_llm_model:       config_map["OPENAI_LLM_MODEL"]       = data.openai_llm_model
        if data.openai_embedding_model: config_map["OPENAI_EMBEDDING_MODEL"] = data.openai_embedding_model
        if data.embedding_api_key:      config_map["EMBEDDING_API_KEY"]      = data.embedding_api_key
        if data.embedding_api_base:     config_map["EMBEDDING_API_BASE"]     = data.embedding_api_base
        if data.doc_llm_api_key:        config_map["DOC_LLM_API_KEY"]        = data.doc_llm_api_key
        if data.doc_llm_api_base:       config_map["DOC_LLM_API_BASE"]       = data.doc_llm_api_base
        if data.doc_llm_model:          config_map["DOC_LLM_MODEL"]          = data.doc_llm_model
        if data.chat_llm_api_key:       config_map["CHAT_LLM_API_KEY"]       = data.chat_llm_api_key
        if data.chat_llm_api_base:      config_map["CHAT_LLM_API_BASE"]      = data.chat_llm_api_base
        if data.chat_llm_model:         config_map["CHAT_LLM_MODEL"]         = data.chat_llm_model
        if data.render_api_key:         config_map["RENDER_API_KEY"]         = data.render_api_key
        if data.render_monthly_budget:  config_map["RENDER_MONTHLY_BUDGET"]  = data.render_monthly_budget
        if data.llm_pricing is not None:        config_map["LLM_PRICING"]           = data.llm_pricing
        if data.operating_cost_items is not None: config_map["OPERATING_COST_ITEMS"] = data.operating_cost_items
        if data.stripe_secret_key:      config_map["STRIPE_SECRET_KEY"]      = data.stripe_secret_key
        if data.stripe_publishable_key: config_map["STRIPE_PUBLISHABLE_KEY"] = data.stripe_publishable_key
        if data.stripe_webhook_secret:  config_map["STRIPE_WEBHOOK_SECRET"]  = data.stripe_webhook_secret
        if data.aws_access_key_id:      config_map["AWS_ACCESS_KEY_ID"]      = data.aws_access_key_id
        if data.aws_secret_access_key:  config_map["AWS_SECRET_ACCESS_KEY"]  = data.aws_secret_access_key
        if data.aws_region:             config_map["AWS_REGION"]             = data.aws_region
        if data.aws_s3_bucket:          config_map["AWS_S3_BUCKET"]          = data.aws_s3_bucket
        if data.smtp_host is not None:     config_map["SMTP_HOST"]     = data.smtp_host
        if data.smtp_port is not None:     config_map["SMTP_PORT"]     = data.smtp_port
        if data.smtp_user is not None:     config_map["SMTP_USER"]     = data.smtp_user
        if data.smtp_password:             config_map["SMTP_PASSWORD"] = data.smtp_password
        if data.smtp_tls is not None:      config_map["SMTP_TLS"]      = data.smtp_tls
        if data.smtp_ssl is not None:      config_map["SMTP_SSL"]      = data.smtp_ssl
        if data.resend_api_key:         config_map["RESEND_API_KEY"]         = data.resend_api_key
        if data.resend_from_email:      config_map["RESEND_FROM_EMAIL"]      = data.resend_from_email
        if data.signrequest_api_key:    config_map["SIGNREQUEST_API_KEY"]    = data.signrequest_api_key
        if data.signwell_api_key:       config_map["SIGNWELL_API_KEY"]       = data.signwell_api_key
        if data.signwell_template_id:   config_map["SIGNWELL_TEMPLATE_ID"]   = data.signwell_template_id
        if data.paypal_client_id:             config_map["PAYPAL_CLIENT_ID"]             = data.paypal_client_id
        if data.paypal_client_secret:         config_map["PAYPAL_CLIENT_SECRET"]         = data.paypal_client_secret
        if data.paypal_mode:                  config_map["PAYPAL_MODE"]                  = data.paypal_mode
        if data.paypal_webhook_id:            config_map["PAYPAL_WEBHOOK_ID"]            = data.paypal_webhook_id
        if data.paypal_plan_search_tier1:     config_map["PAYPAL_PLAN_SEARCH_TIER1"]     = data.paypal_plan_search_tier1
        if data.paypal_plan_search_tier2:     config_map["PAYPAL_PLAN_SEARCH_TIER2"]     = data.paypal_plan_search_tier2
        if data.paypal_plan_provider_profile: config_map["PAYPAL_PLAN_PROVIDER_PROFILE"] = data.paypal_plan_provider_profile
        if data.paypal_plan_advertisement:    config_map["PAYPAL_PLAN_ADVERTISEMENT"]    = data.paypal_plan_advertisement
        if data.rfq_batch_size is not None and data.rfq_batch_size != "": config_map["RFQ_BATCH_SIZE"]          = data.rfq_batch_size
        if data.rfq_batch_interval_hours is not None and data.rfq_batch_interval_hours != "": config_map["RFQ_BATCH_INTERVAL_HOURS"] = data.rfq_batch_interval_hours
        if data.rfq_closed_message is not None:                                              config_map["RFQ_CLOSED_MESSAGE"]       = data.rfq_closed_message

        _log.info(f"[SAVE] Config map keys: {list(config_map.keys())}")

        if not config_map:
            return {"status": "no_changes", "keys_saved": [], "message": "No non-empty values provided"}

        await _save_config_values(db, config_map, user_id=current_user.id)
        _log.info(f"[SAVE] SUCCESS: saved {len(config_map)} keys")
        return {"status": "saved", "keys_saved": list(config_map.keys()), "message": f"Saved {len(config_map)} key(s) successfully"}

    except HTTPException:
        raise
    except Exception as exc:
        import logging as _l
        _l.getLogger("admin.config.save").error(f"[SAVE] FAILED: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(exc)}")



@router.get("/admin/debug/config-test")
async def admin_debug_config_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Diagnostic: test the config save path step by step."""
    import traceback
    results = {"steps": [], "success": False}

    # Step 1: Check if system_config table exists
    try:
        from sqlalchemy import text as _t
        r = await db.execute(_t("SELECT COUNT(*) FROM system_config"))
        count = r.scalar()
        results["steps"].append({"step": "table_exists", "ok": True, "count": count})
    except Exception as e:
        results["steps"].append({"step": "table_exists", "ok": False, "error": str(e)})
        try:
            await db.rollback()
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        return results

    # Step 2: Check table columns
    try:
        r = await db.execute(_t(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'system_config' ORDER BY ordinal_position"
        ))
        cols = [{"name": row[0], "type": row[1]} for row in r.fetchall()]
        results["steps"].append({"step": "columns", "ok": True, "columns": cols})
    except Exception as e:
        results["steps"].append({"step": "columns", "ok": False, "error": str(e)})

    # Step 3: Try a test write using the actual save function
    try:
        await _save_config_values(db, {"_TEST_KEY": "test_value"}, user_id=current_user.id)
        results["steps"].append({"step": "test_write", "ok": True})
    except Exception as e:
        results["steps"].append({"step": "test_write", "ok": False, "error": str(e), "traceback": traceback.format_exc()})

    # Step 4: Verify the test write
    try:
        r = await db.execute(_t("SELECT value FROM system_config WHERE key = '_TEST_KEY'"))
        row = r.fetchone()
        if row and row[0] == "test_value":
            results["steps"].append({"step": "verify_write", "ok": True, "value": row[0]})
        else:
            results["steps"].append({"step": "verify_write", "ok": False, "value": str(row)})
    except Exception as e:
        results["steps"].append({"step": "verify_write", "ok": False, "error": str(e)})

    # Step 5: Clean up test key
    try:
        await db.execute(_t("DELETE FROM system_config WHERE key = '_TEST_KEY'"))
        await db.commit()
        results["steps"].append({"step": "cleanup", "ok": True})
    except Exception as e:
        results["steps"].append({"step": "cleanup", "ok": False, "error": str(e)})

    results["success"] = all(s.get("ok") for s in results["steps"])
    return results

# --- Email Debug Endpoint ---

class TestEmailRequest(_BaseModel):
    to_email: str


@router.post("/admin/debug/test-email")
async def admin_debug_test_email(
    data: TestEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Send a Resend test email to verify email integration."""
    config = await _get_runtime_config(db)
    api_key: str = config.get("RESEND_API_KEY", "") or ""
    api_key_present = bool(api_key)
    api_key_prefix = api_key[:10] if len(api_key) >= 10 else api_key
    from_address = config.get("RESEND_FROM_EMAIL", "") or settings.FROM_EMAIL

    if not api_key_present:
        return {
            "success": False,
            "message_id": None,
            "error": "RESEND_API_KEY is not configured. Add it in Admin Configuration.",
            "api_key_present": False,
            "api_key_prefix": "",
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    html_body = (
        "<h1>Email Test Successful</h1>"
        "<p>Resend integration is working correctly for ProMechDirectory.</p>"
        "<p>Sent at: " + timestamp + "</p>"
    )

    payload = {
        "from": from_address,
        "to": [data.to_email],
        "subject": "ProMechDirectory - Resend Test Email",
        "html": html_body,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
        resend_status = response.status_code
        if resend_status in (200, 201):
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("id"),
                "error": None,
                "api_key_present": True,
                "api_key_prefix": api_key_prefix,
                "from_address": from_address,
                "to_address": data.to_email,
                "resend_status_code": resend_status,
            }
        else:
            try:
                ed = response.json()
                error_msg = ed.get("message") or ed.get("name") or str(ed)
            except Exception:
                error_msg = response.text or "HTTP " + str(resend_status)
            return {
                "success": False,
                "message_id": None,
                "error": "Resend API error (" + str(resend_status) + "): " + error_msg,
                "api_key_present": True,
                "api_key_prefix": api_key_prefix,
                "from_address": from_address,
                "to_address": data.to_email,
                "resend_status_code": resend_status,
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message_id": None,
            "error": "Request to Resend API timed out after 15 seconds.",
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }
    except httpx.RequestError as exc:
        return {
            "success": False,
            "message_id": None,
            "error": "Network error contacting Resend: " + str(exc),
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "message_id": None,
            "error": "Unexpected error: " + str(exc),
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }


# --- Resend Domain Check Endpoint ---

@router.get("/admin/debug/resend-domains")
async def admin_check_resend_domains(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Check which domains are verified in the Resend account for the configured API key."""
    config = await _get_runtime_config(db)
    api_key: str = config.get("RESEND_API_KEY", "") or ""
    from_address = config.get("RESEND_FROM_EMAIL", "") or settings.FROM_EMAIL

    if not api_key:
        return {
            "success": False,
            "error": "RESEND_API_KEY is not configured.",
            "domains": [],
            "from_address": from_address,
            "configured_domain": "",
            "domain_verified": False,
            "tip": "Add your Resend API key in Admin Settings > Email tab.",
        }

    configured_domain = from_address.split("@")[1].lower() if "@" in from_address else ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.resend.com/domains",
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
        if response.status_code == 200:
            data = response.json()
            domains = data.get("data", [])
            domain_statuses = {d.get("name", "").lower(): d.get("status", "unknown") for d in domains}
            domain_verified = (
                configured_domain in domain_statuses
                and domain_statuses.get(configured_domain) == "verified"
            )
            tip = None
            if not domain_verified:
                if configured_domain in domain_statuses:
                    tip = (
                        "Domain '{}' is in your Resend account but status is '{}'. ".format(
                            configured_domain, domain_statuses.get(configured_domain)
                        )
                        + "Check DNS records at https://resend.com/domains"
                    )
                else:
                    tip = (
                        "Domain '{}' is NOT in this Resend account. ".format(configured_domain)
                        + "Go to https://resend.com/domains, click 'Add Domain', enter '{}', ".format(configured_domain)
                        + "add the provided DNS records to Cloudflare, then verify. "
                        + "Make sure you are using the API key from the same Resend workspace."
                    )
            return {
                "success": True,
                "error": None,
                "domains": [
                    {"name": d.get("name"), "status": d.get("status"), "region": d.get("region")}
                    for d in domains
                ],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": domain_verified,
                "tip": tip,
            }
        elif response.status_code == 401:
            return {
                "success": False,
                "error": "Invalid Resend API key (401 Unauthorized). Go to https://resend.com/api-keys to get a valid key.",
                "domains": [],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": False,
                "tip": "The API key stored in Admin Settings is invalid or revoked.",
            }
        else:
            try:
                err = response.json().get("message", response.text)
            except Exception:
                err = response.text
            return {
                "success": False,
                "error": "Resend API error ({}): {}".format(response.status_code, err),
                "domains": [],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": False,
                "tip": None,
            }
    except Exception as exc:
        return {
            "success": False,
            "error": "Error contacting Resend: " + str(exc),
            "domains": [],
            "configured_domain": configured_domain,
            "from_address": from_address,
            "domain_verified": False,
            "tip": None,
        }


# ---------------------------------------------------------------------------
# Admin Debug - Signwell Connection Test
@router.get("/admin/debug/test-signwell")
async def admin_debug_test_signwell_connection(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Test Signwell API key validity by listing document templates."""
    # ALL imports inside try/except to prevent 500s without CORS headers
    try:
        import httpx
        from app.services.config_service import get_config_value

        SIGNWELL_BASE = "https://www.signwell.com/api/v1"

        api_key = await get_config_value(db, "SIGNWELL_API_KEY")
        if not api_key or not api_key.strip():
            return {
                "success": False,
                "error": "Signwell API key not configured.",
                "hint": "Go to Admin > Settings > Document Signing and save your Signwell API key.",
            }

        api_key = api_key.strip()
        key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"

        # Try /document_templates - the correct Signwell v1 read-only endpoint
        endpoints_to_try = [
            ("/document_templates", "document templates"),
            ("/templates", "templates"),
        ]

        last_status = None
        last_body = ""

        async with httpx.AsyncClient(timeout=15.0) as client:
            for path, label in endpoints_to_try:
                try:
                    resp = await client.get(
                        f"{SIGNWELL_BASE}{path}",
                        headers={
                            "X-Api-Key": api_key,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    last_status = resp.status_code
                    last_body = resp.text[:500]

                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception:
                            data = {}
                        items = data if isinstance(data, list) else (data.get("document_templates") or data.get("templates") or data.get("data") or [])
                        items = items if isinstance(items, list) else []
                        template_list = [
                            {"id": str(t.get("id", "")), "name": (t.get("name") or "(unnamed)")}
                            for t in items
                        ][:10]
                        return {
                            "success": True,
                            "message": f"Signwell API key is valid! ({label} endpoint responded 200)",
                            "key_preview": key_preview,
                            "key_length": len(api_key),
                            "endpoint_used": path,
                            # Field names match the admin UI; include names so the
                            # admin can copy the correct API template UUID.
                            "templates_found": len(items),
                            "template_ids": [t["id"] for t in template_list],
                            "templates": template_list,
                        }
                    elif resp.status_code == 401:
                        return {
                            "success": False,
                            "error": "API key is invalid or expired (401 Unauthorized from Signwell)",
                            "key_preview": key_preview,
                            "key_length": len(api_key),
                            "hint": "Copy your API key fresh from Signwell dashboard: Account > API Keys",
                            "raw_response": last_body,
                        }
                    # 404 = endpoint not found, try next
                except httpx.RequestError as req_err:
                    return {"success": False, "error": f"Network error calling Signwell: {req_err}"}

        # None of the endpoints returned 200
        return {
            "success": False,
            "error": f"Signwell API returned HTTP {last_status} on all tested endpoints",
            "key_preview": key_preview,
            "raw_response": last_body,
            "hint": "If status is 404, the API endpoint path may have changed. If 403, check key permissions.",
        }

    except Exception as exc:
        import traceback
        return {
            "success": False,
            "error": str(exc),
            "detail": traceback.format_exc()[-800:],
        }


# Admin Debug - Signwell NDA End-to-End Test
# ---------------------------------------------------------------------------


class TestNDARequest(_BaseModel):
    customer_name: str
    customer_email: str
    provider_name: str
    provider_email: str



@router.post("/admin/debug/test-nda")
async def admin_debug_test_nda(
    data: TestNDARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Create a real Signwell test NDA document and send signing invitations.

    Uses the correct Signwell API per official SDK:
    - recipients (not signees)
    - NO signing_elements (that field is only for raw document creation, not templates)
    - template_fields for pre-filling text values
    """
    from datetime import date
    import logging
    logger = logging.getLogger(__name__)

    try:
        from app.services.nda_service import _headers, _get_template_id, SIGNWELL_BASE_URL
        h = await _headers(db)
        tid = await _get_template_id(db)
    except Exception as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Signwell not configured: {exc}",
            "customer_signing_url": None, "provider_signing_url": None,
        }

    effective_date = date.today().strftime("%m/%d/%Y")

    # Step 1: Fetch template to get placeholder IDs
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            tmpl_resp = await client.get(
                f"{SIGNWELL_BASE_URL}/document_templates/{tid}", headers=h
            )
            tmpl_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Failed to fetch template {exc.response.status_code}: {exc.response.text}",
            "customer_signing_url": None, "provider_signing_url": None,
        }
    except Exception as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Template fetch failed: {exc}",
            "customer_signing_url": None, "provider_signing_url": None,
        }

    tmpl_data = tmpl_resp.json()
    logger.info(f"[TEST-NDA] Template keys: {list(tmpl_data.keys())}")
    logger.info(f"[TEST-NDA] Full template: {json.dumps(tmpl_data, default=str)[:2000]}")

    # Extract template placeholder IDs (signers/roles)
    tmpl_placeholders = (
        tmpl_data.get("placeholder_signers") or
        tmpl_data.get("template_signers") or
        tmpl_data.get("placeholders") or
        tmpl_data.get("roles") or
        tmpl_data.get("recipients") or
        []
    )
    logger.info(f"[TEST-NDA] Template placeholders ({len(tmpl_placeholders)}): {json.dumps(tmpl_placeholders, default=str)[:500]}")

    # Helper to extract the EXACT placeholder name from a placeholder object
    def get_ph_name(p):
        return (
            p.get("name")
            or p.get("placeholder_name")
            or p.get("role")
            or p.get("title")
            or None
        )

    # Extract EXACT placeholder names from template (must match precisely)
    if len(tmpl_placeholders) >= 2:
        customer_placeholder_name = get_ph_name(tmpl_placeholders[0]) or "Customer"
        provider_placeholder_name = get_ph_name(tmpl_placeholders[1]) or "Provider"
    elif len(tmpl_placeholders) == 1:
        customer_placeholder_name = get_ph_name(tmpl_placeholders[0]) or "Customer"
        provider_placeholder_name = "Provider"
    else:
        logger.warning("[TEST-NDA] No placeholders found in template, using fallback names")
        customer_placeholder_name = "Customer"
        provider_placeholder_name = "Provider"

    logger.info(f"[TEST-NDA] Placeholder names from template: customer={customer_placeholder_name!r}, provider={provider_placeholder_name!r}")

    # Step 2: Build template_fields from the template's ACTUAL fields. Matches by
    # api_id OR label (so an auto-named field like 'TextField_1' labelled
    # 'provider_company' is filled) and never sends signature fields. This prevents
    # the 422 'not_in_templates' error when the template differs from old defaults.
    from app.services.nda_service import _build_template_fields
    template_fields = await _build_template_fields(db, {
        "customer_name":        data.customer_name,
        "customer_name2":       data.customer_name,
        "customer_company":     getattr(data, 'customer_company', None) or data.customer_name,
        "customer_entity_type": "Individual",
        "provider_name":        data.provider_name,
        "provider_name2":       data.provider_name,
        "provider_company":     getattr(data, 'provider_company', None) or data.provider_name,
        "provider_entity_type": "Company",
        "effective_date":       effective_date,
        "governing_state":      "Ohio",
    })

    # Step 3: Build payload using CORRECT Signwell API structure per official SDK
    # - "recipients" (not "signees")
    # - NO signing_elements (only applies to raw document creation, not template-based)
    # - "template_fields" for pre-filling text values
    payload = {
        "template_id": tid,
        "test_mode": False,
        "subject": f"[TEST] ProMechDirectory NDA - {data.customer_name} & {data.provider_name}",
        "message": (
            "This is a test NDA document to verify the document signing "
            "integration. Please sign to confirm the workflow works end-to-end."
        ),
        "recipients": [
            {
                "id": "1",
                "name": data.customer_name,
                "email": data.customer_email,
                "placeholder_name": customer_placeholder_name,
            },
            {
                "id": "2",
                "name": data.provider_name,
                "email": data.provider_email,
                "placeholder_name": provider_placeholder_name,
            },
        ],
        "template_fields": template_fields,
    }

    logger.info(f"[TEST-NDA] Sending payload: {json.dumps(payload, default=str)[:1000]}")

    # Step 4: Create document from template
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SIGNWELL_BASE_URL}/document_templates/documents",
                json=payload,
                headers=h,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Signwell create failed {exc.response.status_code}: {exc.response.text}",
            "customer_signing_url": None, "provider_signing_url": None,
        }
    except Exception as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Document creation failed: {exc}",
            "customer_signing_url": None, "provider_signing_url": None,
        }

    doc = resp.json()
    document_id = doc.get("id")
    logger.info(f"[TEST-NDA] Document created: {document_id}")
    logger.info(f"[TEST-NDA] Document keys: {list(doc.keys())}")

    # Extract signing URLs
    customer_signing_url = None
    provider_signing_url = None
    recipients_list = doc.get("recipients") or doc.get("signers") or []
    logger.info(f"[TEST-NDA] Recipients in response: {json.dumps(recipients_list, default=str)[:500]}")
    for s in recipients_list:
        url = s.get("sign_page_url") or s.get("embedded_signing_url")
        email = s.get("email", "")
        if email == data.customer_email:
            customer_signing_url = url
        elif email == data.provider_email:
            provider_signing_url = url
        elif not customer_signing_url:
            customer_signing_url = url
        elif not provider_signing_url:
            provider_signing_url = url

    return {
        "success": True,
        "document_id": document_id,
        "error": None,
        "customer_signing_url": customer_signing_url,
        "provider_signing_url": provider_signing_url,
        "message": f"NDA document created. Signing emails sent to {data.customer_email} and {data.provider_email}.",
    }



@router.post("/admin/rfqs/{rfq_id}/send-post-nda")
async def admin_trigger_post_acceptance_nda(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Manually trigger post-acceptance NDA for an RFQ where quote was accepted.

    Use this when the automatic NDA sending failed silently after quote acceptance.
    """
    import uuid as _uuid
    from app.models.rfq import RFQ
    from app.models.quote import Quote
    from app.models.provider import Provider, ProviderMembership
    from app.models.user import User as _User
    from sqlalchemy import select as _sel

    try:
        rfq_uuid = _uuid.UUID(rfq_id)
    except ValueError:
        return {"success": False, "error": "Invalid RFQ ID format"}

    # Load RFQ
    rfq_result = await db.execute(_sel(RFQ).where(RFQ.id == rfq_uuid))
    rfq = rfq_result.scalar_one_or_none()
    if not rfq:
        return {"success": False, "error": "RFQ not found"}

    if not rfq.nda_required:
        return {"success": False, "error": "This RFQ does not require an NDA"}

    if not rfq.selected_provider_id:
        return {"success": False, "error": "No provider selected yet - quote must be accepted first"}

    # Get the selected provider
    provider_result = await db.execute(
        _sel(Provider).where(Provider.id == rfq.selected_provider_id)
    )
    selected_provider = provider_result.scalar_one_or_none()
    if not selected_provider:
        return {"success": False, "error": f"Provider {rfq.selected_provider_id} not found"}

    # Find active provider user
    membership_result = await db.execute(
        _sel(ProviderMembership)
        .join(_User, _User.id == ProviderMembership.user_id)
        .where(
            ProviderMembership.provider_id == rfq.selected_provider_id,
            ProviderMembership.status == "active",
            _User.is_active == True,
            ~_User.email.like("removed_%"),
        )
        .order_by(ProviderMembership.created_at.desc())
        .limit(1)
    )
    membership = membership_result.scalar_one_or_none()
    if not membership:
        return {"success": False, "error": f"No active user found for provider {rfq.selected_provider_id}"}

    provider_user_result = await db.execute(
        _sel(_User).where(_User.id == membership.user_id)
    )
    provider_user = provider_user_result.scalar_one_or_none()
    if not provider_user:
        return {"success": False, "error": "Provider user account not found"}

    # Find customer user
    if not rfq.customer_user_id:
        return {"success": False, "error": "RFQ has no customer user linked - anonymous RFQ"}

    customer_result = await db.execute(
        _sel(_User).where(_User.id == rfq.customer_user_id)
    )
    customer_user = customer_result.scalar_one_or_none()
    if not customer_user:
        return {"success": False, "error": "Customer user account not found"}

    # Trigger NDA creation
    try:
        from app.services.nda_service import create_post_acceptance_nda
        # Build string arguments matching create_post_acceptance_nda signature
        _cust_first = (customer_user.first_name or '').strip()
        _cust_last  = (customer_user.last_name  or '').strip()
        _cust_name  = f'{_cust_first} {_cust_last}'.strip() or customer_user.email
        _prov_first = (provider_user.first_name or '').strip()
        _prov_last  = (provider_user.last_name  or '').strip()
        _prov_name  = f'{_prov_first} {_prov_last}'.strip() or provider_user.email
        _prov_co    = getattr(selected_provider, 'firm_name', None) or getattr(selected_provider, 'name', None) or 'Provider'
        _biz_name   = (rfq.business_name or rfq.contact_name or '').strip()

        result = await create_post_acceptance_nda(
            rfq_id=rfq.id,
            customer_user_id=customer_user.id,
            customer_name=_cust_name,
            customer_email=customer_user.email,
            business_name=_biz_name,
            provider_id=selected_provider.id,
            provider_signer_name=_prov_name,
            provider_email=provider_user.email,
            provider_company=_prov_co,
            db=db,
        )
        return {
            "success": True,
            "message": f"NDA triggered successfully. Signing emails sent to {customer_user.email} and {provider_user.email}",
            "document_id": result.get("document_id"),
            "nda_id": result.get("nda_id"),
            "customer_email": customer_user.email,
            "provider_email": provider_user.email,
        }
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error(f"Admin NDA trigger failed: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}
@router.get("/admin/debug/test-nda/{document_id}/status")
async def admin_debug_test_nda_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Poll Signwell for per-signer signing status and check S3 for completed PDF."""
    from app.services.nda_service import _headers, SIGNWELL_BASE_URL
    from app.services.file_service import check_file_exists, generate_download_url

    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/documents/{document_id}", headers=h
            )
            resp.raise_for_status()
        doc = resp.json()
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to fetch document from Signwell: {exc}",
            "document_id": document_id,
            "document_status": None,
            "customer_signed": False, "customer_signed_at": None,
            "provider_signed": False, "provider_signed_at": None,
            "fully_signed": False,
            "s3_saved": False, "s3_key_checked": None, "s3_download_url": None,
        }

    doc_status = doc.get("status", "unknown")
    signers = (doc.get("recipients") or doc.get("signees") or doc.get("signers") or [])
    customer_signed, customer_signed_at = False, None
    provider_signed, provider_signed_at = False, None

    if len(signers) >= 1:
        s = signers[0]
        customer_signed = s.get("status") in ("signed", "completed") or bool(s.get("signed_at"))
        customer_signed_at = s.get("signed_at")
    if len(signers) >= 2:
        s = signers[1]
        provider_signed = s.get("status") in ("signed", "completed") or bool(s.get("signed_at"))
        provider_signed_at = s.get("signed_at")

    # Fallback: if Signwell reports document as completed but signer parsing found no data
    if doc_status in ("completed", "signed") and not fully_signed:
        customer_signed = True
        provider_signed = True
    fully_signed = customer_signed and provider_signed
    s3_saved = False
    s3_download_url: Optional[str] = None
    s3_key_checked: Optional[str] = None

    try:
        for key in [
            f"ndas/test/nda_signed_{document_id}.pdf",
            f"ndas/test_{document_id}/nda_signed_{document_id}.pdf",
        ]:
            if check_file_exists(key):
                s3_saved = True
                s3_key_checked = key
                s3_download_url = generate_download_url(key, expire_seconds=3600)
                break
    except Exception:
        pass  # S3 not configured - non-fatal

    return {
        "success": True,
        "error": None,
        "document_id": document_id,
        "document_status": doc_status,
        "customer_signed": customer_signed,
        "customer_signed_at": customer_signed_at,
        "provider_signed": provider_signed,
        "provider_signed_at": provider_signed_at,
        "fully_signed": fully_signed,
        "s3_saved": s3_saved,
        "s3_key_checked": s3_key_checked,
        "s3_download_url": s3_download_url,
    }


@router.post("/admin/debug/test-nda/{document_id}/void")
async def admin_debug_test_nda_void(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Void/cancel a test NDA document in Signwell to clean up after testing."""
    from app.services.nda_service import _headers, SIGNWELL_BASE_URL

    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{SIGNWELL_BASE_URL}/documents/{document_id}", headers=h
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {
                "success": True, "error": None,
                "message": "Document not found (may already be void/completed)",
                "document_id": document_id,
            }
        return {
            "success": False,
            "error": f"Signwell API error {exc.response.status_code}: {exc.response.text}",
            "message": None, "document_id": document_id,
        }
    except Exception as exc:
        return {
            "success": False, "error": f"Request failed: {exc}",
            "message": None, "document_id": document_id,
        }

    return {
        "success": True, "error": None,
        "message": f"Document {document_id} voided successfully.",
        "document_id": document_id,
    }


@router.get("/admin/debug/signwell-template-raw")
async def admin_debug_signwell_template_raw(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Fetch the raw Signwell template JSON to inspect signer IDs, field api_ids, and structure."""
    try:
        from app.services.nda_service import _headers, _get_template_id, SIGNWELL_BASE_URL
        h = await _headers(db)
        tid = await _get_template_id(db)
    except Exception as exc:
        return {"success": False, "error": f"Signwell not configured: {exc}", "template": None}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/document_templates/{tid}",
                headers=h,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False,
            "error": f"Signwell API error {exc.response.status_code}: {exc.response.text}",
            "template": None,
        }
    except Exception as exc:
        return {"success": False, "error": f"Request failed: {exc}", "template": None}

    tmpl = resp.json()
    # Extract useful debug info
    top_level_keys = list(tmpl.keys())
    signers = (
        tmpl.get("template_signers") or
        tmpl.get("signees") or
        tmpl.get("signers") or
        tmpl.get("roles") or
        tmpl.get("signer_roles") or []
    )
    fields = tmpl.get("fields") or tmpl.get("form_fields") or tmpl.get("signing_elements") or []
    return {
        "success": True,
        "error": None,
        "template_id": tid,
        "top_level_keys": top_level_keys,
        "signer_count": len(signers),
        "signers": signers,
        "field_count": len(fields) if isinstance(fields, list) else "(not a list)",
        "fields_sample": fields[:5] if isinstance(fields, list) else fields,
        "full_template": tmpl,  # full raw response for inspection
    }


@router.get("/admin/debug/test-stripe")
async def admin_debug_test_stripe(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Test Stripe API key by creating and cancelling a $1.00 test PaymentIntent."""
    try:
        config = await _get_runtime_config(db)
        key = config.get("STRIPE_SECRET_KEY", "").strip()
    except Exception as exc:
        return {"status": "error", "error": f"Config load failed: {exc}"}

    if not key:
        return {"status": "not_configured", "message": "Stripe API key not configured. Go to Admin Settings > Payments."}

    try:
        import stripe as stripe_lib
        stripe_lib.api_key = key

        mode = "test" if key.startswith("sk_test_") else "live"

        account_id = "sandbox"
        account_name = "Stripe Account"
        try:
            account = stripe_lib.Account.retrieve()
            account_id = account.get("id", "unknown")
            account_name = (
                account.get("settings", {}).get("dashboard", {}).get("display_name")
                or account.get("business_profile", {}).get("name")
                or account.get("email", "Stripe Account")
            )
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

        pi = stripe_lib.PaymentIntent.create(
            amount=100,
            currency="usd",
            payment_method_types=["card"],
            metadata={"test": "promechdirectory_debug"},
        )
        pi_id = pi.get("id", "unknown")

        try:
            stripe_lib.PaymentIntent.cancel(pi_id)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

        return {
            "status": "success",
            "account_id": account_id,
            "account_name": account_name,
            "mode": mode,
            "test_payment_intent_id": pi_id,
            "message": f"Stripe connected in {mode} mode.",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}



@router.get("/admin/debug/test-rfq-unlock")
async def test_rfq_unlock_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Test RFQ unlock checkout configuration without creating real payment."""
    import logging
    logger = logging.getLogger(__name__)

    results = {"steps": [], "status": "unknown", "ready": False}

    # Step 1: Check Stripe key
    try:
        cfg = await _get_runtime_config(db)
        stripe_key = cfg.get("STRIPE_SECRET_KEY", "") or ""
        if not stripe_key:
            results["steps"].append({
                "step": "stripe_key",
                "status": "FAIL",
                "message": "Stripe secret key is NOT configured in admin settings",
            })
            results["status"] = "missing_stripe_key"
            return results
        key_type = (
            "live" if stripe_key.startswith("sk_live")
            else "test" if stripe_key.startswith("sk_test")
            else "unknown_format"
        )
        results["steps"].append({
            "step": "stripe_key",
            "status": "OK",
            "message": f"Stripe key found, type: {key_type}, length: {len(stripe_key)}",
        })
    except Exception as e:
        results["steps"].append({"step": "stripe_key", "status": "ERROR", "message": str(e)})
        results["status"] = "config_error"
        return results

    # Step 2: Test Stripe connectivity
    try:
        import stripe as _stripe
        _stripe.api_key = stripe_key
        # List one customer to verify key works (read-only, no cost)
        _stripe.Customer.list(limit=1)
        results["steps"].append({
            "step": "stripe_connectivity",
            "status": "OK",
            "message": "Stripe API connection successful",
        })
    except Exception as e:
        results["steps"].append({
            "step": "stripe_connectivity",
            "status": "FAIL",
            "message": f"Stripe API error: {str(e)}",
        })
        results["status"] = "stripe_api_error"
        return results

    # Step 3: Check frontend URL setting
    frontend_url = getattr(settings, "FRONTEND_URL", "")
    results["steps"].append({
        "step": "frontend_url",
        "status": "OK" if frontend_url else "WARN",
        "message": f"FRONTEND_URL: {frontend_url or 'not set, will use default'}",
    })

    # Step 4: Check database access (count existing payment attempts)
    try:
        test_result = await db.execute(select(func.count()).select_from(PaymentAttempt))
        count = test_result.scalar()
        results["steps"].append({
            "step": "database_access",
            "status": "OK",
            "message": f"Database accessible, {count} existing payment attempts",
        })
    except Exception as e:
        results["steps"].append({
            "step": "database_access",
            "status": "FAIL",
            "message": f"Database error: {str(e)}",
        })

    results["status"] = "ready"
    results["ready"] = True
    return results

# ─── Data Export Endpoint ────────────────────────────────────────────────────

@router.get("/admin/data-export")
async def admin_data_export(
    export_type: str = Query(..., description="Type of data export"),
    format: str = Query("csv", description="Output format: csv or json"),
    date_from: Optional[str] = Query(None, description="ISO date filter start"),
    date_to: Optional[str] = Query(None, description="ISO date filter end"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Export platform data as CSV or JSON download.

    Supported export_type values:
      search_queries, users_basic, users_full, financial_transactions,
      rfq_analytics, provider_activity, nda_records, advertising_performance,
      audit_logs, full_platform_snapshot
    """
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename_base = f"{export_type}_{today_str}"

    def _df(col: str) -> str:
        parts = []
        if date_from:
            parts.append(f"{col} >= :df_from")
        if date_to:
            parts.append(f"{col} <= :df_to")
        return (" AND " + " AND ".join(parts)) if parts else ""

    def _dp() -> dict:
        p: dict = {}
        if date_from:
            p["df_from"] = date_from
        if date_to:
            p["df_to"] = date_to + " 23:59:59"
        return p

    def _safe(v) -> str:
        return "" if v is None else str(v)

    def _csv_resp(headers: list, rows: list, fname: str):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers)
        for row in rows:
            w.writerow([_safe(c) for c in row])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'}
        )

    def _json_resp(data, fname: str):
        content = json.dumps(data, default=str, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{fname}.json"'}
        )

    try:
        if export_type == "search_queries":
            sql = text(
                "SELECT sr.id, sr.user_id, u.email AS user_email, "
                "u.full_name AS user_full_name, u.business_name AS user_business_name, "
                "sr.ip_address, sr.raw_query_text, sr.normalized_query_text, "
                "sr.search_status, sr.llm_model, sr.embedding_model, "
                "sr.fallback_reason, sr.created_at "
                "FROM search_requests sr "
                "LEFT JOIN users u ON u.id = sr.user_id "
                "WHERE 1=1 " + _df("sr.created_at") +
                " ORDER BY sr.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","user_id","user_email","user_full_name","user_business_name","ip_address","raw_query_text",
                    "normalized_query_text","search_status","llm_model",
                    "embedding_model","fallback_reason","created_at"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "users_basic":
            sql = text(
                "SELECT u.id, u.email, u.full_name AS person_full_name, u.first_name, u.last_name, "
                "u.business_name, u.entity_type, "
                "COALESCE(u.business_name, prov.provider_firm_name) AS effective_company_name, "
                "prov.provider_firm_name, "
                "u.roles::text, u.is_super_admin, u.monthly_search_count, "
                "u.created_at, u.last_login_at, "
                "sub.subscription_type, sub.subscription_status, sub.current_period_end, "
                "COALESCE(pa.total_payments, 0), COALESCE(pa.payment_count, 0), "
                "COALESCE(nda.ndas_signed, 0) "
                "FROM users u "
                "LEFT JOIN LATERAL ( "
                "  SELECT p.firm_name AS provider_firm_name FROM provider_memberships pm "
                "  JOIN providers p ON p.id = pm.provider_id "
                "  WHERE pm.user_id = u.id ORDER BY pm.created_at DESC LIMIT 1 "
                ") prov ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT subscription_type, subscription_status, current_period_end "
                "  FROM subscriptions WHERE user_id = u.id "
                "  ORDER BY created_at DESC LIMIT 1 "
                ") sub ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT SUM(amount) AS total_payments, COUNT(*) AS payment_count "
                "  FROM payment_attempts "
                "  WHERE initiated_by_user_id = u.id AND payment_status = 'confirmed' "
                ") pa ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS ndas_signed FROM rfq_ndas "
                "  WHERE customer_user_id = u.id AND nda_status = 'fully_signed' "
                ") nda ON true "
                "WHERE 1=1 " + _df("u.created_at") +
                " ORDER BY u.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","email","person_full_name","first_name","last_name",
                    "business_name","entity_type","effective_company_name","provider_firm_name",
                    "roles","is_super_admin","monthly_search_count","created_at","last_login_at",
                    "subscription_type","subscription_status","current_period_end",
                    "total_payments","payment_count","ndas_signed"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "users_full":
            sql = text(
                "SELECT u.id, u.email, u.full_name AS person_full_name, u.first_name, u.last_name, "
                "u.business_name, u.entity_type, "
                "COALESCE(u.business_name, prov.provider_firm_name) AS effective_company_name, "
                "prov.provider_firm_name, "
                "u.roles::text, u.is_super_admin, u.monthly_search_count, "
                "u.created_at, u.last_login_at, "
                "sub.subscription_type, sub.subscription_status, sub.current_period_end, "
                "COALESCE(pa.total_payments,0), COALESCE(pa.payment_count,0), "
                "COALESCE(nda.ndas_signed,0), COALESCE(sc.search_count,0), "
                "COALESCE(rc.rfq_count,0), COALESCE(qc.quote_count,0), "
                "ls.last_search_query, ls.last_search_at "
                "FROM users u "
                "LEFT JOIN LATERAL ( "
                "  SELECT p.firm_name AS provider_firm_name FROM provider_memberships pm "
                "  JOIN providers p ON p.id = pm.provider_id "
                "  WHERE pm.user_id = u.id ORDER BY pm.created_at DESC LIMIT 1 "
                ") prov ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT subscription_type, subscription_status, current_period_end "
                "  FROM subscriptions WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1 "
                ") sub ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT SUM(amount) AS total_payments, COUNT(*) AS payment_count "
                "  FROM payment_attempts WHERE initiated_by_user_id = u.id AND payment_status = 'confirmed' "
                ") pa ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS ndas_signed FROM rfq_ndas "
                "  WHERE customer_user_id = u.id AND nda_status = 'fully_signed' "
                ") nda ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS search_count FROM search_requests WHERE user_id = u.id "
                ") sc ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS rfq_count FROM rfqs WHERE customer_user_id = u.id "
                ") rc ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS quote_count FROM quotes q "
                "  JOIN provider_memberships pm ON pm.provider_id = q.provider_id "
                "  WHERE pm.user_id = u.id "
                ") qc ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT raw_query_text AS last_search_query, created_at AS last_search_at "
                "  FROM search_requests WHERE user_id = u.id ORDER BY created_at DESC LIMIT 1 "
                ") ls ON true "
                "WHERE 1=1 " + _df("u.created_at") +
                " ORDER BY u.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","email","person_full_name","first_name","last_name",
                    "business_name","entity_type","effective_company_name","provider_firm_name",
                    "roles","is_super_admin","monthly_search_count","created_at","last_login_at",
                    "subscription_type","subscription_status","current_period_end",
                    "total_payments","payment_count","ndas_signed",
                    "search_count","rfq_count","quote_count",
                    "last_search_query","last_search_at"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "financial_transactions":
            sql = text(
                "SELECT pa.id, pa.provider_name, pa.external_payment_id, pa.purpose, "
                "pa.related_entity_type, pa.related_entity_id, "
                "pa.amount / 100.0 AS amount, pa.currency, pa.payment_status, pa.idempotency_key, "
                "pa.initiated_by_user_id, u.email AS user_email, "
                "u.first_name AS user_first_name, u.last_name AS user_last_name, "
                "u.full_name AS user_person_full_name, u.business_name AS user_business_name, "
                "u.entity_type AS user_entity_type, "
                "pa.initiated_at, pa.confirmed_at, pa.failed_at, "
                "sub.subscription_type "
                "FROM payment_attempts pa "
                "LEFT JOIN users u ON u.id = pa.initiated_by_user_id "
                "LEFT JOIN LATERAL ( "
                "  SELECT subscription_type FROM subscriptions "
                "  WHERE user_id = pa.initiated_by_user_id ORDER BY created_at DESC LIMIT 1 "
                ") sub ON true "
                "WHERE 1=1 " + _df("pa.initiated_at") +
                " ORDER BY pa.initiated_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","provider_name","external_payment_id","purpose",
                    "related_entity_type","related_entity_id",
                    "amount","currency","payment_status","idempotency_key",
                    "initiated_by_user_id","user_email","user_first_name","user_last_name",
                    "user_person_full_name","user_business_name","user_entity_type",
                    "initiated_at","confirmed_at","failed_at","subscription_type"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "rfq_analytics":
            sql = text(
                "SELECT r.id, r.customer_user_id, r.customer_email, "
                "r.business_name AS rfq_business_name, r.contact_name AS rfq_contact_person, "
                "r.urgency, r.nda_required, r.rfq_status, "
                "r.quote_count, r.is_closed, r.selected_provider_id, "
                "r.submitted_at, r.closed_at, r.created_at, "
                "COALESCE(db_.dispatch_count,0), "
                "COALESCE(dp_.total_providers_contacted,0), "
                "COALESCE(qr.quotes_received,0), "
                "acct.account_first_name, acct.account_last_name, "
                "acct.account_person_full_name, acct.account_business_name, acct.account_entity_type "
                "FROM rfqs r "
                "LEFT JOIN LATERAL ( "
                "  SELECT first_name AS account_first_name, last_name AS account_last_name, "
                "  full_name AS account_person_full_name, business_name AS account_business_name, "
                "  entity_type AS account_entity_type FROM users WHERE id = r.customer_user_id "
                ") acct ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS dispatch_count FROM rfq_dispatch_batches WHERE rfq_id = r.id "
                ") db_ ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS total_providers_contacted FROM rfq_provider_dispatches WHERE rfq_id = r.id "
                ") dp_ ON true "
                "LEFT JOIN LATERAL ( "
                "  SELECT COUNT(*) AS quotes_received FROM quotes "
                "  WHERE rfq_id = r.id AND quote_status != 'draft' "
                ") qr ON true "
                "WHERE 1=1 " + _df("r.created_at") +
                " ORDER BY r.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","customer_user_id","customer_email",
                    "rfq_business_name","rfq_contact_person",
                    "urgency","nda_required","rfq_status",
                    "quote_count","is_closed","selected_provider_id",
                    "submitted_at","closed_at","created_at",
                    "dispatch_count","total_providers_contacted","quotes_received",
                    "account_first_name","account_last_name",
                    "account_person_full_name","account_business_name","account_entity_type"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)
        elif export_type == "provider_activity":
            sql = text(
                "SELECT p.id, p.name, p.firm_name, p.city, p.state, p.business_evaluation_tier AS tier, p.primary_specialty, "
                "p.is_engineering_service, sub.subscription_status, "
                "COALESCE(owner.owner_email, p.email_addresses->>0) AS firm_contact_email, "
                "owner.owner_first_name, owner.owner_last_name, "
                "claim.claim_status, COALESCE(tr.tier_requests_count,0), tr.last_tier_request_at, "
                "COALESCE(rd.rfqs_received,0), COALESCE(ru.rfqs_unlocked,0), "
                "COALESCE(qs.quotes_submitted,0), p.embedding_generated_at "
                "FROM providers p "
                "LEFT JOIN LATERAL (SELECT subscription_status FROM subscriptions "
                "  WHERE provider_id = p.id ORDER BY created_at DESC LIMIT 1) sub ON true "
                "LEFT JOIN LATERAL (SELECT u.email AS owner_email, u.first_name AS owner_first_name, "
                "  u.last_name AS owner_last_name FROM provider_memberships pm "
                "  JOIN users u ON u.id = pm.user_id "
                "  WHERE pm.provider_id = p.id AND pm.membership_role = 'owner' LIMIT 1) owner ON true "
                "LEFT JOIN LATERAL (SELECT status AS claim_status FROM provider_claim_requests "
                "  WHERE provider_id = p.id ORDER BY created_at DESC LIMIT 1) claim ON true "
                "LEFT JOIN LATERAL (SELECT COUNT(*) AS tier_requests_count, MAX(created_at) AS last_tier_request_at "
                "  FROM tier_evaluation_requests WHERE provider_id = p.id) tr ON true "
                "LEFT JOIN LATERAL (SELECT COUNT(*) AS rfqs_received "
                "  FROM rfq_provider_dispatches WHERE provider_id = p.id) rd ON true "
                "LEFT JOIN LATERAL (SELECT COUNT(*) AS rfqs_unlocked FROM rfq_unlocks "
                "  WHERE provider_id = p.id AND unlock_status = 'unlocked') ru ON true "
                "LEFT JOIN LATERAL (SELECT COUNT(*) AS quotes_submitted "
                "  FROM quotes WHERE provider_id = p.id) qs ON true "
                "WHERE 1=1 ORDER BY p.name"
            )
            rows = (await db.execute(sql)).fetchall()
            cols = ["id","name","firm_name","city","state","tier","primary_specialty",
                    "is_engineering_service","subscription_status",
                    "firm_contact_email","owner_first_name","owner_last_name",
                    "claim_status","tier_requests_count","last_tier_request_at",
                    "rfqs_received","rfqs_unlocked","quotes_submitted","embedding_generated_at"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "nda_records":
            sql = text(
                "SELECT n.id, n.rfq_id, n.provider_id, n.customer_user_id, n.nda_status, "
                "u.email AS customer_email, u.first_name AS customer_first_name, "
                "u.last_name AS customer_last_name, u.full_name AS customer_person_full_name, "
                "u.business_name AS customer_business_name, u.entity_type AS customer_entity_type, "
                "p.name AS provider_name, p.firm_name AS provider_firm_name, "
                "owner.owner_email AS provider_owner_email, "
                "owner.owner_first_name AS provider_owner_first_name, "
                "owner.owner_last_name AS provider_owner_last_name, "
                "rfq.contact_name AS rfq_contact_person, rfq.business_name AS rfq_business_name, "
                "n.signrequest_document_id, n.customer_signed_at, "
                "n.provider_signed_at, n.fully_signed_at, n.created_at "
                "FROM rfq_ndas n "
                "LEFT JOIN users u ON u.id = n.customer_user_id "
                "LEFT JOIN providers p ON p.id = n.provider_id "
                "LEFT JOIN rfqs rfq ON rfq.id = n.rfq_id "
                "LEFT JOIN LATERAL (SELECT u2.email AS owner_email, u2.first_name AS owner_first_name, "
                "  u2.last_name AS owner_last_name FROM provider_memberships pm2 "
                "  JOIN users u2 ON u2.id = pm2.user_id "
                "  WHERE pm2.provider_id = p.id AND pm2.membership_role = 'owner' LIMIT 1) owner ON true "
                "WHERE 1=1 " + _df("n.created_at") + " ORDER BY n.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","rfq_id","provider_id","customer_user_id","nda_status",
                    "customer_email","customer_first_name","customer_last_name",
                    "customer_person_full_name","customer_business_name","customer_entity_type",
                    "provider_name","provider_firm_name",
                    "provider_owner_email","provider_owner_first_name","provider_owner_last_name",
                    "rfq_contact_person","rfq_business_name",
                    "signrequest_document_id",
                    "customer_signed_at","provider_signed_at","fully_signed_at","created_at"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "advertising_performance":
            sql = text(
                "SELECT a.id, a.ad_slot_id, sl.slot_name, sl.page_type, "
                "u.email AS advertiser_email, u.first_name AS advertiser_first_name, "
                "u.last_name AS advertiser_last_name, u.full_name AS advertiser_person_full_name, "
                "u.business_name AS advertiser_business_name, u.entity_type AS advertiser_entity_type, "
                "a.title, a.promotional_text, a.outbound_url, "
                "a.ad_status, a.started_at, a.ended_at, a.created_at, "
                "50 AS monthly_cost, "
                "EXTRACT(DAY FROM (COALESCE(a.ended_at, NOW()) - a.started_at))::int AS days_active "
                "FROM advertisements a "
                "LEFT JOIN ad_slots sl ON sl.id = a.ad_slot_id "
                "LEFT JOIN users u ON u.id = a.advertiser_user_id "
                "WHERE 1=1 " + _df("a.created_at") + " ORDER BY a.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","ad_slot_id","slot_name","page_type",
                    "advertiser_email","advertiser_first_name","advertiser_last_name",
                    "advertiser_person_full_name","advertiser_business_name","advertiser_entity_type",
                    "title","promotional_text","outbound_url","ad_status",
                    "started_at","ended_at","created_at","monthly_cost","days_active"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)

        elif export_type == "audit_logs":
            sql = text(
                "SELECT al.id, u.email AS actor_email, al.entity_type, al.entity_id, "
                "al.action, al.before_state::text, al.after_state::text, al.metadata::text, al.created_at "
                "FROM audit_logs al "
                "LEFT JOIN users u ON u.id = al.actor_user_id "
                "WHERE 1=1 " + _df("al.created_at") + " ORDER BY al.created_at DESC"
            )
            rows = (await db.execute(sql, _dp())).fetchall()
            cols = ["id","actor_email","entity_type","entity_id",
                    "action","before_state","after_state","metadata","created_at"]
            if format == "json":
                return _json_resp([dict(zip(cols, r)) for r in rows], filename_base)
            return _csv_resp(cols, rows, filename_base)
        elif export_type == "full_platform_snapshot":
            async def _scalar(q: str):
                return (await db.execute(text(q))).scalar() or 0

            now = datetime.utcnow()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            month_q = "SELECT COUNT(*) FROM search_requests WHERE created_at >= '" + month_start + "'"

            roles_rows = (await db.execute(text(
                "SELECT jsonb_array_elements_text(roles::jsonb) AS role, COUNT(*) FROM users GROUP BY role"
            ))).fetchall()
            users_by_role = {str(r[0]): r[1] for r in roles_rows}

            sub_rows = (await db.execute(text(
                "SELECT subscription_type, COUNT(*) FROM subscriptions "
                "WHERE subscription_status = 'active' GROUP BY subscription_type"
            ))).fetchall()
            users_by_sub = {str(r[0]): r[1] for r in sub_rows}

            tq_rows = (await db.execute(text(
                "SELECT raw_query_text, COUNT(*) AS cnt FROM search_requests "
                "WHERE raw_query_text IS NOT NULL "
                "GROUP BY raw_query_text ORDER BY cnt DESC LIMIT 10"
            ))).fetchall()
            top_queries = [r[0] for r in tq_rows]

            rfq_rows = (await db.execute(text(
                "SELECT rfq_status::text, COUNT(*) FROM rfqs GROUP BY rfq_status"
            ))).fetchall()
            rfqs_by_status = {str(r[0]): r[1] for r in rfq_rows}

            tier_rows = (await db.execute(text(
                "SELECT business_evaluation_tier AS tier, COUNT(*) FROM providers GROUP BY business_evaluation_tier"
            ))).fetchall()
            providers_by_tier = {str(r[0]): r[1] for r in tier_rows}

            rev_rows = (await db.execute(text(
                "SELECT purpose, SUM(amount) FROM payment_attempts "
                "WHERE payment_status = 'confirmed' GROUP BY purpose"
            ))).fetchall()
            revenue_by_purpose = {str(r[0]): float(r[1]) for r in rev_rows}

            nda_rows = (await db.execute(text(
                "SELECT nda_status::text, COUNT(*) FROM rfq_ndas GROUP BY nda_status"
            ))).fetchall()
            ndas_by_status = {str(r[0]): r[1] for r in nda_rows}

            ads_rows = (await db.execute(text(
                "SELECT ad_status::text, COUNT(*) FROM advertisements GROUP BY ad_status"
            ))).fetchall()
            ads_by_status = {str(r[0]): r[1] for r in ads_rows}

            total_rev_row = (await db.execute(text(
                "SELECT COALESCE(SUM(amount),0) FROM payment_attempts WHERE payment_status = 'confirmed'"
            ))).scalar()

            snapshot = {
                "generated_at": now.isoformat(),
                "total_users": await _scalar("SELECT COUNT(*) FROM users"),
                "users_by_role": users_by_role,
                "users_by_subscription": users_by_sub,
                "total_searches": await _scalar("SELECT COUNT(*) FROM search_requests"),
                "searches_this_month": await _scalar(month_q),
                "top_queries": top_queries,
                "total_rfqs": await _scalar("SELECT COUNT(*) FROM rfqs"),
                "rfqs_by_status": rfqs_by_status,
                "total_providers": await _scalar("SELECT COUNT(*) FROM providers"),
                "providers_by_tier": providers_by_tier,
                "providers_with_embeddings": await _scalar("SELECT COUNT(*) FROM providers WHERE embedding IS NOT NULL"),
                "total_revenue": float(total_rev_row or 0),
                "revenue_by_purpose": revenue_by_purpose,
                "total_ndas": await _scalar("SELECT COUNT(*) FROM rfq_ndas"),
                "ndas_by_status": ndas_by_status,
                "total_ads": await _scalar("SELECT COUNT(*) FROM advertisements"),
                "ads_by_status": ads_by_status,
            }
            return _json_resp(snapshot, filename_base)

        else:
            raise HTTPException(status_code=400, detail=f"Unknown export_type: {export_type}")

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}\n{tb}")


@router.get("/admin/debug/test-paypal")
async def test_paypal_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Test PayPal API connectivity using stored credentials."""
    import httpx
    from app.services.config_service import get_runtime_config
    cfg = await get_runtime_config(db)
    client_id = cfg.get("PAYPAL_CLIENT_ID", "")
    client_secret = cfg.get("PAYPAL_CLIENT_SECRET", "")
    mode = cfg.get("PAYPAL_MODE", "sandbox")
    if not client_id or not client_secret:
        return {"success": False, "mode": mode,
                "error": "PayPal credentials not configured"}
    base_url = ("https://api-m.sandbox.paypal.com" if mode == "sandbox"
                else "https://api-m.paypal.com")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{base_url}/v1/oauth2/token",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            token_data = r.json()
        return {
            "success": True, "mode": mode,
            "app_id": token_data.get("app_id", ""),
            "token_type": token_data.get("token_type", ""),
            "scope_preview": token_data.get("scope", "")[:120],
        }
    except httpx.HTTPStatusError as e:
        return {"success": False, "mode": mode,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "mode": mode, "error": str(e)}


@router.post("/admin/debug/test-llm")
async def admin_debug_test_llm(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    """Test DeepInfra LLM connectivity using the same client as search."""
    from app.services.search_service import _get_client, _has_api_key, _llm_model
    try:
        cfg = await _get_runtime_config(db)
        if not _has_api_key(cfg):
            return {"success": False, "error": "No API key configured (OPENAI_API_KEY)",
                    "model": None, "response": None}
        model = _llm_model(cfg)
        prompt = body.get("prompt", "Reply with exactly 2 sentences about mechanical engineering.")
        client = _get_client(cfg)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            
            temperature=0.3,
        )
        # Handle reasoning models (like Kimi-K2.5) that may return content in different fields
        reply = None
        if response.choices:
            msg = response.choices[0].message
            # Try standard content first
            content = getattr(msg, 'content', None)
            if content and content.strip():
                reply = content.strip()
            else:
                # Try reasoning_content for reasoning models
                reasoning = getattr(msg, 'reasoning_content', None)
                if reasoning and reasoning.strip():
                    reply = f"[Reasoning model output]:\n{reasoning.strip()}"
                else:
                    reply = f"(model returned empty content - raw: {repr(content)})"
        else:
            reply = "(no choices in response)"
        return {
            "success": True,
            "model": model,
            "prompt": prompt,
            "response": reply,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e), "model": None, "response": None}



@router.post("/admin/debug/test-doc-llm")
async def admin_debug_test_doc_llm(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    """Test Document Collapse LLM (LLM3) connectivity using its configured API key and model."""
    from openai import AsyncOpenAI
    try:
        cfg = await _get_runtime_config(db)
        # Use DOC_LLM config, fall back to main LLM config
        api_key = cfg.get('DOC_LLM_API_KEY') or cfg.get('OPENAI_API_KEY')
        api_base = cfg.get('DOC_LLM_API_BASE') or cfg.get('OPENAI_API_BASE')
        model = cfg.get('DOC_LLM_MODEL') or cfg.get('LLM_MODEL') or 'mistralai/Mistral-7B-Instruct-v0.2'

        if not api_key:
            return {"success": False, "error": "No API key configured for Document Collapse LLM (LLM3). Set DOC_LLM_API_KEY in admin settings.",
                    "model": model, "response": None}

        prompt = body.get('prompt', 'Summarise the following engineering document in two sentences.')
        client = AsyncOpenAI(api_key=api_key, base_url=api_base or None)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        reply = None
        if response.choices:
            msg = response.choices[0].message
            content_val = getattr(msg, 'content', None)
            if content_val and content_val.strip():
                reply = content_val.strip()
            else:
                reasoning = getattr(msg, 'reasoning_content', None)
                if reasoning and reasoning.strip():
                    reply = f"[Reasoning model output]:\n{reasoning.strip()}"
                else:
                    reply = f"(model returned empty content - raw: {repr(content_val)})"
        else:
            reply = "(no choices in response)"
        return {
            "success": True,
            "model": model,
            "api_base": api_base or "(default OpenAI)",
            "prompt": prompt,
            "response": reply,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e), "model": None, "response": None}


@router.post("/admin/debug/test-chat-llm")
async def admin_debug_test_chat_llm(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    """Test Chatbot LLM (LLM4) connectivity. Falls back to LLM3 then LLM1 config."""
    from openai import AsyncOpenAI
    try:
        cfg = await _get_runtime_config(db)
        api_key = cfg.get('CHAT_LLM_API_KEY') or cfg.get('DOC_LLM_API_KEY') or cfg.get('OPENAI_API_KEY')
        api_base = cfg.get('CHAT_LLM_API_BASE') or cfg.get('DOC_LLM_API_BASE') or cfg.get('OPENAI_API_BASE')
        model = (cfg.get('CHAT_LLM_MODEL') or cfg.get('DOC_LLM_MODEL')
                 or cfg.get('OPENAI_LLM_MODEL') or 'gpt-4o-mini')
        if not api_key:
            return {"success": False, "error": "No API key configured for Chatbot LLM (LLM4). Set CHAT_LLM_API_KEY in admin settings.",
                    "model": model, "response": None}
        prompt = body.get('prompt', 'Reply with a one-sentence friendly greeting for a help chatbot.')
        client = AsyncOpenAI(api_key=api_key, base_url=api_base or None)
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        reply = None
        if response.choices:
            msg = response.choices[0].message
            content_val = getattr(msg, 'content', None)
            if content_val and content_val.strip():
                reply = content_val.strip()
            else:
                reasoning = getattr(msg, 'reasoning_content', None)
                reply = (f"[Reasoning model output]:\n{reasoning.strip()}" if reasoning and reasoning.strip()
                         else f"(model returned empty content - raw: {repr(content_val)})")
        else:
            reply = "(no choices in response)"
        return {
            "success": True,
            "model": model,
            "api_base": api_base or "(default OpenAI)",
            "prompt": prompt,
            "response": reply,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                "completion_tokens": response.usage.completion_tokens if response.usage else None,
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e), "model": None, "response": None}

# ---------------------------------------------------------------------------
# Admin Extract: RFQ Dispatches
# ---------------------------------------------------------------------------

@router.get("/admin/extract/rfq-dispatches")
async def admin_extract_rfq_dispatches(
    rfq_id: Optional[str] = Query(None, description="Filter by specific RFQ UUID"),
    limit: int = Query(200, description="Max records to return"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
) -> List[Dict[str, Any]]:
    """Export all RFQ dispatch records joined with RFQ and provider details."""
    try:
        from app.models.rfq import RFQDispatchBatch
        stmt = (
            select(
                RFQDispatch.id,
                RFQDispatch.rfq_id,
                RFQDispatch.provider_id,
                RFQDispatch.email_target,
                RFQDispatch.dispatch_status,
                RFQDispatch.teaser_email_sent_at,
                RFQ.project_description,
                RFQ.urgency,
                RFQ.rfq_status,
                RFQ.created_at.label("rfq_created_at"),
                Provider.firm_name,
                RFQDispatchBatch.batch_number,
            )
            .join(RFQ, RFQDispatch.rfq_id == RFQ.id)
            .join(Provider, RFQDispatch.provider_id == Provider.id)
            .outerjoin(RFQDispatchBatch, RFQDispatch.batch_id == RFQDispatchBatch.id)
            .order_by(RFQDispatch.teaser_email_sent_at.desc().nullslast())
            .limit(limit)
        )
        if rfq_id:
            import uuid as _uuid
            stmt = stmt.where(RFQDispatch.rfq_id == _uuid.UUID(rfq_id))

        result = await db.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "id": str(row["id"]),
                "rfq_id": str(row["rfq_id"]),
                "provider_id": str(row["provider_id"]),
                "provider_name": row["firm_name"] or "",
                "email_target": row["email_target"] or "",
                "dispatch_status": str(row["dispatch_status"]) if row["dispatch_status"] else "",
                "teaser_email_sent_at": row["teaser_email_sent_at"].isoformat() if row["teaser_email_sent_at"] else None,
                "project_description": (row["project_description"] or "")[:200],
                "urgency": str(row["urgency"]) if row["urgency"] else "",
                "rfq_status": str(row["rfq_status"]) if row["rfq_status"] else "",
                "rfq_created_at": row["rfq_created_at"].isoformat() if row["rfq_created_at"] else None,
                "batch_number": row["batch_number"] if row["batch_number"] is not None else "",
            }
            for row in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extract failed: {str(exc)}")

@router.post("/admin/debug/test-s3")
async def admin_debug_test_s3(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Test S3 upload and download using runtime DB configuration.

    Uploads a small test file, generates a presigned URL, then deletes it.
    Returns detailed success/failure information to diagnose S3 configuration issues.
    """
    if "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=403, detail="Admin only")

    from app.services.config_service import get_runtime_config
    import boto3 as _boto3
    from botocore.config import Config as _BotoConfig
    from botocore.exceptions import ClientError as _ClientError
    import uuid as _uuid

    config = await get_runtime_config(db)

    aws_access_key = config.get("AWS_ACCESS_KEY_ID") or ""
    aws_secret_key = config.get("AWS_SECRET_ACCESS_KEY") or ""
    aws_region = config.get("AWS_REGION") or "us-east-1"
    bucket_name = config.get("AWS_S3_BUCKET") or ""

    result = {
        "aws_access_key_configured": bool(aws_access_key),
        "aws_secret_key_configured": bool(aws_secret_key),
        "aws_region": aws_region,
        "bucket_name": bucket_name,
        "bucket_configured": bool(bucket_name),
        "upload_success": False,
        "download_url_success": False,
        "delete_success": False,
        "error": None,
        "download_url": None,
        "test_key": None,
    }

    if not aws_access_key or not aws_secret_key or not bucket_name:
        result["error"] = (
            "AWS S3 is not fully configured. "
            f"Missing: {'Access Key ' if not aws_access_key else ''}"
            f"{'Secret Key ' if not aws_secret_key else ''}"
            f"{'Bucket Name' if not bucket_name else ''}. "
            "Please configure these in Admin Settings > AWS S3 Storage."
        )
        return result

    test_key = f"s3-test/{_uuid.uuid4()}/test.txt"
    result["test_key"] = test_key
    test_data = b"ProReadyEngineer S3 test file. Safe to delete."

    try:
        s3 = _boto3.client(
            "s3",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
            config=_BotoConfig(signature_version="s3v4"),
        )

        # Test 1: Upload
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_data,
            ContentType="text/plain",
        )
        result["upload_success"] = True

        # Test 2: Generate presigned download URL
        download_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": test_key},
            ExpiresIn=300,
        )
        result["download_url_success"] = True
        result["download_url"] = download_url

        # Test 3: Delete test file
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        result["delete_success"] = True

    except _ClientError as ce:
        error_code = ce.response.get("Error", {}).get("Code", "Unknown")
        error_msg = ce.response.get("Error", {}).get("Message", str(ce))
        result["error"] = f"AWS Error [{error_code}]: {error_msg}"
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"

    return result


# ─── Admin Provider Add/Delete Endpoints (PART 6) ───────────────────────────

class AdminProviderCreateRequest(_BaseModel):
    """Body for admin-created provider record."""
    firm_name: str
    name: str
    business_description: Optional[str] = None
    primary_specialty: Optional[str] = None
    secondary_specialties: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[List[str]] = None
    email_addresses: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    equipment: Optional[List[str]] = None
    proven_experience_notable_projects: Optional[List[str]] = None
    proven_experience_case_studies: Optional[List[str]] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    team_summary: Optional[str] = None



@router.get("/admin/providers")
async def admin_list_providers(
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: List providers with optional search and pagination.

    Search matches any of: provider name, firm name, city, primary specialty,
    one of the firm's public contact emails (JSON `email_addresses`),
    the email of a linked user account (via provider_memberships), or the
    email the original ownership invite was sent to (`invite_email`).
    """
    from sqlalchemy import select, func, or_, cast, String
    from app.models.provider import Provider, ProviderMembership
    from app.models.user import User

    offset = (page - 1) * limit
    query = select(Provider)
    count_query = select(func.count(Provider.id.distinct()))

    if search:
        # Sub-select for any provider id whose membership user (or invite_email)
        # matches the search term. Done as a subquery so we don't duplicate
        # provider rows when a firm has multiple members.
        membership_email_match = (
            select(ProviderMembership.provider_id)
            .join(User, User.id == ProviderMembership.user_id, isouter=True)
            .where(or_(
                User.email.ilike(f"%{search}%"),
                ProviderMembership.invite_email.ilike(f"%{search}%"),
            ))
        )
        search_filter = or_(
            Provider.name.ilike(f"%{search}%"),
            Provider.firm_name.ilike(f"%{search}%"),
            Provider.city.ilike(f"%{search}%"),
            Provider.primary_specialty.ilike(f"%{search}%"),
            # email_addresses is a JSON list — cast to text for ilike. This
            # produces matches like %"alice@example.com"% which is exactly
            # what we want.
            cast(Provider.email_addresses, String).ilike(f"%{search}%"),
            Provider.id.in_(membership_email_match),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Provider.name).offset(offset).limit(limit))
    providers = result.scalars().all()

    return {
        "providers": [
            {
                "id": str(p.id),
                "name": p.name,
                "firm_name": p.firm_name,
                "city": p.city,
                "state": p.state,
                "business_evaluation_tier": p.business_evaluation_tier,
                "primary_specialty": p.primary_specialty,
                "is_engineering_service": p.is_engineering_service,
                "user_email": (p.email_addresses[0] if isinstance(p.email_addresses, list) and p.email_addresses else p.email_addresses if isinstance(p.email_addresses, str) else None),
                "website": p.website,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in providers
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/admin/providers", status_code=201)
async def admin_create_provider(
    data: AdminProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Create a new provider record and queue embedding generation."""
    import logging
    _log = logging.getLogger(__name__)

    try:
        from app.core.celery import celery_app
    except Exception:
        _cadmin = None

    provider = Provider(
        firm_name=data.firm_name,
        name=data.name,
        business_description=data.business_description,
        primary_specialty=data.primary_specialty,
        secondary_specialties=data.secondary_specialties,
        capabilities=data.capabilities,
        specialties=data.specialties,
        software_tools=data.software_tools,
        notable_clients="\n".join(data.notable_clients) if data.notable_clients else None,
        email_addresses=data.email_addresses,
        certifications=data.certifications,
        equipment=data.equipment,
        proven_experience_notable_projects=data.proven_experience_notable_projects,
        proven_experience_case_studies=data.proven_experience_case_studies,
        website=data.website,
        phone=data.phone,
        address=data.address,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        team_summary=data.team_summary,
        is_engineering_service=1,
        is_mechanical_focus=1,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    _log.info("Admin created provider id=%s name=%s", provider.id, provider.name)

    await generate_provider_embedding_async(str(provider.id))
    _log.info("Embedding queued in background for provider %s", provider.id)

    return {"id": str(provider.id), "name": provider.name, "firm_name": provider.firm_name, "message": "Provider created successfully"}


@router.delete("/admin/providers/{provider_id}")
async def admin_delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Delete a provider record and all associated memberships and claim requests."""
    import logging
    _log = logging.getLogger(__name__)

    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Explicitly delete associated provider_memberships
    memberships_result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.provider_id == provider_id)
    )
    for membership in memberships_result.scalars().all():
        await db.delete(membership)

    # Explicitly delete associated provider_claim_requests
    claims_result = await db.execute(
        select(ProviderClaimRequest).where(ProviderClaimRequest.provider_id == provider_id)
    )
    for claim in claims_result.scalars().all():
        await db.delete(claim)

    await db.delete(provider)
    await db.commit()

    _log.info("Admin deleted provider id=%s", provider_id)
    return {"message": "Provider deleted", "provider_id": str(provider_id)}


@router.get("/admin/providers/{provider_id}")
async def admin_get_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Get full provider details for editing."""
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderResponse.from_orm(provider)


class AdminProviderUpdateRequest(_BaseModel):
    firm_name: Optional[str] = None
    name: Optional[str] = None
    business_description: Optional[str] = None
    primary_specialty: Optional[str] = None
    secondary_specialties: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    software_tools: Optional[List[str]] = None
    notable_clients: Optional[str] = None
    email_addresses: Optional[List[str]] = None
    certifications: Optional[List[str]] = None
    equipment: Optional[List[str]] = None
    proven_experience_notable_projects: Optional[List[str]] = None
    proven_experience_case_studies: Optional[List[str]] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    team_summary: Optional[str] = None


_ADMIN_EMBEDDING_FIELDS = {
    'firm_name', 'name', 'primary_specialty', 'business_description',
    'capabilities', 'specialties', 'software_tools',
    'proven_experience_notable_projects',
}


@router.patch("/admin/providers/{provider_id}")
async def admin_update_provider(
    provider_id: int,
    data: AdminProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin: Update provider fields and trigger embedding regeneration if needed."""
    import logging
    _log = logging.getLogger(__name__)

    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Capture before state for audit log
    before_state = {
        field: getattr(provider, field, None)
        for field in data.dict(exclude_unset=True).keys()
    }

    updated_fields = data.dict(exclude_unset=True)
    embedding_changed = False
    for field, value in updated_fields.items():
        setattr(provider, field, value)
        if field in _ADMIN_EMBEDDING_FIELDS:
            embedding_changed = True

    await db.commit()

    # Audit log entry
    after_state = {
        field: getattr(provider, field, None)
        for field in updated_fields.keys()
    }
    audit_entry = AuditLog(
        actor_user_id=current_user.id,
        entity_type="provider",
        entity_id=str(provider_id),
        action="admin_update_provider",
        before_state=before_state,
        after_state=after_state,
    )
    db.add(audit_entry)
    await db.commit()

    # Re-query with eager loading
    result2 = await db.execute(
        select(Provider)
        .options(selectinload(Provider.memberships).selectinload(ProviderMembership.user))
        .where(Provider.id == provider.id)
    )
    provider = result2.scalar_one()

    if embedding_changed:
        await generate_provider_embedding_async(str(provider.id))
        _log.info("Embedding queued in background for provider %s", provider.id)

    _log.info("Admin updated provider id=%s fields=%s", provider_id, list(updated_fields.keys()))
    return ProviderResponse.from_orm(provider)



# ─── Admin Website Crawl Endpoints (synchronous - no Celery worker required) ──

class AdminCrawlWebsiteRequest(_BaseModel):
    website_url: str


async def _admin_fetch_website_text(url: str) -> str:
    """Fetch website pages using httpx with dynamic link discovery.

    Uses a real browser User-Agent so CDN/bot-protection layers (Vercel,
    Cloudflare, etc.) serve the actual HTML rather than a JS challenge page.
    The skip-tag tracker uses a counter stack so nested tags don't
    accidentally re-enable text capture mid-block.
    """
    import httpx
    import logging as _logging
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlparse

    _log = _logging.getLogger(__name__)

    # ── Real browser headers — avoids bot-detection on Vercel / Cloudflare ──
    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
    }

    # ── HTML parser: counter-based skip so nested tags don't break capture ──
    class _TextExtractor(HTMLParser):
        # Tags whose entire subtree we discard (code/style only — keep nav/footer)
        SKIP_TAGS = frozenset(("script", "style", "head", "noscript", "iframe",
                               "svg", "canvas", "template"))

        def __init__(self):
            super().__init__()
            self._parts: list = []
            self._links: list = []
            self._skip_depth: int = 0   # counter, not bool

        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP_TAGS:
                self._skip_depth += 1
            if tag == "a":
                href = dict(attrs).get("href", "")
                if href:
                    self._links.append(href)

        def handle_endtag(self, tag):
            if tag in self.SKIP_TAGS and self._skip_depth > 0:
                self._skip_depth -= 1

        def handle_data(self, data):
            if self._skip_depth == 0 and data.strip():
                self._parts.append(data.strip())

    def _parse(html: str):
        p = _TextExtractor()
        try:
            p.feed(html)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        return " ".join(p._parts), p._links

    def _is_internal(href: str, domain: str) -> bool:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            return False
        if href.startswith("http"):
            return urlparse(href).netloc == domain
        return True

    def _norm(href: str, base: str) -> str:
        return urljoin(base, href).split("#")[0].rstrip("/")

    parsed = urlparse(url)
    domain = parsed.netloc
    base_url = url.rstrip("/")

    seed_paths = ["/about", "/about-us", "/services", "/capabilities",
                  "/projects", "/case-studies", "/portfolio", "/experience",
                  "/industries", "/our-work", "/solutions", "/team",
                  "/clients", "/technology", "/expertise", "/work",
                  "/contact", "/home", "/products", "/features"]

    collected: list = []
    visited: set = set()
    to_visit: list = [url] + [base_url + p for p in seed_paths]
    MAX_PAGES = 25

    async with httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=15.0,
        follow_redirects=True,
        verify=False,
    ) as client:
        while to_visit and len(visited) < MAX_PAGES:
            page_url = _norm(to_visit.pop(0), url)
            if page_url in visited:
                continue
            visited.add(page_url)
            try:
                resp = await client.get(page_url)
                ct = resp.headers.get("content-type", "")
                _log.info(
                    "Crawl %s → status=%d ct=%s bytes=%d",
                    page_url, resp.status_code, ct[:40], len(resp.content),
                )
                if resp.status_code != 200 or "text/html" not in ct:
                    continue
                text, links = _parse(resp.text)
                text = text.strip()
                if len(text) > 20:            # lowered from 50 → catch short pages
                    collected.append(f"[Page: {page_url}]\n{text}")
                for href in links:
                    if _is_internal(href, domain):
                        abs_url = _norm(href, page_url)
                        if abs_url not in visited and abs_url not in to_visit:
                            to_visit.append(abs_url)
            except Exception as exc:
                _log.warning("Crawl error %s: %s", page_url, exc)

    result = "\n\n".join(collected)[:100000]
    _log.info("Crawl complete domain=%s pages=%d total_chars=%d", domain, len(visited), len(result))
    return result




async def _admin_extract_with_llm3(raw_text: str, db: AsyncSession) -> dict:
    """Send raw website text to LLM3 and return structured provider fields."""
    import json
    from app.services.config_service import get_runtime_config
    from openai import AsyncOpenAI

    cfg = await get_runtime_config(db)
    api_key = cfg.get('DOC_LLM_API_KEY') or cfg.get('OPENAI_API_KEY')
    api_base = (cfg.get('DOC_LLM_API_BASE') or cfg.get('OPENAI_API_BASE')
                or 'https://api.openai.com/v1')
    model = cfg.get('DOC_LLM_MODEL') or cfg.get('OPENAI_LLM_MODEL') or 'gpt-4o'

    prompt = (
        "You are extracting structured data from an engineering firm website.\n\n"
        "Website content:\n" + raw_text + "\n\n"
        "Return a JSON object with ONLY these exact keys (null if not found):\n"
        "{\n"
        '  "firm_name": "Legal firm name",\n'
        '  "name": "Display/trade name",\n'
        '  "business_description": "2-4 sentence description of services",\n'
        '  "primary_specialty": "Single primary engineering specialty",\n'
        '  "secondary_specialties": ["list of secondary specialties"],\n'
        '  "capabilities": ["list of specific engineering capabilities"],\n'
        '  "specialties": ["list of specialties"],\n'
        '  "software_tools": ["list of software tools used"],\n'
        '  "proven_experience_notable_projects": ["For each project/case study found write EXACTLY ONE sentence: (1) what engineering service was performed (2) the method/approach used (3) the outcome/purpose. Be factual and technical. One array item per project."],\n'
        '  "proven_experience_case_studies": ["case study summaries if separate from projects"],\n'
        '  "website": "firm website URL",\n'
        '  "phone": "primary phone number",\n'
        '  "email_addresses": ["email@addresses.com"],\n'
        '  "address": "street address",\n'
        '  "city": "city",\n'
        '  "state": "2-letter state abbreviation e.g. OH",\n'
        '  "postal_code": "postal code",\n'
        '  "certifications": ["list of certifications e.g. ISO 9001"],\n'
        '  "notable_clients": ["list of notable clients"],\n'
        '  "equipment": ["list of key equipment"],\n'
        '  "team_members": ["Name - Title format for key team members"],\n'
        '  "team_summary": "1-2 sentence team description",\n'
        '  "projects": "general project portfolio description"\n'
        "}\n\n"
        "Return ONLY valid JSON. No markdown. No explanation."
    )

    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    resp = await client.chat.completions.create(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        response_format={'type': 'json_object'},
        temperature=0.1,
    )
    return json.loads(resp.choices[0].message.content)


@router.post('/admin/crawl-website')
async def admin_crawl_website(
    data: AdminCrawlWebsiteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
):
    """Admin: Crawl a firm website and extract profile fields via LLM3.
    Runs fully synchronously in-process — no Celery worker required.
    Returns extracted data directly in the response.
    """
    import logging
    _log = logging.getLogger(__name__)

    url = data.website_url.strip()
    if not url.startswith('http'):
        url = 'https://' + url

    _log.info('Admin crawl started url=%s user=%s', url, current_user.id)

    try:
        raw_text = await _admin_fetch_website_text(url)
    except Exception as exc:
        _log.error('Admin crawl fetch error url=%s err=%s', url, exc)
        raise HTTPException(status_code=422,
                            detail=f'Could not fetch website: {exc}')

    if not raw_text or not raw_text.strip():
        raise HTTPException(
            status_code=422,
            detail='No content could be extracted from the website. Check the URL and try again.')

    try:
        extracted = await _admin_extract_with_llm3(raw_text, db)
    except Exception as exc:
        _log.error('Admin crawl LLM error url=%s err=%s', url, exc)
        raise HTTPException(status_code=422,
                            detail=f'LLM extraction failed: {exc}')

    _log.info('Admin crawl done url=%s fields=%s', url, list(extracted.keys()))
    return {'status': 'done', 'data': extracted}


@router.get('/admin/crawl-status/{task_id}')
async def admin_crawl_status(
    task_id: str,
    current_user: User = Depends(require_role(['admin'])),
):
    """Deprecated: crawl is now synchronous. Kept for compatibility."""
    return {'status': 'done', 'data': None}




# ---------------------------------------------------------------------------
# Payment Analytics Endpoints
# ---------------------------------------------------------------------------

@router.get('/admin/payments/production-window')
async def get_payments_production_window(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Return the 'Production' revenue cutoff timestamp (null if never set)."""
    from app.services.config_service import get_config_value
    val = await get_config_value(db, 'PAYMENTS_PRODUCTION_SINCE')
    return {"since": val or None}


@router.post('/admin/payments/production-window')
async def set_payments_production_window(
    reset: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Stamp the 'Production' cutoff to now (set once = the go-live marker; reset=true re-stamps)."""
    from app.services.config_service import get_config_value, save_config_values
    existing = await get_config_value(db, 'PAYMENTS_PRODUCTION_SINCE')
    if existing and not reset:
        return {"since": existing}
    now_iso = datetime.utcnow().isoformat()
    await save_config_values(db, {'PAYMENTS_PRODUCTION_SINCE': now_iso}, current_user.id)
    return {"since": now_iso}


@router.get('/admin/founding-invites')
async def get_founding_invites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Admin: current founding-provider invitation counter."""
    from app.services.config_service import get_config_value
    raw_limit = await get_config_value(db, 'FOUNDING_INVITE_LIMIT')
    raw_sent = await get_config_value(db, 'FOUNDING_INVITE_SENT')
    try:
        limit = int(raw_limit) if raw_limit is not None else 50
    except (TypeError, ValueError):
        limit = 50
    try:
        sent = int(raw_sent) if raw_sent is not None else 0
    except (TypeError, ValueError):
        sent = 0
    sent = max(0, sent)
    remaining = max(0, limit - sent)
    return {"limit": limit, "sent": sent, "remaining": remaining, "closed": remaining <= 0}


@router.post('/admin/founding-invites')
async def set_founding_invites(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Admin: adjust the founding-provider invitation counter.

    Body keys (all optional): limit (int total invitations), sent (int used),
    reset (bool -> sent back to 0). Lets an admin raise the cap or re-open the
    offer after all invitations have been used.
    """
    from app.services.config_service import save_config_values, get_config_value
    updates: Dict[str, str] = {}
    if 'limit' in body and body['limit'] is not None:
        try:
            updates['FOUNDING_INVITE_LIMIT'] = str(max(0, int(body['limit'])))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit must be an integer")
    if body.get('reset'):
        updates['FOUNDING_INVITE_SENT'] = '0'
    elif 'sent' in body and body['sent'] is not None:
        try:
            updates['FOUNDING_INVITE_SENT'] = str(max(0, int(body['sent'])))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="sent must be an integer")
    if updates:
        await save_config_values(db, updates, current_user.id)
    raw_limit = updates.get('FOUNDING_INVITE_LIMIT') or await get_config_value(db, 'FOUNDING_INVITE_LIMIT')
    raw_sent = updates.get('FOUNDING_INVITE_SENT')
    if raw_sent is None:
        raw_sent = await get_config_value(db, 'FOUNDING_INVITE_SENT')
    try:
        limit = int(raw_limit) if raw_limit is not None else 50
    except (TypeError, ValueError):
        limit = 50
    try:
        sent = int(raw_sent) if raw_sent is not None else 0
    except (TypeError, ValueError):
        sent = 0
    remaining = max(0, limit - sent)
    return {"limit": limit, "sent": sent, "remaining": remaining, "closed": remaining <= 0}


@router.get('/admin/payments/analytics')
async def admin_payment_analytics(
    since: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Aggregated payment analytics. When `since` (ISO) is given (Production view), only
    payments initiated at/after it are counted, so pre-launch / test data is excluded."""
    from datetime import timedelta
    from sqlalchemy import and_, true as _sa_true

    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00')).replace(tzinfo=None)
        except (ValueError, AttributeError):
            since_dt = None
    _sc = (PaymentAttempt.initiated_at >= since_dt) if since_dt is not None else _sa_true()

    async def _sum(*conds) -> float:
        try:
            r = await db.execute(
                select(func.coalesce(func.sum(PaymentAttempt.amount), 0)).where(and_(*conds, _sc))
            )
            return float(r.scalar() or 0) / 100.0
        except Exception:
            return 0.0

    async def _count(*conds) -> int:
        try:
            r = await db.execute(
                select(func.count()).select_from(PaymentAttempt).where(and_(*conds, _sc))
            )
            return int(r.scalar() or 0)
        except Exception:
            return 0

    _ok = PaymentAttempt.payment_status.notin_(['failed', 'refunded', 'disputed'])
    total_revenue = await _sum(_ok)
    total_this_month = await _sum(_ok, PaymentAttempt.initiated_at >= first_of_month)
    total_pending = await _sum(PaymentAttempt.payment_status.in_(['initiated', 'processing']))
    total_failed_30d = await _count(PaymentAttempt.payment_status == 'failed',
                                    PaymentAttempt.initiated_at >= thirty_days_ago)
    total_refunded = await _sum(PaymentAttempt.payment_status == 'refunded')

    monthly_series: List[Dict[str, Any]] = []
    try:
        for i in range(5, -1, -1):
            month_offset = now.month - i
            year_offset = now.year
            while month_offset <= 0:
                month_offset += 12
                year_offset -= 1
            m_start = datetime(year_offset, month_offset, 1)
            if month_offset == 12:
                m_end = datetime(year_offset + 1, 1, 1)
            else:
                m_end = datetime(year_offset, month_offset + 1, 1)
            rev = await _sum(_ok, PaymentAttempt.initiated_at >= m_start,
                             PaymentAttempt.initiated_at < m_end)
            monthly_series.append({'month': m_start.strftime('%Y-%m'), 'revenue': rev})
    except Exception:
        monthly_series = []

    async def _by(status_cond) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            r = await db.execute(
                select(
                    PaymentAttempt.purpose,
                    func.coalesce(func.sum(PaymentAttempt.amount), 0).label('total'),
                    func.count().label('cnt'),
                )
                .where(and_(status_cond, _sc))
                .group_by(PaymentAttempt.purpose)
                .order_by(func.sum(PaymentAttempt.amount).desc())
            )
            for row in r.fetchall():
                out.append({'purpose': str(row.purpose), 'total': float(row.total) / 100.0, 'count': int(row.cnt)})
        except Exception:
            out = []
        return out

    by_purpose = await _by(PaymentAttempt.payment_status == 'completed')
    by_purpose_all = await _by(_ok)

    return {
        'total_revenue': total_revenue,
        'total_this_month': total_this_month,
        'total_pending': total_pending,
        'total_failed_30d': total_failed_30d,
        'total_refunded': total_refunded,
        'monthly_series': monthly_series,
        'by_purpose': by_purpose,
        'by_purpose_all': by_purpose_all,
    }


@router.get('/admin/payments/transactions')
async def admin_payment_transactions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    purpose: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Any:
    """Paginated payment transactions with optional filters. Supports CSV export."""
    from sqlalchemy import and_

    filters = []
    if since:
        try:
            filters.append(PaymentAttempt.initiated_at >= datetime.fromisoformat(since.replace('Z', '+00:00')).replace(tzinfo=None))
        except (ValueError, AttributeError):
            pass
    if purpose:
        filters.append(PaymentAttempt.purpose == purpose)
    if status:
        filters.append(PaymentAttempt.payment_status == status)
    if date_from:
        try:
            filters.append(PaymentAttempt.initiated_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            filters.append(PaymentAttempt.initiated_at <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    base_q = (
        select(PaymentAttempt, User.email.label('user_email'), User.full_name.label('user_name'))
        .outerjoin(User, PaymentAttempt.initiated_by_user_id == User.id)
    )
    if filters:
        base_q = base_q.where(and_(*filters))

    count_q = select(func.count()).select_from(PaymentAttempt)
    if filters:
        count_q = count_q.where(and_(*filters))

    total_res = await db.execute(count_q)
    total = int(total_res.scalar() or 0)

    ordered_q = base_q.order_by(PaymentAttempt.initiated_at.desc())

    if format == 'csv':
        all_res = await db.execute(ordered_q)
        rows = all_res.fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['id', 'date', 'purpose', 'amount', 'currency', 'status',
                         'provider', 'user_email', 'user_name', 'external_payment_id'])
        for row in rows:
            pa = row[0]
            writer.writerow([
                str(pa.id),
                pa.initiated_at.isoformat() if pa.initiated_at else '',
                str(pa.purpose),
                str(float(pa.amount) / 100.0),
                pa.currency,
                str(pa.payment_status),
                pa.provider_name,
                row.user_email or '',
                row.user_name or '',
                pa.external_payment_id or '',
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="payments.csv"'},
        )

    offset = (page - 1) * per_page
    paged_res = await db.execute(ordered_q.offset(offset).limit(per_page))
    rows = paged_res.fetchall()

    items = []
    for row in rows:
        pa = row[0]
        items.append({
            'id': str(pa.id),
            'initiated_at': pa.initiated_at.isoformat() if pa.initiated_at else None,
            'confirmed_at': pa.confirmed_at.isoformat() if pa.confirmed_at else None,
            'failed_at': pa.failed_at.isoformat() if pa.failed_at else None,
            'purpose': str(pa.purpose),
            'amount': float(pa.amount) / 100.0,
            'currency': pa.currency,
            'payment_status': str(pa.payment_status),
            'provider_name': pa.provider_name,
            'external_payment_id': pa.external_payment_id,
            'external_checkout_id': pa.external_checkout_id,
            'related_entity_type': pa.related_entity_type,
            'related_entity_id': str(pa.related_entity_id) if pa.related_entity_id else None,
            'user_email': row.user_email,
            'user_name': row.user_name,
        })

    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page),
    }


@router.get('/admin/spend/openai')
async def admin_spend_openai(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Fetch OpenAI credit balance and current month usage."""
    from app.services.config_service import get_runtime_config as _grc
    from datetime import date, timedelta

    cfg = await _grc(db)
    api_key = cfg.get('OPENAI_API_KEY') or cfg.get('DOC_LLM_API_KEY')
    if not api_key:
        return {'available': False, 'error': 'No OPENAI_API_KEY configured'}

    headers = {'Authorization': f'Bearer {api_key}'}
    now_date = date.today()
    start_date = now_date.replace(day=1).strftime('%Y-%m-%d')
    end_date = now_date.strftime('%Y-%m-%d')

    result: Dict[str, Any] = {'available': True}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            sub_resp = await client.get(
                'https://api.openai.com/v1/dashboard/billing/subscription',
                headers=headers,
            )
            if sub_resp.status_code == 200:
                sub_data = sub_resp.json()
                result['hard_limit_usd'] = sub_data.get('hard_limit_usd')
                result['soft_limit_usd'] = sub_data.get('soft_limit_usd')
        except Exception as exc:
            result['subscription_error'] = str(exc)

        try:
            usage_resp = await client.get(
                f'https://api.openai.com/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}',
                headers=headers,
            )
            if usage_resp.status_code == 200:
                usage_data = usage_resp.json()
                total_usage_cents = usage_data.get('total_usage', 0)
                result['current_month_usd'] = round(float(total_usage_cents) / 100, 4)
                result['source'] = 'billing_api'
            elif usage_resp.status_code in (404, 410):
                import time as _time
                start_epoch = int(datetime(now_date.year, now_date.month, 1).timestamp())
                end_epoch = int(datetime.utcnow().timestamp())
                org_resp = await client.get(
                    f'https://api.openai.com/v1/organization/usage/completions?start_time={start_epoch}&end_time={end_epoch}',
                    headers=headers,
                )
                if org_resp.status_code == 200:
                    org_data = org_resp.json()
                    total_tokens = 0
                    for bucket in org_data.get('data', []):
                        for item in bucket.get('results', []):
                            total_tokens += item.get('input_tokens', 0)
                            total_tokens += item.get('output_tokens', 0)
                    result['total_tokens_this_month'] = total_tokens
                    result['source'] = 'organization_usage_api'
                    result['current_month_usd'] = None
                else:
                    result['usage_error'] = f'org usage api returned {org_resp.status_code}'
            else:
                result['usage_error'] = f'billing usage returned {usage_resp.status_code}'
        except Exception as exc:
            result['usage_error'] = str(exc)

    return result




@router.get('/admin/spend/llms')
async def admin_spend_llms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Check LLM2 and LLM3 connectivity. Returns status for both LLMs without
    relying on deprecated billing APIs that require admin session keys."""
    from app.services.config_service import get_runtime_config as _grc
    cfg = await _grc(db)

    async def _check_llm(api_key: str, api_base: str, model: str, label: str) -> Dict[str, Any]:
        if not api_key:
            return {'label': label, 'available': False, 'error': 'No API key configured', 'model': model}
        base = (api_base or 'https://api.openai.com/v1').rstrip('/')
        headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                # Use a minimal chat completion to test - works on all OpenAI-compatible providers
                c_resp = await client.post(
                    f'{base}/chat/completions',
                    headers=headers,
                    json={'model': model, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 1}
                )
                if c_resp.status_code == 200:
                    return {'label': label, 'available': True, 'model': model, 'base_url': base, 'status': 'Connected'}
                elif c_resp.status_code == 401:
                    return {'label': label, 'available': False, 'error': 'Invalid API key', 'model': model}
                elif c_resp.status_code == 404:
                    return {'label': label, 'available': False, 'error': f'Model not found: {model}', 'model': model}
                else:
                    try:
                        err_detail = c_resp.json().get('error', {}).get('message', f'HTTP {c_resp.status_code}')
                    except Exception:
                        err_detail = f'HTTP {c_resp.status_code}'
                    return {'label': label, 'available': False, 'error': err_detail, 'model': model}
            except Exception as exc:
                return {'label': label, 'available': False, 'error': str(exc), 'model': model}

    llm2_key = cfg.get('OPENAI_API_KEY', '')
    llm2_base = cfg.get('OPENAI_API_BASE', 'https://api.openai.com/v1')
    llm2_model = cfg.get('OPENAI_LLM_MODEL', '')

    llm3_key = cfg.get('DOC_LLM_API_KEY', '')
    llm3_base = cfg.get('DOC_LLM_API_BASE', '')
    llm3_model = cfg.get('DOC_LLM_MODEL', '')

    llm2_result = await _check_llm(llm2_key, llm2_base, llm2_model, 'LLM 2 — Firm Ranking')
    # If LLM3 key is same as LLM2 key, skip separate check
    if llm3_key and llm3_key != llm2_key:
        llm3_result = await _check_llm(llm3_key, llm3_base or llm2_base, llm3_model or llm2_model, 'LLM 3 — Document Collapse')
        # If LLM3 uses OpenRouter, also fetch billing/usage data
        effective_base = (llm3_base or llm2_base or '').lower()
        if 'openrouter.ai' in effective_base:
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    key_resp = await client.get(
                        'https://openrouter.ai/api/v1/key',
                        headers={'Authorization': f'Bearer {llm3_key}'}
                    )
                    if key_resp.status_code == 200:
                        kdata = key_resp.json().get('data', {})
                        llm3_result['usage_total_usd'] = kdata.get('usage')
                        llm3_result['usage_daily_usd'] = kdata.get('usage_daily')
                        llm3_result['usage_monthly_usd'] = kdata.get('usage_monthly')
                        llm3_result['limit_remaining_usd'] = kdata.get('limit_remaining')
                        llm3_result['billing_source'] = 'openrouter'
                    else:
                        llm3_result['billing_error'] = f'OpenRouter key API returned {key_resp.status_code}'
                except Exception as bill_exc:
                    llm3_result['billing_error'] = str(bill_exc)
    elif llm3_key == llm2_key and llm3_key:
        llm3_result = dict(llm2_result)
        llm3_result['label'] = 'LLM 3 — Document Collapse'
        llm3_result['model'] = llm3_model or llm2_model
        llm3_result['note'] = 'Same key as LLM 2'
    else:
        llm3_result = {'label': 'LLM 3 — Document Collapse', 'available': False, 'error': 'No DOC_LLM_API_KEY configured', 'model': llm3_model}

    # LLM4 - Chatbot Assistant (CHAT_LLM_*, falls back to DOC_LLM then OPENAI)
    llm4_key = cfg.get('CHAT_LLM_API_KEY', '') or llm3_key or llm2_key
    llm4_base = cfg.get('CHAT_LLM_API_BASE', '') or llm3_base or llm2_base
    llm4_model = cfg.get('CHAT_LLM_MODEL', '') or llm3_model or llm2_model
    if cfg.get('CHAT_LLM_API_KEY', '') and cfg.get('CHAT_LLM_API_KEY', '') not in (llm2_key, llm3_key):
        llm4_result = await _check_llm(llm4_key, llm4_base, llm4_model, 'LLM 4 - Chatbot Assistant')
    elif llm4_key:
        llm4_result = {'label': 'LLM 4 - Chatbot Assistant', 'available': bool(llm4_key),
                       'model': llm4_model, 'status': 'Connected (shared key)',
                       'note': 'Falls back to LLM3/LLM1 - no dedicated CHAT_LLM key set'}
    else:
        llm4_result = {'label': 'LLM 4 - Chatbot Assistant', 'available': False,
                       'error': 'No CHAT_LLM_API_KEY (and no fallback) configured', 'model': llm4_model}

    return {'llm2': llm2_result, 'llm3': llm3_result, 'llm4': llm4_result}


@router.get('/admin/spend/aws')
async def admin_spend_aws(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Fetch AWS Cost Explorer data for the current month."""
    from app.services.config_service import get_runtime_config as _grc
    import os

    cfg = await _grc(db)
    aws_key = cfg.get('AWS_ACCESS_KEY_ID') or os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret = cfg.get('AWS_SECRET_ACCESS_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')

    if not aws_key or not aws_secret:
        return {'available': False, 'error': 'No AWS credentials configured'}

    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError
        from datetime import date

        now_date = date.today()
        first_of_month = now_date.replace(day=1).strftime('%Y-%m-%d')
        today_str = now_date.strftime('%Y-%m-%d')
        if today_str == first_of_month:
            return {'available': True, 'total_this_month': 0.0, 'services': [], 'note': 'First day of month'}

        client = boto3.client(
            'ce',
            region_name='us-east-1',
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
        )
        response = client.get_cost_and_usage(
            TimePeriod={'Start': first_of_month, 'End': today_str},
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}],
        )

        services = []
        total = 0.0
        results = response.get('ResultsByTime', [])
        if results:
            groups = results[0].get('Groups', [])
            for g in groups:
                svc = g['Keys'][0]
                amt = float(g['Metrics']['UnblendedCost']['Amount'])
                if amt > 0:
                    services.append({'service': svc, 'amount': round(amt, 4)})
                    total += amt
            services.sort(key=lambda x: x['amount'], reverse=True)

        return {
            'available': True,
            'total_this_month': round(total, 4),
            'services': services[:5],
            'period_start': first_of_month,
            'period_end': today_str,
        }

    except Exception as exc:
        return {'available': False, 'error': str(exc)}


@router.get('/admin/spend/render')
async def admin_spend_render(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Fetch Render services list and optional budget from runtime config."""
    from app.services.config_service import get_runtime_config as _grc

    cfg = await _grc(db)
    render_key = cfg.get('RENDER_API_KEY')
    if not render_key:
        return {'available': False, 'error': 'No RENDER_API_KEY configured'}

    manual_budget_raw = cfg.get('RENDER_MONTHLY_BUDGET')
    manual_budget: Optional[float] = None
    if manual_budget_raw:
        try:
            manual_budget = float(manual_budget_raw)
        except (ValueError, TypeError):
            pass

    headers = {'Authorization': f'Bearer {render_key}', 'Accept': 'application/json'}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get('https://api.render.com/v1/services', headers=headers)
            if resp.status_code != 200:
                return {'available': False, 'error': f'Render API returned {resp.status_code}'}

            data = resp.json()
            services = []
            for item in data:
                svc = item.get('service', item)
                services.append({
                    'id': svc.get('id'),
                    'name': svc.get('name'),
                    'type': svc.get('type'),
                    'status': svc.get('suspended', 'not_suspended'),
                    'service_details': svc.get('serviceDetails', {}),
                    'updated_at': svc.get('updatedAt'),
                    'created_at': svc.get('createdAt'),
                })

        return {
            'available': True,
            'services': services,
            'manual_budget': manual_budget,
        }

    except Exception as exc:
        return {'available': False, 'error': str(exc)}


@router.get('/admin/bandwidth')
async def admin_bandwidth(
    window_hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Performance & capacity panel ("Bandwidth").

    Pulls CPU, memory, HTTP request volume and latency from the Render Metrics API for
    the web + API services over a trailing window, summarizes/trends them, and emits a
    plain-language scale recommendation grounded in utilization vs. the current plan.
    """
    import time as _time
    from app.services.config_service import get_runtime_config as _grc
    from app.services.capacity_advisor import (
        parse_series, summarize, trend_pct, recommend, RENDER_PLANS, _plan_index,
    )

    cfg = await _grc(db)
    render_key = cfg.get('RENDER_API_KEY')
    if not render_key:
        return {'available': False, 'error': 'No RENDER_API_KEY configured. Add it in Settings to enable performance monitoring.'}

    try:
        window_hours = max(1, min(int(window_hours or 24), 168))  # clamp 1h..7d
    except (ValueError, TypeError):
        window_hours = 24
    end_t = int(_time.time())
    start_t = end_t - window_hours * 3600
    resolution = 300 if window_hours <= 24 else 900  # 5m for <=1d, 15m otherwise
    headers = {'Authorization': f'Bearer {render_key}', 'Accept': 'application/json'}
    base = 'https://api.render.com/v1'

    async def _metric(client, path, resource):
        params = {'resource': resource, 'startTime': start_t, 'endTime': end_t,
                  'resolutionSeconds': resolution, 'aggregationMethod': 'AVG'}
        try:
            r = await client.get(f'{base}/metrics/{path}', headers=headers, params=params)
            if r.status_code == 200:
                return parse_series(r.json())
        except Exception as exc:
            logger.info('[bandwidth] metric %s failed for %s: %s', path, resource, exc)
        return []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # 1) Discover the web + API services and their plans.
            svc_resp = await client.get(f'{base}/services?limit=50', headers=headers)
            if svc_resp.status_code != 200:
                return {'available': False, 'error': f'Render API returned {svc_resp.status_code} for services list'}
            # Only this product's own services — the Render account may host unrelated
            # software. Allowlist by name (override via BANDWIDTH_SERVICES = comma list).
            _allow_raw = (cfg.get('BANDWIDTH_SERVICES') or 'proreadyengineer-api,proreadyengineer-web')
            _allow = {n.strip().lower() for n in _allow_raw.split(',') if n.strip()}
            services = []
            for item in svc_resp.json():
                svc = item.get('service', item)
                if svc.get('type') not in ('web_service', 'web', 'private_service'):
                    continue
                if (svc.get('name') or '').strip().lower() not in _allow:
                    continue
                services.append({
                    'id': svc.get('id'),
                    'name': svc.get('name'),
                    'plan': (svc.get('serviceDetails', {}) or {}).get('plan'),
                })

            results = []
            for svc in services:
                rid = svc['id']
                cpu = await _metric(client, 'cpu', rid)
                mem = await _metric(client, 'memory', rid)
                reqs = await _metric(client, 'http_requests', rid)
                lat = await _metric(client, 'http_latency', rid)

                plan_entry = RENDER_PLANS[_plan_index(svc.get('plan'))]
                cpu_cap = plan_entry['cpu']            # vCPU
                ram_cap_bytes = plan_entry['ram_gb'] * (1024 ** 3)

                cpu_sum = summarize(cpu)        # values are vCPU-seconds/sec ~ cores used
                mem_sum = summarize(mem)        # bytes
                req_sum = summarize(reqs)       # requests in each bucket
                lat_sum = summarize(lat)        # ms (or s) latency

                # Utilization % of the instance's capacity (peak-based for headroom).
                cpu_peak_pct = round((cpu_sum['peak'] / cpu_cap) * 100, 1) if cpu_sum['peak'] is not None and cpu_cap else None
                mem_peak_pct = round((mem_sum['peak'] / ram_cap_bytes) * 100, 1) if mem_sum['peak'] is not None and ram_cap_bytes else None
                cpu_tr = trend_pct(cpu)

                rec = recommend(cpu_peak_pct, mem_peak_pct, cpu_tr, svc.get('plan'))

                results.append({
                    'service': svc['name'],
                    'plan': svc.get('plan'),
                    'plan_cpu': cpu_cap,
                    'plan_ram_gb': plan_entry['ram_gb'],
                    'cpu': {**cpu_sum, 'peak_pct': cpu_peak_pct, 'trend_pct': cpu_tr},
                    'memory': {**mem_sum, 'peak_pct': mem_peak_pct,
                               'peak_gb': round(mem_sum['peak'] / (1024 ** 3), 3) if mem_sum['peak'] is not None else None},
                    'http_requests': req_sum,
                    'latency_ms': lat_sum,
                    'recommendation': rec,
                })

        # Roll up a single worst-case headline recommendation across services.
        order = {'scale_now': 3, 'watch': 2, 'healthy': 1, 'unknown': 0}
        overall = max((r['recommendation'] for r in results),
                      key=lambda rec: order.get(rec.get('status'), 0), default=None)
        return {
            'available': True,
            'window_hours': window_hours,
            'resolution_seconds': resolution,
            'services': results,
            'overall': overall,
            'plans': RENDER_PLANS,
            'notes': ('CPU/memory utilization is peak-based (worst case in the window) to preserve '
                      'headroom for spikes. Recommendations consider current plan capacity and the '
                      'load trend. Render metrics require a paid instance.'),
        }
    except Exception as exc:
        return {'available': False, 'error': str(exc)}


@router.get('/admin/operating-cost')
async def admin_operating_cost(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(['admin'])),
) -> Dict[str, Any]:
    """Transparent operating-cost breakdown: LLM spend (by model, from real tokens where
    available), Stripe processing fees, Render hosting, and config-driven other monthly
    line items. Each figure is labelled 'actual' (measured) or 'estimate'.

    Prices come from the live cost catalog (admin-editable LLM_PRICING) with static fallback.
    """
    from datetime import datetime, timezone
    from app.services.config_service import get_runtime_config
    from app.services.cost_catalog import cost_for_tokens, price_for_model
    from app.models.help_chat import HelpChatLog
    from app.models.search import SearchRequest as _SearchReq

    cfg = await get_runtime_config(db)
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    llm_rows = []  # per-model cost rows

    # --- 1) Chatbot LLM (LLM3/LLM4): REAL tokens + cost from help_chat_logs ---
    try:
        rows = (await db.execute(
            select(
                HelpChatLog.model,
                func.coalesce(func.sum(HelpChatLog.prompt_tokens), 0),
                func.coalesce(func.sum(HelpChatLog.completion_tokens), 0),
                func.coalesce(func.sum(HelpChatLog.cost_usd), 0.0),
                func.count(),
            ).where(HelpChatLog.created_at >= month_start, HelpChatLog.model.isnot(None))
             .group_by(HelpChatLog.model)
        )).all()
        for model, pt, ct, cost, n in rows:
            # Recompute from catalog when a row's stored cost is null/zero but tokens exist.
            calc = float(cost or 0.0)
            if calc <= 0 and (int(pt or 0) + int(ct or 0)) > 0:
                calc = cost_for_tokens(model, pt, ct, cfg)
            llm_rows.append({
                "label": "Chatbot assistant", "model": model,
                "prompt_tokens": int(pt or 0), "completion_tokens": int(ct or 0),
                "calls": int(n or 0), "cost_usd": round(calc, 4), "basis": "actual",
            })
    except Exception as exc:
        logger.warning("[operating-cost] chatbot agg failed: %s", exc)

    # --- 2) Search/ranking LLM (LLM1/LLM2): ACTUAL tokens when recorded, else ESTIMATE ---
    try:
        model = cfg.get("OPENAI_LLM_MODEL") or "moonshotai/Kimi-K2.5"
        agg = (await db.execute(
            select(
                func.coalesce(func.sum(_SearchReq.llm_prompt_tokens), 0),
                func.coalesce(func.sum(_SearchReq.llm_completion_tokens), 0),
                func.coalesce(func.sum(_SearchReq.llm_cost_usd), 0.0),
                func.count(),
            ).where(_SearchReq.created_at >= month_start)
        )).first()
        sum_pt, sum_ct, sum_cost, n_search = int(agg[0] or 0), int(agg[1] or 0), float(agg[2] or 0.0), int(agg[3] or 0)
        if (sum_pt + sum_ct) > 0:
            # Real tokens were recorded -> actual.
            cost = sum_cost if sum_cost > 0 else cost_for_tokens(model, sum_pt, sum_ct, cfg)
            llm_rows.append({
                "label": "Search & ranking", "model": model,
                "prompt_tokens": sum_pt, "completion_tokens": sum_ct,
                "calls": n_search, "cost_usd": round(cost, 4), "basis": "actual",
            })
        elif n_search:
            # No tokens recorded yet (older rows) -> conservative estimate.
            AVG_IN, AVG_OUT = 1200, 300
            est = cost_for_tokens(model, AVG_IN * n_search, AVG_OUT * n_search, cfg)
            llm_rows.append({
                "label": "Search & ranking", "model": model,
                "prompt_tokens": AVG_IN * n_search, "completion_tokens": AVG_OUT * n_search,
                "calls": n_search, "cost_usd": round(est, 4), "basis": "estimate",
            })
    except Exception as exc:
        logger.warning("[operating-cost] search agg failed: %s", exc)

    llm_total = round(sum(r["cost_usd"] for r in llm_rows), 4)

    other_rows = []  # non-LLM monthly costs

    # --- 3) Stripe processing fees (ESTIMATE): 2.9% + $0.30 per completed payment this month ---
    try:
        pay_rows = (await db.execute(
            select(func.coalesce(func.sum(PaymentAttempt.amount), 0), func.count())
            .where(PaymentAttempt.payment_status == "completed",
                   PaymentAttempt.created_at >= month_start)
        )).first()
        gross = float(pay_rows[0] or 0.0)
        n_pay = int(pay_rows[1] or 0)
        stripe_fee = round(gross * 0.029 + 0.30 * n_pay, 2)
        other_rows.append({
            "label": "Stripe processing fees", "detail": f"{n_pay} payments, ${gross:,.2f} gross",
            "cost_usd": stripe_fee, "basis": "estimate",
        })
    except Exception as exc:
        logger.warning("[operating-cost] stripe agg failed: %s", exc)

    # --- 4) Render hosting (manual budget from config, if set) ---
    rb = cfg.get("RENDER_MONTHLY_BUDGET")
    if rb:
        try:
            other_rows.append({"label": "Render hosting", "detail": "from RENDER_MONTHLY_BUDGET",
                               "cost_usd": round(float(rb), 2), "basis": "manual"})
        except (ValueError, TypeError):
            pass

    # --- 5) Other fixed/usage monthly costs from config (admin-editable JSON) ---
    # OPERATING_COST_ITEMS = [{"label": "...", "cost_usd": 12.5}, ...]
    raw_items = cfg.get("OPERATING_COST_ITEMS")
    if raw_items:
        try:
            items = json.loads(raw_items) if isinstance(raw_items, str) else raw_items
            for it in (items or []):
                if isinstance(it, dict) and "cost_usd" in it:
                    other_rows.append({
                        "label": str(it.get("label", "Other"))[:80],
                        "detail": str(it.get("detail", ""))[:120],
                        "cost_usd": round(float(it["cost_usd"]), 2), "basis": "manual",
                    })
        except Exception as exc:
            logger.info("[operating-cost] bad OPERATING_COST_ITEMS: %s", exc)

    # Reminder list of services that bill but may not be auto-tracked here.
    untracked = [
        s for s, present in [
            ("AWS S3 (storage/egress)", bool(cfg.get("AWS_ACCESS_KEY_ID"))),
            ("Resend (email)", bool(cfg.get("RESEND_API_KEY"))),
            ("SignWell (e-signature)", bool(cfg.get("SIGNWELL_API_KEY"))),
            ("DeepInfra / Gemini API base", bool(cfg.get("OPENAI_API_KEY"))),
        ] if present
    ]

    other_total = round(sum(r["cost_usd"] for r in other_rows), 2)
    grand_total = round(llm_total + other_total, 2)

    return {
        "month": now.strftime("%Y-%m"),
        "llm": {"rows": llm_rows, "total_usd": llm_total},
        "other": {"rows": other_rows, "total_usd": other_total},
        "grand_total_usd": grand_total,
        "untracked_services": untracked,
        "notes": (
            "LLM chatbot costs are actual (measured from token usage). Search/ranking and "
            "Stripe fees are estimates. Prices are read from the live catalog (edit LLM_PRICING "
            "in Settings) with static fallback. Add fixed monthly costs via OPERATING_COST_ITEMS."
        ),
    }


# ---------------------------------------------------------------------------
# Admin: Reconcile Stripe Initiated Payments
# ---------------------------------------------------------------------------

class _ReconcileRequest(_BaseModel):
    dry_run: bool = False
    limit: int = 100  # max sessions to check per run

@router.post("/admin/payments/reconcile-stripe")
async def admin_reconcile_stripe_payments(
    body: _ReconcileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Reconcile payment_attempts stuck at 'initiated' by cross-referencing Stripe API.
    Runs Stripe API calls in parallel (asyncio.gather) with a per-call timeout.
    Processes at most `limit` records per call to prevent Cloudflare 30-second timeout.
    """
    import asyncio as _asyncio
    import logging
    import stripe as _stripe
    from app.services.payment_service import _handle_checkout_session_completed
    from app.models.payment import PaymentStatus
    from app.services.config_service import get_runtime_config as _grc

    dry_run: bool = body.dry_run
    limit: int = max(1, min(body.limit, 100))  # cap at 100 for parallel safety
    _log = logging.getLogger(__name__)

    cfg = await _grc(db)
    stripe_key = cfg.get("STRIPE_SECRET_KEY") or ""
    if not stripe_key:
        raise HTTPException(
            status_code=400,
            detail="STRIPE_SECRET_KEY not configured in admin settings. Go to Admin → System Configuration → Payments tab.",
        )

    _stripe.api_key = stripe_key

    # Find initiated Stripe checkout session payment attempts (limited batch)
    result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.provider_name == "stripe",
            PaymentAttempt.payment_status == PaymentStatus.INITIATED,
            PaymentAttempt.external_payment_id.like("cs_%"),
        ).order_by(PaymentAttempt.initiated_at.desc()).limit(limit)
    )
    initiated_payments = result.scalars().all()

    report: Dict[str, Any] = {
        "dry_run": dry_run,
        "total_checked": len(initiated_payments),
        "paid_found": 0,
        "fulfilled": 0,
        "already_complete": 0,
        "stripe_errors": 0,
        "fulfill_errors": 0,
        "details": [],
    }

    if not initiated_payments:
        return report

    async def _check_one(pa: PaymentAttempt) -> Dict[str, Any]:
        """Check one payment attempt against Stripe with a hard 10-second timeout."""
        entry: Dict[str, Any] = {
            "payment_id": str(pa.id),
            "stripe_session_id": str(pa.external_payment_id or ""),
            "purpose": str(pa.purpose.value) if hasattr(pa.purpose, "value") else str(pa.purpose),
            "amount_usd": float(pa.amount or 0) / 100.0,
            "initiated_at": pa.initiated_at.isoformat() if pa.initiated_at else None,
            "action": None,
            "error": None,
            "stripe_payment_status": None,
        }
        try:
            session = await _asyncio.wait_for(
                _asyncio.to_thread(
                    lambda: _stripe.checkout.Session.retrieve(str(pa.external_payment_id or ""))
                ),
                timeout=10.0,
            )
            stripe_status = (
                session.get("payment_status", "") if isinstance(session, dict)
                else getattr(session, "payment_status", "")
            )
            entry["stripe_payment_status"] = stripe_status

            if stripe_status == "paid":
                entry["action"] = "would_fulfill" if dry_run else "pending_fulfill"
            else:
                entry["action"] = "not_paid"
        except _asyncio.TimeoutError:
            entry["action"] = "stripe_timeout"
            entry["error"] = "Stripe API timed out after 10 seconds"
        except Exception as stripe_err:
            entry["action"] = "stripe_error"
            entry["error"] = str(stripe_err)
            _log.warning("Reconcile Stripe lookup failed for %s: %s", pa.external_payment_id, stripe_err)
        return entry

    # Run all Stripe lookups in parallel
    entries = await _asyncio.gather(*[_check_one(pa) for pa in initiated_payments])

    # Now process fulfillments sequentially (DB writes need ordering)
    for i, (pa, entry) in enumerate(zip(initiated_payments, entries)):
        if entry.get("stripe_payment_status") == "paid":
            report["paid_found"] += 1
            if not dry_run:
                try:
                    session = await _asyncio.wait_for(
                        _asyncio.to_thread(
                            lambda pid=pa.external_payment_id: _stripe.checkout.Session.retrieve(str(pid or ""))
                        ),
                        timeout=10.0,
                    )
                    session_dict = session.to_dict() if hasattr(session, "to_dict") else dict(session)
                    await _handle_checkout_session_completed(db, session_dict)
                    report["fulfilled"] += 1
                    entry["action"] = "fulfilled"
                except Exception as fulfill_err:
                    report["fulfill_errors"] += 1
                    entry["action"] = "fulfill_failed"
                    entry["error"] = str(fulfill_err)
                    _log.error("Reconcile fulfill failed for %s: %s", pa.external_payment_id, fulfill_err)
        elif entry.get("action") in ("stripe_timeout", "stripe_error"):
            report["stripe_errors"] += 1

        report["details"].append(entry)

    _log.info(
        "Stripe reconciliation complete: dry_run=%s checked=%d paid=%d fulfilled=%d errors=%d",
        dry_run, report["total_checked"], report["paid_found"],
        report["fulfilled"], report["stripe_errors"],
    )
    return report


# ---------------------------------------------------------------------------
# Admin: Force-complete individual payment + Bulk resolve NDA initiated
# ---------------------------------------------------------------------------

class _ForceCompleteRequest(_BaseModel):
    reason: str = "Admin force-complete: payment verified in Stripe dashboard"

@router.post("/admin/payments/{payment_id}/force-complete")
async def admin_force_complete_payment(
    payment_id: str,
    body: _ForceCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Force-complete a single payment_attempt and trigger fulfillment.
    Use when admin has verified payment was received in Stripe/PayPal dashboard.
    Creates an audit log entry recording the override.
    """
    from app.services.payment_service import _fulfill_nda_fee, _fulfill_rfq_unlock
    import uuid as _uuid

    try:
        pa_uuid = _uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment_id format")

    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == pa_uuid))
    pa = result.scalar_one_or_none()
    if not pa:
        raise HTTPException(status_code=404, detail="Payment attempt not found")

    if pa.payment_status == PaymentStatus.COMPLETED:
        return {"status": "already_completed", "payment_id": payment_id}

    # Mark as completed
    pa.payment_status = PaymentStatus.COMPLETED
    pa.confirmed_at = datetime.utcnow()
    await db.flush()

    # Trigger fulfillment based on purpose
    fulfillment_result = "no_fulfillment_needed"
    fulfillment_error = None
    try:
        if pa.purpose == "nda_fee" and pa.related_entity_id:
            rfq_uuid = _uuid.UUID(str(pa.related_entity_id))
            await _fulfill_nda_fee(db, rfq_uuid)
            fulfillment_result = "nda_fee_fulfilled"
        elif pa.purpose == "rfq_unlock" and pa.related_entity_id:
            await _fulfill_rfq_unlock(db, pa.related_entity_id, pa.id)
            fulfillment_result = "rfq_unlock_fulfilled"
    except Exception as fe:
        fulfillment_error = str(fe)
        fulfillment_result = "fulfillment_failed"

    # Audit log
    try:
        audit = AuditLog(
            actor_user_id=current_user.id,
            entity_type="payment_attempt",
            entity_id=str(pa.id),
            action="force_complete",
            before_state={"payment_status": "initiated"},
            after_state={"payment_status": "completed"},
            metadata={"reason": body.reason, "fulfillment": fulfillment_result},
        )
        db.add(audit)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    await db.commit()
    await db.commit()
    return {
        "status": "completed",
        "payment_id": payment_id,
        "purpose": pa.purpose,
        "amount_usd": float(pa.amount or 0) / 100.0,
        "fulfillment": fulfillment_result,
        "fulfillment_error": fulfillment_error,
    }


from pydantic import BaseModel as _RefundBaseModel


class _RefundRequest(_RefundBaseModel):
    reason: str
    reverse_fulfillment: bool = True


@router.post("/admin/payments/{payment_id}/refund")
async def admin_refund_payment(
    payment_id: str,
    body: _RefundRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Issue a Stripe refund for a completed payment and optionally reverse fulfillment.

    Supports:
    - rfq_unlock  → revokes RFQUnlock record (status → refunded)
    - nda_fee     → cancels RFQNDA record (status → cancelled)
    - search_subscription → cancels Subscription record
    - provider_annual_subscription → cancels Subscription record
    Creates an audit log entry for every refund.
    """
    import logging
    import stripe as _stripe
    import uuid as _uuid

    _log = logging.getLogger(__name__)

    if not body.reason or len(body.reason.strip()) < 3:
        raise HTTPException(status_code=422, detail="A reason is required for refund audit trail")

    # ── look up payment ──────────────────────────────────────────────────
    try:
        pa_uuid = _uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment_id format")

    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == pa_uuid))
    pa = result.scalar_one_or_none()
    if not pa:
        raise HTTPException(status_code=404, detail="Payment attempt not found")

    if pa.payment_status == PaymentStatus.REFUNDED:
        return {"status": "already_refunded", "payment_id": payment_id}

    if pa.payment_status not in (PaymentStatus.COMPLETED, PaymentStatus.INITIATED, PaymentStatus.PROCESSING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refund a payment with status '{pa.payment_status}'. Only completed/initiated payments can be refunded.",
        )

    # ── call Stripe Refund API ───────────────────────────────────────────
    stripe_refund_id = None
    stripe_error = None

    # We need a Stripe payment intent ID to issue the refund
    external_pid = pa.external_payment_id  # payment_intent ID
    external_cid = pa.external_checkout_id  # checkout session ID

    if external_pid or external_cid:
        try:
            _stripe.api_key = settings.STRIPE_SECRET_KEY
            if not _stripe.api_key:
                raise HTTPException(status_code=500, detail="Stripe API key not configured")

            # If we only have checkout_session_id, retrieve the payment_intent from it
            payment_intent_id = external_pid
            if not payment_intent_id and external_cid:
                try:
                    session = _stripe.checkout.Session.retrieve(external_cid)
                    payment_intent_id = session.payment_intent
                except Exception as se:
                    _log.warning("Could not retrieve checkout session %s: %s", external_cid, se)

            if payment_intent_id:
                refund = _stripe.Refund.create(
                    payment_intent=payment_intent_id,
                    reason="requested_by_customer",
                    metadata={
                        "admin_user_id": str(current_user.id),
                        "admin_reason": body.reason[:200],
                        "payment_attempt_id": str(pa.id),
                    },
                )
                stripe_refund_id = refund.id
                _log.info("Stripe refund created: %s for payment_intent %s", refund.id, payment_intent_id)
            else:
                stripe_error = "No payment_intent found — Stripe refund skipped. Mark as refunded in records only."
                _log.warning("No payment_intent for PA %s — Stripe refund skipped", pa.id)
        except _stripe.error.InvalidRequestError as e:
            # e.g. "charge already refunded"
            stripe_error = str(e)
            _log.warning("Stripe refund API error for PA %s: %s", pa.id, e)
        except Exception as e:
            stripe_error = str(e)
            _log.error("Stripe refund failed for PA %s: %s", pa.id, e, exc_info=True)
    else:
        stripe_error = "No external Stripe IDs on this payment — record-only refund."

    # ── update payment status ────────────────────────────────────────────
    before_status = pa.payment_status
    pa.payment_status = PaymentStatus.REFUNDED
    pa.extra_data = pa.extra_data or {}
    pa.extra_data["refund"] = {
        "refunded_at": datetime.utcnow().isoformat(),
        "refunded_by": str(current_user.id),
        "reason": body.reason,
        "stripe_refund_id": stripe_refund_id,
        "stripe_error": stripe_error,
    }

    # ── reverse fulfillment ──────────────────────────────────────────────
    reversal_result = "no_reversal_requested"
    reversal_error = None

    if body.reverse_fulfillment:
        try:
            reversal_result = await _reverse_fulfillment(db, pa, _log)
        except Exception as re:
            reversal_error = str(re)
            reversal_result = "reversal_failed"
            _log.error("Fulfillment reversal failed for PA %s: %s", pa.id, re, exc_info=True)

    # ── audit log ────────────────────────────────────────────────────────
    try:
        audit = AuditLog(
            actor_user_id=current_user.id,
            entity_type="payment_attempt",
            entity_id=str(pa.id),
            action="refund",
            before_state={"payment_status": str(before_status)},
            after_state={"payment_status": "refunded"},
            metadata={
                "reason": body.reason,
                "stripe_refund_id": stripe_refund_id,
                "stripe_error": stripe_error,
                "reversal": reversal_result,
                "reversal_error": reversal_error,
                "amount_usd": float(pa.amount or 0) / 100.0,
                "purpose": pa.purpose,
            },
        )
        db.add(audit)
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    await db.commit()

    return {
        "status": "refunded",
        "payment_id": payment_id,
        "purpose": pa.purpose,
        "amount_usd": float(pa.amount or 0) / 100.0,
        "stripe_refund_id": stripe_refund_id,
        "stripe_error": stripe_error,
        "reversal": reversal_result,
        "reversal_error": reversal_error,
    }


async def _reverse_fulfillment(db: AsyncSession, pa: PaymentAttempt, _log) -> str:
    """Reverse the fulfillment action for a refunded payment.

    Returns a string describing what was reversed.
    """
    from app.models.enums import UnlockStatus as _US, NdaStatus as _NS, SubscriptionStatus as _SS
    import uuid as _uuid

    purpose = pa.purpose
    related_id = pa.related_entity_id

    # ── RFQ unlock → revoke access ───────────────────────────────────────
    if purpose == "rfq_unlock" and related_id:
        from app.models.rfq import RFQUnlock
        result = await db.execute(
            select(RFQUnlock).where(
                RFQUnlock.payment_attempt_id == pa.id,
            )
        )
        unlock = result.scalar_one_or_none()
        if not unlock:
            # Fallback: find by rfq_id + most recent unlock
            result2 = await db.execute(
                select(RFQUnlock).where(
                    RFQUnlock.rfq_id == related_id,
                    RFQUnlock.unlock_status == _US.UNLOCKED,
                ).order_by(RFQUnlock.unlocked_at.desc()).limit(1)
            )
            unlock = result2.scalar_one_or_none()

        if unlock and unlock.unlock_status == _US.UNLOCKED:
            unlock.unlock_status = _US.REFUNDED
            _log.info("RFQUnlock %s revoked (status → refunded)", unlock.id)
            return "rfq_unlock_revoked"
        elif unlock and unlock.unlock_status == _US.REFUNDED:
            return "rfq_unlock_already_revoked"
        else:
            return "rfq_unlock_not_found"

    # ── NDA fee → cancel NDA record ──────────────────────────────────────
    if purpose == "nda_fee" and related_id:
        from app.models.nda import RFQNDA
        result = await db.execute(
            select(RFQNDA).where(
                RFQNDA.rfq_id == related_id,
            ).order_by(RFQNDA.created_at.desc()).limit(1)
        )
        nda = result.scalar_one_or_none()
        if nda and nda.nda_status not in (_NS.FULLY_SIGNED, _NS.CANCELLED):
            old_status = nda.nda_status
            nda.nda_status = _NS.CANCELLED
            _log.info("RFQNDA %s cancelled (was %s) due to refund", nda.id, old_status)
            return f"nda_cancelled (was {old_status})"
        elif nda and nda.nda_status == _NS.FULLY_SIGNED:
            _log.warning("RFQNDA %s is fully_signed — cannot auto-cancel. Manual review needed.", nda.id)
            return "nda_fully_signed_manual_review_needed"
        elif nda and nda.nda_status == _NS.CANCELLED:
            return "nda_already_cancelled"
        else:
            return "nda_record_not_found"

    # ── Subscription → cancel ────────────────────────────────────────────
    if purpose in ("search_subscription", "provider_annual_subscription", "provider_profile_subscription", "advertisement_subscription"):
        from app.models.payment import Subscription
        user_id = pa.initiated_by_user_id
        if user_id:
            sub_type_map = {
                "search_subscription": "search_tier_1",
                "provider_annual_subscription": "provider_annual",
                "provider_profile_subscription": "provider_profile",
                "advertisement_subscription": "advertisement",
            }
            sub_type = sub_type_map.get(purpose)
            if sub_type:
                result = await db.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.subscription_type == sub_type,
                        Subscription.subscription_status == _SS.ACTIVE,
                    ).order_by(Subscription.current_period_start.desc()).limit(1)
                )
                sub = result.scalar_one_or_none()
                if sub:
                    sub.subscription_status = _SS.CANCELLED
                    sub.cancelled_at = datetime.utcnow()
                    _log.info("Subscription %s cancelled due to refund", sub.id)

                    # Also cancel in Stripe if external subscription ID exists
                    if sub.external_subscription_id:
                        try:
                            import stripe as _s2
                            _s2.api_key = settings.STRIPE_SECRET_KEY
                            _s2.Subscription.cancel(sub.external_subscription_id)
                            _log.info("Stripe subscription %s cancelled", sub.external_subscription_id)
                        except Exception as se:
                            _log.warning("Could not cancel Stripe subscription %s: %s", sub.external_subscription_id, se)

                    return f"subscription_{sub_type}_cancelled"
                else:
                    return f"subscription_{sub_type}_not_found_or_already_cancelled"
        return "subscription_no_user_linked"

    return f"no_reversal_logic_for_{purpose}"


@router.post("/admin/payments/bulk-resolve-nda-initiated")
async def admin_bulk_resolve_nda_initiated(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Bulk-update all NDA fee PaymentAttempts stuck at 'initiated' to 'completed'.

    Use when the NDA signing flow works end-to-end but PaymentAttempt records
    were never updated (e.g. because Stripe webhook wasn't configured).
    Does NOT require Stripe API keys — trusts that if an NDA fee was initiated
    and the NDA flow completed, the payment was successful.
    Creates an audit log entry for each update.
    """
    import logging
    _log = logging.getLogger(__name__)

    result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.purpose == "nda_fee",
            PaymentAttempt.payment_status == PaymentStatus.INITIATED,
        )
    )
    stuck_payments = result.scalars().all()

    if not stuck_payments:
        return {"status": "nothing_to_do", "updated": 0}

    updated = 0
    for pa in stuck_payments:
        pa.payment_status = PaymentStatus.COMPLETED
        pa.confirmed_at = datetime.utcnow()
        updated += 1

        # Audit log
        try:
            audit = AuditLog(
                actor_user_id=current_user.id,
                entity_type="payment_attempt",
                entity_id=str(pa.id),
                action="bulk_resolve_nda_initiated",
                before_state={"payment_status": "initiated"},
                after_state={"payment_status": "completed"},
                metadata={"reason": "Admin bulk resolve: NDA flow confirmed working, payment records retroactively updated"},
            )
            db.add(audit)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    await db.commit()
    _log.info("Bulk resolved %d NDA fee payments from initiated to completed (admin: %s)", updated, current_user.id)
    return {"status": "resolved", "updated": updated}


@router.post("/admin/payments/{payment_id}/force-fulfill-subscription")
async def admin_force_fulfill_subscription(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Force-run subscription fulfillment for a COMPLETED payment.
    Handles missing provider_id in extra_data by falling back to user's provider membership.
    Safe to call multiple times (idempotent).
    """
    import logging
    import uuid as _uuid
    from datetime import datetime, timedelta
    from app.models.payment import PaymentAttempt
    from app.models.payment import Subscription
    from app.models.enums import SubscriptionType, SubscriptionStatus
    from app.models.provider import ProviderMembership
    from app.services.payment_service import _fulfill_search_subscription, _fulfill_full_profile_edit_unlock
    _log = logging.getLogger(__name__)

    try:
        pid = _uuid.UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment_id format")

    result = await db.execute(select(PaymentAttempt).where(PaymentAttempt.id == pid))
    pa = result.scalar_one_or_none()
    if not pa:
        raise HTTPException(status_code=404, detail="Payment attempt not found")

    purpose = pa.purpose.value if hasattr(pa.purpose, "value") else str(pa.purpose)
    status_val = pa.payment_status.value if hasattr(pa.payment_status, "value") else str(pa.payment_status)

    if status_val not in ("completed", "COMPLETED"):
        raise HTTPException(
            status_code=400,
            detail=f"Payment status is '{status_val}' — only COMPLETED payments. Use Reconcile for INITIATED.",
        )

    msg = ""
    try:
        if purpose == "provider_annual_subscription":
            # Step 1: resolve provider_id from extra_data
            metadata = pa.extra_data or {}
            provider_id_str = metadata.get("provider_id")
            provider_id = None
            if provider_id_str:
                try:
                    provider_id = int(provider_id_str)
                    _log.info("force-fulfill: provider_id=%s from extra_data", provider_id)
                except (ValueError, TypeError):
                    pass

            # Step 2: fallback — look up user's provider membership
            if not provider_id and pa.initiated_by_user_id:
                mem = (await db.execute(
                    select(ProviderMembership)
                    .where(ProviderMembership.user_id == pa.initiated_by_user_id)
                    .limit(1)
                )).scalar_one_or_none()
                if mem:
                    provider_id = mem.provider_id
                    _log.info("force-fulfill: provider_id=%s from user membership (fallback)", provider_id)

            if not provider_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot determine provider_id: extra_data empty and user has no provider membership. Check the user account linked to this payment.",
                )

            # Step 3: idempotency check
            existing = (await db.execute(
                select(Subscription).where(
                    Subscription.provider_id == provider_id,
                    Subscription.subscription_type == SubscriptionType.PROVIDER_ANNUAL,
                    Subscription.subscription_status == SubscriptionStatus.ACTIVE,
                )
            )).scalar_one_or_none()

            if existing:
                msg = f"Annual Pro already active for provider {provider_id} (idempotent — no change needed)"
            else:
                sub = Subscription(
                    provider_id=provider_id,
                    user_id=pa.initiated_by_user_id,
                    provider_name="stripe",
                    external_subscription_id=str(pa.external_payment_id or pa.id),
                    subscription_type=SubscriptionType.PROVIDER_ANNUAL,
                    subscription_status=SubscriptionStatus.ACTIVE,
                    current_period_start=datetime.utcnow(),
                    current_period_end=datetime.utcnow() + timedelta(days=365),
                )
                db.add(sub)
                await db.commit()
                msg = f"Annual Pro activated for provider {provider_id}"
                _log.info("force-fulfill: %s (payment_id=%s)", msg, payment_id)

        elif purpose in ("search_subscription", "search_tier1", "search_tier2"):
            await _fulfill_search_subscription(db, pa.related_entity_id, pa)
            msg = "Search subscription fulfilled"
        elif purpose == "full_profile_edit_unlock":
            await _fulfill_full_profile_edit_unlock(db, pa)
            msg = "Profile edit unlock fulfilled"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported purpose: {purpose}")

    except HTTPException:
        raise
    except Exception as e:
        _log.error("force-fulfill failed for %s: %s", payment_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Fulfillment failed: {str(e)}")

    try:
        audit = AuditLog(
            actor_user_id=current_user.id,
            entity_type="payment_attempt",
            entity_id=str(pa.id),
            action="force_fulfill_subscription",
            metadata={"purpose": purpose, "result": msg, "forced_by": str(current_user.id)},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return {"success": True, "payment_id": payment_id, "purpose": purpose, "message": msg}


@router.post("/admin/payments/bulk-resolve-nda-initiated")
async def admin_bulk_resolve_nda_initiated(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Bulk force-complete ALL initiated NDA fee payments and trigger fulfillment.
    Use when admin confirms all pending NDA payments were received in Stripe dashboard.
    Safe to run multiple times (idempotent — skips already-completed records).
    """
    from app.services.payment_service import _fulfill_nda_fee
    import uuid as _uuid

    result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.purpose == "nda_fee",
            PaymentAttempt.payment_status == PaymentStatus.INITIATED,
        ).order_by(PaymentAttempt.initiated_at.desc())
    )
    nda_payments = result.scalars().all()

    report = {
        "total_found": len(nda_payments),
        "completed": 0,
        "fulfillment_errors": 0,
        "details": [],
    }

    for pa in nda_payments:
        pa.payment_status = PaymentStatus.COMPLETED
        pa.confirmed_at = datetime.utcnow()
        await db.flush()

        fulfillment_result = "skipped_no_rfq_id"
        fulfillment_error = None
        try:
            if pa.related_entity_id:
                rfq_uuid = _uuid.UUID(str(pa.related_entity_id))
                await _fulfill_nda_fee(db, rfq_uuid)
                fulfillment_result = "nda_fee_fulfilled"
        except Exception as fe:
            fulfillment_error = str(fe)
            fulfillment_result = "fulfillment_failed"
            report["fulfillment_errors"] += 1

        try:
            audit = AuditLog(
                actor_user_id=current_user.id,
                entity_type="payment_attempt",
                entity_id=str(pa.id),
                action="bulk_force_complete_nda",
                before_state={"payment_status": "initiated"},
                after_state={"payment_status": "completed"},
                metadata={"fulfillment": fulfillment_result, "error": fulfillment_error},
            )
            db.add(audit)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

        report["completed"] += 1
        report["details"].append({
            "payment_id": str(pa.id),
            "amount_usd": float(pa.amount or 0) / 100.0,
            "fulfillment": fulfillment_result,
            "error": fulfillment_error,
        })

    await db.commit()
    return report


# ---- Email failures (Debugging panel) -------------------------------------
# Surfaces the email_failures table to admins, with resolve / dismiss actions
# and a lightweight count endpoint for the nav red dot.

from app.models.email_failure import EmailFailure  # noqa: E402
from app.services.email_failure_service import unresolved_count as _unresolved_count  # noqa: E402


@router.get("/admin/email-failures")
async def list_email_failures(
    unresolved_only: bool = Query(False, description="If true, only return unresolved rows"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Paginated list of email delivery failures, newest first."""
    base = select(EmailFailure)
    count_base = select(func.count(EmailFailure.id))
    if unresolved_only:
        base = base.where(EmailFailure.resolved.is_(False))
        count_base = count_base.where(EmailFailure.resolved.is_(False))

    total = int((await db.execute(count_base)).scalar() or 0)
    rows = (await db.execute(
        base.order_by(EmailFailure.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "to_email": r.to_email,
                "subject": r.subject,
                "source": r.source,
                "error_code": r.error_code,
                "error_message": r.error_message,
                "resend_email_id": r.resend_email_id,
                "resolved": bool(r.resolved),
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/admin/email-failures/unresolved-count")
async def email_failures_unresolved_count(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Lightweight count used by the Debugging nav red-dot poller."""
    n = await _unresolved_count(db)
    return {"count": n}


@router.post("/admin/email-failures/{failure_id}/resolve")
async def resolve_email_failure(
    failure_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_role("admin")),
):
    """Mark a single email failure as resolved."""
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    try:
        fid = _uuid.UUID(failure_id)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid failure id")

    row = (await db.execute(
        select(EmailFailure).where(EmailFailure.id == fid)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")

    row.resolved = True
    row.resolved_at = _dt.now(_tz.utc)
    row.resolved_by_user_id = current_admin.id
    await db.commit()
    return {"id": str(row.id), "resolved": True}


@router.delete("/admin/email-failures/{failure_id}")
async def delete_email_failure(
    failure_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Permanently delete an email failure row (admin housekeeping)."""
    import uuid as _uuid
    try:
        fid = _uuid.UUID(failure_id)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid failure id")

    row = (await db.execute(
        select(EmailFailure).where(EmailFailure.id == fid)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")

    await db.delete(row)
    await db.commit()
    return {"id": failure_id, "deleted": True}


# ---- Provider login-email sync --------------------------------------------
# Admin tool: keep the User.email (login credential) of a provider's OWNER
# in sync with the firm's primary contact email (provider.email_addresses[0]).
#
# Why this exists: when an admin updates a firm's contact email via the
# Providers panel, the linked user's login email is NOT auto-changed (the
# two are semantically different — a generic 'info@firm.com' contact vs a
# named 'alice@firm.com' login). After a bulk address change, owners would
# otherwise still log in with the OLD email until they update it themselves.

from app.models.enums import MembershipRole as _MR, MembershipStatus as _MS  # noqa: E402


def _firm_primary_email(p: Provider) -> Optional[str]:
    """Return the firm's primary contact email (first non-empty entry)."""
    if not p.email_addresses:
        return None
    if isinstance(p.email_addresses, list):
        for e in p.email_addresses:
            if isinstance(e, str) and e.strip():
                return e.strip()
        return None
    if isinstance(p.email_addresses, str):
        return p.email_addresses.strip() or None
    return None


async def _owner_user_for_provider(db: AsyncSession, provider_id: int) -> Optional[User]:
    """Return the User account of the provider's OWNER membership.

    Falls back to the first ACTIVE non-owner member if no owner exists.
    """
    from app.models.provider import ProviderMembership as _PM
    # Try owner first
    res = await db.execute(
        select(User).join(_PM, _PM.user_id == User.id).where(
            _PM.provider_id == provider_id,
            _PM.membership_role == _MR.OWNER.value,
            _PM.status == _MS.ACTIVE.value,
        ).limit(1)
    )
    u = res.scalar_one_or_none()
    if u is not None:
        return u
    # Fallback: any active member
    res = await db.execute(
        select(User).join(_PM, _PM.user_id == User.id).where(
            _PM.provider_id == provider_id,
            _PM.status == _MS.ACTIVE.value,
        ).order_by(_PM.created_at.asc() if hasattr(_PM, "created_at") else _PM.id.asc()).limit(1)
    )
    return res.scalar_one_or_none()


@router.get("/admin/email-sync-candidates")
async def list_email_sync_candidates(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(["admin"])),
):
    """List providers where the owner's login email != the firm's primary contact email.

    Used by the 'Sync Logins' modal on /admin/providers.
    """
    from app.models.provider import ProviderMembership as _PM

    # Pull every provider that has at least one email address AND at least
    # one membership. We do the mismatch check in Python because the JSON
    # column makes a clean SQL comparison annoyingly portable-unfriendly.
    res = await db.execute(
        select(Provider).where(Provider.email_addresses.isnot(None))
    )
    candidates = []
    seen_providers = 0
    for p in res.scalars().all():
        firm_email = _firm_primary_email(p)
        if not firm_email:
            continue
        seen_providers += 1
        owner = await _owner_user_for_provider(db, p.id)
        if owner is None:
            continue
        if owner.email and owner.email.strip().lower() == firm_email.lower():
            continue  # already matches
        candidates.append({
            "provider_id": p.id,
            "provider_name": p.name or p.firm_name,
            "firm_name": p.firm_name,
            "city": p.city,
            "firm_email": firm_email,
            "user_id": str(owner.id),
            "current_login_email": owner.email,
        })
    return {"total_scanned": seen_providers, "mismatches": candidates}


async def _do_sync_one(
    db: AsyncSession,
    provider_id: int,
    actor: User,
    new_email_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync a single provider's owner login email. Returns a result dict.

    Never raises HTTPException — returns a dict with `ok` / `error`.
    """
    p = await db.get(Provider, provider_id)
    if p is None:
        return {"provider_id": provider_id, "ok": False, "error": "provider_not_found"}

    target_email = (new_email_override or _firm_primary_email(p) or "").strip()
    if not target_email:
        return {"provider_id": provider_id, "ok": False, "error": "no_firm_email"}

    # very basic shape check
    if "@" not in target_email or "." not in target_email.split("@", 1)[-1]:
        return {"provider_id": provider_id, "ok": False, "error": "invalid_email"}

    owner = await _owner_user_for_provider(db, provider_id)
    if owner is None:
        return {"provider_id": provider_id, "ok": False, "error": "no_owner_account"}

    old_email = (owner.email or "").strip()
    if old_email.lower() == target_email.lower():
        return {
            "provider_id": provider_id, "ok": True, "skipped": True,
            "reason": "already_in_sync", "user_id": str(owner.id),
        }

    # Collision check — cannot have two Users with the same email.
    res = await db.execute(
        select(User.id).where(
            func.lower(User.email) == target_email.lower(),
            User.id != owner.id,
        ).limit(1)
    )
    if res.scalar_one_or_none() is not None:
        return {
            "provider_id": provider_id, "ok": False,
            "error": "email_already_in_use_by_another_account",
            "user_id": str(owner.id), "attempted_email": target_email,
        }

    owner.email = target_email
    # Newly-changed email should be re-verified to avoid trust laundering
    try:
        if hasattr(owner, "email_verified"):
            owner.email_verified = False
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    audit = AuditLog(
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=str(owner.id),
        action="admin_sync_login_email_from_provider",
        before_state={"email": old_email},
        after_state={"email": target_email, "provider_id": provider_id},
    )
    db.add(audit)

    # Fire-and-forget notification to BOTH the old and new addresses.
    try:
        import asyncio as _asyncio
        from app.services import email_service as _es

        async def _notify(addr: str):
            if not addr:
                return
            await _es._send_email_now(
                to=[addr],
                subject="Your ProReadyEngineer login email has changed",
                html_content=(
                    "<p>An administrator has updated the login email on your "
                    "ProReadyEngineer account.</p>"
                    f"<p><strong>New login email:</strong> {target_email}<br>"
                    f"<strong>Previous login email:</strong> {old_email or '(empty)'}</p>"
                    "<p>If this wasn't expected, contact us via the Contact page right away.</p>"
                ),
                text_content=(
                    "An administrator has updated the login email on your "
                    "ProReadyEngineer account.\n\n"
                    f"New login email: {target_email}\n"
                    f"Previous login email: {old_email or '(empty)'}\n\n"
                    "If this wasn't expected, contact us via the Contact page right away."
                ),
            )
        _asyncio.create_task(_notify(target_email))
        if old_email and old_email.lower() != target_email.lower():
            _asyncio.create_task(_notify(old_email))
    except Exception as exc:
        import logging as _lg
        _lg.getLogger(__name__).warning("[sync-login-email] notify dispatch failed: %s", exc)

    return {
        "provider_id": provider_id, "ok": True, "skipped": False,
        "user_id": str(owner.id),
        "old_email": old_email, "new_email": target_email,
    }


@router.post("/admin/providers/{provider_id}/sync-login-email")
async def sync_provider_login_email(
    provider_id: int,
    payload: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Sync the OWNER user's login email to the firm's primary contact email.

    Body (optional): {"new_email": "explicit@override.com"} to use an explicit
    target email instead of the firm's first email_address entry.
    """
    override = None
    if isinstance(payload, dict):
        v = payload.get("new_email")
        if isinstance(v, str) and v.strip():
            override = v.strip()

    result = await _do_sync_one(db, provider_id, current_user, override)
    if result.get("ok"):
        await db.commit()
        return result
    await db.rollback()
    raise HTTPException(status_code=400, detail=result)


@router.post("/admin/bulk-sync-login-emails")
async def bulk_sync_provider_login_emails(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Sync login emails for a list of provider ids in one transaction.

    Body: {"provider_ids": [1, 2, 3, ...]}.
    Returns a per-provider result list; failures don't abort the batch.
    """
    ids = payload.get("provider_ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="provider_ids list is required")

    results: List[Dict[str, Any]] = []
    for raw in ids:
        try:
            pid = int(raw)
        except Exception:
            results.append({"provider_id": raw, "ok": False, "error": "invalid_id"})
            continue
        results.append(await _do_sync_one(db, pid, current_user))

    await db.commit()
    summary = {
        "total": len(results),
        "synced": sum(1 for r in results if r.get("ok") and not r.get("skipped")),
        "skipped": sum(1 for r in results if r.get("ok") and r.get("skipped")),
        "failed": sum(1 for r in results if not r.get("ok")),
    }
    return {"summary": summary, "results": results}


@router.get("/admin/debug/email-auth")
async def admin_email_auth(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: live SPF / DKIM / DMARC posture for the sending domain.

    Resolves the relevant TXT records over DNS-over-HTTPS and evaluates them, so
    the admin Email Authentication panel can show config health (and the current
    DMARC policy) without any access to the DMARC report mailbox.
    """
    from app.services import email_auth as _ea

    config = await _get_runtime_config(db)
    from_address = (config.get("RESEND_FROM_EMAIL", "") or getattr(settings, "FROM_EMAIL", "") or "")
    send_domain = from_address.split("@")[1].lower() if "@" in from_address else "promechdirectory.com"
    # Organization (registrable) domain — DMARC is published here and applies to subdomains.
    # Simple last-two-labels heuristic (fine for .com; good enough for this panel).
    labels = send_domain.split(".")
    org_domain = ".".join(labels[-2:]) if len(labels) > 2 else send_domain

    # SPF: check the sending domain first; if absent, fall back to the org domain.
    spf = _ea.evaluate_spf(await _ea.fetch_txt(send_domain))
    spf_domain = send_domain
    if spf["status"] == "fail" and org_domain != send_domain:
        org_spf = _ea.evaluate_spf(await _ea.fetch_txt(org_domain))
        if org_spf["status"] != "fail":
            org_spf["detail"] += " (Published at the organization domain {}.)".format(org_domain)
            spf, spf_domain = org_spf, org_domain

    # DKIM: published on the sending domain.
    dkim = _ea.evaluate_dkim(await _ea.fetch_txt("resend._domainkey." + send_domain), selector="resend")

    # DMARC: organization-level. Prefer a subdomain record if one exists, else the org domain.
    dmarc = _ea.evaluate_dmarc(await _ea.fetch_txt("_dmarc." + send_domain))
    dmarc_domain = send_domain
    if dmarc["status"] == "fail" and org_domain != send_domain:
        dmarc = _ea.evaluate_dmarc(await _ea.fetch_txt("_dmarc." + org_domain))
        dmarc_domain = org_domain

    summary = _ea.overall_status(spf, dkim, dmarc)
    return {
        "domain": org_domain,
        "send_domain": send_domain,
        "from_address": from_address,
        "checks": {"spf": spf, "dkim": dkim, "dmarc": dmarc},
        "found_at": {"spf": spf_domain, "dkim": "resend._domainkey." + send_domain, "dmarc": "_dmarc." + dmarc_domain},
        "summary": summary,
    }
