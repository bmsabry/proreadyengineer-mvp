"""RFQ background tasks."""
import asyncio
from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal


@celery_app.task(bind=True, max_retries=3)
def dispatch_rfq_batch_task(self, rfq_id: str):
    """Dispatch next batch for an RFQ if quote_count < 5."""
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
    """Every 24h: for each open RFQ with quote_count < 5, dispatch next batch."""
    async def _check():
        from sqlalchemy import select
        from app.models.rfq import RFQ, RfqStatus
        async with AsyncSessionLocal() as db:
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
                if rfq.quote_count < 5:
                    dispatch_rfq_batch_task.delay(str(rfq.id))

    asyncio.run(_check())
