"""Admin API endpoints."""

import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.api.deps import get_db, require_role
from app.schemas.base import PagedResponse
from app.schemas.user import UserResponse
from app.schemas.provider import ProviderResponse, TierEvaluationResponse
from app.schemas.rfq import RFQResponse, RFQStatusOverrideRequest
from app.schemas.payment import PaymentAttemptResponse, WebhookEventResponse
from app.schemas.advertising import AdvertisementResponse

router = APIRouter()


@router.get("/admin/status")
async def admin_status(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin"])),
):
    """Get system status overview for admin dashboard."""
    from sqlalchemy import select, func
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.rfq import RFQ
    from app.core.config import settings

    status_info = {
        "database": {},
        "api_keys": {},
        "timestamp": None
    }

    # Database counts
    try:
        # Provider count
        result = await db.execute(select(func.count()).select_from(Provider))
        status_info["database"]["provider_count"] = result.scalar()

        # RFQ count
        result = await db.execute(select(func.count()).select_from(RFQ))
        status_info["database"]["rfq_count"] = result.scalar()

        # User count
        result = await db.execute(select(func.count()).select_from(User))
        status_info["database"]["user_count"] = result.scalar()

        # Providers with embeddings
        result = await db.execute(
            select(func.count()).select_from(Provider).where(Provider.embedding.isnot(None))
        )
        status_info["database"]["providers_with_embeddings"] = result.scalar()

        status_info["database"]["connection_ok"] = True
    except Exception as e:
        status_info["database"]["connection_ok"] = False
        status_info["database"]["error"] = str(e)

    # API Keys status (masked)
    status_info["api_keys"] = {
        "openai_configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "dummy-key"),
        "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
        "paypal_configured": bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET),
        "signrequest_configured": bool(settings.SIGNREQUEST_API_KEY),
        "aws_s3_configured": bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY),
    }

    from datetime import datetime
    status_info["timestamp"] = datetime.utcnow().isoformat()

    return status_info




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
