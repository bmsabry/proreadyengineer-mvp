"""RFQ background tasks."""
import asyncio
from datetime import datetime, timezone, timedelta
from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal


@celery_app.task(bind=True, max_retries=3)
def dispatch_rfq_batch_task(self, rfq_id: str):
    """Dispatch next batch for an RFQ if quote_count < max."""
    async def _dispatch():
        from app.services.rfq_service import dispatch_next_batch
        import uuid
        async with AsyncSessionLocal() as db:
            await dispatch_next_batch(db, uuid.UUID(rfq_id))

    try:
        asyncio.run(_dispatch())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(bind=True)
def check_and_dispatch_rfqs_task(self):
    """Polling task (runs every 15 min via beat).
    For each open RFQ, fires the next batch only if the configured
    batch interval has elapsed since the last batch was dispatched.
    Reads RFQ_BATCH_INTERVAL_HOURS from admin DB config at runtime.
    """
    async def _check():
        from sqlalchemy import select, func
        from app.models.rfq import RFQ, RfqStatus, RFQDispatchBatch
        from app.services.config_service import _get_runtime_config
        from app.core.config import settings

        async with AsyncSessionLocal() as db:
            # Read interval from admin config
            try:
                cfg = await _get_runtime_config(db)
                interval_hours = float(cfg.get('RFQ_BATCH_INTERVAL_HOURS',
                                               settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS))
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

            for rfq in rfqs:
                if rfq.quote_count >= 5:
                    continue

                # Find when the last batch was dispatched for this RFQ
                last_batch_result = await db.execute(
                    select(RFQDispatchBatch)
                    .where(RFQDispatchBatch.rfq_id == rfq.id)
                    .order_by(RFQDispatchBatch.batch_number.desc())
                    .limit(1)
                )
                last_batch = last_batch_result.scalar_one_or_none()

                if last_batch is None:
                    # No batch ever sent - fire immediately
                    dispatch_rfq_batch_task.delay(str(rfq.id))
                    continue

                last_dispatched = last_batch.dispatched_at
                if last_dispatched is None:
                    dispatch_rfq_batch_task.delay(str(rfq.id))
                    continue

                # Ensure timezone-aware comparison
                if last_dispatched.tzinfo is None:
                    last_dispatched = last_dispatched.replace(tzinfo=timezone.utc)

                elapsed = now - last_dispatched
                if elapsed >= interval_delta:
                    dispatch_rfq_batch_task.delay(str(rfq.id))

    asyncio.run(_check())
