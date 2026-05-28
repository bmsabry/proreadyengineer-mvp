"""Internal endpoints for cron jobs and system operations."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import logging
from typing import Optional

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# NOTE: CRON_SECRET auth intentionally removed.
# The /internal/* endpoints are called by the Render Cron Job service on the
# same Render network. Requiring a secret that must be manually synced to BOTH
# the API service AND the cron service env vars caused silent 401 failures
# every time, preventing any batch from being dispatched.
# The only callers of this endpoint are: Render cron service + admin panel.
# If you need auth, use a static CRON_INTERNAL_TOKEN env var set identically
# on both services via render.yaml value (not sync:false).


async def _log_cron_run(db: AsyncSession, result: dict, trigger_source: str = "http_cron") -> None:
    """Store last cron execution + trigger source in system_config for admin visibility.

    trigger_source distinguishes the two dispatch triggers so the admin Cron
    Health card can warn 'primary Render cron is dead, asyncio backup is
    carrying' when only the in-process loop is firing.
        - "http_cron"      = called via POST from Render Cron Job (primary)
        - "asyncio_loop"   = called by the asyncio fallback in main.py (backup)
        - "admin_manual"   = called by an admin from the panel (one-off)
    """
    import json
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        result_str = json.dumps(result)[:2000]
        await db.execute(
            text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES ('cron_last_run', :ts, now())
                ON CONFLICT (key) DO UPDATE SET value = :ts, updated_at = now()
            """),
            {"ts": now_str}
        )
        await db.execute(
            text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES ('cron_last_result', :res, now())
                ON CONFLICT (key) DO UPDATE SET value = :res, updated_at = now()
            """),
            {"res": result_str}
        )
        await db.execute(
            text("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES ('cron_last_trigger_source', :src, now())
                ON CONFLICT (key) DO UPDATE SET value = :src, updated_at = now()
            """),
            {"src": trigger_source}
        )
        # Per-source last-run keys so the admin card can flag 'http_cron dead'.
        if trigger_source in ("http_cron", "asyncio_loop", "admin_manual"):
            await db.execute(
                text("""
                    INSERT INTO system_config (key, value, updated_at)
                    VALUES (:k, :v, now())
                    ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()
                """),
                {"k": f"cron_last_run_{trigger_source}", "v": now_str}
            )
        await db.commit()
    except Exception as e:
        logger.warning("_log_cron_run: could not save cron log: %s", e)


@router.post("/internal/cron/dispatch-rfq-batches")
async def cron_dispatch_rfq_batches(
    db: AsyncSession = Depends(get_db),
    trigger_source: str = "http_cron",
):
    """
    Cron endpoint: check all open RFQs and dispatch next batch if interval elapsed.
    Called by Render Cron Job every 15 minutes.
    Runs natively in FastAPI async context - no asyncio.run() needed.
    Auth removed: cron service and API service must share CRON_SECRET via render.yaml
    value (not sync:false) to avoid mismatch. For now, endpoint is unauthenticated
    but internal-only.
    """
    from app.models.rfq import RFQ, RfqStatus, RFQDispatchBatch
    from app.services.rfq_service import dispatch_next_batch
    from app.services.config_service import get_runtime_config as _get_runtime_config
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal

    try:
        cfg = await _get_runtime_config(db)
        interval_hours = float(cfg.get('RFQ_BATCH_INTERVAL_HOURS', settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS))
    except Exception:
        interval_hours = float(settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS)

    # Enforce minimum interval floor: 15 minutes regardless of config.
    # Prevents interval=0 from causing every cron poll to fire a new batch.
    _MIN_INTERVAL = 0.25
    if interval_hours < _MIN_INTERVAL:
        logger.warning("cron_dispatch: interval %.2fh below minimum %.2fh, enforcing floor", interval_hours, _MIN_INTERVAL)
        interval_hours = _MIN_INTERVAL

    interval_delta = timedelta(hours=interval_hours)
    now = datetime.now(timezone.utc)

    logger.info("cron_dispatch: starting poll interval_hours=%.2f", interval_hours)

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

    logger.info("cron_dispatch: found %d open RFQs", len(rfqs))

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
                    logger.info("cron_dispatch: rfq=%s elapsed=%.2fh >= interval=%.2fh -> dispatching",
                                rfq.id, elapsed.total_seconds()/3600, interval_hours)
                else:
                    remaining = interval_delta - elapsed
                    skip_msg = f"too_soon_wait_{remaining.total_seconds()/60:.0f}min"
                    skipped_rfqs.append({"rfq_id": str(rfq.id), "reason": skip_msg})
                    logger.info("cron_dispatch: rfq=%s skipped reason=%s", rfq.id, skip_msg)

        if should_dispatch:
            try:
                async with AsyncSessionLocal() as fresh_db:
                    dispatched = await dispatch_next_batch(fresh_db, rfq.id)
                dispatched_rfqs.append({
                    "rfq_id": str(rfq.id),
                    "providers_emailed": len(dispatched),
                    "reason": reason,
                })
                logger.info("cron_dispatch: dispatched batch rfq=%s providers=%d reason=%s",
                            rfq.id, len(dispatched), reason)
            except Exception as e:
                err_msg = f"error:{str(e)[:100]}"
                logger.error("cron_dispatch: error rfq=%s: %s", rfq.id, e, exc_info=True)
                skipped_rfqs.append({"rfq_id": str(rfq.id), "reason": err_msg})

    response = {
        "status": "ok",
        "dispatched": dispatched_rfqs,
        "skipped": skipped_rfqs,
        "interval_hours": interval_hours,
        "checked_at": now.isoformat(),
        "open_rfqs_found": len(rfqs),
    }

    # Log cron execution to system_config for admin visibility
    await _log_cron_run(db, response, trigger_source=trigger_source)

    return response


@router.post("/internal/cron/dispatch-rfq/{rfq_id}")
async def cron_dispatch_single_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Force dispatch next batch for a specific RFQ. Used by admin manual dispatch."""
    import uuid
    from app.services.rfq_service import dispatch_next_batch

    try:
        rfq_uuid = uuid.UUID(rfq_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid RFQ ID")

    # Safety check: validate RFQ exists and is in a dispatchable state before forcing
    from app.models.rfq import RFQ, RfqStatus
    from sqlalchemy import select as _select
    _rfq_result = await db.execute(_select(RFQ).where(RFQ.id == rfq_uuid))
    _rfq = _rfq_result.scalar_one_or_none()
    if not _rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")
    if _rfq.is_closed:
        raise HTTPException(status_code=400, detail=f"RFQ is closed (status={_rfq.rfq_status}) - dispatch blocked")
    _DISPATCHABLE = {"open_for_dispatch", "dispatching", "open_for_unlock"}
    _status_str = str(_rfq.rfq_status).lower().replace("rfqstatus.", "")
    if _status_str not in _DISPATCHABLE:
        raise HTTPException(status_code=400, detail=f"RFQ status '{_rfq.rfq_status}' is not dispatchable - dispatch blocked")

    try:
        dispatched = await dispatch_next_batch(db, rfq_uuid)
        return {
            "status": "ok",
            "rfq_id": rfq_id,
            "providers_emailed": len(dispatched),
        }
    except Exception as e:
        logger.error("force_dispatch: error rfq=%s: %s", rfq_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/internal/cron/status")
async def cron_status(
    db: AsyncSession = Depends(get_db),
):
    """Return last cron execution info. Used by admin panel to verify cron is firing."""
    try:
        result = await db.execute(
            text("SELECT key, value FROM system_config WHERE key IN ('cron_last_run', 'cron_last_result')")
        )
        rows = {row[0]: row[1] for row in result.fetchall()}
        last_run = rows.get('cron_last_run')
        last_result = rows.get('cron_last_result')
        last_trigger = rows.get('cron_last_trigger_source')
        last_run_http = rows.get('cron_last_run_http_cron')
        last_run_asyncio = rows.get('cron_last_run_asyncio_loop')

        def _minutes_ago(iso: Optional[str]) -> Optional[int]:
            if not iso:
                return None
            try:
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
            except Exception:
                return None

        minutes_ago = _minutes_ago(last_run)
        minutes_ago_http = _minutes_ago(last_run_http)
        minutes_ago_asyncio = _minutes_ago(last_run_asyncio)

        # Health logic:
        #   healthy: any cron fired in the last 20 min (covers 5-min backup + 15-min primary)
        #   degraded: only the asyncio backup has been running -- Render cron is dead
        #   stale: nothing fired in the last 20 min at all
        if minutes_ago is None or minutes_ago >= 20:
            status_label = "stale"
        elif minutes_ago_http is None or (minutes_ago_http >= 60):
            # asyncio firing but no http cron in the last hour -> primary down
            status_label = "degraded"
        else:
            status_label = "healthy"

        return {
            "last_run": last_run,
            "minutes_ago": minutes_ago,
            "last_trigger_source": last_trigger,
            "last_run_http_cron": last_run_http,
            "last_run_http_cron_minutes_ago": minutes_ago_http,
            "last_run_asyncio_loop": last_run_asyncio,
            "last_run_asyncio_loop_minutes_ago": minutes_ago_asyncio,
            "last_result": last_result,
            "status": status_label,
        }
    except Exception as e:
        return {"error": str(e), "status": "unknown"}
