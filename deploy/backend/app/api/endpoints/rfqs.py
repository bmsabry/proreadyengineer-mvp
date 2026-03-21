"""RFQ API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.api.deps import get_db, get_current_active_user, get_current_user_optional, get_client_ip
from app.schemas.rfq import (
    RFQCreateRequest, RFQResponse, RFQStatusResponse,
    RFQMatchResponse, RFQFileUploadResponse,
)
from app.schemas.payment import PaymentIntentResponse
from app.models.user import User
from app.services.rfq_service import create_rfq, submit_rfq, get_rfq_matches
from app.services.file_service import generate_upload_url
from app.services.payment_service import create_payment_intent
from app.core.celery import celery_app

router = APIRouter()


@router.post("/rfqs", response_model=RFQResponse, status_code=status.HTTP_201_CREATED)
async def create_rfq_endpoint(
    data: RFQCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Create a new RFQ (anonymous or authenticated)."""
    rfq = await create_rfq(db, data, current_user)
    return RFQResponse.from_orm(rfq)


# ── Customer RFQ listing & tracking ──────────────────────────────────────────

@router.get("/customer/my-rfqs")
async def get_my_rfqs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all RFQs owned by the authenticated customer."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    rows = (await db.execute(
        select(RFQ).where(RFQ.customer_user_id == current_user.id).order_by(RFQ.created_at.desc())
    )).scalars().all()
    return [{
        "id": str(r.id),
        "project_description": r.project_description,
        "rfq_status": r.rfq_status.value if hasattr(r.rfq_status, "value") else str(r.rfq_status),
        "urgency": r.urgency, "nda_required": r.nda_required,
        "quote_count": r.quote_count, "is_closed": r.is_closed,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
    } for r in rows]


@router.get("/customer/rfqs/{rfq_id}/tracking")
async def get_rfq_tracking(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Real-time RFQ tracking: batches, dispatched providers, quotes."""
    import uuid as _u
    from sqlalchemy import select, func as F
    from app.models.rfq import RFQ, RFQMatch, RFQDispatch, RFQDispatchBatch
    from app.models.provider import Provider
    from app.models.quote import Quote
    try:
        uid = _u.UUID(rfq_id)
    except ValueError:
        raise HTTPException(400, "Invalid RFQ ID")
    rfq = await db.get(RFQ, uid)
    if not rfq:
        raise HTTPException(404, "RFQ not found")
    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(403, "Not authorized")
    batches = (await db.execute(
        select(RFQDispatchBatch).where(RFQDispatchBatch.rfq_id == uid)
        .order_by(RFQDispatchBatch.batch_number)
    )).scalars().all()
    disp_rows = (await db.execute(
        select(RFQDispatch, Provider)
        .join(Provider, RFQDispatch.provider_id == Provider.id)
        .where(RFQDispatch.rfq_id == uid).order_by(RFQDispatch.created_at)
    )).all()
    quotes = (await db.execute(select(Quote).where(Quote.rfq_id == uid))).scalars().all()
    total_matches = (await db.execute(
        select(F.count()).select_from(RFQMatch).where(RFQMatch.rfq_id == uid)
    )).scalar() or 0
    def sv(v): return v.value if hasattr(v, "value") else str(v)
    def iso(d): return d.isoformat() if d else None
    def pname(p): return getattr(p, "name", None) or getattr(p, "firm_name", None) or "Unknown"
    dispatched = [{
        "provider_id": p.id, "provider_name": pname(p),
        "city": getattr(p, "city", None), "state": getattr(p, "state", None),
        "tier": getattr(p, "tier", None), "dispatch_status": sv(d.dispatch_status),
        "teaser_email_sent_at": iso(d.teaser_email_sent_at),
        "batch_id": str(d.batch_id) if d.batch_id else None,
    } for d, p in disp_rows]
    batch_list = [{
        "id": str(b.id), "batch_number": b.batch_number, "status": b.status,
        "scheduled_for": iso(b.scheduled_for), "dispatched_at": iso(b.dispatched_at),
        "providers_contacted": [x for x in dispatched if x["batch_id"] == str(b.id)],
    } for b in batches]
    qlist = [{
        "id": str(q.id), "provider_id": q.provider_id, "quote_status": sv(q.quote_status),
        "rough_price_min": float(q.rough_price_min) if q.rough_price_min else None,
        "rough_price_max": float(q.rough_price_max) if q.rough_price_max else None,
        "currency": q.currency, "turnaround_estimate_text": q.turnaround_estimate_text,
        "submitted_at": iso(q.submitted_at),
    } for q in quotes]
    return {
        "rfq": {"id": str(rfq.id), "project_description": rfq.project_description,
                "rfq_status": sv(rfq.rfq_status), "urgency": rfq.urgency,
                "nda_required": rfq.nda_required, "quote_count": rfq.quote_count,
                "is_closed": rfq.is_closed, "created_at": iso(rfq.created_at),
                "submitted_at": iso(rfq.submitted_at)},
        "total_matches": total_matches, "total_dispatched": len(dispatched),
        "quotes_received": len(qlist), "batches": batch_list, "quotes": qlist,
    }


@router.get("/rfqs/{rfq_id}", response_model=RFQResponse)
async def get_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get RFQ details (customer only)."""
    from sqlalchemy import select
    from app.models.rfq import RFQ

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    return RFQResponse.from_orm(rfq)


@router.post("/rfqs/{rfq_id}/files/initiate")
async def initiate_file_upload(
    rfq_id: str,
    filename: str,
    content_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get presigned URL for RFQ file upload."""
    import uuid
    key = f"rfqs/{rfq_id}/files/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)
    return {"upload_url": url_data["url"], "fields": url_data["fields"], "key": key}


@router.post("/rfqs/{rfq_id}/files/complete")
async def complete_file_upload(
    rfq_id: str,
    key: str,
    filename: str,
    mime_type: str,
    file_size: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Record uploaded RFQ file."""
    from app.models.rfq import RFQFile
    import uuid
    from datetime import datetime

    rfq_file = RFQFile(
        id=uuid.uuid4(),
        rfq_id=rfq_id,
        s3_key=key,
        original_filename=filename,
        mime_type=mime_type,
        file_size_bytes=file_size,
        uploaded_by_user_id=current_user.id if current_user else None,
        created_at=datetime.utcnow(),
    )
    db.add(rfq_file)
    await db.commit()

    return {"file_id": str(rfq_file.id), "status": "uploaded"}


@router.post("/rfqs/{rfq_id}/nda/checkout", response_model=PaymentIntentResponse)
async def nda_checkout(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create payment intent for NDA fee."""
    from sqlalchemy import select
    from app.models.rfq import RFQ

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if not rfq.nda_required:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NDA not required for this RFQ")

    intent = await create_payment_intent(
        db, "nda_fee", 500, "usd", current_user, rfq_id  # $5.00
    )

    return PaymentIntentResponse(
        client_secret=intent["client_secret"],
        payment_intent_id=intent["id"],
    )


@router.get("/rfqs/{rfq_id}/status", response_model=RFQStatusResponse)
async def get_rfq_status(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get RFQ status and progress."""
    from sqlalchemy import select, func
    from app.models.rfq import RFQ, RFQDispatch, RFQDispatchBatch
    from app.models.quote import Quote

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Count dispatches
    result = await db.execute(
        select(func.count()).where(RFQDispatch.rfq_id == rfq_id)
    )
    firms_contacted = result.scalar()

    # Count quotes
    result = await db.execute(
        select(func.count()).where(Quote.rfq_id == rfq_id, Quote.quote_status == "submitted")
    )
    quotes_received = result.scalar()

    return RFQStatusResponse(
        rfq_id=rfq_id,
        status=str(rfq.rfq_status) if rfq.rfq_status else "unknown",
        firms_contacted=firms_contacted,
        quotes_received=quotes_received,
        quote_limit=5,
        is_closed=rfq.is_closed,
    )


@router.post("/rfqs/{rfq_id}/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_rfq_endpoint(
    rfq_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit RFQ for dispatch to providers.

    Returns 202 immediately - AI search and dispatch run in the background
    to avoid request timeout on long-running LLM pipeline.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQ

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    # Allow owner OR admin to submit
    is_admin = "admin" in (current_user.roles or [])
    if rfq.customer_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if rfq.rfq_status not in ("draft", None):
        from app.models.enums import RfqStatus
        if hasattr(rfq.rfq_status, "value"):
            status_val = rfq.rfq_status.value
        else:
            status_val = str(rfq.rfq_status)
        if status_val != "draft":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"RFQ already submitted (status: {status_val})"
            )

    # Run the full AI search + dispatch in the background
    # This avoids 30-60 second request timeout on Render
    async def _run_submit():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            try:
                await submit_rfq(bg_db, rfq_id)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    "Background submit_rfq failed for %s: %s", rfq_id, exc
                )

    background_tasks.add_task(_run_submit)

    return {"message": "RFQ submitted — provider matching and dispatch in progress", "rfq_id": rfq_id}


# Provider RFQ endpoints
@router.get("/provider/rfqs/teasers")
async def get_provider_teasers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get RFQ teasers for provider - returns rich data including project preview."""
    from sqlalchemy import select
    from app.models.rfq import RFQDispatch, RFQ
    from app.models.provider import ProviderMembership

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        return {"teasers": [], "has_membership": False}

    # Get dispatches with RFQ data joined
    result = await db.execute(
        select(RFQDispatch, RFQ).join(
            RFQ, RFQ.id == RFQDispatch.rfq_id
        ).where(
            RFQDispatch.provider_id == membership.provider_id
        ).order_by(RFQDispatch.created_at.desc())
    )
    rows = result.all()

    teasers = []
    for dispatch, rfq in rows:
        desc = rfq.project_description or ""
        preview = (desc[:300] + "...") if len(desc) > 300 else desc
        teasers.append({
            "rfq_id": str(rfq.id),
            "status": str(dispatch.dispatch_status) if dispatch.dispatch_status else "unknown",
            "urgency": rfq.urgency,
            "tollgate_phases": rfq.tollgate_phases or [],
            "nda_required": rfq.nda_required,
            "business_name": rfq.business_name,
            "project_description_preview": preview,
            "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
            "created_at": rfq.created_at.isoformat() if rfq.created_at else None,
        })

    return {"teasers": teasers, "has_membership": True}

@router.get("/provider/rfqs/{rfq_id}/teaser")
async def get_rfq_teaser(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get teaser details for an RFQ - returns full project preview info."""
    from sqlalchemy import select
    from app.models.rfq import RFQ, RFQDispatch
    from app.models.provider import ProviderMembership

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a provider")

    result = await db.execute(
        select(RFQDispatch).where(
            RFQDispatch.rfq_id == rfq_id,
            RFQDispatch.provider_id == membership.provider_id
        )
    )
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teaser not found")

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one()

    desc = rfq.project_description or ""
    preview = (desc[:300] + "...") if len(desc) > 300 else desc

    return {
        "rfq_id": rfq_id,
        "urgency": rfq.urgency,
        "dispatch_status": str(dispatch.dispatch_status) if dispatch.dispatch_status else "unknown",
        "tollgate_phases": rfq.tollgate_phases or [],
        "nda_required": rfq.nda_required,
        "business_name": rfq.business_name,
        "project_description_preview": preview,
        "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
    }

@router.post("/provider/rfqs/{rfq_id}/unlock/checkout")
async def unlock_checkout(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create Stripe Checkout Session to unlock RFQ access for $10."""
    from app.services.payment_service import create_stripe_checkout_session
    from app.core.config import settings as _settings

    # Verify RFQ exists and is open
    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    rfq_status_str = str(rfq.rfq_status)
    if rfq_status_str in ("closed_no_selection", "cancelled", "quote_limit_reached"):
        raise HTTPException(status_code=400, detail="This RFQ is no longer accepting new providers.")

    # Build redirect URLs
    frontend_url = getattr(_settings, 'FRONTEND_URL', 'https://promechdirectory.onrender.com')
    success_url = f"{frontend_url}/provider/rfq/{rfq_id}?payment=success"
    cancel_url = f"{frontend_url}/provider/rfq/{rfq_id}?payment=cancelled"

    try:
        session_data = await create_stripe_checkout_session(
            db=db,
            purpose="rfq_unlock",
            amount=1000,  # $10.00
            currency="usd",
            user=current_user,
            related_entity_type="rfq",
            related_id=rfq_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"unlock_checkout error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=f"Payment error: {str(e)}")

    return {
        "checkout_url": session_data["checkout_url"],
        "payment_attempt_id": session_data["payment_attempt_id"],
    }


@router.get("/provider/rfqs/{rfq_id}/unlock/status")
async def get_unlock_status(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Check if RFQ is unlocked for provider. Always returns teaser info."""
    from sqlalchemy import select
    from app.models.rfq import RFQUnlock, RFQ, RFQDispatch
    from app.models.provider import ProviderMembership

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        return {"unlocked": False, "has_membership": False}

    # Get RFQ data - always available as teaser info
    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # Check dispatch exists for this provider
    result = await db.execute(
        select(RFQDispatch).where(
            RFQDispatch.rfq_id == rfq_id,
            RFQDispatch.provider_id == membership.provider_id
        )
    )
    dispatch = result.scalar_one_or_none()

    desc = rfq.project_description or ""
    preview = (desc[:300] + "...") if len(desc) > 300 else desc

    base_info = {
        "has_membership": True,
        "has_dispatch": dispatch is not None,
        "urgency": rfq.urgency,
        "tollgate_phases": rfq.tollgate_phases or [],
        "nda_required": rfq.nda_required,
        "business_name": rfq.business_name,
        "project_description_preview": preview,
        "rfq_status": str(rfq.rfq_status) if rfq.rfq_status else None,
        "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
    }

    # Check for completed unlock
    result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == membership.provider_id,
            RFQUnlock.unlock_status == "completed"
        )
    )
    unlock = result.scalar_one_or_none()

    if unlock:
        return {"unlocked": True, "project_description": rfq.project_description, **base_info}
    else:
        return {"unlocked": False, **base_info}

@router.get("/provider/rfqs/{rfq_id}/files")
async def get_rfq_files(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get download URLs for RFQ files (subscription + unlock required)."""
    from sqlalchemy import select
    from app.models.rfq import RFQUnlock, RFQFile
    from app.models.provider import ProviderMembership, ProviderSubscription
    from app.models.payment import SubscriptionStatusEnum
    from app.services.file_service import generate_download_url

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a provider")

    # Check active subscription (required to access documents)
    result = await db.execute(
        select(ProviderSubscription).where(
            ProviderSubscription.provider_id == membership.provider_id,
            ProviderSubscription.status == SubscriptionStatusEnum.active,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SUBSCRIPTION_REQUIRED: An active provider subscription ($10/month) is required to access project documents."
        )

    # Check unlock
    result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == membership.provider_id,
            RFQUnlock.unlock_status == "completed"
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RFQ not unlocked")

    # Get files
    result = await db.execute(select(RFQFile).where(RFQFile.rfq_id == rfq_id))
    files = result.scalars().all()

    return {
        "files": [
            {
                "file_id": str(f.id),
                "filename": f.original_filename,
                "download_url": generate_download_url(f.s3_key, 3600),
            }
            for f in files
        ]
    }




# ─── NDA Endpoints ─────────────────────────────────────────────────────────────

@router.post("/rfqs/{rfq_id}/nda/initiate")
async def nda_initiate(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Initiate NDA signing for customer after payment.

    Creates a Signwell document from the NDA template and returns
    the embedded signing URL for the customer iframe flow.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.nda import RFQNDA
    from app.models.enums import RfqStatus, NdaStatus
    from app.services.nda_service import create_customer_nda

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    # Must belong to current user
    if str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    # Must require NDA
    if not rfq.nda_required:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NDA not required for this RFQ")

    # Check NDA payment has been completed (status must be past awaiting_nda_payment)
    current_rfq_status = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status)
    if current_rfq_status not in ("awaiting_customer_signature", "draft", "submitted"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"NDA cannot be initiated in RFQ status: {current_rfq_status}"
        )

    # Check no existing pending NDA
    existing = await db.execute(
        select(RFQNDA).where(
            RFQNDA.rfq_id == rfq_id,
            RFQNDA.provider_id == None,  # noqa: E711
        )
    )
    existing_nda = existing.scalar_one_or_none()

    if existing_nda and existing_nda.nda_status not in (
        NdaStatus.NOT_REQUIRED, NdaStatus.FAILED, NdaStatus.CANCELLED
    ):
        # Return existing signing URL if still pending
        from app.services.nda_service import get_customer_signing_url
        signing_url = await get_customer_signing_url(rfq_id, db)
        return {
            "document_id": existing_nda.signrequest_document_id,
            "signing_url": signing_url,
            "status": existing_nda.nda_status.value if hasattr(existing_nda.nda_status, "value") else str(existing_nda.nda_status),
            "message": "Existing NDA document found",
        }

    result = await create_customer_nda(rfq_id, current_user, db)
    return result


@router.get("/rfqs/{rfq_id}/nda/signing-url")
async def get_nda_signing_url(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get or refresh the embedded signing URL for the customer NDA."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.services.nda_service import get_customer_signing_url

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    signing_url = await get_customer_signing_url(rfq_id, db)
    return {"signing_url": signing_url}


@router.get("/rfqs/{rfq_id}/nda/status")
async def get_nda_status(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get NDA status for an RFQ."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.nda import RFQNDA

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    result = await db.execute(
        select(RFQNDA).where(
            RFQNDA.rfq_id == rfq_id,
            RFQNDA.provider_id == None,  # noqa: E711
        )
    )
    nda = result.scalar_one_or_none()

    if not nda:
        return {
            "rfq_id": rfq_id,
            "nda_required": rfq.nda_required,
            "nda_status": None,
            "customer_signed_at": None,
            "fully_signed_at": None,
            "signed_pdf_available": False,
        }

    return {
        "rfq_id": rfq_id,
        "nda_required": rfq.nda_required,
        "nda_status": nda.nda_status.value if hasattr(nda.nda_status, "value") else str(nda.nda_status),
        "document_id": nda.signrequest_document_id,
        "customer_signed_at": nda.customer_signed_at.isoformat() if nda.customer_signed_at else None,
        "fully_signed_at": nda.fully_signed_at.isoformat() if nda.fully_signed_at else None,
        "signed_pdf_available": bool(nda.signed_pdf_s3_key),
    }


@router.post("/provider/rfqs/{rfq_id}/nda/signing-url")
async def get_provider_nda_signing_url(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get provider NDA signing URL after RFQ unlock.

    Called when a provider has paid to unlock an RFQ that requires an NDA.
    The customer must have already signed. Creates a provider signing
    document instance and returns the embedded signing URL.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQ, RFQUnlock
    from app.models.provider import ProviderMembership
    from app.services.nda_service import add_provider_to_nda

    # Verify provider membership
    mem_result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = mem_result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a provider")

    # Verify RFQ is unlocked by this provider
    unlock_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == membership.provider_id,
            RFQUnlock.unlock_status == "completed",
        )
    )
    if not unlock_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RFQ not unlocked")

    # Verify RFQ exists and requires NDA
    rfq_result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = rfq_result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if not rfq.nda_required:
        return {"message": "NDA not required for this RFQ", "signing_url": None}

    result = await add_provider_to_nda(rfq_id, membership.provider_id, current_user, db)
    return result
