"""Celery configuration for background tasks."""

from celery import Celery
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "proready_engineer",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.search_tasks",
        "app.tasks.rfq_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3000,  # 50 minutes

    # Result backend
    result_expires=3600,
    result_backend=settings.REDIS_URL,

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_heartbeat=60,

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "cleanup-expired-tokens": {
        "task": "app.tasks.maintenance.cleanup_expired_tokens",
        "schedule": 86400.0,  # 24 hours
    },
    "process-rfq-dispatches": {
        "task": "app.tasks.rfq_tasks.process_pending_dispatches",
        "schedule": 900.0,  # 15 minutes
    },
    'check-and-dispatch-rfqs-every-24h': {
        'task': 'app.tasks.rfq_tasks.check_and_dispatch_rfqs_task',
        'schedule': 86400.0,  # 24 hours in seconds
    },
}


def get_task_info(task_id: str) -> dict:
    """Get information about a Celery task."""
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }
