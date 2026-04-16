"""Celery background tasks."""

from app.core.celery import celery_app

__all__ = ["celery_app"]
