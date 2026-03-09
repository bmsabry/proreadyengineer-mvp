"""RFQ background tasks."""

import asyncio
from datetime import datetime

from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal
from app.services.rfq_service import dispatch_teaser_batch


@celery_app.task(bind=True, max_retries=3)
def dispatch_rfq_batch_task(self, rfq_id: str, batch_number: int):
    """Dispatch RFQ teaser batch to providers."""
    async def _dispatch():
        async with AsyncSessionLocal() as db:
            await dispatch_teaser_batch(db, rfq_id, batch_number)

    try:
        asyncio.run(_dispatch())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True)
def process_pending_dispatches_task(self):
    """Process all pending RFQ dispatches (scheduled every 15 min)."""
    async def _process():
        from sqlalchemy import select
        from app.models.rfq import RFQDispatchBatch

        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            result = await db.execute(
                select(RFQDispatchBatch).where(
                    RFQDispatchBatch.scheduled_for <= now,
                    RFQDispatchBatch.status == "pending"
                )
            )
            batches = result.scalars().all()

            for batch in batches:
                dispatch_rfq_batch_task.delay(str(batch.rfq_id), batch.batch_number)
                batch.status = "dispatched"

            await db.commit()

    asyncio.run(_process())
