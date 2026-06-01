"""Payment and webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.payment_service import (
    handle_stripe_webhook, handle_paypal_webhook,
    create_billing_portal_session,
)
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


from app.services.provider_membership import get_user_provider_membership

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

    if not subscription or not subscription.external_customer_id:
        return {"no_subscription": True}

    try:
        portal_url = await create_billing_portal_session(
            subscription.external_customer_id,
            return_url=f"{settings.FRONTEND_URL}/customer/dashboard",
        )
    except Exception as exc:
        # Common causes: missing return_url (now passed), a legacy TEST-mode customer id
        # under live keys ("No such customer"), or the live Customer Portal not yet
        # configured in the Stripe dashboard. Fail cleanly instead of a 500/Network Error.
        logger.error(
            "Billing portal session failed (user=%s customer=%s): %s",
            current_user.id, subscription.external_customer_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't open the billing portal right now. If your subscription predates our payment launch, please contact support to manage it.",
        )
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
            SubscriptionType.SEARCH_TIER_1.value: ("Search Plan", "month", None),
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


@router.get("/billing/my-transactions")
async def get_my_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List ALL of the current user\'s money transactions, each tagged with the
    single action available to them under the published refund policy.

    Categorisation (see SYSTEM_SPEC refund policy):
      - Membership / subscription fees -> within the refund window: action
        "refund" (auto-refund + immediate downgrade via /billing/cancel-subscription);
        outside the window: action "cancel_membership" (cancel at period end, no refund).
        Window: 5 days for monthly plans, 14 days for the yearly (provider annual) plan.
      - One-time fees that are non-refundable (NDA fee, RFQ unlock): action
        "contact_support".
      - Anything already refunded / disputed: action "none" (informational).

    The frontend Transactions page renders exactly one button per row from
    `action`. `cancel_key` (when present) is the subscription_type the
    /billing/cancel-subscription endpoint expects.
    """
    from datetime import datetime, timezone, timedelta as _td
    from sqlalchemy import select as _sel
    from app.models.payment import PaymentAttempt as _PA
    from app.models.enums import PaymentStatus as _PS, PaymentPurpose as _PP

    def _aware(dt):
        if dt is None:
            return None
        return dt if getattr(dt, "tzinfo", None) else dt.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)

    # purpose -> (refund_window_days, cancel_key understood by /billing/cancel-subscription)
    _MEMBERSHIP = {
        _PP.SEARCH_SUBSCRIPTION.value:           (5,  "customer_monthly"),
        _PP.PROVIDER_ANNUAL_SUBSCRIPTION.value:  (14, "provider_annual"),
        _PP.PROVIDER_PROFILE_SUBSCRIPTION.value: (5,  None),
        _PP.ADVERTISEMENT_SUBSCRIPTION.value:    (5,  None),
    }
    _ONE_TIME = {_PP.NDA_FEE.value, _PP.RFQ_UNLOCK.value}
    _LABELS = {
        _PP.SEARCH_SUBSCRIPTION.value: "Search membership",
        _PP.PROVIDER_ANNUAL_SUBSCRIPTION.value: "Annual Professional membership",
        _PP.PROVIDER_PROFILE_SUBSCRIPTION.value: "Provider profile subscription",
        _PP.ADVERTISEMENT_SUBSCRIPTION.value: "Advertisement subscription",
        _PP.NDA_FEE.value: "NDA fee",
        _PP.RFQ_UNLOCK.value: "RFQ unlock fee",
    }

    rows = (await db.execute(
        _sel(_PA)
        .where(_PA.initiated_by_user_id == current_user.id)
        .order_by(_PA.initiated_at.desc())
    )).scalars().all()

    items = []
    for pa in rows:
        purpose = pa.purpose.value if hasattr(pa.purpose, "value") else str(pa.purpose)
        pstatus = pa.payment_status.value if hasattr(pa.payment_status, "value") else str(pa.payment_status)

        # Only real money movements are actionable. Hide initiated/processing/failed
        # so the page only shows charges the user actually paid (or that were refunded).
        if pstatus not in (_PS.COMPLETED.value, _PS.REFUNDED.value, _PS.DISPUTED.value):
            continue

        charged_at = _aware(pa.confirmed_at) or _aware(pa.initiated_at)
        try:
            amount_cents = int(round(float(pa.amount)))
        except (TypeError, ValueError):
            amount_cents = 0
        amount_display = f"${amount_cents / 100:,.2f}"

        category = "membership" if purpose in _MEMBERSHIP else ("one_time" if purpose in _ONE_TIME else "other")

        action = "none"
        within_window = None
        window_days = None
        cancel_key = None
        note = None

        if pstatus == _PS.REFUNDED.value:
            note = "Refunded"
        elif pstatus == _PS.DISPUTED.value:
            note = "Disputed"
        elif category == "membership":
            window_days, cancel_key = _MEMBERSHIP[purpose]
            within_window = bool(charged_at and now_utc <= charged_at + _td(days=window_days))
            if cancel_key is None:
                # No auto-refund key wired for this membership type -> support handles it.
                action = "contact_support"
            elif within_window:
                action = "refund"
            else:
                action = "cancel_membership"
        else:
            # one_time fees (NDA, RFQ unlock) and any unknown purpose: non-refundable.
            action = "contact_support"

        items.append({
            "id": str(pa.id),
            "date": charged_at.isoformat() if charged_at else None,
            "purpose": purpose,
            "label": _LABELS.get(purpose, purpose.replace("_", " ").title()),
            "amount_cents": amount_cents,
            "amount_display": amount_display,
            "currency": pa.currency or "USD",
            "status": pstatus,
            "category": category,
            "action": action,
            "within_window": within_window,
            "refund_window_days": window_days,
            "cancel_key": cancel_key,
            "note": note,
        })

    return {"transactions": items, "count": len(items)}


@router.get("/billing/subscription-status")
async def get_subscription_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user subscription status for customer dashboard/profile."""
    from sqlalchemy import select as _select
    from app.models.payment import Subscription
    from app.core.config import settings
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
        nda_credits_total = (getattr(settings, 'NDA_FREE_CREDITS_PER_MONTH', 5) if sub else 0)
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
        nda_credits_total = (getattr(settings, 'NDA_FREE_CREDITS_PER_MONTH', 5) if sub else 0)
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
    # billing_interval: "month" ($50/mo) or "year" ($500/yr). Same access tier
    # (search_tier_1) either way - only the price and the granted period differ.
    billing_interval = str(body.get("billing_interval", "month")).lower()
    if billing_interval not in ("month", "year"):
        billing_interval = "month"
    origin = body.get("origin", "https://proreadyengineer.com")

    # Map to amount from settings (no hardcoded prices). The customer search plan is
    # the only customer subscription; it can be billed monthly or annually.
    if subscription_type not in ("search_tier1", "search_tier_1"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown subscription_type: {subscription_type}. Allowed: ['search_tier1']",
        )
    amount = settings.SEARCH_ANNUAL_PRICE if billing_interval == "year" else settings.SEARCH_TIER_1_PRICE

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
            metadata={"subscription_type": "search_tier1", "billing_interval": billing_interval},
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
    membership = await get_user_provider_membership(db, current_user.id)
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
    """Handle PayPal webhooks. Verifies PayPal's transmission signature before
    processing; in production an unverified event is rejected (fail-closed)."""
    from app.services.payment_service import verify_paypal_webhook_signature
    from app.core.config import settings as _settings
    import logging as _logging
    _log = _logging.getLogger(__name__)

    payload = await request.json()
    verified = await verify_paypal_webhook_signature(db, dict(request.headers), payload)

    if not verified:
        if _settings.is_production:
            _log.warning("[paypal_webhook] unverified event rejected in production")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")
        _log.warning("[paypal_webhook] signature NOT verified (non-production) — processing for dev only")

    try:
        await handle_paypal_webhook(db, payload, signature_verified=verified)
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

    from datetime import timedelta as _td
    from app.models.payment import PaymentAttempt as _PA
    from app.models.enums import PaymentStatus as _PS, SubscriptionStatus as _SS, PaymentPurpose as _PP

    def _aware(dt):
        if dt is None:
            return None
        return dt if getattr(dt, "tzinfo", None) else dt.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    p_start = _aware(sub.current_period_start)
    p_end = _aware(sub.current_period_end)

    # Latest completed subscription charge for this user — used to refund + as a fallback
    # for the period start / interval when the Subscription period fields are not populated.
    ref_pa = (await db.execute(
        _sel(_PA)
        .where(
            _PA.initiated_by_user_id == current_user.id,
            _PA.payment_status == _PS.COMPLETED,
            _PA.purpose.in_([_PP.SEARCH_SUBSCRIPTION, _PP.PROVIDER_ANNUAL_SUBSCRIPTION]),
        )
        .order_by(_PA.confirmed_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    # Refund window: 5 days for monthly, 14 for yearly. Prefer the period length; fall back
    # to the charge amount (cents): <= $60 => monthly. Default 14 if nothing is known.
    window_days = None
    if p_start and p_end:
        window_days = 5 if (p_end - p_start).days <= 60 else 14
    if window_days is None and ref_pa is not None:
        try:
            window_days = 5 if float(ref_pa.amount) <= 6000 else 14
        except (TypeError, ValueError):
            window_days = None
    if p_start is None and ref_pa is not None and ref_pa.confirmed_at:
        p_start = _aware(ref_pa.confirmed_at)
    if window_days is None:
        window_days = 14
    within_window = bool(p_start and now_utc <= p_start + _td(days=window_days))

    is_stripe_sub = bool(sub.external_subscription_id and str(sub.external_subscription_id).startswith("sub_"))

    # Free / promo subscription (e.g. founding) — no money to move; downgrade immediately.
    if not is_stripe_sub:
        sub.subscription_status = _SS.CANCELLED
        sub.cancelled_at = datetime.utcnow()
        await db.commit()
        return {"success": True, "refunded": False, "immediate": True,
                "message": "Your subscription was cancelled."}

    # Within the refund window -> refund the latest charge + cancel immediately + downgrade now.
    if within_window:
        refunded = False
        refund_error = None
        try:
            stripe_sub = await asyncio.to_thread(
                _stripe.Subscription.retrieve, sub.external_subscription_id,
                expand=["latest_invoice.payment_intent"],
            )
            li = getattr(stripe_sub, "latest_invoice", None)
            pi_obj = getattr(li, "payment_intent", None) if li else None
            pi = (pi_obj.id if hasattr(pi_obj, "id") else pi_obj) if pi_obj else None
            if not pi and ref_pa is not None:
                pi = ref_pa.external_payment_id
            if pi:
                await asyncio.to_thread(
                    _stripe.Refund.create, payment_intent=pi, reason="requested_by_customer",
                    metadata={"reason": "in_app_cancel_within_window", "user_id": str(current_user.id)},
                )
                refunded = True
                _pa = (await db.execute(_sel(_PA).where(_PA.external_payment_id == pi))).scalar_one_or_none()
                if _pa is not None and _pa.payment_status != _PS.REFUNDED:
                    _pa.payment_status = _PS.REFUNDED
            else:
                refund_error = "No charge found to refund."
        except Exception as exc:
            refund_error = str(exc)
            logger.error("cancel within-window refund failed (user=%s sub=%s): %s",
                         current_user.id, sub.external_subscription_id, exc)
        # Cancel the Stripe subscription immediately (prefer .cancel, fall back to .delete).
        try:
            _cancel_fn = getattr(_stripe.Subscription, "cancel", None) or _stripe.Subscription.delete
            await asyncio.to_thread(_cancel_fn, sub.external_subscription_id)
        except Exception as exc:
            logger.warning("immediate Stripe cancel failed (sub=%s): %s", sub.external_subscription_id, exc)
        sub.subscription_status = _SS.CANCELLED
        sub.cancelled_at = datetime.utcnow()
        await db.commit()
        msg = ("Your subscription was cancelled and your payment refunded. Access has ended."
               if refunded else
               "Your subscription was cancelled. The automatic refund didn't go through; our team will review it.")
        return {"success": True, "refunded": refunded, "immediate": True,
                "refund_error": refund_error, "message": msg}

    # Outside the window -> cancel at period end (keep access to period end, no refund).
    stripe_sub = await asyncio.to_thread(
        _stripe.Subscription.modify,
        sub.external_subscription_id,
        cancel_at_period_end=True,
    )
    cancel_at_ts = getattr(stripe_sub, "cancel_at", None)
    cancel_at_dt = datetime.fromtimestamp(cancel_at_ts, tz=timezone.utc) if cancel_at_ts else p_end
    sub.cancel_at = cancel_at_dt
    await db.commit()
    return {
        "success": True,
        "refunded": False,
        "immediate": False,
        "cancel_at": cancel_at_dt.isoformat() if cancel_at_dt else None,
        "message": "Your subscription won't renew. You keep full access until the end of your paid period.",
    }


@router.post("/billing/cancel-user-subscription-by-id")
async def cancel_user_subscription_by_id(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel a specific subscription (or legacy ad) the user owns.

    The id is the `id` returned by GET /billing/user-subscriptions. For
    real Subscription rows it is the row UUID; for legacy one-time ads
    it is prefixed "legacy-ad-<ad_uuid>".

    Body: { "id": "<id>" }

    Behaviour:
      - Real Stripe subscription: sets cancel_at_period_end=True so the
        user keeps access until the end of the current billing period.
      - Legacy one-time ad: immediately pauses the ad (ad_status=CANCELLED).
    """
    import stripe as _stripe
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import select as _sel
    from app.models.payment import Subscription
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.services.config_service import get_runtime_config as _grc

    body = await request.json()
    raw_id = str(body.get("id") or "").strip()
    if not raw_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="id is required")

    # Legacy ad path: id looks like "legacy-ad-<uuid>"
    if raw_id.startswith("legacy-ad-"):
        ad_id_str = raw_id[len("legacy-ad-"):]
        ad_row = (
            await db.execute(_sel(Advertisement).where(Advertisement.id == ad_id_str))
        ).scalar_one_or_none()
        if not ad_row or ad_row.advertiser_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")
        ad_row.ad_status = AdStatus.CANCELLED
        await db.commit()
        return {"success": True, "cancel_at": None, "effective": "immediate"}

    # Normal path: Subscription row
    sub = (
        await db.execute(_sel(Subscription).where(Subscription.id == raw_id))
    ).scalar_one_or_none()
    if not sub or sub.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    if not sub.external_subscription_id:
        # Local-only sub (no Stripe id yet) — mark as cancelled at period end
        # so the renewal webhook can't re-activate it.
        from app.models.enums import SubscriptionStatus
        sub.subscription_status = SubscriptionStatus.CANCELLED
        await db.commit()
        return {"success": True, "cancel_at": None, "effective": "immediate"}

    _cfg = await _grc(db)
    _stripe.api_key = _cfg.get("STRIPE_SECRET_KEY", "") or ""
    if not _stripe.api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe not configured")

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
        "effective": "period_end",
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


# ---- Resend webhook -------------------------------------------------------
# Receives delivery-state events from Resend so admins know when an email
# bounces, gets complained-about, is delayed, or fails. Wire the same URL in
# the Resend dashboard: https://resend.com/webhooks
# Events captured: email.bounced, email.complained, email.delivery_delayed,
# email.failed. Others (delivered, opened, clicked) are accepted-and-ignored.

@router.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Resend delivery-state webhooks (bounce/complaint/delay/failed)."""
    import json
    import logging
    from app.core.config import settings as _settings
    from app.services.email_failure_service import record_email_failure

    _log = logging.getLogger(__name__)
    raw = await request.body()
    body_text = raw.decode("utf-8", errors="replace")[:8000]

    # Optional signature verification — Resend uses svix-style headers.
    # If RESEND_WEBHOOK_SECRET is configured, compute HMAC and reject mismatches.
    secret = getattr(_settings, "RESEND_WEBHOOK_SECRET", None)
    if secret:
        try:
            import base64
            import hashlib
            import hmac
            svix_id = request.headers.get("svix-id", "")
            svix_ts = request.headers.get("svix-timestamp", "")
            svix_sig = request.headers.get("svix-signature", "")
            # Strip 'whsec_' prefix per Resend / Svix convention
            secret_bytes = base64.b64decode(secret.split("_", 1)[-1]) if secret.startswith("whsec_") else secret.encode()
            signed_payload = f"{svix_id}.{svix_ts}.{body_text}".encode()
            expected = base64.b64encode(hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()).decode()
            # svix_sig looks like "v1,<sig> v1,<sig>" — check any match
            sigs = [p.split(",", 1)[1] for p in svix_sig.split() if "," in p]
            if not any(hmac.compare_digest(expected, s) for s in sigs):
                _log.warning("[resend_webhook] signature mismatch — rejecting")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")
        except HTTPException:
            raise
        except Exception as exc:
            _log.warning("[resend_webhook] signature check error: %s", exc)
            # Be conservative: if a secret is configured but verification errors,
            # reject rather than process unverified events.
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="signature check failed")

    try:
        payload = json.loads(body_text or "{}")
    except Exception as exc:
        _log.warning("[resend_webhook] invalid JSON: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON")

    event_type = (payload.get("type") or "").strip().lower()
    data = payload.get("data") or {}

    # Map Resend events -> our internal source values
    SOURCE_MAP = {
        "email.bounced": "webhook_bounced",
        "email.complained": "webhook_complained",
        "email.delivery_delayed": "webhook_delivery_delayed",
        "email.failed": "webhook_failed",
    }
    if event_type not in SOURCE_MAP:
        # Accepted-and-ignored (e.g. email.delivered, email.opened, email.clicked)
        return {"status": "ignored", "type": event_type}

    # Resend payload shape: data has `to` (list[str] or str), `subject`, `email_id`,
    # and event-specific fields like `bounce.message`, `bounce.subType`, etc.
    to_raw = data.get("to") or data.get("recipient") or ""
    if isinstance(to_raw, list):
        to_addrs = [str(x).strip() for x in to_raw if str(x).strip()]
    else:
        to_addrs = [str(to_raw).strip()] if to_raw else ["unknown@unknown"]

    subject = data.get("subject") or data.get("Subject")
    email_id = data.get("email_id") or data.get("id")

    # Extract a human-readable reason from event-specific fields
    bounce_info = data.get("bounce") or {}
    complaint_info = data.get("complaint") or {}
    reason_parts = []
    if isinstance(bounce_info, dict):
        if bounce_info.get("subType"):
            reason_parts.append(f"bounce.subType={bounce_info['subType']}")
        if bounce_info.get("message"):
            reason_parts.append(bounce_info["message"])
    if isinstance(complaint_info, dict) and complaint_info.get("type"):
        reason_parts.append(f"complaint.type={complaint_info['type']}")
    if not reason_parts and data.get("reason"):
        reason_parts.append(str(data["reason"]))
    error_message = " | ".join(reason_parts)[:1000] if reason_parts else f"Resend reported {event_type}"

    src = SOURCE_MAP[event_type]
    for addr in to_addrs:
        try:
            await record_email_failure(
                to_email=addr,
                subject=subject,
                source=src,
                error_message=error_message,
                provider_response=body_text,
                resend_email_id=email_id,
                db=db,
            )
        except Exception as exc:
            _log.warning("[resend_webhook] could not record failure for %s: %s", addr, exc)

    return {"status": "recorded", "type": event_type, "recipients": len(to_addrs)}
