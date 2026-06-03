"""Payment service with Stripe/PayPal webhook handling and idempotent fulfillment."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import logging

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    RFQ,
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


async def resolve_stripe_payment_intent_id(external_payment_id, external_checkout_id=None):
    """Resolve a Stripe PaymentIntent id (``pi_...``) for a payment.

    ``external_payment_id`` may itself be a PaymentIntent id (``pi_...``) OR a
    Checkout Session id (``cs_...``) depending on which flow created it. A refund
    requires the PaymentIntent, so a ``cs_`` id must be resolved via the session.
    Requires ``stripe.api_key`` to already be set. Returns ``pi_...`` or ``None``.
    """
    import stripe as _stripe
    import asyncio as _asyncio
    pid = (external_payment_id or "").strip()
    if pid.startswith("pi_"):
        return pid
    if pid.startswith("cs_"):
        try:
            sess = await _asyncio.to_thread(_stripe.checkout.Session.retrieve, pid)
            pi = getattr(sess, "payment_intent", None)
            return (pi.id if hasattr(pi, "id") else pi) if pi else None
        except Exception:
            return None
    return None


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
        extra_data=metadata,
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
    recurring_interval: Optional[str] = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session that redirects to Stripe-hosted payment page.

    Returns dict with 'checkout_url' and 'payment_attempt_id'.
    Handles duplicate idempotency keys gracefully for payment retries.
    """
    _log = logging.getLogger(__name__)

    from app.services.config_service import get_runtime_config as _grc
    _cfg = await _grc(db)
    stripe.api_key = _cfg.get('STRIPE_SECRET_KEY', '') or ''

    if not stripe.api_key:
        raise RuntimeError(
            "Stripe is not configured. Please add your Stripe secret key in admin settings."
        )

    # Step 1: Compute idempotency key first
    idempotency_key = _create_idempotency_key(purpose, user.id, related_id)

    # Step 2: Check for existing PaymentAttempt with this key
    existing_result = await db.execute(
        select(PaymentAttempt).where(
            PaymentAttempt.idempotency_key == idempotency_key,
        )
    )
    existing_payment = existing_result.scalar_one_or_none()

    if existing_payment:
        _log.info(
            "Found existing PaymentAttempt %s with status %s for idempotency_key %s",
            existing_payment.id, existing_payment.payment_status, idempotency_key,
        )

        # Step 4: If COMPLETED, return already_paid immediately
        if existing_payment.payment_status == PaymentStatus.COMPLETED:
            _log.info("Payment %s already COMPLETED - returning already_paid", existing_payment.id)
            return {
                "checkout_url": "",
                "already_paid": True,
                "payment_attempt_id": str(existing_payment.id),
            }

        # Step 3: If INITIATED or PROCESSING, check Stripe session status
        if existing_payment.payment_status in (PaymentStatus.INITIATED, PaymentStatus.PROCESSING):
            stripe_session_id = existing_payment.external_payment_id
            if stripe_session_id:
                try:
                    existing_session = stripe.checkout.Session.retrieve(stripe_session_id)

                    # 3a: If Stripe session is paid, fulfill the unlock
                    if existing_session.payment_status == "paid":
                        _log.info(
                            "Stripe session %s is paid but PaymentAttempt %s not COMPLETED - fulfilling now",
                            stripe_session_id, existing_payment.id,
                        )
                        existing_payment.payment_status = PaymentStatus.COMPLETED
                        existing_payment.confirmed_at = datetime.now(timezone.utc)
                        await db.commit()

                        # Fulfill the unlock
                        if purpose == "rfq_unlock":
                            provider_id_str = (metadata or {}).get("provider_id", "")
                            await _fulfill_checkout_rfq_unlock(
                                db=db,
                                rfq_id_str=str(related_id),
                                user_id_str=str(user.id),
                                provider_id_str=provider_id_str,
                                payment_attempt_id=existing_payment.id,
                            )

                        return {
                            "checkout_url": "",
                            "already_paid": True,
                            "payment_attempt_id": str(existing_payment.id),
                        }

                    # 3b: If Stripe session is still active (not expired), return existing URL
                    if existing_session.status != "expired":
                        _log.info(
                            "Stripe session %s still active (status=%s) - returning existing checkout URL",
                            stripe_session_id, existing_session.status,
                        )
                        checkout_url = existing_payment.external_checkout_id or existing_session.url
                        return {
                            "checkout_url": checkout_url,
                            "payment_attempt_id": str(existing_payment.id),
                            "session_id": stripe_session_id,
                        }

                    # 3c: Stripe session is expired - create NEW session, UPDATE existing record
                    _log.info(
                        "Stripe session %s expired - creating new session and updating PaymentAttempt %s",
                        stripe_session_id, existing_payment.id,
                    )
                    try:
                        new_session = stripe.checkout.Session.create(
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
                        raise RuntimeError(f"Stripe error creating replacement session: {e}")

                    # Update existing PaymentAttempt row instead of inserting new one
                    existing_payment.external_payment_id = new_session.id
                    existing_payment.external_checkout_id = new_session.url
                    existing_payment.payment_status = PaymentStatus.INITIATED
                    existing_payment.extra_data = metadata
                    await db.commit()
                    await db.refresh(existing_payment)

                    return {
                        "checkout_url": new_session.url,
                        "payment_attempt_id": str(existing_payment.id),
                        "session_id": new_session.id,
                    }

                except stripe.error.StripeError as e:
                    _log.warning(
                        "Could not retrieve Stripe session %s: %s - will create new session",
                        stripe_session_id, e,
                    )
                    # Fall through to create new session below, updating the existing record

    # Step 5: No existing payment attempt, OR existing one is FAILED/REFUNDED/DISPUTED
    # For FAILED payments, update existing record; otherwise create new.
    # If recurring_interval is set (e.g. 'month'), use mode='subscription'
    # so Stripe bills the customer automatically every period.
    price_data_block = {
        "currency": currency.lower(),
        "product_data": {
            "name": _get_payment_product_name(purpose),
            "description": _get_payment_description(
                purpose, related_entity_type, str(related_id)
            ),
        },
        "unit_amount": amount,
    }
    session_mode = "payment"
    subscription_extra: dict = {}
    if recurring_interval:
        price_data_block["recurring"] = {"interval": recurring_interval}
        session_mode = "subscription"
        # Propagate metadata to the underlying Stripe Subscription so the
        # subscription.* webhooks can resolve back to our DB rows.
        subscription_extra = {
            "subscription_data": {
                "metadata": {
                    "purpose": purpose,
                    "user_id": str(user.id),
                    "related_entity_type": related_entity_type,
                    "related_id": str(related_id),
                    **(metadata or {}),
                },
            }
        }
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": price_data_block,
                "quantity": 1,
            }],
            mode=session_mode,
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
            **subscription_extra,
        )
    except stripe.error.StripeError as e:
        raise RuntimeError(f"Stripe error: {e}")

    # Convert related_id to UUID if it's a string
    import uuid as _uuid_mod
    try:
        related_entity_uuid = _uuid_mod.UUID(str(related_id)) if related_id else None
    except (ValueError, AttributeError):
        related_entity_uuid = None

    # If existing payment was FAILED, update it instead of creating new row
    if existing_payment and existing_payment.payment_status == PaymentStatus.FAILED:
        _log.info("Updating FAILED PaymentAttempt %s with new session", existing_payment.id)
        existing_payment.external_payment_id = session.id
        existing_payment.external_checkout_id = session.url
        existing_payment.payment_status = PaymentStatus.INITIATED
        existing_payment.extra_data = metadata
        await db.commit()
        await db.refresh(existing_payment)
        return {
            "checkout_url": session.url,
            "payment_attempt_id": str(existing_payment.id),
            "session_id": session.id,
        }

    # Create brand new payment attempt record
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
        extra_data=metadata,
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
        "provider_annual_subscription": "Annual Professional - $1,000/year",
        "search_subscription": "Search Subscription",
        "advertisement_subscription": "Advertisement Subscription",
        "full_profile_edit_unlock": "Full Profile Edit - One Time Unlock",
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
    elif purpose == "provider_annual_subscription":
        return (
            "Annual Professional membership: free RFQ access, unlimited profile updates, "
            "rank-up eligibility, and priority dispatch. Valid for 12 months."
        )
    elif purpose == "full_profile_edit_unlock":
        return "One-time payment to unlock all 17 profile fields for editing."
    return f"ProReadyEngineer {purpose} payment"


async def _handle_checkout_session_completed(
    db: AsyncSession,
    session: dict,
) -> None:
    """Handle Stripe checkout.session.completed webhook event.

    Primary fulfillment event for Stripe Checkout flow.
    Routes to the correct fulfillment function based on payment purpose.
    Handles: rfq_unlock, nda_fee, provider_annual_subscription,
             search_subscription, full_profile_edit_unlock, advertisement_subscription.
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

    # --- Mark PaymentAttempt COMPLETED (idempotent) ---
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
        await db.refresh(payment)

    if not payment:
        _log.warning(
            "checkout.session.completed: no PaymentAttempt found for session_id=%s purpose=%s",
            session_id, purpose,
        )
        # Still attempt direct fulfillment for rfq_unlock and nda_fee using metadata
        if purpose == "rfq_unlock":
            await _fulfill_checkout_rfq_unlock(
                db=db,
                rfq_id_str=related_id_str,
                user_id_str=user_id_str,
                provider_id_str=provider_id_str,
                payment_attempt_id=None,
            )
        elif purpose == "nda_fee":
            import uuid as _uuid
            try:
                rfq_uuid = _uuid.UUID(related_id_str)
                await _fulfill_nda_fee(db, rfq_uuid)
            except Exception as e:
                _log.error("Failed to fulfill nda_fee (no payment record): %s", e)
        return

    # --- Route to fulfillment function based on purpose ---
    await fulfill_payment_purpose(db, payment, stripe_session=session)


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

    # quota guard — re-check under lock using actual submitted quote count
    from sqlalchemy import func
    from app.models.quote import Quote as QuoteModel
    submitted_count_result = await db.execute(
        select(func.count()).select_from(QuoteModel).where(
            QuoteModel.rfq_id == rfq_uuid,
            QuoteModel.quote_status.in_(["submitted", "accepted"])
        )
    )
    submitted_count = submitted_count_result.scalar() or 0
    if submitted_count >= 5:
        _log.warning(
            "RFQ %s already has %d submitted quotes — quota full",
            rfq_uuid, submitted_count,
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

    await db.commit()
    _log.info(
        "RFQ %s unlocked for provider %s",
        rfq_uuid, provider_id,
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
        elif event["type"] == "customer.subscription.updated":
            await _handle_subscription_updated(db, event["data"]["object"])
        elif event["type"] == "payment_intent.payment_failed":
            await _handle_payment_failed(db, event["data"]["object"])
        elif event["type"] == "checkout.session.completed":
            await _handle_checkout_session_completed(db, event["data"]["object"])
        elif event["type"] in ("charge.refunded", "charge.refund.updated"):
            await _handle_charge_refunded(db, event["data"]["object"])

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


async def _handle_charge_refunded(db: AsyncSession, charge: dict) -> None:
    """Mark the matching PaymentAttempt refunded when a Stripe refund happens — including
    refunds issued directly in the Stripe dashboard — so Payment Monitoring reflects every
    refund. Only flips on a FULL refund; partial refunds leave the record. Idempotent."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    pi = charge.get("payment_intent")
    if not pi:
        return
    if not charge.get("refunded"):  # full-refund flag; skip partials
        return
    result = await db.execute(
        select(PaymentAttempt).where(PaymentAttempt.external_payment_id == pi)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        _log.info("charge.refunded: no PaymentAttempt for payment_intent=%s", pi)
        return
    if payment.payment_status == PaymentStatus.REFUNDED:
        return
    payment.payment_status = PaymentStatus.REFUNDED
    for _attr in ("refunded_at", "confirmed_at"):
        if hasattr(payment, _attr) and _attr == "refunded_at":
            setattr(payment, _attr, datetime.utcnow())
    await db.commit()
    _log.info("charge.refunded: PaymentAttempt %s marked refunded (pi=%s)", payment.id, pi)


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

    Stripe fires customer.subscription.deleted AFTER the final period
    finishes (for cancel_at_period_end=True) or immediately (for hard
    cancel). When this fires for an ADVERTISEMENT subscription, the
    user has received everything they paid for, so the linked
    Advertisement must come down.

    Args:
        db: Database session.
        stripe_subscription: Stripe subscription object.
    """
    import logging as _log_mod
    _logd = _log_mod.getLogger(__name__)
    result = await db.execute(
        select(Subscription).where(
            Subscription.external_subscription_id == stripe_subscription["id"]
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.subscription_status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = datetime.utcnow()

        # Deactivate the linked ad (period has ended).
        if subscription.advertisement_id:
            try:
                from app.models.advertising import Advertisement as _Ad
                from app.models.enums import AdStatus as _AdStatus
                ad_row = (
                    await db.execute(
                        select(_Ad).where(_Ad.id == subscription.advertisement_id)
                    )
                ).scalar_one_or_none()
                if ad_row is not None and ad_row.ad_status != _AdStatus.CANCELLED:
                    ad_row.ad_status = _AdStatus.CANCELLED
                    ad_row.ended_at = datetime.utcnow()
                    _logd.info(
                        "subscription.deleted: deactivated ad %s after final period",
                        subscription.advertisement_id,
                    )
            except Exception as _ad_err:
                _logd.error(
                    "subscription.deleted: failed to deactivate ad %s: %s",
                    subscription.advertisement_id, _ad_err,
                )
        await db.commit()


async def _handle_subscription_updated(
    db: AsyncSession,
    stripe_subscription: dict,
) -> None:
    """Handle Stripe customer.subscription.updated webhook event.

    Updates subscription period dates and status on Stripe-driven changes
    (e.g. renewals, downgrades, cancel_at_period_end changes).
    Idempotent – safe to call multiple times.
    """
    _log = logging.getLogger(__name__)
    sub_id = stripe_subscription.get("id", "")
    new_status = stripe_subscription.get("status", "")
    cancel_at_ts = stripe_subscription.get("cancel_at")
    current_period_end_ts = stripe_subscription.get("current_period_end")
    current_period_start_ts = stripe_subscription.get("current_period_start")

    result = await db.execute(
        select(Subscription).where(
            Subscription.external_subscription_id == sub_id
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        _log.info("subscription.updated: no DB record for Stripe sub %s – skipping", sub_id)
        return

    # Map Stripe status to internal SubscriptionStatus
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELLED,
        "cancelled": SubscriptionStatus.CANCELLED,
        "unpaid": SubscriptionStatus.PAST_DUE,
        "trialing": SubscriptionStatus.ACTIVE,
    }
    mapped_status = status_map.get(new_status)
    if mapped_status:
        subscription.subscription_status = mapped_status

    if cancel_at_ts:
        subscription.cancel_at = datetime.fromtimestamp(cancel_at_ts, tz=timezone.utc)
    else:
        subscription.cancel_at = None  # cancel_at_period_end was cleared

    if current_period_start_ts:
        subscription.current_period_start = datetime.fromtimestamp(current_period_start_ts, tz=timezone.utc)
    if current_period_end_ts:
        subscription.current_period_end = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

    if new_status in ("canceled", "cancelled") and not subscription.cancelled_at:
        subscription.cancelled_at = datetime.utcnow()

    await db.commit()
    _log.info("subscription.updated: updated sub %s status=%s", sub_id, new_status)


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


async def verify_paypal_webhook_signature(db: AsyncSession, headers: dict, webhook_event: dict) -> bool:
    """Verify a PayPal webhook via PayPal's verify-webhook-signature API.

    Returns True only on a confirmed SUCCESS. Returns False if credentials or the
    webhook id are not configured, or if PayPal does not confirm the signature.
    """
    import httpx
    from app.services.config_service import get_runtime_config as _grc
    cfg = await _grc(db)
    client_id   = cfg.get("PAYPAL_CLIENT_ID", "") or ""
    client_secret = cfg.get("PAYPAL_CLIENT_SECRET", "") or ""
    webhook_id  = cfg.get("PAYPAL_WEBHOOK_ID", "") or ""
    mode        = cfg.get("PAYPAL_MODE", "sandbox") or "sandbox"
    if not (client_id and client_secret and webhook_id):
        logger.warning("PayPal webhook verification skipped: missing client id/secret/webhook id")
        return False

    def _h(name):
        # header lookup is case-insensitive
        for k, v in headers.items():
            if k.lower() == name:
                return v
        return None

    body = {
        "transmission_id":   _h("paypal-transmission-id"),
        "transmission_time": _h("paypal-transmission-time"),
        "cert_url":          _h("paypal-cert-url"),
        "auth_algo":         _h("paypal-auth-algo"),
        "transmission_sig":  _h("paypal-transmission-sig"),
        "webhook_id":        webhook_id,
        "webhook_event":     webhook_event,
    }
    if not all([body["transmission_id"], body["transmission_sig"], body["cert_url"], body["auth_algo"], body["transmission_time"]]):
        logger.warning("PayPal webhook verification failed: missing transmission headers")
        return False

    try:
        token = await get_paypal_access_token(client_id, client_secret, mode)
        base = _paypal_base(mode)
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(
                f"{base}/v1/notifications/verify-webhook-signature",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            r.raise_for_status()
            status_ = r.json().get("verification_status")
            ok = status_ == "SUCCESS"
            if not ok:
                logger.warning("PayPal webhook verification_status=%s", status_)
            return ok
    except Exception as exc:
        logger.error("PayPal webhook verification error: %s", exc)
        return False


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
        initiated_by_user_id=user.id, initiated_at=datetime.utcnow(), extra_data=metadata or {})
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

async def handle_paypal_webhook(db: AsyncSession, payload: dict, signature_verified: bool = False) -> None:
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
        signature_verified=signature_verified, processing_status="processing",
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
    stripe_session: Optional[dict] = None,
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
        await _fulfill_advertisement_subscription(db, related_id, stripe_session=stripe_session, payment=payment)

    elif purpose == "full_profile_edit_unlock":
        await _fulfill_full_profile_edit_unlock(db, payment)

    elif purpose == "provider_annual_subscription":
        await _fulfill_provider_annual_subscription(db, payment)


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

    # Track NDA progress only. Do NOT change rfq_status here: the customer NDA
    # signature is collected later (provider-triggered) and must never block
    # dispatch. Keeping the RFQ in its pre-dispatch state lets the customer's
    # follow-up submit() dispatch it normally. (Root-cause fix: previously this
    # set AWAITING_CUSTOMER_SIGNATURE, which the submit guard then rejected,
    # stranding every NDA RFQ.)
    nda.nda_status = NdaStatus.CUSTOMER_SIGNATURE_PENDING

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

    Creates/updates Subscription record and sends confirmation email.
    Idempotent – safe to call multiple times.
    """
    _log = logging.getLogger(__name__)

    metadata = payment.extra_data or {}
    # Checkout session passes 'subscription_type' in metadata (e.g. 'search_tier1')
    sub_type_raw = metadata.get("subscription_type", metadata.get("tier", "search_tier1"))
    # billing_interval determines the granted period: "year" -> 365 days, else 30 days.
    billing_interval = str(metadata.get("billing_interval", "month")).lower()
    period_days = 365 if billing_interval == "year" else 30
    # Display amount for the confirmation email ($50/mo or $500/yr).
    amount_usd = 500.00 if billing_interval == "year" else 50.00

    if sub_type_raw in ("search_tier2", "tier_2", "search_tier_2"):
        sub_type = SubscriptionType.SEARCH_TIER_2
    else:
        sub_type = SubscriptionType.SEARCH_TIER_1

    # Idempotency: check for existing active subscription of this type
    existing_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.subscription_type == sub_type,
            Subscription.subscription_status == SubscriptionStatus.ACTIVE,
        )
    )
    existing_sub = existing_result.scalar_one_or_none()
    if existing_sub:
        # Update period dates for renewal
        existing_sub.current_period_start = datetime.utcnow()
        existing_sub.current_period_end = datetime.utcnow() + timedelta(days=period_days)
        await db.commit()
        _log.info("search_subscription: renewed %s (%s) for user %s (idempotent)", sub_type, billing_interval, user_id)
        return

    # Create new subscription record
    subscription = Subscription(
        user_id=user_id,
        provider_name="stripe",
        subscription_type=sub_type,
        subscription_status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=period_days),
    )
    db.add(subscription)
    await db.commit()
    _log.info("search_subscription: activated %s (%s) for user %s", sub_type, billing_interval, user_id)

    # Send confirmation email
    try:
        from app.services.email_service import send_subscription_confirmation
        user_result = await db.execute(select(User).where(User.id == user_id))
        user_obj = user_result.scalar_one_or_none()
        if user_obj and user_obj.email:
            await send_subscription_confirmation(
                email=user_obj.email,
                subscription_type=sub_type_raw,
                amount=amount_usd,
                db=db,
            )
    except Exception as email_exc:
        _log.warning("search_subscription: failed to send confirmation email for user %s: %s", user_id, email_exc)

async def _fulfill_advertisement_subscription(
    db: AsyncSession,
    ad_id: uuid.UUID,
    stripe_session: Optional[dict] = None,
    payment: Optional[PaymentAttempt] = None,
) -> None:
    """Fulfill advertisement subscription.

    1. Flip the ad_status to ACTIVE and set started_at.
    2. Upsert a Subscription row of type ADVERTISEMENT linked to the
       user + ad. When the checkout was done in mode='subscription',
       the Stripe subscription id is on session['subscription']; we
       stash it in external_subscription_id so the
       customer.subscription.updated / .deleted / invoice.paid
       webhooks can find and update this row on each renewal.
    3. When legacy mode='payment' was used (no stripe subscription),
       we still create a Subscription row so the provider dashboard
       can display the subscription; but external_subscription_id
       stays NULL (it won't auto-renew — the one-time price only
       covers the current month).
    """
    _log = logging.getLogger(__name__)
    from app.models import AdStatus, Advertisement
    from app.models.enums import SubscriptionStatus, SubscriptionType

    ad = await db.get(Advertisement, ad_id)
    if not ad:
        _log.warning("advertisement_subscription: Advertisement %s not found", ad_id)
        return

    now = datetime.utcnow()
    ad.ad_status = AdStatus.ACTIVE
    ad.started_at = now

    stripe_sub_id = None
    if stripe_session and isinstance(stripe_session, dict):
        stripe_sub_id = stripe_session.get("subscription") or None
    if stripe_sub_id:
        ad.stripe_subscription_id = stripe_sub_id

    # Upsert a Subscription row so the dashboard can show the plan.
    # Prefer matching by stripe subscription id; fall back to (user, ad).
    owner_user_id = ad.advertiser_user_id
    if payment and getattr(payment, 'initiated_by_user_id', None):
        owner_user_id = payment.initiated_by_user_id

    existing = None
    if stripe_sub_id:
        r = await db.execute(
            select(Subscription).where(
                Subscription.external_subscription_id == stripe_sub_id,
            )
        )
        existing = r.scalar_one_or_none()
    if existing is None:
        r = await db.execute(
            select(Subscription).where(
                Subscription.advertisement_id == ad_id,
                Subscription.subscription_type == SubscriptionType.ADVERTISEMENT,
            ).order_by(Subscription.id.desc()).limit(1)
        )
        existing = r.scalar_one_or_none()

    if existing is None:
        sub_row = Subscription(
            user_id=owner_user_id,
            provider_id=ad.provider_id,
            advertisement_id=ad_id,
            provider_name="stripe",
            external_subscription_id=stripe_sub_id,
            subscription_type=SubscriptionType.ADVERTISEMENT,
            subscription_status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            # best-effort 30 days; webhook invoice.paid will overwrite
            # with the real Stripe period boundaries.
            current_period_end=now + timedelta(days=30),
        )
        db.add(sub_row)
    else:
        existing.subscription_status = SubscriptionStatus.ACTIVE
        if stripe_sub_id and not existing.external_subscription_id:
            existing.external_subscription_id = stripe_sub_id
        if not existing.current_period_start:
            existing.current_period_start = now
        if not existing.current_period_end:
            existing.current_period_end = now + timedelta(days=30)

    await db.commit()
    _log.info(
        "advertisement_subscription: ad=%s active; stripe_sub=%s; subscription row upserted",
        ad_id, stripe_sub_id or "<legacy one-time>",
    )


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


async def _fulfill_full_profile_edit_unlock(
    db,
    payment,
) -> None:
    """Fulfill full profile edit unlock payment.

    Sets provider.full_profile_edit_paid = True on confirmed payment.
    Idempotent - safe to call multiple times.
    """
    import logging
    _log = logging.getLogger(__name__)

    from sqlalchemy import select
    from app.models.provider import Provider

    # Get provider_id from payment metadata
    metadata = payment.extra_data or {}
    provider_id_str = metadata.get("provider_id")
    if not provider_id_str:
        _log.warning("full_profile_edit_unlock: no provider_id in payment metadata (payment_id=%s)", payment.id)
        return

    try:
        provider_id = int(provider_id_str)
    except (ValueError, TypeError):
        _log.warning("full_profile_edit_unlock: invalid provider_id=%s (payment_id=%s)", provider_id_str, payment.id)
        return

    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        _log.warning("full_profile_edit_unlock: provider %s not found (payment_id=%s)", provider_id, payment.id)
        return

    if provider.full_profile_edit_paid:
        _log.info("full_profile_edit_unlock: already unlocked for provider %s (idempotent)", provider_id)
        return

    provider.full_profile_edit_paid = True
    await db.commit()
    _log.info("full_profile_edit_unlock: unlocked full profile edit for provider %s (payment_id=%s)", provider_id, payment.id)

async def _fulfill_provider_annual_subscription(
    db: AsyncSession,
    payment: PaymentAttempt,
) -> None:
    """Fulfill provider annual subscription payment ($1000/year).

    Creates a Subscription record with type provider_annual and links it to the provider.
    Idempotent - safe to call multiple times.

    Args:
        db: Database session.
        payment: Confirmed payment attempt with provider_id in metadata.
    """
    import logging
    _log = logging.getLogger(__name__)

    metadata = payment.extra_data or {}
    provider_id_str = metadata.get("provider_id")
    if not provider_id_str:
        _log.warning("provider_annual_subscription: no provider_id in payment metadata (payment_id=%s)", payment.id)
        return

    try:
        provider_id = int(provider_id_str)
    except (ValueError, TypeError):
        _log.warning("provider_annual_subscription: invalid provider_id=%s (payment_id=%s)", provider_id_str, payment.id)
        return

    # Idempotency: check if active annual subscription already exists
    existing = await db.execute(
        select(Subscription).where(
            Subscription.provider_id == provider_id,
            Subscription.subscription_type == SubscriptionType.PROVIDER_ANNUAL,
            Subscription.subscription_status == SubscriptionStatus.ACTIVE,
        )
    )
    if existing.scalar_one_or_none():
        _log.info("provider_annual_subscription: already active for provider %s (idempotent)", provider_id)
        return

    subscription = Subscription(
        provider_id=provider_id,
        user_id=payment.initiated_by_user_id,
        provider_name="stripe",
        external_subscription_id=str(payment.external_payment_id or payment.id),
        subscription_type=SubscriptionType.PROVIDER_ANNUAL,
        subscription_status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=365),
    )
    db.add(subscription)
    await db.commit()
    _log.info(
        "provider_annual_subscription: activated annual subscription for provider %s (payment_id=%s)",
        provider_id, payment.id,
    )

    # Send confirmation email to the purchasing user
    try:
        from app.services.email_service import send_subscription_confirmation
        if payment.initiated_by_user_id:
            user_result = await db.execute(
                select(User).where(User.id == payment.initiated_by_user_id)
            )
            user_obj = user_result.scalar_one_or_none()
            if user_obj and user_obj.email:
                await send_subscription_confirmation(
                    email=user_obj.email,
                    subscription_type="provider_annual",
                    amount=1000.00,
                    db=db,
                )
    except Exception as email_exc:
        _log.warning(
            "provider_annual_subscription: failed to send confirmation email for user %s: %s",
            payment.initiated_by_user_id, email_exc,
        )
