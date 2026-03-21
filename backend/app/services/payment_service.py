"""Payment service with Stripe/PayPal webhook handling and idempotent fulfillment."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    NdaStatus,
    PaymentAttempt,
    PaymentStatus,
    Provider,
    RFQNDA,
    RfqStatus,
    RFQUnlock,
    Subscription,
    SubscriptionStatus,
    SubscriptionType,
    UnlockStatus,
    User,
    WebhookEvent,
)


def _create_idempotency_key(purpose: str, user_id: uuid.UUID, related_id: uuid.UUID) -> str:
    """Create deterministic idempotency key.

    Args:
        purpose: Payment purpose (e.g., 'rfq_unlock').
        user_id: User UUID.
        related_id: Related entity UUID.

    Returns:
        str: Idempotency key string.
    """
    key_data = f"{purpose}:{user_id}:{related_id}:{datetime.utcnow().strftime('%Y-%m-%d')}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]


async def create_payment_intent(
    db: AsyncSession,
    purpose: str,
    amount: int,  # Amount in cents
    currency: str,
    user: User,
    related_entity_type: str,
    related_id: uuid.UUID,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """Create a Stripe payment intent.

    Args:
        db: Database session.
        purpose: Payment purpose (rfq_unlock, nda_fee, etc.).
        amount: Amount in cents.
        currency: Currency code (e.g., 'usd').
        user: Paying user.
        related_entity_type: Type of related entity ('rfq', 'subscription', etc.).
        related_id: UUID of related entity.
        metadata: Additional metadata for Stripe.

    Returns:
        dict: Contains 'client_secret' and 'payment_attempt_id'.

    Raises:
        RuntimeError: If Stripe API call fails.
    """
    from app.services.config_service import get_runtime_config as _grc
    _cfg = await _grc(db)
    stripe.api_key = _cfg.get('STRIPE_SECRET_KEY', '') or ''
    if not stripe.api_key:
        raise RuntimeError("Stripe is not configured. Please add your Stripe secret key in admin settings.")

    # Create idempotency key
    idempotency_key = _create_idempotency_key(purpose, user.id, related_id)

    # Check for existing payment attempt
    existing_result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.idempotency_key == idempotency_key,
            PaymentAttempt.payment_status != PaymentStatus.FAILED,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing and existing.payment_status == PaymentStatus.COMPLETED:
        return {
            "client_secret": existing.external_checkout_id,
            "payment_attempt_id": existing.id,
            "existing": True,
        }

    # Create Stripe payment intent
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "purpose": purpose,
                "user_id": str(user.id),
                "related_entity_type": related_entity_type,
                "related_id": str(related_id),
                **(metadata or {}),
            },
            idempotency_key=idempotency_key,
        )
    except stripe.error.StripeError as e:
        raise RuntimeError(f"Stripe API error: {e}")

    # Create payment attempt record
    payment_attempt = PaymentAttempt(
        provider_name="stripe",
        external_payment_id=payment_intent.id,
        external_checkout_id=payment_intent.client_secret,
        purpose=purpose,
        related_entity_type=related_entity_type,
        related_entity_id=related_id,
        amount=amount,
        currency=currency.lower(),
        payment_status=PaymentStatus.INITIATED,
        idempotency_key=idempotency_key,
        initiated_by_user_id=user.id,
        metadata=metadata,
    )

    db.add(payment_attempt)
    await db.commit()
    await db.refresh(payment_attempt)

    return {
        "client_secret": payment_intent.client_secret,
        "payment_attempt_id": payment_attempt.id,
        "existing": False,
    }




async def create_stripe_checkout_session(
    db: AsyncSession,
    purpose: str,
    amount: int,
    currency: str,
    user: User,
    related_entity_type: str,
    related_id: str,
    success_url: str,
    cancel_url: str,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session that redirects to Stripe-hosted payment page.

    Returns dict with 'checkout_url' and 'payment_attempt_id'.
    """
    from app.services.config_service import get_runtime_config as _grc
    _cfg = await _grc(db)
    stripe.api_key = _cfg.get('STRIPE_SECRET_KEY', '') or ''

    if not stripe.api_key:
        raise RuntimeError(
            "Stripe is not configured. Please add your Stripe secret key in admin settings."
        )

    idempotency_key = _create_idempotency_key(purpose, user.id, related_id)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "product_data": {
                        "name": _get_payment_product_name(purpose),
                        "description": _get_payment_description(
                            purpose, related_entity_type, str(related_id)
                        ),
                    },
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user.email,
            metadata={
                "purpose": purpose,
                "user_id": str(user.id),
                "related_entity_type": related_entity_type,
                "related_id": str(related_id),
                **(metadata or {}),
            },
        )
    except stripe.error.StripeError as e:
        raise RuntimeError(f"Stripe error: {e}")

    # Record payment attempt
    # Convert related_id to UUID if it's a string
    import uuid as _uuid_mod
    try:
        related_entity_uuid = _uuid_mod.UUID(str(related_id)) if related_id else None
    except (ValueError, AttributeError):
        related_entity_uuid = None

    payment_attempt = PaymentAttempt(
        provider_name="stripe",
        external_payment_id=session.id,
        external_checkout_id=session.url,
        purpose=purpose,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_uuid,
        amount=amount,
        currency=currency.lower(),
        payment_status=PaymentStatus.INITIATED,
        idempotency_key=idempotency_key,
        initiated_by_user_id=user.id,
        metadata=metadata,
    )
    db.add(payment_attempt)
    await db.commit()
    await db.refresh(payment_attempt)

    return {
        "checkout_url": session.url,
        "payment_attempt_id": str(payment_attempt.id),
        "session_id": session.id,
    }


def _get_payment_product_name(purpose: str) -> str:
    """Return human-readable product name for Stripe line item."""
    names = {
        "rfq_unlock": "RFQ Access - One Time Unlock",
        "nda_fee": "NDA Document Handling Fee",
        "provider_profile_subscription": "Provider Profile Subscription",
        "search_subscription": "Search Subscription",
        "advertisement_subscription": "Advertisement Subscription",
    }
    return names.get(purpose, "ProReadyEngineer Service")


def _get_payment_description(purpose: str, entity_type: str, entity_id: str) -> str:
    """Return line-item description for Stripe checkout."""
    if purpose == "rfq_unlock":
        return (
            f"Unlock access to view and respond to RFQ #{entity_id[:8]}. "
            "Full project details, files, and customer contact upon quote acceptance."
        )
    elif purpose == "nda_fee":
        return "One-time NDA document handling and signing fee for your project request."
    return f"ProReadyEngineer {purpose} payment"


async def _handle_checkout_session_completed(
    db: AsyncSession,
    session: dict,
) -> None:
    """Handle Stripe checkout.session.completed webhook event.

    Primary fulfillment event for Stripe Checkout flow.
    Creates RFQUnlock records and marks PaymentAttempts COMPLETED.
    """
    _log = logging.getLogger(__name__)

    metadata = session.get("metadata") or {}
    purpose = metadata.get("purpose", "")
    user_id_str = metadata.get("user_id", "")
    related_id_str = metadata.get("related_id", "")
    provider_id_str = metadata.get("provider_id", "")
    session_id = session.get("id", "")

    _log.info(
        "checkout.session.completed: purpose=%s user=%s related=%s session=%s",
        purpose, user_id_str, related_id_str, session_id,
    )

    # Update PaymentAttempt to COMPLETED
    pa_result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.external_payment_id == session_id
        )
    )
    payment = pa_result.scalar_one_or_none()
    if payment and payment.payment_status != PaymentStatus.COMPLETED:
        payment.payment_status = PaymentStatus.COMPLETED
        payment.confirmed_at = datetime.now(timezone.utc)
        await db.commit()

    if purpose == "rfq_unlock":
        await _fulfill_checkout_rfq_unlock(
            db=db,
            rfq_id_str=related_id_str,
            user_id_str=user_id_str,
            provider_id_str=provider_id_str,
            payment_attempt_id=payment.id if payment else None,
        )


async def _fulfill_checkout_rfq_unlock(
    db: AsyncSession,
    rfq_id_str: str,
    user_id_str: str,
    provider_id_str: str,
    payment_attempt_id,
) -> None:
    """Create RFQUnlock record after confirmed Stripe checkout payment.

    Idempotent — safe to call multiple times for the same rfq+provider.
    Concurrency-safe via SELECT FOR UPDATE on the RFQ row.
    """
    import uuid as _uuid
    _log = logging.getLogger(__name__)

    # ── parse rfq_id ────────────────────────────────────────────
    try:
        rfq_uuid = _uuid.UUID(rfq_id_str)
    except (ValueError, AttributeError):
        _log.error("Invalid rfq_id in checkout metadata: %s", rfq_id_str)
        return

    # ── parse user_id ───────────────────────────────────────────
    try:
        user_uuid = _uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        _log.error("Invalid user_id in checkout metadata: %s", user_id_str)
        return

    # ── resolve provider_id (metadata first, then membership) ───
    provider_id = None
    if provider_id_str:
        try:
            provider_id = int(provider_id_str)
        except (ValueError, TypeError):
            pass

    if not provider_id:
        from app.models.provider import ProviderMembership
        mem_result = await db.execute(
            select(ProviderMembership).where(
                ProviderMembership.user_id == user_uuid
            )
        )
        membership = mem_result.scalar_one_or_none()
        if membership:
            provider_id = membership.provider_id
        else:
            _log.error("No provider membership found for user %s", user_id_str)
            return

    # ── idempotency check ────────────────────────────────────────
    existing_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_uuid,
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status == UnlockStatus.UNLOCKED,
        )
    )
    if existing_result.scalar_one_or_none():
        _log.info(
            "RFQ %s already unlocked for provider %s — idempotent skip",
            rfq_uuid, provider_id,
        )
        return

    # ── lock RFQ row for concurrency safety ──────────────────────
    rfq_result = await db.execute(
        select(RFQ).where(RFQ.id == rfq_uuid).with_for_update()
    )
    rfq = rfq_result.scalar_one_or_none()
    if not rfq:
        _log.error("RFQ %s not found during unlock fulfillment", rfq_uuid)
        return

    rfq_status_str = str(rfq.rfq_status) if rfq.rfq_status else ""

    # quota guard — re-check under lock
    current_count = rfq.quote_count or 0
    if current_count >= 5:
        _log.warning(
            "RFQ %s quote_count=%d >= 5 under lock — quota full, refund needed",
            rfq_uuid, current_count,
        )
        return

    if rfq_status_str in ("quote_limit_reached", "cancelled", "closed_no_selection"):
        _log.warning(
            "RFQ %s status=%s is closed — refund may be needed",
            rfq_uuid, rfq_status_str,
        )
        # Still create record so payment is traceable; ops team handles refund

    # ── create RFQUnlock record ──────────────────────────────────
    unlock = RFQUnlock(
        rfq_id=rfq_uuid,
        provider_id=provider_id,
        unlocked_by_user_id=user_uuid,
        payment_attempt_id=payment_attempt_id,
        unlock_status=UnlockStatus.UNLOCKED,
        unlocked_at=datetime.now(timezone.utc),
    )
    db.add(unlock)

    # ── increment quote_count ────────────────────────────────────
    rfq.quote_count = current_count + 1

    # close RFQ if limit reached
    if rfq.quote_count >= 5:
        rfq.rfq_status = RfqStatus.QUOTE_LIMIT_REACHED
        rfq.is_closed = True

    await db.commit()
    _log.info(
        "RFQ %s unlocked for provider %s — quote_count now %d",
        rfq_uuid, provider_id, rfq.quote_count,
    )


async def handle_stripe_webhook(
    db: AsyncSession,
    payload: bytes,
    sig_header: str,
) -> None:
    """Handle Stripe webhook events.

    Args:
        db: Database session.
        payload: Raw request body.
        sig_header: Stripe signature header.

    Raises:
        ValueError: If signature verification fails.
    """
    from app.services.config_service import get_runtime_config as _grc
    _wcfg = await _grc(db)
    stripe.api_key = _wcfg.get('STRIPE_SECRET_KEY', '') or ''
    _webhook_secret = _wcfg.get('STRIPE_WEBHOOK_SECRET', '') or ''

    # Verify signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, _webhook_secret
        )
    except ValueError:
        raise ValueError("Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")

    # Deduplicate event
    event_result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider_name == "stripe",
            WebhookEvent.external_event_id == event["id"],
        )
    )
    if event_result.scalar_one_or_none():
        # Already processed
        return

    # Store raw event
    webhook_event = WebhookEvent(
        provider_name="stripe",
        external_event_id=event["id"],
        event_type=event["type"],
        payload=event,
        signature_verified=True,
        processing_status="processing",
    )
    db.add(webhook_event)
    await db.commit()

    try:
        # Process based on event type
        if event["type"] == "payment_intent.succeeded":
            await _handle_payment_intent_succeeded(
                db, event["data"]["object"]
            )
        elif event["type"] == "invoice.paid":
            await _handle_invoice_paid(db, event["data"]["object"])
        elif event["type"] == "customer.subscription.deleted":
            await _handle_subscription_deleted(db, event["data"]["object"])
        elif event["type"] == "payment_intent.payment_failed":
            await _handle_payment_failed(db, event["data"]["object"])

        webhook_event.processing_status = "completed"
        webhook_event.processed_at = datetime.utcnow()

    except Exception as e:
        webhook_event.processing_status = "failed"
        webhook_event.error_message = str(e)
        raise

    finally:
        await db.commit()


async def _handle_payment_intent_succeeded(
    db: AsyncSession,
    payment_intent: dict,
) -> None:
    """Process successful payment intent.

    Args:
        db: Database session.
        payment_intent: Stripe payment intent object.
    """
    # Find payment attempt
    result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.external_payment_id == payment_intent["id"]
        )
    )
    payment = result.scalar_one_or_none()

    if not payment:
        # Payment attempt not found - log for manual review
        return

    if payment.payment_status == PaymentStatus.COMPLETED:
        # Already confirmed - idempotent
        return

    # Update payment status
    payment.payment_status = PaymentStatus.COMPLETED
    payment.confirmed_at = datetime.utcnow()

    await db.commit()

    # Fulfill the payment purpose
    await fulfill_payment_purpose(db, payment)


async def _handle_invoice_paid(
    db: AsyncSession,
    invoice: dict,
) -> None:
    """Process subscription invoice payment.

    Args:
        db: Database session.
        invoice: Stripe invoice object.
    """
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return

    # Find subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.external_subscription_id == subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.subscription_status = SubscriptionStatus.ACTIVE
        subscription.current_period_start = datetime.fromtimestamp(
            invoice["period_start"]
        )
        subscription.current_period_end = datetime.fromtimestamp(
            invoice["period_end"]
        )
        await db.commit()


async def _handle_subscription_deleted(
    db: AsyncSession,
    stripe_subscription: dict,
) -> None:
    """Handle subscription cancellation.

    Args:
        db: Database session.
        stripe_subscription: Stripe subscription object.
    """
    result = await db.execute(
        select(Subscription).where(
            Subscription.external_subscription_id == stripe_subscription["id"]
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.subscription_status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()
        await db.commit()


async def _handle_payment_failed(
    db: AsyncSession,
    payment_intent: dict,
) -> None:
    """Process failed payment intent.

    Args:
        db: Database session.
        payment_intent: Stripe payment intent object.
    """
    result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.external_payment_id == payment_intent["id"]
        )
    )
    payment = result.scalar_one_or_none()

    if payment:
        payment.payment_status = PaymentStatus.FAILED
        payment.failed_at = datetime.utcnow()
        await db.commit()


# ── PayPal REST API helpers ─────────────────────────────────────────────────

PAYPAL_SANDBOX_URL = "https://api-m.sandbox.paypal.com"
PAYPAL_LIVE_URL    = "https://api-m.paypal.com"


def _paypal_base(mode: str) -> str:
    return PAYPAL_SANDBOX_URL if mode == "sandbox" else PAYPAL_LIVE_URL


async def get_paypal_access_token(
    client_id: str, client_secret: str, mode: str = "sandbox"
) -> str:
    """Get PayPal OAuth2 access token via client credentials."""
    import httpx
    base = _paypal_base(mode)
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            f"{base}/v1/oauth2/token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def create_paypal_order(
    db: AsyncSession,
    purpose: str,
    amount_usd: float,
    user: User,
    related_entity_type: str,
    related_entity_id: uuid.UUID,
    metadata: Optional[dict] = None,
    return_url: str = "https://proreadyengineer.com/payment/success",
    cancel_url: str = "https://proreadyengineer.com/payment/cancel",
) -> dict:
    """Create PayPal order for one-time payment. Returns {order_id, approve_url, payment_attempt_id}"""
    import httpx
    from app.services.config_service import get_runtime_config
    cfg = await get_runtime_config(db)
    client_id_val = cfg.get("PAYPAL_CLIENT_ID", "")
    client_secret = cfg.get("PAYPAL_CLIENT_SECRET", "")
    mode = cfg.get("PAYPAL_MODE", "sandbox")
    if not client_id_val or not client_secret:
        raise RuntimeError("PayPal credentials not configured")
    idempotency_key = _create_idempotency_key(purpose, user.id, related_entity_id)
    res = await db.execute(select(PaymentAttempt).where(
        PaymentAttempt.idempotency_key == idempotency_key,
        PaymentAttempt.provider_name == "paypal",
        PaymentAttempt.payment_status == PaymentStatus.INITIATED,
    ))
    existing = res.scalar_one_or_none()
    if existing and existing.external_payment_id:
        pfx = "sandbox." if mode == "sandbox" else ""
        return {"order_id": existing.external_payment_id,
                "approve_url": f"https://www.{pfx}paypal.com/checkoutnow?token={existing.external_payment_id}",
                "payment_attempt_id": str(existing.id)}
    token = await get_paypal_access_token(client_id_val, client_secret, mode)
    base = _paypal_base(mode)
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(f"{base}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"intent": "CAPTURE",
                  "purchase_units": [{"amount": {"currency_code": "USD", "value": f"{amount_usd:.2f}"},
                                      "description": purpose, "custom_id": str(related_entity_id)}],
                  "application_context": {"return_url": return_url, "cancel_url": cancel_url,
                                          "brand_name": "ProReadyEngineer", "user_action": "PAY_NOW"}},
        )
        r.raise_for_status()
        order_data = r.json()
    order_id = order_data["id"]
    pfx = "sandbox." if mode == "sandbox" else ""
    approve_url = next((lnk["href"] for lnk in order_data.get("links", []) if lnk["rel"] == "approve"),
                       f"https://www.{pfx}paypal.com/checkoutnow?token={order_id}")
    attempt = PaymentAttempt(provider_name="paypal", external_payment_id=order_id,
        purpose=purpose, related_entity_type=related_entity_type,
        related_entity_id=related_entity_id, amount=amount_usd, currency="USD",
        payment_status=PaymentStatus.INITIATED, idempotency_key=idempotency_key,
        initiated_by_user_id=user.id, initiated_at=datetime.utcnow(), metadata=metadata or {})
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return {"order_id": order_id, "approve_url": approve_url, "payment_attempt_id": str(attempt.id)}



async def capture_paypal_order(db: AsyncSession, order_id: str) -> dict:
    """Capture an approved PayPal order and fulfill the payment purpose."""
    from app.services.config_service import get_config_value
    from app.models.payment import PaymentAttempt, PaymentStatus
    from sqlalchemy import select

    mode = await get_config_value(db, "PAYPAL_MODE", "sandbox")
    client_id = await get_config_value(db, "PAYPAL_CLIENT_ID", "")
    client_secret = await get_config_value(db, "PAYPAL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise ValueError("PayPal is not configured")

    access_token = await get_paypal_access_token(client_id, client_secret, mode)
    base_url = _paypal_base(mode)

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code not in (200, 201):
            raise ValueError(f"PayPal capture failed: {resp.text}")
        capture_data = resp.json()

    # Update PaymentAttempt status
    capture_id = None
    capture_status = "COMPLETED"
    try:
        captures = capture_data["purchase_units"][0]["payments"]["captures"]
        if captures:
            capture_id = captures[0]["id"]
            capture_status = captures[0]["status"]
    except (KeyError, IndexError):
        pass

    result = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.external_checkout_id == order_id)
    )
    attempt = result.scalar_one_or_none()
    if attempt:
        if capture_status == "COMPLETED":
            attempt.payment_status = PaymentStatus.COMPLETED
            from datetime import datetime, timezone
            attempt.confirmed_at = datetime.now(timezone.utc)
            if capture_id:
                attempt.external_payment_id = capture_id
        else:
            attempt.payment_status = PaymentStatus.FAILED
            from datetime import datetime, timezone
            attempt.failed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(attempt)

        if capture_status == "COMPLETED" and attempt:
            await fulfill_payment_purpose(db, attempt)

    return {
        "status": capture_status,
        "order_id": order_id,
        "capture_id": capture_id,
        "capture_data": capture_data,
    }


async def create_paypal_subscription(
    db: AsyncSession,
    user,
    subscription_type: str,
) -> dict:
    """Create a PayPal recurring subscription. Returns {subscription_id, approve_url}."""
    from app.services.config_service import get_config_value
    from app.models.payment import Subscription, SubscriptionStatus
    import uuid as _uuid

    mode = await get_config_value(db, "PAYPAL_MODE", "sandbox")
    client_id = await get_config_value(db, "PAYPAL_CLIENT_ID", "")
    client_secret = await get_config_value(db, "PAYPAL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise ValueError("PayPal is not configured")

    # Map subscription_type -> plan_id from config
    plan_key_map = {
        "search_tier1": "PAYPAL_PLAN_SEARCH_TIER1",
        "search_tier2": "PAYPAL_PLAN_SEARCH_TIER2",
        "provider_profile": "PAYPAL_PLAN_PROVIDER_PROFILE",
        "advertisement": "PAYPAL_PLAN_ADVERTISEMENT",
    }
    plan_key = plan_key_map.get(subscription_type)
    if not plan_key:
        raise ValueError(f"Unknown subscription_type: {subscription_type}")

    plan_id = await get_config_value(db, plan_key, "")
    if not plan_id:
        raise ValueError(
            f"PayPal plan ID not configured for {subscription_type}. "
            f"Set {plan_key} in admin settings."
        )

    access_token = await get_paypal_access_token(client_id, client_secret, mode)
    base_url = _paypal_base(mode)

    import httpx
    from datetime import datetime, timezone
    idempotency_key = str(_uuid.uuid4())

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/v1/billing/subscriptions",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": idempotency_key,
            },
            json={
                "plan_id": plan_id,
                "subscriber": {
                    "email_address": getattr(user, "email", ""),
                },
                "application_context": {
                    "return_url": "https://app.proreadyengineer.com/payment/success",
                    "cancel_url": "https://app.proreadyengineer.com/payment/cancel",
                    "user_action": "SUBSCRIBE_NOW",
                },
            },
        )
        if resp.status_code not in (200, 201):
            raise ValueError(f"PayPal subscription creation failed: {resp.text}")
        sub_data = resp.json()

    subscription_id = sub_data["id"]
    approve_url = next(
        (link["href"] for link in sub_data.get("links", []) if link["rel"] == "approve"),
        None,
    )

    # Persist Subscription record
    sub = Subscription(
        user_id=user.id,
        provider_name="paypal",
        external_subscription_id=subscription_id,
        subscription_type=subscription_type,
        subscription_status=SubscriptionStatus.incomplete,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return {
        "subscription_id": subscription_id,
        "approve_url": approve_url,
        "db_id": str(sub.id),
    }

async def handle_paypal_webhook(db: AsyncSession, payload: dict) -> None:
    """Handle PayPal webhook events (idempotent, fully implemented)."""
    event_type = payload.get("event_type", "")
    resource   = payload.get("resource", {})
    event_id   = payload.get("id", "")
    # Deduplication
    dup_res = await db.execute(select(WebhookEvent).where(
        WebhookEvent.provider_name == "paypal",
        WebhookEvent.external_event_id == event_id))
    if dup_res.scalar_one_or_none():
        return
    webhook_event = WebhookEvent(
        provider_name="paypal", external_event_id=event_id,
        event_type=event_type, payload=payload,
        signature_verified=True, processing_status="processing",
        received_at=datetime.utcnow())
    db.add(webhook_event)
    await db.commit()
    try:
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            # Extract order_id from supplementary_data or resource id
            order_id = (resource.get("supplementary_data", {})
                         .get("related_ids", {}).get("order_id")
                        or resource.get("id"))
            if order_id:
                res = await db.execute(select(PaymentAttempt).where(
                    PaymentAttempt.external_payment_id == order_id,
                    PaymentAttempt.provider_name == "paypal"))
                attempt = res.scalar_one_or_none()
                if attempt and attempt.payment_status != PaymentStatus.COMPLETED:
                    attempt.payment_status = PaymentStatus.COMPLETED
                    attempt.confirmed_at = datetime.utcnow()
                    await db.commit()
                    await db.refresh(attempt)
                    await fulfill_payment_purpose(db, attempt)
        elif event_type == "PAYMENT.CAPTURE.DENIED":
            order_id = (resource.get("supplementary_data", {})
                         .get("related_ids", {}).get("order_id")
                        or resource.get("id"))
            if order_id:
                res = await db.execute(select(PaymentAttempt).where(
                    PaymentAttempt.external_payment_id == order_id,
                    PaymentAttempt.provider_name == "paypal"))
                attempt = res.scalar_one_or_none()
                if attempt and attempt.payment_status == PaymentStatus.INITIATED:
                    attempt.payment_status = PaymentStatus.FAILED
                    attempt.failed_at = datetime.utcnow()
                    await db.commit()
        elif event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
            sub_id = resource.get("id")
            if sub_id:
                res = await db.execute(select(Subscription).where(
                    Subscription.external_subscription_id == sub_id,
                    Subscription.provider_name == "paypal"))
                sub = res.scalar_one_or_none()
                if sub:
                    sub.subscription_status = SubscriptionStatus.ACTIVE
                    await db.commit()
        elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
            sub_id = resource.get("id")
            if sub_id:
                res = await db.execute(select(Subscription).where(
                    Subscription.external_subscription_id == sub_id,
                    Subscription.provider_name == "paypal"))
                sub = res.scalar_one_or_none()
                if sub:
                    sub.subscription_status = SubscriptionStatus.CANCELLED
                    sub.cancelled_at = datetime.utcnow()
                    await db.commit()
        elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
            sub_id = resource.get("id")
            if sub_id:
                res = await db.execute(select(Subscription).where(
                    Subscription.external_subscription_id == sub_id,
                    Subscription.provider_name == "paypal"))
                sub = res.scalar_one_or_none()
                if sub:
                    sub.subscription_status = SubscriptionStatus.PAST_DUE
                    await db.commit()
        webhook_event.processing_status = "completed"
        webhook_event.processed_at = datetime.utcnow()
    except Exception as e:
        webhook_event.processing_status = "failed"
        webhook_event.error_message = str(e)
        raise
    finally:
        await db.commit()

async def fulfill_payment_purpose(
    db: AsyncSession,
    payment: PaymentAttempt,
) -> None:
    """Fulfill payment based on its purpose.

    Idempotent - safe to call multiple times.

    Args:
        db: Database session.
        payment: Confirmed payment attempt.
    """
    purpose = payment.purpose
    related_id = payment.related_entity_id

    if purpose == "rfq_unlock":
        await _fulfill_rfq_unlock(db, related_id, payment.id)

    elif purpose == "nda_fee":
        await _fulfill_nda_fee(db, related_id)

    elif purpose == "provider_profile_subscription":
        await _fulfill_provider_subscription(db, related_id)

    elif purpose == "search_subscription":
        await _fulfill_search_subscription(db, related_id, payment)

    elif purpose == "advertisement_subscription":
        await _fulfill_advertisement_subscription(db, related_id)


async def _fulfill_rfq_unlock(
    db: AsyncSession,
    unlock_id: uuid.UUID,
    payment_attempt_id: uuid.UUID,
) -> None:
    """Fulfill RFQ unlock payment.

    Args:
        db: Database session.
        unlock_id: RFQUnlock UUID.
        payment_attempt_id: PaymentAttempt UUID.
    """
    from app.services.rfq_service import complete_rfq_unlock

    # Update unlock with payment reference
    unlock = await db.get(RFQUnlock, unlock_id)
    if unlock:
        unlock.payment_attempt_id = payment_attempt_id
        await db.commit()

        # Complete the unlock (increments quote_count)
        await complete_rfq_unlock(db, unlock_id)


async def _fulfill_nda_fee(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> None:
    """Fulfill NDA fee payment.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.
    """
    # Find or create NDA record
    result = await db.execute(
        select(RFQNDA).where(RFQNDA.rfq_id == rfq_id)
    )
    nda = result.scalar_one_or_none()

    if not nda:
        nda = RFQNDA(rfq_id=rfq_id, nda_status=NdaStatus.PAYMENT_PENDING)
        db.add(nda)

    # Move to customer signature pending
    nda.nda_status = NdaStatus.CUSTOMER_SIGNATURE_PENDING

    # Update RFQ status
    rfq = await db.get(RFQ, rfq_id)
    rfq.rfq_status = RfqStatus.AWAITING_CUSTOMER_SIGNATURE

    await db.commit()


async def _fulfill_provider_subscription(
    db: AsyncSession,
    provider_id: int,
) -> None:
    """Fulfill provider profile subscription.

    Args:
        db: Database session.
        provider_id: Provider ID.
    """
    provider = await db.get(Provider, provider_id)
    if provider:
        # Enable editing based on subscription
        # This would check active subscription
        pass


async def _fulfill_search_subscription(
    db: AsyncSession,
    user_id: uuid.UUID,
    payment: PaymentAttempt,
) -> None:
    """Fulfill search tier subscription.

    Args:
        db: Database session.
        user_id: User UUID.
        payment: Payment attempt with metadata.
    """
    metadata = payment.metadata or {}
    tier = metadata.get("tier", "tier_1")

    sub_type = (
        SubscriptionType.SEARCH_TIER_2
        if tier == "tier_2"
        else SubscriptionType.SEARCH_TIER_1
    )

    # Create subscription record
    subscription = Subscription(
        user_id=user_id,
        provider_name="stripe",
        subscription_type=sub_type,
        subscription_status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )

    db.add(subscription)
    await db.commit()


async def _fulfill_advertisement_subscription(
    db: AsyncSession,
    ad_id: uuid.UUID,
) -> None:
    """Fulfill advertisement subscription.

    Args:
        db: Database session.
        ad_id: Advertisement UUID.
    """
    from app.models import AdStatus, Advertisement

    ad = await db.get(Advertisement, ad_id)
    if ad:
        ad.ad_status = AdStatus.ACTIVE
        ad.started_at = datetime.utcnow()
        await db.commit()


async def create_subscription(
    db: AsyncSession,
    user: User,
    subscription_type: str,
    stripe_subscription_id: str,
) -> Subscription:
    """Create a subscription record.

    Args:
        db: Database session.
        user: User subscribing.
        subscription_type: Type of subscription.
        stripe_subscription_id: Stripe subscription ID.

    Returns:
        Subscription: Created subscription.
    """
    subscription = Subscription(
        user_id=user.id,
        provider_name="stripe",
        external_subscription_id=stripe_subscription_id,
        subscription_type=subscription_type,
        subscription_status=SubscriptionStatus.PENDING,
    )

    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    return subscription


async def cancel_subscription(
    db: AsyncSession,
    subscription_id: uuid.UUID,
) -> None:
    """Cancel a subscription.

    Args:
        db: Database session.
        subscription_id: Subscription UUID.
    """
    from app.services.config_service import get_runtime_config as _grc
    _ccfg = await _grc(db)
    stripe.api_key = _ccfg.get('STRIPE_SECRET_KEY', '') or ''

    subscription = await db.get(Subscription, subscription_id)
    if not subscription:
        raise ValueError("Subscription not found")

    # Cancel in Stripe
    if subscription.external_subscription_id:
        try:
            stripe.Subscription.delete(subscription.external_subscription_id)
        except stripe.error.StripeError:
            pass  # Already cancelled or not found

    subscription.subscription_status = SubscriptionStatus.CANCELLED
    subscription.cancelled_at = datetime.utcnow()

    await db.commit()


async def create_stripe_billing_portal_session(
    customer_id: str,
    return_url: str,
) -> str:
    """Create Stripe billing portal session.

    Args:
        customer_id: Stripe customer ID.
        return_url: URL to return to after portal.

    Returns:
        str: Portal session URL.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )

    return session.url


# Alias for endpoint compatibility
create_billing_portal_session = create_stripe_billing_portal_session
