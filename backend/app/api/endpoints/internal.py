"""Internal endpoints for cron jobs and system operations."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from app.db.session import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_cron_secret(authorization: Optional[str] = Header(None)):
    """Verify the cron job secret token."""
    cron_secret = getattr(settings, 'CRON_SECRET', None)
    if cron_secret:
        if not authorization or authorization != f"Bearer {cron_secret}":
            raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.post("/internal/cron/dispatch-rfq-batches")
async def cron_dispatch_rfq_batches(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_cron_secret),
):
    """
    Cron endpoint: check all open RFQs and dispatch next batch if interval elapsed.
    Called by Render Cron Job every 15 minutes.
    Runs natively in FastAPI async context - no asyncio.run() needed.
    """
    from app.models.rfq import RFQ, RfqStatus, RFQDispatchBatch
    from app.services.rfq_service import dispatch_next_batch
    from app.services.config_service import _get_runtime_config

    try:
        cfg = await _get_runtime_config(db)
        interval_hours = float(cfg.get('RFQ_BATCH_INTERVAL_HOURS', settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS))
    except Exception:
        interval_hours = float(settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS)

    interval_delta = timedelta(hours=interval_hours)
    now = datetime.now(timezone.utc)

    # Find all open RFQs that still need more quotes
    result = await db.execute(
        select(RFQ).where(
            RFQ.is_closed == False,
            RFQ.rfq_status.in_([
                RfqStatus.OPEN_FOR_DISPATCH,
                RfqStatus.OPEN_FOR_UNLOCK,
                RfqStatus.DISPATCHING,
            ])
        )
    )
    rfqs = result.scalars().all()

    dispatched_rfqs = []
    skipped_rfqs = []

    for rfq in rfqs:
        if rfq.quote_count >= 5:
            skipped_rfqs.append({"rfq_id": str(rfq.id), "reason": "quote_limit_reached"})
            continue

        # Find when the last batch was dispatched
        last_batch_result = await db.execute(
            select(RFQDispatchBatch)
            .where(RFQDispatchBatch.rfq_id == rfq.id)
            .order_by(RFQDispatchBatch.batch_number.desc())
            .limit(1)
        )
        last_batch = last_batch_result.scalar_one_or_none()

        should_dispatch = False
        reason = ""
        if last_batch is None:
            should_dispatch = True
            reason = "no_batch_yet"
        else:
            last_dispatched = last_batch.dispatched_at
            if last_dispatched is None:
                should_dispatch = True
                reason = "no_dispatched_at"
            else:
                if last_dispatched.tzinfo is None:
                    last_dispatched = last_dispatched.replace(tzinfo=timezone.utc)
                elapsed = now - last_dispatched
                if elapsed >= interval_delta:
                    should_dispatch = True
                    reason = f"interval_elapsed_{elapsed.total_seconds()/3600:.2f}h"
                else:
                    remaining = interval_delta - elapsed
                    skipped_rfqs.append({
                        "rfq_id": str(rfq.id),
                        "reason": f"too_soon_wait_{remaining.total_seconds()/60:.0f}min"
                    })

        if should_dispatch:
            try:
                dispatched = await dispatch_next_batch(db, rfq.id)
                dispatched_rfqs.append({
                    "rfq_id": str(rfq.id),
                    "providers_emailed": len(dispatched),
                    "reason": reason,
                })
                logger.info("cron_dispatch: dispatched batch for rfq=%s providers=%d", rfq.id, len(dispatched))
            except Exception as e:
                logger.error("cron_dispatch: error dispatching rfq=%s: %s", rfq.id, e)
                skipped_rfqs.append({"rfq_id": str(rfq.id), "reason": f"error:{str(e)[:100]}"})

    return {
        "status": "ok",
        "dispatched": dispatched_rfqs,
        "skipped": skipped_rfqs,
        "interval_hours": interval_hours,
        "checked_at": now.isoformat(),
    }


@router.post("/internal/cron/dispatch-rfq/{rfq_id}")
async def cron_dispatch_single_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_cron_secret),
):
    """Force dispatch next batch for a specific RFQ. Used by admin manual dispatch."""
    import uuid
    from app.services.rfq_service import dispatch_next_batch

    try:
        rfq_uuid = uuid.UUID(rfq_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid RFQ ID")

    try:
        dispatched = await dispatch_next_batch(db, rfq_uuid)
        return {
            "status": "ok",
            "rfq_id": rfq_id,
            "providers_emailed": len(dispatched),
        }
    except Exception as e:
        logger.error("force_dispatch: error rfq=%s: %s", rfq_id, e)
        raise HTTPException(status_code=500, detail=str(e))
