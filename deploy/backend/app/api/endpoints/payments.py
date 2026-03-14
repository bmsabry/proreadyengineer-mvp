"""Payment and webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.payment_service import (
    handle_stripe_webhook, handle_paypal_webhook,
    create_billing_portal_session
)

router = APIRouter()


@router.get("/billing/portal")
async def get_billing_portal(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get Stripe billing portal URL for user."""
    from sqlalchemy import select
    from app.models.payment import Subscription

    # Find user's subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found")

    portal_url = await create_billing_portal_session(subscription.external_customer_id)
    return {"portal_url": portal_url}


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhooks."""
    payload = await request.body()

    try:
        await handle_stripe_webhook(db, payload, stripe_signature)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle PayPal/Braintree webhooks."""
    payload = await request.json()

    try:
        await handle_paypal_webhook(db, payload)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/webhooks/signwell")
async def signwell_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Signwell document signing webhooks.

    Signwell uses a single workspace callback URL (no per-document secrets).
    Events: document_signer_completed, document_completed.
    """
    import logging
    _log = logging.getLogger(__name__)

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event_type = (
        payload.get("event_type")
        or payload.get("type")
        or payload.get("data", {}).get("event_type")
        or ""
    )
    _log.info("Signwell webhook received: event_type=%s", event_type)

    try:
        from app.services.nda_service import handle_signwell_webhook
        await handle_signwell_webhook(event_type, payload, db)
    except Exception as exc:
        _log.error("Error processing Signwell webhook: %s", exc)
        # Return 200 so Signwell does not retry indefinitely

    return {"status": "received"}
