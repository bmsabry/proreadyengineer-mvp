"""Admin API endpoints."""

import csv
import io
from datetime import datetime
import httpx
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.models.advertising import Advertisement
from app.models.payment import PaymentAttempt, WebhookEvent
from app.models.provider import Provider, ProviderMembership, ProviderClaimRequest
from app.models.admin import TierEvaluationRequest, AuditLog
from app.models.rfq import RFQ
from app.models.search import SearchRequest
from app.models.user import User
from app.schemas.advertising import AdvertisementResponse
from app.schemas.base import PagedResponse
from app.schemas.payment import PaymentAttemptResponse, WebhookEventResponse
from app.schemas.provider import ProviderResponse, TierEvaluationResponse
from app.schemas.rfq import RFQResponse, RFQStatusOverrideRequest
from app.schemas.user import UserResponse

router = APIRouter()


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Get system statistics for the admin dashboard."""
    db_stats: Dict[str, Any] = {
        "user_count": 0,
        "provider_count": 0,
        "rfq_count": 0,
        "providers_with_embeddings": 0,
        "total_searches": 0,
        "connection_ok": False,
    }

    try:
        r = await db.execute(select(func.count()).select_from(User))
        db_stats["user_count"] = r.scalar() or 0
        db_stats["connection_ok"] = True
    except Exception as exc:
        db_stats["user_count_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(Provider))
        db_stats["provider_count"] = r.scalar() or 0
    except Exception as exc:
        db_stats["provider_count_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(RFQ))
        db_stats["rfq_count"] = r.scalar() or 0
    except Exception as exc:
        db_stats["rfq_count_error"] = str(exc)

    try:
        r = await db.execute(
            text("SELECT COUNT(*) FROM providers WHERE embedding IS NOT NULL")
        )
        db_stats["providers_with_embeddings"] = r.scalar() or 0
    except Exception as exc:
        db_stats["providers_with_embeddings_error"] = str(exc)

    try:
        r = await db.execute(select(func.count()).select_from(SearchRequest))
        db_stats["total_searches"] = r.scalar() or 0
    except Exception as exc:
        db_stats["total_searches_error"] = str(exc)

    # Check each API key independently using a FRESH session to avoid transaction corruption.
    # Each key has its own try/except so one failure never affects others.
    # Checks DB config first (keys saved via admin UI), then falls back to env vars.
    async def _key_set(db_key: str, env_val: str = "") -> bool:
        """Return True if this key is configured in DB or environment."""
        # Check env var first - always reliable
        if env_val and env_val.strip() and env_val.strip() not in ("dummy-key", "your-key-here", "none", "null", ""):
            return True
        # Try DB with a completely fresh session - never reuse the stats session
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as fresh_db:
                r = await fresh_db.execute(
                    text("SELECT value FROM system_config WHERE key = :k AND value IS NOT NULL AND value != ''  LIMIT 1"),
                    {"k": db_key},
                )
                row = r.fetchone()
                if row and row[0] and str(row[0]).strip() not in ("dummy-key", "your-key-here", ""):
                    return True
        except Exception:
            pass
        return False

    api_keys: Dict[str, bool] = {
        "openai_configured": await _key_set(
            "DEEPINFRA_API_KEY",
            getattr(settings, "OPENAI_API_KEY", "") or "",
        ),
        "stripe_configured": await _key_set(
            "STRIPE_SECRET_KEY",
            getattr(settings, "STRIPE_SECRET_KEY", "") or "",
        ),
        "paypal_configured": await _key_set(
            "PAYPAL_CLIENT_ID",
            getattr(settings, "PAYPAL_CLIENT_ID", "") or "",
        ),
        "signwell_configured": await _key_set(
            "SIGNWELL_API_KEY",
            getattr(settings, "SIGNWELL_API_KEY", "") or "",
        ),
        "aws_s3_configured": await _key_set(
            "AWS_ACCESS_KEY_ID",
            getattr(settings, "AWS_ACCESS_KEY_ID", "") or "",
        ),
        "resend_configured": await _key_set(
            "RESEND_API_KEY",
            getattr(settings, "RESEND_API_KEY", "") or "",
        ),
    }

    return {
        "database": db_stats,
        "api_keys": api_keys,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/admin/status")
async def admin_status_alias(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Backward-compat alias for /admin/stats."""
    return await admin_stats(db=db, current_user=current_user)


@router.get("/admin/rfqs", response_model=PagedResponse[RFQResponse])
async def admin_list_rfqs(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List all RFQs."""
    from sqlalchemy import select, func
    from app.models.rfq import RFQ

    query = select(RFQ)
    if status:
        query = query.where(RFQ.rfq_status == status)

    # Get total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Get paginated results
    result = await db.execute(query.offset((page - 1) * size).limit(size))
    rfqs = result.scalars().all()

    return PagedResponse(
        items=[RFQResponse.from_orm(r) for r in rfqs],
        total=total,
        page=page,
        size=size
    )


@router.get("/admin/rfqs/{rfq_id}", response_model=RFQResponse)
async def admin_get_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Get RFQ details."""
    from sqlalchemy import select
    from app.models.rfq import RFQ

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    return RFQResponse.from_orm(rfq)


@router.post("/admin/rfqs/{rfq_id}/override-status")
async def admin_override_rfq_status(
    rfq_id: str,
    data: RFQStatusOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Override RFQ status."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.admin import AuditLog
    import uuid
    from datetime import datetime

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    old_status = rfq.rfq_status
    rfq.rfq_status = data.new_status

    # Create audit log
    audit = AuditLog(
        id=uuid.uuid4(),
        actor_user_id=current_user.id,
        entity_type="rfq",
        entity_id=rfq_id,
        action="status_override",
        before_state={"status": old_status.value if old_status else None},
        after_state={"status": data.new_status},
        metadata={"reason": data.reason},
        created_at=datetime.utcnow(),
    )
    db.add(audit)
    await db.commit()

    return {"message": f"RFQ status changed to {data.new_status}", "rfq_id": rfq_id}


@router.get("/admin/payments", response_model=PagedResponse[PaymentAttemptResponse])
async def admin_list_payments(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List payment attempts."""
    from sqlalchemy import select, func
    from app.models.payment import PaymentAttempt

    query = select(PaymentAttempt)
    if status:
        query = query.where(PaymentAttempt.payment_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(PaymentAttempt.created_at.desc()).offset((page - 1) * size).limit(size))
    payments = result.scalars().all()

    return PagedResponse(
        items=[PaymentAttemptResponse.from_orm(p) for p in payments],
        total=total,
        page=page,
        size=size
    )


@router.get("/admin/webhooks", response_model=PagedResponse[WebhookEventResponse])
async def admin_list_webhooks(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List webhook events."""
    from sqlalchemy import select, func
    from app.models.payment import WebhookEvent

    query = select(WebhookEvent)
    if provider:
        query = query.where(WebhookEvent.provider_name == provider)
    if status:
        query = query.where(WebhookEvent.processing_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(WebhookEvent.received_at.desc()).offset((page - 1) * size).limit(size))
    events = result.scalars().all()

    return PagedResponse(
        items=[WebhookEventResponse.from_orm(e) for e in events],
        total=total,
        page=page,
        size=size
    )


@router.post("/admin/webhooks/{event_id}/replay")
async def admin_replay_webhook(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Replay a webhook event."""
    from sqlalchemy import select
    from app.models.payment import WebhookEvent
    from app.services.payment_service import handle_stripe_webhook, handle_paypal_webhook

    result = await db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found")

    # Replay based on provider
    if event.provider_name == "stripe":
        await handle_stripe_webhook(db, event.payload, "")
    elif event.provider_name == "paypal":
        await handle_paypal_webhook(db, event.payload)

    event.processing_status = "replayed"
    await db.commit()

    return {"message": "Webhook replayed", "event_id": event_id}


@router.get("/admin/tier-requests", response_model=PagedResponse[TierEvaluationResponse])
async def admin_list_tier_requests(
    status: Optional[str] = "pending",
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List tier evaluation requests."""
    from sqlalchemy import select, func
    from app.models.provider import TierEvaluationRequest

    query = select(TierEvaluationRequest)
    if status:
        query = query.where(TierEvaluationRequest.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(TierEvaluationRequest.created_at.desc()).offset((page - 1) * size).limit(size))
    requests = result.scalars().all()

    return PagedResponse(
        items=[TierEvaluationResponse.from_orm(r) for r in requests],
        total=total,
        page=page,
        size=size
    )


@router.post("/admin/tier-requests/{request_id}/approve")
async def admin_approve_tier_request(
    request_id: str,
    new_tier: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Approve tier evaluation request."""
    from sqlalchemy import select
    from app.models.provider import TierEvaluationRequest, Provider
    from datetime import datetime

    result = await db.execute(
        select(TierEvaluationRequest).where(TierEvaluationRequest.id == request_id)
    )
    tier_request = result.scalar_one_or_none()

    if not tier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    tier_request.status = "approved"
    tier_request.reviewed_by = current_user.id
    tier_request.reviewed_at = datetime.utcnow()
    tier_request.review_notes = notes

    # Update provider tier
    result = await db.execute(select(Provider).where(Provider.id == tier_request.provider_id))
    provider = result.scalar_one()
    provider.tier = new_tier

    await db.commit()

    return {"message": f"Tier upgraded to {new_tier}", "provider_id": str(provider.id)}


@router.post("/admin/tier-requests/{request_id}/reject")
async def admin_reject_tier_request(
    request_id: str,
    notes: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Reject tier evaluation request."""
    from sqlalchemy import select
    from app.models.provider import TierEvaluationRequest
    from datetime import datetime

    result = await db.execute(
        select(TierEvaluationRequest).where(TierEvaluationRequest.id == request_id)
    )
    tier_request = result.scalar_one_or_none()

    if not tier_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    tier_request.status = "rejected"
    tier_request.reviewed_by = current_user.id
    tier_request.reviewed_at = datetime.utcnow()
    tier_request.review_notes = notes

    await db.commit()

    return {"message": "Request rejected"}


@router.get("/admin/ads", response_model=PagedResponse[AdvertisementResponse])
async def admin_list_ads(
    status: Optional[str] = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: List all advertisements."""
    from sqlalchemy import select, func
    from app.models.advertising import Advertisement

    query = select(Advertisement)
    if status:
        query = query.where(Advertisement.ad_status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await db.execute(query.order_by(Advertisement.created_at.desc()).offset((page - 1) * size).limit(size))
    ads = result.scalars().all()

    return PagedResponse(
        items=[AdvertisementResponse.from_orm(a) for a in ads],
        total=total,
        page=page,
        size=size
    )


@router.post("/admin/ads/{ad_id}/pause")
async def admin_pause_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Pause an advertisement."""
    from sqlalchemy import select
    from app.models.advertising import Advertisement, AdStatusEnum

    result = await db.execute(select(Advertisement).where(Advertisement.id == ad_id))
    ad = result.scalar_one_or_none()

    if not ad:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ad not found")

    ad.ad_status = AdStatusEnum.paused
    await db.commit()

    return {"message": "Ad paused", "ad_id": ad_id}




@router.get("/admin/users")
async def admin_list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: List all users with pagination and optional search."""
    from sqlalchemy import select, func, or_
    from app.models.user import User
    from app.models.payment import Subscription

    query = select(User)
    count_query = select(func.count()).select_from(User)

    if search:
        filter_clause = or_(
            User.email.ilike(f"%{search}%"),
            User.full_name.ilike(f"%{search}%"),
            User.business_name.ilike(f"%{search}%"),
        )
        query = query.where(filter_clause)
        count_query = count_query.where(filter_clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(
        query.order_by(User.email).offset((page - 1) * size).limit(size)
    )
    users = result.scalars().all()

    # Get subscription info for each user
    user_ids = [u.id for u in users]
    sub_result = await db.execute(
        select(Subscription).where(
            Subscription.user_id.in_(user_ids),
            Subscription.subscription_status == "active",
        )
    )
    subs = {str(s.user_id): s for s in sub_result.scalars().all()}

    items = []
    for u in users:
        sub = subs.get(str(u.id))
        items.append({
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "business_name": u.business_name,
            "roles": u.roles,
            "is_super_admin": u.is_super_admin,
            "monthly_search_count": u.monthly_search_count or 0,
            "search_count_reset_at": u.search_count_reset_at.isoformat() if u.search_count_reset_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "failed_login_count": u.failed_login_count or 0,
            "locked_until": u.locked_until.isoformat() if u.locked_until else None,
            "membership_type": sub.subscription_type if sub else "free",
            "subscription_status": sub.subscription_status if sub else None,
            "subscription_id": str(sub.id) if sub else None,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/admin/users/export.csv")
async def admin_export_users_csv(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Export all users to CSV with full account info and membership type."""
    from sqlalchemy import select
    from app.models.user import User
    from app.models.payment import Subscription

    result = await db.execute(select(User).order_by(User.email))
    users = result.scalars().all()

    sub_result = await db.execute(
        select(Subscription).where(Subscription.subscription_status == "active")
    )
    subs = {str(s.user_id): s for s in sub_result.scalars().all()}

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id", "email", "full_name", "business_name", "roles",
        "is_super_admin", "membership_type", "subscription_status",
        "monthly_search_count", "search_count_reset_at",
        "last_login_at", "failed_login_count", "locked_until",
    ])

    for u in users:
        sub = subs.get(str(u.id))
        writer.writerow([
            str(u.id),
            u.email,
            u.full_name or "",
            u.business_name or "",
            ",".join(u.roles) if u.roles else "",
            u.is_super_admin,
            sub.subscription_type if sub else "free",
            sub.subscription_status if sub else "none",
            u.monthly_search_count or 0,
            u.search_count_reset_at.isoformat() if u.search_count_reset_at else "",
            u.last_login_at.isoformat() if u.last_login_at else "",
            u.failed_login_count or 0,
            u.locked_until.isoformat() if u.locked_until else "",
        ])

    output.seek(0)
    filename = f"users_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/admin/users/{user_id}/reset-search-quota")
async def admin_reset_user_search_quota(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Reset a user's monthly search count to zero."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_count = user.monthly_search_count or 0
    user.monthly_search_count = 0
    user.search_count_reset_at = datetime.utcnow()
    await db.commit()

    return {
        "message": "Search quota reset successfully",
        "user_id": user_id,
        "old_count": old_count,
        "new_count": 0,
    }

@router.post("/admin/users/{user_id}/suspend")
async def admin_suspend_user(
    user_id: str,
    reason: str = "",
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Admin: Suspend a user account."""
    from sqlalchemy import select
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    await db.commit()

    # Revoke all tokens
    from app.services.auth_service import revoke_all_user_tokens
    await revoke_all_user_tokens(db, user_id)

    return {"message": "User suspended", "user_id": user_id}


# ─── System Configuration Endpoints ──────────────────────────────────────────
from pydantic import BaseModel as _BaseModel
from app.services.config_service import get_runtime_config as _get_runtime_config
from app.services.config_service import save_config_values as _save_config_values


class SystemConfigRequest(_BaseModel):
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None
    openai_llm_model: Optional[str] = None
    openai_embedding_model: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_publishable_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    aws_s3_bucket: Optional[str] = None
    resend_api_key: Optional[str] = None
    resend_from_email: Optional[str] = None
    signrequest_api_key: Optional[str] = None
    signwell_api_key: Optional[str] = None
    signwell_template_id: Optional[str] = None


def _mask(v: str) -> str:
    if not v or len(v) < 8:
        return ''
    return v[:4] + '•' * 16 + v[-4:]


@router.get("/admin/config")
async def get_system_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get current system configuration (secrets masked)."""
    config = await _get_runtime_config(db)
    return {
        "openai_api_key": _mask(config.get("OPENAI_API_KEY", "")),
        "openai_api_key_set": bool(config.get("OPENAI_API_KEY")),
        "openai_api_base": config.get("OPENAI_API_BASE", ""),
        "openai_llm_model": config.get("OPENAI_LLM_MODEL", ""),
        "openai_embedding_model": config.get("OPENAI_EMBEDDING_MODEL", ""),
        "stripe_secret_key": _mask(config.get("STRIPE_SECRET_KEY", "")),
        "stripe_secret_key_set": bool(config.get("STRIPE_SECRET_KEY")),
        "stripe_publishable_key": config.get("STRIPE_PUBLISHABLE_KEY", ""),
        "aws_access_key_id": _mask(config.get("AWS_ACCESS_KEY_ID", "")),
        "aws_access_key_set": bool(config.get("AWS_ACCESS_KEY_ID")),
        "aws_region": config.get("AWS_REGION", ""),
        "aws_s3_bucket": config.get("AWS_S3_BUCKET", ""),
        "resend_api_key": _mask(config.get("RESEND_API_KEY", "")),
        "resend_api_key_set": bool(config.get("RESEND_API_KEY")),
        "signrequest_api_key": _mask(config.get("SIGNREQUEST_API_KEY", "")),
        "signrequest_api_key_set": bool(config.get("SIGNREQUEST_API_KEY")),
        "signwell_api_key": _mask(config.get("SIGNWELL_API_KEY", "")),
        "signwell_api_key_set": bool(config.get("SIGNWELL_API_KEY")),
        "signwell_template_id": config.get("SIGNWELL_TEMPLATE_ID", ""),
        "source": "db_or_env",
    }


@router.post("/admin/config")
async def save_system_config(
    data: SystemConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Save API keys and config to database for runtime use."""
    import logging
    _log = logging.getLogger("admin.config.save")
    _log.info(f"[SAVE] POST /admin/config from user {current_user.id}")
    _log.info(f"[SAVE] Request data fields: {[f for f in data.__dict__ if getattr(data, f)]}")

    config_map: dict = {}
    if data.openai_api_key:         config_map["OPENAI_API_KEY"]         = data.openai_api_key
    if data.openai_api_base:        config_map["OPENAI_API_BASE"]        = data.openai_api_base
    if data.openai_llm_model:       config_map["OPENAI_LLM_MODEL"]       = data.openai_llm_model
    if data.openai_embedding_model: config_map["OPENAI_EMBEDDING_MODEL"] = data.openai_embedding_model
    if data.stripe_secret_key:      config_map["STRIPE_SECRET_KEY"]      = data.stripe_secret_key
    if data.stripe_publishable_key: config_map["STRIPE_PUBLISHABLE_KEY"] = data.stripe_publishable_key
    if data.stripe_webhook_secret:  config_map["STRIPE_WEBHOOK_SECRET"]  = data.stripe_webhook_secret
    if data.aws_access_key_id:      config_map["AWS_ACCESS_KEY_ID"]      = data.aws_access_key_id
    if data.aws_secret_access_key:  config_map["AWS_SECRET_ACCESS_KEY"]  = data.aws_secret_access_key
    if data.aws_region:             config_map["AWS_REGION"]             = data.aws_region
    if data.aws_s3_bucket:          config_map["AWS_S3_BUCKET"]          = data.aws_s3_bucket
    if data.resend_api_key:         config_map["RESEND_API_KEY"]         = data.resend_api_key
    if data.resend_from_email:      config_map["RESEND_FROM_EMAIL"]      = data.resend_from_email
    if data.signrequest_api_key:    config_map["SIGNREQUEST_API_KEY"]    = data.signrequest_api_key
    if data.signwell_api_key:       config_map["SIGNWELL_API_KEY"]       = data.signwell_api_key
    if data.signwell_template_id:   config_map["SIGNWELL_TEMPLATE_ID"]   = data.signwell_template_id

    _log.info(f"[SAVE] Config map keys: {list(config_map.keys())}")

    if not config_map:
        _log.info("[SAVE] No non-empty values, returning no_changes")
        return {"status": "no_changes", "keys_saved": [], "message": "No non-empty values provided"}
    try:
        await _save_config_values(db, config_map, user_id=current_user.id)
        _log.info(f"[SAVE] SUCCESS: saved {len(config_map)} keys")
    except Exception as exc:
        _log.error(f"[SAVE] FAILED: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save config: {exc}")
    return {"status": "saved", "keys_saved": list(config_map.keys()), "message": f"Saved {len(config_map)} key(s) successfully"}




@router.get("/admin/debug/config-test")
async def admin_debug_config_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Diagnostic: test the config save path step by step."""
    import traceback
    results = {"steps": [], "success": False}

    # Step 1: Check if system_config table exists
    try:
        from sqlalchemy import text as _t
        r = await db.execute(_t("SELECT COUNT(*) FROM system_config"))
        count = r.scalar()
        results["steps"].append({"step": "table_exists", "ok": True, "count": count})
    except Exception as e:
        results["steps"].append({"step": "table_exists", "ok": False, "error": str(e)})
        try:
            await db.rollback()
        except Exception:
            pass
        return results

    # Step 2: Check table columns
    try:
        r = await db.execute(_t(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'system_config' ORDER BY ordinal_position"
        ))
        cols = [{"name": row[0], "type": row[1]} for row in r.fetchall()]
        results["steps"].append({"step": "columns", "ok": True, "columns": cols})
    except Exception as e:
        results["steps"].append({"step": "columns", "ok": False, "error": str(e)})

    # Step 3: Try a test write using the actual save function
    try:
        await _save_config_values(db, {"_TEST_KEY": "test_value"}, user_id=current_user.id)
        results["steps"].append({"step": "test_write", "ok": True})
    except Exception as e:
        results["steps"].append({"step": "test_write", "ok": False, "error": str(e), "traceback": traceback.format_exc()})

    # Step 4: Verify the test write
    try:
        r = await db.execute(_t("SELECT value FROM system_config WHERE key = '_TEST_KEY'"))
        row = r.fetchone()
        if row and row[0] == "test_value":
            results["steps"].append({"step": "verify_write", "ok": True, "value": row[0]})
        else:
            results["steps"].append({"step": "verify_write", "ok": False, "value": str(row)})
    except Exception as e:
        results["steps"].append({"step": "verify_write", "ok": False, "error": str(e)})

    # Step 5: Clean up test key
    try:
        await db.execute(_t("DELETE FROM system_config WHERE key = '_TEST_KEY'"))
        await db.commit()
        results["steps"].append({"step": "cleanup", "ok": True})
    except Exception as e:
        results["steps"].append({"step": "cleanup", "ok": False, "error": str(e)})

    results["success"] = all(s.get("ok") for s in results["steps"])
    return results

# --- Email Debug Endpoint ---

class TestEmailRequest(_BaseModel):
    to_email: str


@router.post("/admin/debug/test-email")
async def admin_debug_test_email(
    data: TestEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Send a Resend test email to verify email integration."""
    config = await _get_runtime_config(db)
    api_key: str = config.get("RESEND_API_KEY", "") or ""
    api_key_present = bool(api_key)
    api_key_prefix = api_key[:10] if len(api_key) >= 10 else api_key
    from_address = config.get("RESEND_FROM_EMAIL", "") or settings.FROM_EMAIL

    if not api_key_present:
        return {
            "success": False,
            "message_id": None,
            "error": "RESEND_API_KEY is not configured. Add it in Admin Configuration.",
            "api_key_present": False,
            "api_key_prefix": "",
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    html_body = (
        "<h1>Email Test Successful</h1>"
        "<p>Resend integration is working correctly for ProMechDirectory.</p>"
        "<p>Sent at: " + timestamp + "</p>"
    )

    payload = {
        "from": from_address,
        "to": [data.to_email],
        "subject": "ProMechDirectory - Resend Test Email",
        "html": html_body,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
        resend_status = response.status_code
        if resend_status in (200, 201):
            resp_json = response.json()
            return {
                "success": True,
                "message_id": resp_json.get("id"),
                "error": None,
                "api_key_present": True,
                "api_key_prefix": api_key_prefix,
                "from_address": from_address,
                "to_address": data.to_email,
                "resend_status_code": resend_status,
            }
        else:
            try:
                ed = response.json()
                error_msg = ed.get("message") or ed.get("name") or str(ed)
            except Exception:
                error_msg = response.text or "HTTP " + str(resend_status)
            return {
                "success": False,
                "message_id": None,
                "error": "Resend API error (" + str(resend_status) + "): " + error_msg,
                "api_key_present": True,
                "api_key_prefix": api_key_prefix,
                "from_address": from_address,
                "to_address": data.to_email,
                "resend_status_code": resend_status,
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message_id": None,
            "error": "Request to Resend API timed out after 15 seconds.",
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }
    except httpx.RequestError as exc:
        return {
            "success": False,
            "message_id": None,
            "error": "Network error contacting Resend: " + str(exc),
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "message_id": None,
            "error": "Unexpected error: " + str(exc),
            "api_key_present": True,
            "api_key_prefix": api_key_prefix,
            "from_address": from_address,
            "to_address": data.to_email,
            "resend_status_code": None,
        }


# --- Resend Domain Check Endpoint ---

@router.get("/admin/debug/resend-domains")
async def admin_check_resend_domains(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Check which domains are verified in the Resend account for the configured API key."""
    config = await _get_runtime_config(db)
    api_key: str = config.get("RESEND_API_KEY", "") or ""
    from_address = config.get("RESEND_FROM_EMAIL", "") or settings.FROM_EMAIL

    if not api_key:
        return {
            "success": False,
            "error": "RESEND_API_KEY is not configured.",
            "domains": [],
            "from_address": from_address,
            "configured_domain": "",
            "domain_verified": False,
            "tip": "Add your Resend API key in Admin Settings > Email tab.",
        }

    configured_domain = from_address.split("@")[1].lower() if "@" in from_address else ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.resend.com/domains",
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
            )
        if response.status_code == 200:
            data = response.json()
            domains = data.get("data", [])
            domain_statuses = {d.get("name", "").lower(): d.get("status", "unknown") for d in domains}
            domain_verified = (
                configured_domain in domain_statuses
                and domain_statuses.get(configured_domain) == "verified"
            )
            tip = None
            if not domain_verified:
                if configured_domain in domain_statuses:
                    tip = (
                        "Domain '{}' is in your Resend account but status is '{}'. ".format(
                            configured_domain, domain_statuses.get(configured_domain)
                        )
                        + "Check DNS records at https://resend.com/domains"
                    )
                else:
                    tip = (
                        "Domain '{}' is NOT in this Resend account. ".format(configured_domain)
                        + "Go to https://resend.com/domains, click 'Add Domain', enter '{}', ".format(configured_domain)
                        + "add the provided DNS records to Cloudflare, then verify. "
                        + "Make sure you are using the API key from the same Resend workspace."
                    )
            return {
                "success": True,
                "error": None,
                "domains": [
                    {"name": d.get("name"), "status": d.get("status"), "region": d.get("region")}
                    for d in domains
                ],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": domain_verified,
                "tip": tip,
            }
        elif response.status_code == 401:
            return {
                "success": False,
                "error": "Invalid Resend API key (401 Unauthorized). Go to https://resend.com/api-keys to get a valid key.",
                "domains": [],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": False,
                "tip": "The API key stored in Admin Settings is invalid or revoked.",
            }
        else:
            try:
                err = response.json().get("message", response.text)
            except Exception:
                err = response.text
            return {
                "success": False,
                "error": "Resend API error ({}): {}".format(response.status_code, err),
                "domains": [],
                "configured_domain": configured_domain,
                "from_address": from_address,
                "domain_verified": False,
                "tip": None,
            }
    except Exception as exc:
        return {
            "success": False,
            "error": "Error contacting Resend: " + str(exc),
            "domains": [],
            "configured_domain": configured_domain,
            "from_address": from_address,
            "domain_verified": False,
            "tip": None,
        }


# ---------------------------------------------------------------------------
# Admin Debug - Signwell Connection Test
@router.get("/admin/debug/test-signwell")
async def admin_debug_test_signwell_connection(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Admin: Test Signwell API key validity by listing document templates."""
    # ALL imports inside try/except to prevent 500s without CORS headers
    try:
        import httpx
        from app.services.config_service import get_config_value

        SIGNWELL_BASE = "https://www.signwell.com/api/v1"

        api_key = await get_config_value(db, "SIGNWELL_API_KEY")
        if not api_key or not api_key.strip():
            return {
                "success": False,
                "error": "Signwell API key not configured.",
                "hint": "Go to Admin > Settings > Document Signing and save your Signwell API key.",
            }

        api_key = api_key.strip()
        key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"

        # Try /document_templates - the correct Signwell v1 read-only endpoint
        endpoints_to_try = [
            ("/document_templates", "document templates"),
            ("/templates", "templates"),
        ]

        last_status = None
        last_body = ""

        async with httpx.AsyncClient(timeout=15.0) as client:
            for path, label in endpoints_to_try:
                try:
                    resp = await client.get(
                        f"{SIGNWELL_BASE}{path}",
                        headers={
                            "X-Api-Key": api_key,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                    )
                    last_status = resp.status_code
                    last_body = resp.text[:500]

                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                        except Exception:
                            data = {}
                        items = data if isinstance(data, list) else data.get("data", [])
                        item_ids = [str(t.get("id", "")) for t in (items if isinstance(items, list) else [])][:5]
                        return {
                            "success": True,
                            "message": f"Signwell API key is valid! ({label} endpoint responded 200)",
                            "key_preview": key_preview,
                            "key_length": len(api_key),
                            "endpoint_used": path,
                            "items_found": len(item_ids),
                            "item_ids": item_ids,
                        }
                    elif resp.status_code == 401:
                        return {
                            "success": False,
                            "error": "API key is invalid or expired (401 Unauthorized from Signwell)",
                            "key_preview": key_preview,
                            "key_length": len(api_key),
                            "hint": "Copy your API key fresh from Signwell dashboard: Account > API Keys",
                            "raw_response": last_body,
                        }
                    # 404 = endpoint not found, try next
                except httpx.RequestError as req_err:
                    return {"success": False, "error": f"Network error calling Signwell: {req_err}"}

        # None of the endpoints returned 200
        return {
            "success": False,
            "error": f"Signwell API returned HTTP {last_status} on all tested endpoints",
            "key_preview": key_preview,
            "raw_response": last_body,
            "hint": "If status is 404, the API endpoint path may have changed. If 403, check key permissions.",
        }

    except Exception as exc:
        import traceback
        return {
            "success": False,
            "error": str(exc),
            "detail": traceback.format_exc()[-800:],
        }


# Admin Debug - Signwell NDA End-to-End Test
# ---------------------------------------------------------------------------


class TestNDARequest(_BaseModel):
    customer_name: str
    customer_email: str
    provider_name: str
    provider_email: str


@router.post("/admin/debug/test-nda")
async def admin_debug_test_nda(
    data: TestNDARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Create a real Signwell test NDA document and send signing invitations
    to two email addresses - verifies the full document-signing integration."""
    from datetime import date

    try:
        from app.services.nda_service import _headers, _get_template_id, SIGNWELL_BASE_URL
        h = await _headers(db)
        tid = await _get_template_id(db)
    except Exception as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Signwell not configured: {exc}",
            "customer_signing_url": None, "provider_signing_url": None,
        }

    effective_date = date.today().strftime("%B %d, %Y")
    payload = {
        "test_mode": False,
        "template_id": tid,
        "subject": f"[TEST] ProMechDirectory NDA - {data.customer_name} & {data.provider_name}",
        "message": (
            "This is a test NDA document to verify the document signing "
            "integration. Please sign to confirm the workflow works end-to-end."
        ),
        "signers": [
            {
                "id": "signer_1",
                "name": data.customer_name,
                "email": data.customer_email,
                "embedded_signing": False,
            },
            {
                "id": "signer_2",
                "name": data.provider_name,
                "email": data.provider_email,
                "embedded_signing": False,
            },
        ],
        "fields": [
            {"api_id": "customer_name",        "value": data.customer_name},
            {"api_id": "customer_name2",       "value": data.customer_name},
            {"api_id": "customer_company",     "value": data.customer_name},
            {"api_id": "customer_entity_type", "value": "Individual"},
            {"api_id": "customer_signature",   "value": ""},
            {"api_id": "effective_date",       "value": effective_date},
            {"api_id": "governing_state",      "value": "Ohio"},
            {"api_id": "provider_name",        "value": data.provider_name},
            {"api_id": "provider_name2",       "value": data.provider_name},
            {"api_id": "provider_company",     "value": data.provider_name},
            {"api_id": "provider_entity_type", "value": "Company"},
            {"api_id": "provider_signature",   "value": ""},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SIGNWELL_BASE_URL}/documents", json=payload, headers=h
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Signwell API error {exc.response.status_code}: {exc.response.text}",
            "customer_signing_url": None, "provider_signing_url": None,
        }
    except Exception as exc:
        return {
            "success": False, "document_id": None,
            "error": f"Request failed: {exc}",
            "customer_signing_url": None, "provider_signing_url": None,
        }

    doc = resp.json()
    document_id = doc.get("id")
    customer_url: Optional[str] = None
    provider_url: Optional[str] = None
    for s in doc.get("signers", []):
        url = s.get("sign_page_url") or s.get("embedded_signing_url")
        if s.get("email", "") == data.customer_email:
            customer_url = url
        elif s.get("email", "") == data.provider_email:
            provider_url = url

    return {
        "success": True,
        "document_id": document_id,
        "error": None,
        "customer_signing_url": customer_url,
        "provider_signing_url": provider_url,
        "signwell_status": doc.get("status"),
        "created_at": doc.get("created_at"),
    }


@router.get("/admin/debug/test-nda/{document_id}/status")
async def admin_debug_test_nda_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Poll Signwell for per-signer signing status and check S3 for completed PDF."""
    from app.services.nda_service import _headers, SIGNWELL_BASE_URL
    from app.services.file_service import check_file_exists, generate_download_url

    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/documents/{document_id}", headers=h
            )
            resp.raise_for_status()
        doc = resp.json()
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to fetch document from Signwell: {exc}",
            "document_id": document_id,
            "document_status": None,
            "customer_signed": False, "customer_signed_at": None,
            "provider_signed": False, "provider_signed_at": None,
            "fully_signed": False,
            "s3_saved": False, "s3_key_checked": None, "s3_download_url": None,
        }

    doc_status = doc.get("status", "unknown")
    signers = doc.get("signers", [])
    customer_signed, customer_signed_at = False, None
    provider_signed, provider_signed_at = False, None

    if len(signers) >= 1:
        s = signers[0]
        customer_signed = s.get("status") == "signed" or bool(s.get("signed_at"))
        customer_signed_at = s.get("signed_at")
    if len(signers) >= 2:
        s = signers[1]
        provider_signed = s.get("status") == "signed" or bool(s.get("signed_at"))
        provider_signed_at = s.get("signed_at")

    fully_signed = customer_signed and provider_signed
    s3_saved = False
    s3_download_url: Optional[str] = None
    s3_key_checked: Optional[str] = None

    try:
        for key in [
            f"ndas/test/nda_signed_{document_id}.pdf",
            f"ndas/test_{document_id}/nda_signed_{document_id}.pdf",
        ]:
            if check_file_exists(key):
                s3_saved = True
                s3_key_checked = key
                s3_download_url = generate_download_url(key, expire_seconds=3600)
                break
    except Exception:
        pass  # S3 not configured - non-fatal

    return {
        "success": True,
        "error": None,
        "document_id": document_id,
        "document_status": doc_status,
        "customer_signed": customer_signed,
        "customer_signed_at": customer_signed_at,
        "provider_signed": provider_signed,
        "provider_signed_at": provider_signed_at,
        "fully_signed": fully_signed,
        "s3_saved": s3_saved,
        "s3_key_checked": s3_key_checked,
        "s3_download_url": s3_download_url,
    }


@router.post("/admin/debug/test-nda/{document_id}/void")
async def admin_debug_test_nda_void(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> dict:
    """Admin: Void/cancel a test NDA document in Signwell to clean up after testing."""
    from app.services.nda_service import _headers, SIGNWELL_BASE_URL

    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{SIGNWELL_BASE_URL}/documents/{document_id}", headers=h
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {
                "success": True, "error": None,
                "message": "Document not found (may already be void/completed)",
                "document_id": document_id,
            }
        return {
            "success": False,
            "error": f"Signwell API error {exc.response.status_code}: {exc.response.text}",
            "message": None, "document_id": document_id,
        }
    except Exception as exc:
        return {
            "success": False, "error": f"Request failed: {exc}",
            "message": None, "document_id": document_id,
        }

    return {
        "success": True, "error": None,
        "message": f"Document {document_id} voided successfully.",
        "document_id": document_id,
    }
