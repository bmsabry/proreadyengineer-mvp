"""Payment and webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.payment_service import (
    handle_stripe_webhook, handle_paypal_webhook,
    create_billing_portal_session,
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
        return {"no_subscription": True}

    portal_url = await create_billing_portal_session(subscription.external_customer_id)
    return {"url": portal_url}






@router.get("/billing/provider-subscription-status")
async def get_provider_subscription_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get provider subscription status (annual professional plan)."""
    from sqlalchemy import select as _select
    from app.models.payment import Subscription
    result = await db.execute(
        _select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.subscription_status == "active",
            Subscription.subscription_type == "provider_annual",
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    return {
        "has_active": sub is not None,
        "subscription_type": sub.subscription_type if sub else None,
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "cancel_at": sub.cancel_at.isoformat() if sub and sub.cancel_at else None,
    }
@router.get("/billing/user-subscriptions")
async def get_user_subscriptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return ALL active subscriptions the current user holds.

    Drives the "Subscription" line in the provider / customer dashboard so
    it reflects every plan (Annual Professional, Monthly Advertisement,
    Search tier, etc.) instead of only provider_annual.

    Each item has:
      - type: internal SubscriptionType value
      - label: human-readable plan name
      - status: active | past_due | cancelled | trialing
      - current_period_end: ISO string (next renewal / expiry date)
      - cancel_at: ISO string if cancel_at_period_end is set
      - billing_interval: 'month' | 'year' | 'one_time'
      - amount_display: e.g. '$50/mo', '$1,000/yr'

    Also synthesizes a pseudo-entry for any ACTIVE Advertisement the user
    owns that has no Subscription row yet (a legacy one-time ad). The
    pseudo-entry is tagged billing_interval='one_time' so the dashboard
    can tell the user the ad will NOT auto-renew until they re-subscribe.
    """
    from sqlalchemy import select as _select
    from app.models.payment import Subscription
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus, SubscriptionStatus, SubscriptionType

    # 1) Active subscription rows.
    result = await db.execute(
        _select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.subscription_status.in_([
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
                SubscriptionStatus.TRIALING,
            ]),
        )
        .order_by(Subscription.created_at.desc() if hasattr(Subscription, 'created_at') else Subscription.id.desc())
    )
    subs = list(result.scalars().all())

    # A map so we can detect ads already covered by a subscription row.
    ads_with_subscription = {
        sub.advertisement_id for sub in subs if sub.advertisement_id
    }

    def _plan_display(st: str):
        return {
            SubscriptionType.PROVIDER_ANNUAL.value: ("Annual Professional", "year", "$1,000/yr"),
            SubscriptionType.ADVERTISEMENT.value: ("Monthly Advertisement", "month", "$50/mo"),
            SubscriptionType.SEARCH_TIER_1.value: ("Search Tier 1", "month", None),
            SubscriptionType.SEARCH_TIER_2.value: ("Search Tier 2", "month", None),
            SubscriptionType.PROVIDER_PROFILE.value: ("Provider Profile", "month", None),
        }.get(st, (st.replace("_", " ").title(), "month", None))

    items = []
    for sub in subs:
        st_val = sub.subscription_type.value if hasattr(sub.subscription_type, 'value') else str(sub.subscription_type)
        label, interval, amount = _plan_display(st_val)
        items.append({
            "id": str(sub.id),
            "type": st_val,
            "label": label,
            "status": sub.subscription_status.value if hasattr(sub.subscription_status, 'value') else str(sub.subscription_status),
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
            "cancel_at": sub.cancel_at.isoformat() if sub.cancel_at else None,
            "billing_interval": interval,
            "amount_display": amount,
            "has_stripe_subscription": bool(sub.external_subscription_id),
            "advertisement_id": str(sub.advertisement_id) if sub.advertisement_id else None,
        })

    # 2) Synthesize entries for active Advertisements not tied to a Sub row.
    ad_result = await db.execute(
        _select(Advertisement).where(
            Advertisement.advertiser_user_id == current_user.id,
            Advertisement.ad_status == AdStatus.ACTIVE,
        )
    )
    for ad in ad_result.scalars().all():
        if ad.id in ads_with_subscription:
            continue
        items.append({
            "id": f"legacy-ad-{ad.id}",
            "type": "advertisement_legacy",
            "label": "Monthly Advertisement",
            "status": "active",
            "current_period_end": None,
            "current_period_start": ad.started_at.isoformat() if ad.started_at else None,
            "cancel_at": None,
            # The legacy ad was a one-time $50 payment, so it will NOT
            # auto-renew next month. Flag it so the dashboard can warn.
            "billing_interval": "one_time",
            "amount_display": "$50 (one-time)",
            "has_stripe_subscription": False,
            "advertisement_id": str(ad.id),
            "warning": (
                "This ad was paid with a one-time $50 charge and will NOT "
                "renew automatically. Cancel and recreate to switch to "
                "monthly auto-renewing billing."
            ),
        })

    return {"subscriptions": items, "count": len(items)}


@router.get("/billing/subscription-status")
async def get_subscription_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user subscription status for customer dashboard/profile."""
    from sqlalchemy import select as _select
    from app.models.payment import Subscription
    result = await db.execute(
        _select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.subscription_status == 'active',
            Subscription.subscription_type.in_(['search_tier_1', 'search_tier_2']),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()

    # Compute NDA credits for subscribed customers (defensive - columns may not exist yet)
    try:
        from datetime import datetime, timezone as _tz
        nda_credits_total = 3 if sub else 0
        if sub:
            _now = datetime.now(_tz.utc)
            _credits_used = getattr(current_user, 'monthly_nda_credits_used', None)
            _reset_at = getattr(current_user, 'nda_credits_reset_at', None)
            if _credits_used is None:
                # Migration not yet run - columns missing, return full credits
                nda_credits_used = 0
            else:
                # Reset if new calendar month
                if _reset_at:
                    _reset_m = _reset_at.year * 12 + _reset_at.month
                    _cur_m = _now.year * 12 + _now.month
                    if _cur_m > _reset_m:
                        _credits_used = 0
                nda_credits_used = int(_credits_used)
        else:
            nda_credits_used = 0
        nda_credits_remaining = max(0, nda_credits_total - nda_credits_used)
    except Exception:
        nda_credits_total = 3 if sub else 0
        nda_credits_used = 0
        nda_credits_remaining = nda_credits_total

    return {
        "has_active": sub is not None,
        "subscription_type": sub.subscription_type if sub else None,
        "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
        "cancel_at": sub.cancel_at.isoformat() if sub and sub.cancel_at else None,
        "nda_credits_total": nda_credits_total,
        "nda_credits_used": nda_credits_used,
        "nda_credits_remaining": nda_credits_remaining,
    }
@router.post("/stripe/create-search-subscription")
async def stripe_create_search_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe Checkout Session for a search tier subscription.

    Pricing is pulled from settings.SEARCH_TIER_1_PRICE (2000 cents = $20/month).
    Returns a checkout_url to redirect the customer to Stripe-hosted payment.
    """
    from app.core.config import settings
    from app.services.payment_service import create_stripe_checkout_session
    import uuid as uuid_lib

    body = await request.json()
    subscription_type = body.get("subscription_type", "search_tier1")
    origin = body.get("origin", "https://proreadyengineer.com")

    # Map subscription_type to amount from settings (no hardcoded prices)
    amount_map = {
        "search_tier1": settings.SEARCH_TIER_1_PRICE,   # 2000 cents = $20/month
        "search_tier2": settings.SEARCH_TIER_2_PRICE,   # 2000 cents = $20/month
    }
    amount = amount_map.get(subscription_type)
    if amount is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown subscription_type: {subscription_type}. Allowed: {list(amount_map.keys())}",
        )

    related_id = str(current_user.id)
    success_url = f"{origin}/customer/dashboard?payment=success&purpose=search_subscription&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/for-customers?payment=cancelled"

    try:
        session_data = await create_stripe_checkout_session(
            db=db,
            purpose="search_subscription",
            amount=amount,
            currency="usd",
            user=current_user,
            related_entity_type="user",
            related_id=related_id,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"subscription_type": subscription_type},
        )
        return session_data
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))




@router.post("/stripe/create-provider-subscription")
async def stripe_create_provider_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe Checkout Session for the $1,000/year Annual Professional subscription.

    This grants providers:
    - Automatic receipt of all dispatched RFQs
    - Free access to all RFQ details (no $50/RFQ unlock fee)
    - Unlimited profile updates (all 17 fields)
    - Request Rank Up eligibility

    Returns {checkout_url, payment_attempt_id}.
    """
    from app.core.config import settings
    from app.services.payment_service import create_stripe_checkout_session
    from app.models import ProviderMembership
    from sqlalchemy import select
    import uuid as uuid_lib

    body = await request.json()
    origin = body.get("origin", settings.FRONTEND_URL)

    # Resolve provider from current user membership
    mem_result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = mem_result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No provider profile found. Please create or claim a provider profile first.",
        )

    provider_id = membership.provider_id
    success_url = f"{origin}/provider/dashboard?payment=success&purpose=provider_annual_subscription&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/provider/upgrade?payment=cancelled"

    try:
        session_data = await create_stripe_checkout_session(
            db=db,
            purpose="provider_annual_subscription",
            amount=settings.PROVIDER_ANNUAL_SUBSCRIPTION_PRICE,  # 100000 = $1000.00
            currency="usd",
            user=current_user,
            related_entity_type="provider",
            related_id=provider_id,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"provider_id": str(provider_id)},
        )
        return {
            "checkout_url": session_data["checkout_url"],
            "payment_attempt_id": session_data["payment_attempt_id"],
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


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
    """Handle PayPal/Braintree webhooks (legacy transaction processing)."""
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
        payload.get("event")
        or payload.get("event_type")
        or payload.get("type")
        or payload.get("data", {}).get("event_type")
        or payload.get("data", {}).get("event")
        or ""
    )
    _log.info("Signwell webhook received: event_type=%s", event_type)

    try:
        from app.services.nda_service import handle_signwell_webhook
        await handle_signwell_webhook(event_type, payload, db)
    except Exception as exc:
        _log.error("Error processing Signwell webhook: %s", exc)
        # Return 200 so Signwell does not retry indefinitely



@router.post("/billing/cancel-subscription")
async def cancel_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel a subscription at period end (Stripe cancel_at_period_end=True).

    User retains access until current period ends. No immediate termination.
    Body: { "subscription_type": "customer_monthly" | "provider_annual" }
    """
    import stripe as _stripe
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import select as _sel, update as _upd
    from app.models.payment import Subscription
    from app.services.config_service import get_runtime_config as _grc

    body = await request.json()
    subscription_type = body.get("subscription_type")

    allowed_types = {
        "customer_monthly": ["search_tier_1", "search_tier_2"],
        "provider_annual": ["provider_annual"],
    }
    if subscription_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"subscription_type must be one of: {list(allowed_types.keys())}",
        )

    db_types = allowed_types[subscription_type]

    _cfg = await _grc(db)
    _stripe.api_key = _cfg.get("STRIPE_SECRET_KEY", "") or ""
    if not _stripe.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

    result = await db.execute(
        _sel(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.subscription_status == "active",
            Subscription.subscription_type.in_(db_types),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")
    if not sub.external_subscription_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription has no Stripe ID")

    stripe_sub = await asyncio.to_thread(
        _stripe.Subscription.modify,
        sub.external_subscription_id,
        cancel_at_period_end=True,
    )

    cancel_at_ts = getattr(stripe_sub, "cancel_at", None)
    cancel_at_dt = (
        datetime.fromtimestamp(cancel_at_ts, tz=timezone.utc) if cancel_at_ts else None
    )

    sub.cancel_at = cancel_at_dt
    await db.commit()

    return {
        "success": True,
        "cancel_at": cancel_at_dt.isoformat() if cancel_at_dt else None,
    }


@router.post("/billing/reactivate-subscription")
async def reactivate_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Reactivate a subscription that was scheduled for cancellation.

    Clears cancel_at_period_end on Stripe and locally.
    Body: { "subscription_type": "customer_monthly" | "provider_annual" }
    """
    import stripe as _stripe
    import asyncio
    from sqlalchemy import select as _sel
    from app.models.payment import Subscription
    from app.services.config_service import get_runtime_config as _grc

    body = await request.json()
    subscription_type = body.get("subscription_type")

    allowed_types = {
        "customer_monthly": ["search_tier_1", "search_tier_2"],
        "provider_annual": ["provider_annual"],
    }
    if subscription_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"subscription_type must be one of: {list(allowed_types.keys())}",
        )

    db_types = allowed_types[subscription_type]

    _cfg = await _grc(db)
    _stripe.api_key = _cfg.get("STRIPE_SECRET_KEY", "") or ""
    if not _stripe.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

    result = await db.execute(
        _sel(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.subscription_status == "active",
            Subscription.subscription_type.in_(db_types),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found")
    if not sub.external_subscription_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription has no Stripe ID")

    await asyncio.to_thread(
        _stripe.Subscription.modify,
        sub.external_subscription_id,
        cancel_at_period_end=False,
    )

    sub.cancel_at = None
    await db.commit()

    return {"success": True}


@router.post("/billing/verify-subscription")
async def verify_subscription_payment(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Verify Stripe checkout session and fulfill subscription if payment confirmed.

    Called by the frontend after Stripe redirects back with ?payment=success&session_id=xxx.
    This is the guaranteed fulfillment path — works even if the webhook was delayed or failed.
    Idempotent: safe to call multiple times for the same session.
    """
    import asyncio
    import logging
    from datetime import datetime, timezone
    from sqlalchemy import select as _sel
    from app.core.config import settings
    from app.services.config_service import get_runtime_config
    from app.models.payment import Subscription, PaymentAttempt, PaymentStatus

    _log = logging.getLogger(__name__)

    body = await request.json()
    session_id = body.get("session_id")
    purpose = body.get("purpose", "search_subscription")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    try:
        cfg = await get_runtime_config(db)
        stripe_key = cfg.get("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
        if not stripe_key:
            raise HTTPException(status_code=400, detail="Stripe not configured")

        import stripe as _stripe
        _stripe.api_key = stripe_key

        # Retrieve the checkout session from Stripe to confirm payment status
        session = await asyncio.to_thread(_stripe.checkout.Session.retrieve, session_id)

        if session.payment_status != "paid":
            return {"fulfilled": False, "status": session.payment_status}

        # Find existing PaymentAttempt by session_id
        pa_result = await db.execute(
            _sel(PaymentAttempt).where(PaymentAttempt.external_payment_id == session_id)
        )
        payment = pa_result.scalar_one_or_none()

        if payment:
            # Mark completed if not already (idempotent)
            if payment.payment_status != PaymentStatus.COMPLETED:
                payment.payment_status = PaymentStatus.COMPLETED
                payment.confirmed_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(payment)

            # Run fulfillment (idempotent on the service side)
            from app.services.payment_service import fulfill_payment_purpose
            await fulfill_payment_purpose(db, payment)

        else:
            # No PaymentAttempt found — create one and fulfill directly
            _log.warning(
                "verify_subscription: no PaymentAttempt found for session %s; creating one for user %s",
                session_id, current_user.id,
            )
            new_pa = PaymentAttempt(
                provider_name="stripe",
                external_payment_id=session_id,
                purpose=purpose,
                related_entity_type="user",
                related_entity_id=str(current_user.id),
                amount=int(session.amount_total or 0),
                currency=(session.currency or "usd").lower(),
                payment_status=PaymentStatus.COMPLETED,
                idempotency_key=f"verify_{session_id}",
                initiated_by_user_id=current_user.id,
                confirmed_at=datetime.now(timezone.utc),
                extra_data=dict(session.metadata or {}),
            )
            db.add(new_pa)
            await db.commit()
            await db.refresh(new_pa)

            from app.services.payment_service import fulfill_payment_purpose
            await fulfill_payment_purpose(db, new_pa)

        # Return the current live subscription status for this user
        sub_result = await db.execute(
            _sel(Subscription)
            .where(
                Subscription.user_id == current_user.id,
                Subscription.subscription_status == "active",
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        sub = sub_result.scalar_one_or_none()

        return {
            "fulfilled": True,
            "has_active": sub is not None,
            "subscription_type": sub.subscription_type if sub else None,
        }

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("verify_subscription failed for user %s: %s", current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
