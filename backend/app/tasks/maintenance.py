"""Periodic maintenance tasks (run via Celery beat).

- expire_subscriptions: enforce that EVERY subscription tier ends as advertised.
  All access gates check only ``subscription_status == 'active'`` and nothing else
  ever flips a subscription off when its paid period ends. This task is the single
  enforcement point: it cancels any ACTIVE subscription whose ``current_period_end``
  has passed (beyond a small grace window). Recurring Stripe subs have their end date
  pushed forward by invoice.paid / subscription.updated webhooks, so they are only
  caught here if they genuinely lapsed; one-time annual ($1000) and founding-promo
  subscriptions (which never renew) are correctly ended on schedule.
- cleanup_expired_tokens: prune expired refresh/password-reset tokens.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, or_, select

from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Grace window absorbs the gap between a recurring sub's period end and the
# renewal webhook that extends current_period_end. 1 day is far longer than
# Stripe's webhook latency while still ending lapsed access promptly.
EXPIRY_GRACE = timedelta(days=1)


async def expire_due_subscriptions(db, *, now=None, grace=EXPIRY_GRACE) -> int:
    """Cancel ACTIVE subscriptions whose period ended before ``now - grace``.

    Returns the number cancelled. Skips rows with a NULL period end. Testable
    helper shared by the Celery task.
    """
    from app.models.payment import Subscription
    from app.models.enums import SubscriptionStatus

    now = now or datetime.now(timezone.utc)
    cutoff = now - grace
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.subscription_status == SubscriptionStatus.ACTIVE,
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end < cutoff,
            )
        )
    )
    expired = result.scalars().all()
    for sub in expired:
        sub.subscription_status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = now
    if expired:
        await db.commit()
    logger.info("expire_subscriptions: cancelled %d expired subscription(s)", len(expired))
    return len(expired)


@celery_app.task(bind=True)
def expire_subscriptions(self):
    """Cancel ACTIVE subscriptions whose period has ended (beyond the grace window)."""

    async def _run():
        async with AsyncSessionLocal() as db:
            return await expire_due_subscriptions(db)

    return asyncio.run(_run())


@celery_app.task(bind=True)
def cleanup_expired_tokens(self):
    """Delete expired refresh tokens and used/expired password-reset tokens."""

    async def _run():
        from app.models.user import RefreshToken, PasswordResetToken

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            r1 = await db.execute(
                delete(RefreshToken).where(RefreshToken.expires_at < now)
            )
            r2 = await db.execute(
                delete(PasswordResetToken).where(
                    or_(
                        PasswordResetToken.expires_at < now,
                        PasswordResetToken.used_at.is_not(None),
                    )
                )
            )
            await db.commit()
            removed = (r1.rowcount or 0) + (r2.rowcount or 0)
            logger.info("cleanup_expired_tokens: removed %d expired token row(s)", removed)
            return removed

    return asyncio.run(_run())
