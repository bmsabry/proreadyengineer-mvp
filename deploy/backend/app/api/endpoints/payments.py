"""Payment and webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.payment_service import (
    handle_stripe_webhook, handle_paypal_webhook,
    create_billing_portal_session
,
    create_paypal_order, capture_paypal_order, create_paypal_subscription,
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


# --------------- PayPal Routes ---------------

@router.get("/paypal/config")
async def paypal_get_config(db: AsyncSession = Depends(get_db)):
    """Return public PayPal client_id and mode for frontend SDK."""
    from app.services.config_service import get_runtime_config
    cfg = await get_runtime_config(db)
    client_id = cfg.get("PAYPAL_CLIENT_ID", "")
    mode = cfg.get("PAYPAL_MODE", "sandbox")
    return {"client_id": client_id, "mode": mode, "enabled": bool(client_id)}


@router.post("/paypal/create-order")
async def paypal_create_order_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a PayPal order for one-time payment (RFQ unlock $10, NDA $5)."""
    import uuid as uuid_lib
    body = await request.json()
    purpose = body.get("purpose")
    amount_usd = float(body.get("amount_usd", 0))
    related_entity_type = body.get("related_entity_type", "")
    related_entity_id_str = body.get("related_entity_id", "")
    metadata = body.get("metadata", {})
    return_url = body.get("return_url", "https://proreadyengineer.com/payment/success")
    cancel_url = body.get("cancel_url", "https://proreadyengineer.com/payment/cancel")
    if not purpose or amount_usd <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="purpose and positive amount_usd are required")
    try:
        related_entity_id = uuid_lib.UUID(related_entity_id_str)
    except (ValueError, AttributeError):
        related_entity_id = uuid_lib.uuid4()
    return await create_paypal_order(
        db, purpose=purpose, amount_usd=amount_usd, user=current_user,
        related_entity_type=related_entity_type, related_entity_id=related_entity_id,
        metadata=metadata, return_url=return_url, cancel_url=cancel_url,
    )


@router.post("/paypal/capture-order")
async def paypal_capture_order_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Capture a PayPal order after customer approves it."""
    body = await request.json()
    order_id = body.get("order_id")
    if not order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="order_id is required")
    return await capture_paypal_order(db, order_id)


@router.post("/paypal/create-subscription")
async def paypal_create_subscription_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create PayPal billing subscription for recurring plans."""
    from app.services.config_service import get_runtime_config
    body = await request.json()
    subscription_type = body.get("subscription_type")
    if not subscription_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="subscription_type is required")
    cfg = await get_runtime_config(db)
    plan_key_map = {
        "search_tier1":     "PAYPAL_PLAN_SEARCH_TIER1",
        "search_tier2":     "PAYPAL_PLAN_SEARCH_TIER2",
        "provider_profile": "PAYPAL_PLAN_PROVIDER_PROFILE",
        "advertisement":    "PAYPAL_PLAN_ADVERTISEMENT",
    }
    plan_key = plan_key_map.get(subscription_type)
    if not plan_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unknown subscription_type: {subscription_type}")
    plan_id = cfg.get(plan_key, "")
    return await create_paypal_subscription(
        db, user=current_user, plan_id=plan_id, subscription_type=subscription_type
    )
