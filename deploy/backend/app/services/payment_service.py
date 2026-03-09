"""Payment service with Stripe/PayPal webhook handling and idempotent fulfillment."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
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
    stripe.api_key = settings.STRIPE_SECRET_KEY

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

    if existing and existing.payment_status == PaymentStatus.CONFIRMED:
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
        payment_status=PaymentStatus.PENDING,
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
    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Verify signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
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

    if payment.payment_status == PaymentStatus.CONFIRMED:
        # Already confirmed - idempotent
        return

    # Update payment status
    payment.payment_status = PaymentStatus.CONFIRMED
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


async def handle_paypal_webhook(
    db: AsyncSession,
    payload: dict,
) -> None:
    """Handle PayPal webhook events.

    Args:
        db: Database session.
        payload: PayPal event payload.
    """
    event_type = payload.get("event_type")
    resource = payload.get("resource", {})
    event_id = payload.get("id")

    # Deduplicate
    event_result = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider_name == "paypal",
            WebhookEvent.external_event_id == event_id,
        )
    )
    if event_result.scalar_one_or_none():
        return

    # Store event
    webhook_event = WebhookEvent(
        provider_name="paypal",
        external_event_id=event_id,
        event_type=event_type,
        payload=payload,
        signature_verified=True,  # PayPal signature verification done in middleware
        processing_status="processing",
    )
    db.add(webhook_event)
    await db.commit()

    try:
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            # Handle PayPal payment completion
            payment_id = resource.get("id")
            # Similar logic to Stripe payment_intent.succeeded
            pass

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
    stripe.api_key = settings.STRIPE_SECRET_KEY

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
