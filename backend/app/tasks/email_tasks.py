"""Email background tasks."""

import logging
import uuid

from app.core.celery import celery_app
from app.services.email_service import (
    send_teaser_email,
    send_quote_notification,
    send_nda_ready_email,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_teaser_email_task(self, provider_email: str, rfq_data: dict):
    """Send RFQ teaser email to provider."""
    try:
        send_teaser_email(provider_email, rfq_data)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_quote_notification_task(self, customer_email: str, quote_data: dict):
    """Notify customer of new quote."""
    try:
        send_quote_notification(customer_email, quote_data)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_nda_ready_task(self, email: str, nda_id: str):
    """Notify user NDA is ready for signing."""
    try:
        send_nda_ready_email(email, nda_id)
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=0,           # No auto-retry — batch logic handles recovery
    name="tasks.process_campaign_batch",
    queue="campaigns",
)
def process_campaign_batch_task(self, campaign_id: str):
    """Process next email batch for a provider campaign.

    This task is the Celery worker entry-point for campaign batch sending.
    It runs synchronously inside the worker using asyncio.run(), calls
    send_next_batch(), then re-schedules itself for the next day if there
    are still pending invites.

    Scheduling: countdown=86400 (24 hours) ensures one batch per day.
    """
    import asyncio
    from datetime import datetime, timezone

    campaign_uuid = uuid.UUID(campaign_id)
    logger.info("[campaign_batch] Starting batch for campaign %s", campaign_id)

    async def _run():
        from app.db.session import AsyncSessionLocal
        from app.services.campaign_service import send_next_batch
        from app.models.enums import CampaignStatus
        from app.models.campaign import ProviderCampaign
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await send_next_batch(db, campaign_uuid)

        logger.info("[campaign_batch] Batch result for %s: %s", campaign_id, result)

        # Check if campaign is still active and has more pending invites
        if result.get("completed") or result.get("skipped"):
            logger.info(
                "[campaign_batch] Campaign %s — no further batches needed (result=%s)",
                campaign_id, result,
            )
            return

        # Re-schedule for next batch (24 hours from now)
        async with AsyncSessionLocal() as db2:
            from sqlalchemy import select as sa_select
            from app.models.campaign import ProviderCampaign
            camp_result = await db2.execute(
                sa_select(ProviderCampaign).where(ProviderCampaign.id == campaign_uuid)
            )
            campaign = camp_result.scalar_one_or_none()
            if campaign and campaign.status == CampaignStatus.ACTIVE:
                process_campaign_batch_task.apply_async(
                    args=[campaign_id],
                    countdown=86400,  # 24 hours
                )
                logger.info(
                    "[campaign_batch] Next batch for campaign %s scheduled in 24h",
                    campaign_id,
                )

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(
            "[campaign_batch] Fatal error processing campaign %s: %s",
            campaign_id, exc, exc_info=True,
        )
        raise
