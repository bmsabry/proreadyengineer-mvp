"""Email background tasks."""

from app.core.celery import celery_app
from app.services.email_service import (
    send_teaser_email,
    send_quote_notification,
    send_nda_ready_email,
)


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
