"""RFQ API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.api.deps import get_db, get_current_active_user, get_current_user, get_current_user_optional, get_client_ip
from app.schemas.rfq import (
    RFQCreateRequest, RFQResponse, RFQStatusResponse,
    RFQMatchResponse, RFQFileUploadResponse,
)
from app.schemas.payment import PaymentIntentResponse
from app.models.user import User
from app.services.rfq_service import create_rfq, submit_rfq, get_rfq_matches
from app.services.file_service import generate_upload_url
from app.services.payment_service import create_payment_intent

router = APIRouter()


def _redact_pii(text: str, business_name: str = "") -> str:
    """Strip emails, phone numbers, and the customer's business name from teaser text."""
    import re
    if not text:
        return text
    # Remove email addresses
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[redacted]', text)
    # Remove phone numbers (US / international)
    text = re.sub(r'(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})', '[redacted]', text)
    # Remove the customer's own company name (case-insensitive, whole word)
    if business_name and len(business_name) >= 3:
        escaped = re.escape(business_name)
        text = re.sub(rf'\b{escaped}\b', '[Company]', text, flags=re.IGNORECASE)
    return text


@router.post("/rfqs", response_model=RFQResponse, status_code=status.HTTP_201_CREATED)
async def create_rfq_endpoint(
    data: RFQCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Create a new RFQ (anonymous or authenticated)."""
    from sqlalchemy.orm import selectinload
    from app.models.rfq import RFQ as _RFQ
    rfq = await create_rfq(db, data, current_user)
    # Re-fetch with eager-loaded files to prevent MissingGreenlet in async context
    result = await db.execute(
        select(_RFQ).options(selectinload(_RFQ.files)).where(_RFQ.id == rfq.id)
    )
    rfq = result.scalar_one()
    return RFQResponse.from_orm(rfq)


# ── Customer RFQ listing & tracking ──────────────────────────────────────────

@router.get("/customer/my-rfqs")
async def get_my_rfqs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all RFQs owned by the authenticated customer with dispatch stats."""
    from sqlalchemy import select, func as F
    from app.models.rfq import RFQ, RFQMatch, RFQDispatch
    rows = (await db.execute(
        select(RFQ).where(RFQ.customer_user_id == current_user.id).order_by(RFQ.created_at.desc())
    )).scalars().all()

    # Bulk-query NDA statuses for all customer RFQs
    from app.models.nda import RFQNDA
    all_rfq_ids = [r.id for r in rows]
    nda_result = (await db.execute(
        select(RFQNDA.rfq_id, RFQNDA.nda_status).where(
            RFQNDA.rfq_id.in_(all_rfq_ids)
        ).order_by(RFQNDA.created_at.desc())
    )).all() if all_rfq_ids else []
    nda_status_map: dict[str, str] = {}
    for nda_rfq_id, nda_st in nda_result:
        key = str(nda_rfq_id)
        if key not in nda_status_map:
            nda_status_map[key] = nda_st.value if hasattr(nda_st, "value") else str(nda_st)

    result = []
    for r in rows:
        uid = r.id
        # Count total matched providers
        total_matched = (await db.execute(
            select(F.count()).select_from(RFQMatch).where(RFQMatch.rfq_id == uid)
        )).scalar() or 0
        # Count dispatched providers (teaser emails sent)
        dispatched_count = (await db.execute(
            select(F.count()).select_from(RFQDispatch).where(RFQDispatch.rfq_id == uid)
        )).scalar() or 0
        remaining = max(0, total_matched - dispatched_count)
        result.append({
            "id": str(uid),
            "project_description": r.project_description,
            "rfq_status": r.rfq_status.value if hasattr(r.rfq_status, "value") else str(r.rfq_status),
            "urgency": r.urgency,
            "nda_required": r.nda_required,
            "nda_status": nda_status_map.get(str(uid), "not_required" if not r.nda_required else "payment_pending"),
            "quote_count": r.quote_count,
            "is_closed": r.is_closed,
            "business_name": r.business_name,
            "contact_name": r.contact_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "total_matched": total_matched,
            "dispatched_count": dispatched_count,
            "remaining_count": remaining,
        })
    return result


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
    # Fetch latest NDA status for this RFQ
    from app.models.nda import RFQNDA
    nda_row = (await db.execute(
        select(RFQNDA.nda_status).where(RFQNDA.rfq_id == uid).order_by(RFQNDA.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    nda_status_val = (nda_row.value if hasattr(nda_row, "value") else str(nda_row)) if nda_row else ("not_required" if not rfq.nda_required else "payment_pending")

    return {
        "rfq": {"id": str(rfq.id), "project_description": rfq.project_description,
                "rfq_status": sv(rfq.rfq_status), "urgency": rfq.urgency,
                "nda_required": rfq.nda_required, "nda_status": nda_status_val,
                "quote_count": rfq.quote_count,
                "is_closed": rfq.is_closed, "created_at": iso(rfq.created_at),
                "submitted_at": iso(rfq.submitted_at)},
        "total_matches": total_matches, "total_dispatched": len(dispatched),
        "quotes_received": len(qlist), "batches": batch_list, "quotes": qlist,
    }


@router.get("/rfqs/{rfq_id}", response_model=None)
async def get_rfq(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get RFQ details with files (customer or admin)."""
    import uuid as _u
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.rfq import RFQ, RFQFile
    from app.services.file_service import generate_download_url

    # Validate and convert UUID
    try:
        uid = _u.UUID(rfq_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid RFQ ID format")

    # Eagerly load files relationship
    result = await db.execute(
        select(RFQ)
        .options(selectinload(RFQ.files))
        .where(RFQ.id == uid)
    )
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    # Allow customer owner OR admin
    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Build response with files + presigned download URLs
    rfq_data = RFQResponse.model_validate(rfq).model_dump()

    # Attach latest NDA status
    from app.models.nda import RFQNDA
    nda_row = (await db.execute(
        select(RFQNDA.nda_status).where(RFQNDA.rfq_id == uid).order_by(RFQNDA.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    rfq_data["nda_status"] = (nda_row.value if hasattr(nda_row, "value") else str(nda_row)) if nda_row else ("not_required" if not rfq.nda_required else "payment_pending")

    # Load runtime config for S3 presigned URL generation
    from app.services.config_service import get_runtime_config
    s3_config = await get_runtime_config(db)

    # Attach files with presigned download URLs
    file_responses = []
    for f in (rfq.files or []):
        file_dict = {
            "id": f.id,
            "rfq_id": f.rfq_id,
            "original_filename": f.original_filename,
            "mime_type": f.mime_type,
            "file_size_bytes": f.file_size_bytes,
            "extracted_text": getattr(f, "extracted_text", None),
            "download_url": None,
        }
        if f.s3_key and not f.s3_key.startswith("text:"):
            try:
                file_dict["download_url"] = generate_download_url_from_config(f.s3_key, s3_config, expire_seconds=3600)
            except Exception:
                pass
        file_responses.append(file_dict)

    rfq_data["files"] = file_responses
    return rfq_data


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


@router.post("/rfqs/{rfq_id}/nda/checkout")
async def nda_checkout(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create Stripe Checkout Session for $5 NDA fee.

    Returns {checkout_url, payment_attempt_id} for frontend redirect.
    After payment, Stripe redirects to /nda/{rfq_id}/sign?paid=true
    where the frontend calls /nda/initiate to get the Signwell signing URL.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.services.payment_service import create_stripe_checkout_session
    from app.core.config import settings as _settings
    import uuid as _uuid

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if not rfq.nda_required:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NDA not required for this RFQ")

    frontend_url = getattr(_settings, "FRONTEND_URL", "https://promechdirectory.onrender.com")
    success_url = f"{frontend_url}/nda/{rfq_id}/sign?paid=true&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{frontend_url}/nda/{rfq_id}/sign?cancelled=true"

    try:
        rfq_uuid = _uuid.UUID(rfq_id)
    except (ValueError, AttributeError):
        rfq_uuid = rfq_id

    # --- NDA Credit Check: subscribed customers get 3 free NDAs/month ---
    _active_sub = None
    try:
        from app.models.payment import Subscription as _Sub
        _sub_res = await db.execute(
            select(_Sub).where(
                _Sub.user_id == current_user.id,
                _Sub.subscription_status == 'active',
                _Sub.subscription_type.in_(['search_tier_1', 'search_tier_2']),
            ).limit(1)
        )
        _active_sub = _sub_res.scalar_one_or_none()
    except Exception as _sub_err:
        _log.warning(f"NDA subscription lookup failed: {_sub_err}")
        _active_sub = None

    if _active_sub:
        # Best-effort: advance RFQ status. Does NOT block the free credit response.
        try:
            if str(rfq.rfq_status) in ('submitted', 'draft', 'awaiting_nda_payment',
                                        'RFQStatus.submitted', 'RFQStatus.draft',
                                        'RFQStatus.awaiting_nda_payment'):
                from app.models.rfq import RFQStatus as _RS
                rfq.rfq_status = _RS.awaiting_customer_signature
                await db.commit()
        except Exception as _commit_err:
            _log.warning(f"NDA RFQ status update failed (non-critical): {_commit_err}")
        _log.info(f"NDA free credit granted rfq={rfq_id} user={current_user.id}")
        return {
            "free_credit": True,
            "credits_remaining": 3,
            "checkout_url": None,
            "payment_attempt_id": None,
        }
    # --- End NDA Credit Check ---
    _log.info(f"Creating NDA Stripe checkout for rfq={rfq_id} user={current_user.id}")

    session_data = await create_stripe_checkout_session(
        db=db,
        purpose="nda_fee",
            amount=1000,  # $10.00 NDA handling fee
        currency="usd",
        user=current_user,
        related_entity_type="rfq",
        related_id=rfq_uuid,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"rfq_id": rfq_id},
    )

    return {
        "checkout_url": session_data["checkout_url"],
        "payment_attempt_id": session_data.get("payment_attempt_id", ""),
    }


@router.post("/rfqs/{rfq_id}/nda/verify-payment")
async def nda_verify_payment(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Verify NDA fee payment by cross-referencing Stripe and update PaymentAttempt status.

    Called by the frontend after Stripe redirects back to /nda/{id}/sign?paid=true.
    Mirrors the RFQ unlock verify-payment pattern: queries Stripe directly so the
    PaymentAttempt record is updated even if the webhook hasn't arrived yet.
    """
    import logging as _logging
    import uuid as _uuid
    _log = _logging.getLogger(__name__)

    try:
        from sqlalchemy import select
        from app.models.payment import PaymentAttempt
        from app.models.enums import PaymentStatus
        from app.services.config_service import get_runtime_config as _grc
        from datetime import datetime, timezone
        import stripe

        # Step 1: Parse rfq_id
        try:
            rfq_uuid = _uuid.UUID(rfq_id)
        except (ValueError, AttributeError):
            return {"verified": False, "reason": "Invalid RFQ ID"}

        # Step 2: Find the most recent NDA fee PaymentAttempt for this rfq+user
        result = await db.execute(
            select(PaymentAttempt)
            .where(
                PaymentAttempt.related_entity_id == rfq_uuid,
                PaymentAttempt.purpose == "nda_fee",
                PaymentAttempt.initiated_by_user_id == current_user.id,
            )
            .order_by(PaymentAttempt.initiated_at.desc())
            .limit(1)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            _log.warning("nda-verify-payment: No NDA payment found for rfq=%s user=%s", rfq_id, current_user.id)
            return {"verified": False, "reason": "No NDA payment record found."}

        # Step 3: Already completed — nothing to do
        if str(payment.payment_status) == str(PaymentStatus.COMPLETED):
            _log.info("nda-verify-payment: Already COMPLETED for rfq=%s", rfq_id)
            return {"verified": True, "reason": "Payment already verified"}

        # Step 4: Query Stripe directly using stored session ID
        stripe_session_id = payment.external_payment_id
        if not stripe_session_id:
            _log.error("nda-verify-payment: No Stripe session ID for payment %s", payment.id)
            return {"verified": False, "reason": "Payment session not found."}

        cfg = await _grc(db)
        stripe.api_key = cfg.get('STRIPE_SECRET_KEY', '') or ''
        if not stripe.api_key:
            return {"verified": False, "reason": "Payment system not configured."}

        try:
            checkout_session = stripe.checkout.Session.retrieve(stripe_session_id)
            _log.info("nda-verify-payment: Stripe session %s: payment_status=%s",
                      stripe_session_id, checkout_session.payment_status)
        except Exception as e:
            _log.error("nda-verify-payment: Failed to retrieve Stripe session %s: %s", stripe_session_id, e)
            return {"verified": False, "reason": "Could not verify payment with Stripe."}

        # Step 5: Check if paid
        if checkout_session.payment_status != "paid":
            _log.info("nda-verify-payment: Session %s not paid: %s", stripe_session_id, checkout_session.payment_status)
            return {"verified": False, "reason": f"Payment status: {checkout_session.payment_status}"}

        # Step 6: PAID — update PaymentAttempt to COMPLETED
        _log.info("nda-verify-payment: Session %s PAID — updating PaymentAttempt", stripe_session_id)
        payment.payment_status = PaymentStatus.COMPLETED
        payment.confirmed_at = datetime.now(timezone.utc)
        await db.commit()

        return {"verified": True, "reason": "Payment verified and confirmed"}

    except Exception as e:
        _log.exception("nda-verify-payment: Unexpected error: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"verified": False, "reason": f"Verification error: {type(e).__name__}: {e}"}


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


@router.post("/rfqs/{rfq_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_rfq_endpoint(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Cancel an RFQ. Only the owning customer or an admin may cancel.
    RFQs that are already closed or cancelled cannot be cancelled again.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.enums import RfqStatus
    from datetime import datetime

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    is_admin = "admin" in (current_user.roles or [])
    if rfq.customer_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Get string value of current status
    current_status = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status or "")

    if current_status == "cancelled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is already cancelled")

    if rfq.is_closed and current_status not in ("quote_limit_reached",):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RFQ is already closed and cannot be cancelled")

    # Cancel the RFQ
    rfq.rfq_status = RfqStatus.CANCELLED
    rfq.is_closed = True
    rfq.closed_at = datetime.utcnow()
    await db.commit()

    # Write audit log
    try:
        from app.models.admin import AuditLog
        audit = AuditLog(
            actor_user_id=current_user.id,
            entity_type="rfq",
            entity_id=str(rfq_id),
            action="cancel",
            after_state={"rfq_status": "cancelled", "is_closed": True},
        )
        db.add(audit)
        await db.commit()
    except Exception:
        pass  # Audit log failure must never block the cancel action

    return {"message": "RFQ cancelled successfully", "rfq_id": rfq_id, "rfq_status": "cancelled"}


# Provider RFQ endpoints
@router.get("/provider/rfqs/teasers")
async def get_provider_teasers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get RFQ teasers for provider - returns rich data including project preview.
    Status is derived: 'quoted' if provider submitted a quote, 'unlocked' if paid unlock,
    'pending' otherwise.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQDispatch, RFQ, RFQUnlock
    from app.models.quote import Quote
    from app.models.provider import ProviderMembership
    from app.models.enums import UnlockStatus

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        return {"teasers": [], "has_membership": False}

    provider_id = membership.provider_id

    # Get dispatches with RFQ data joined
    result = await db.execute(
        select(RFQDispatch, RFQ).join(
            RFQ, RFQ.id == RFQDispatch.rfq_id
        ).where(
            RFQDispatch.provider_id == provider_id
        ).order_by(RFQDispatch.created_at.desc())
    )
    rows = result.all()

    if not rows:
        return {"teasers": [], "has_membership": True}

    # Collect all RFQ ids for bulk lookup
    rfq_ids = [rfq.id for _, rfq in rows]

    # Bulk-query NDA status for these RFQs (latest NDA per RFQ)
    from app.models.nda import RFQNDA
    nda_result = await db.execute(
        select(RFQNDA.rfq_id, RFQNDA.nda_status).where(
            RFQNDA.rfq_id.in_(rfq_ids)
        ).order_by(RFQNDA.created_at.desc())
    )
    nda_status_map: dict[str, str] = {}
    for nda_rfq_id, nda_st in nda_result.all():
        key = str(nda_rfq_id)
        if key not in nda_status_map:  # keep latest (first due to desc order)
            nda_status_map[key] = nda_st.value if hasattr(nda_st, "value") else str(nda_st)

    # Bulk-query active unlocks for this provider
    unlock_result = await db.execute(
        select(RFQUnlock.rfq_id).where(
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status == UnlockStatus.UNLOCKED,
            RFQUnlock.rfq_id.in_(rfq_ids)
        )
    )
    unlocked_rfq_ids = set(str(row[0]) for row in unlock_result.all())

    # Bulk-query submitted quotes for this provider (non-draft, non-withdrawn)
    quote_result = await db.execute(
        select(Quote.rfq_id).where(
            Quote.provider_id == provider_id,
            Quote.quote_status.notin_(["draft", "withdrawn"]),
            Quote.rfq_id.in_(rfq_ids)
        )
    )
    quoted_rfq_ids = set(str(row[0]) for row in quote_result.all())

    teasers = []
    for dispatch, rfq in rows:
        rfq_id_str = str(rfq.id)
        # Derive meaningful status for filter tabs
        if rfq_id_str in quoted_rfq_ids:
            derived_status = "quoted"
        elif rfq_id_str in unlocked_rfq_ids:
            derived_status = "unlocked"
        else:
            derived_status = "pending"

        desc = rfq.project_description or ""
        biz = rfq.business_name or ""
        preview = (desc[:300] + "...") if len(desc) > 300 else desc
        preview = _redact_pii(preview, biz)
        teasers.append({
            "rfq_id": rfq_id_str,
            "status": derived_status,
            "dispatch_status": str(dispatch.dispatch_status) if dispatch.dispatch_status else "unknown",
            "urgency": rfq.urgency,
            "tollgate_phases": rfq.tollgate_phases or [],
            "nda_required": rfq.nda_required,
            "nda_status": nda_status_map.get(rfq_id_str, "not_required" if not rfq.nda_required else "payment_pending"),
            "business_name": rfq.business_name,
            "project_description_preview": preview,
            "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
            "created_at": rfq.created_at.isoformat() if rfq.created_at else None,
            "rfq_status": str(rfq.rfq_status.value) if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status or ""),
            "rfq_is_closed": rfq.is_closed or False,
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

    # Fetch latest NDA status for this RFQ
    from app.models.nda import RFQNDA
    nda_row = (await db.execute(
        select(RFQNDA.nda_status).where(RFQNDA.rfq_id == rfq_id).order_by(RFQNDA.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    nda_status_val = (nda_row.value if hasattr(nda_row, "value") else str(nda_row)) if nda_row else ("not_required" if not rfq.nda_required else "payment_pending")

    desc = rfq.project_description or ""
    biz = rfq.business_name or ""
    preview = (desc[:300] + "...") if len(desc) > 300 else desc
    preview = _redact_pii(preview, biz)

    return {
        "rfq_id": rfq_id,
        "urgency": rfq.urgency,
        "dispatch_status": str(dispatch.dispatch_status) if dispatch.dispatch_status else "unknown",
        "tollgate_phases": rfq.tollgate_phases or [],
        "nda_required": rfq.nda_required,
        "nda_status": nda_status_val,
        "business_name": rfq.business_name,
        "project_description_preview": preview,
        "submitted_at": rfq.submitted_at.isoformat() if rfq.submitted_at else None,
    }



async def _provider_has_annual_subscription(provider_id: int, db) -> bool:
    """Return True if the provider has an active annual subscription.

    Annual subscribers receive all dispatched RFQs for free without paying
    the per-RFQ $50 unlock fee.

    Args:
        provider_id: Provider database ID.
        db: AsyncSession database session.

    Returns:
        True if an active provider_annual subscription exists.
    """
    from sqlalchemy import select
    from app.models.payment import Subscription
    from app.models.enums import SubscriptionStatus

    result = await db.execute(
        select(Subscription).where(
            Subscription.provider_id == provider_id,
            Subscription.subscription_type == "provider_annual",
            Subscription.subscription_status == SubscriptionStatus.ACTIVE,
        )
    )
    return result.scalar_one_or_none() is not None


@router.post("/provider/rfqs/{rfq_id}/unlock/checkout")
async def unlock_checkout(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create Stripe Checkout Session to unlock RFQ access for $50."""
    import logging
    import uuid as _uuid
    logger = logging.getLogger(__name__)

    try:
        from app.services.payment_service import create_stripe_checkout_session
        from app.core.config import settings as _settings
        from sqlalchemy import select
        from app.models.rfq import RFQ
        from app.models.provider import ProviderMembership

        # Verify RFQ exists and is open
        result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
        rfq = result.scalar_one_or_none()
        if not rfq:
            raise HTTPException(status_code=404, detail="RFQ not found")

        rfq_status_str = str(rfq.rfq_status)
        if rfq_status_str in ("closed_no_selection", "cancelled", "quote_limit_reached"):
            raise HTTPException(
                status_code=400,
                detail="This RFQ is no longer accepting new providers.",
            )

        # Check if provider has active annual subscription — grant free access
        _mem_result = await db.execute(
            select(ProviderMembership).where(
                ProviderMembership.user_id == current_user.id
            )
        )
        _membership = _mem_result.scalar_one_or_none()
        _provider_id_for_sub = _membership.provider_id if _membership else None

        if _provider_id_for_sub and await _provider_has_annual_subscription(_provider_id_for_sub, db):
            # Annual subscriber — create unlock record with no payment required
            from app.models.rfq import RFQUnlock
            from app.models.enums import UnlockStatus
            import datetime as _dt

            # Idempotency: skip if already unlocked
            _existing = await db.execute(
                select(RFQUnlock).where(
                    RFQUnlock.rfq_id == rfq_id,
                    RFQUnlock.provider_id == _provider_id_for_sub,
                    RFQUnlock.unlock_status == UnlockStatus.UNLOCKED,
                )
            )
            if not _existing.scalar_one_or_none():
                _unlock = RFQUnlock(
                    rfq_id=rfq_id,
                    provider_id=_provider_id_for_sub,
                    unlocked_by_user_id=current_user.id,
                    unlock_status="granted_by_subscription",
                    unlocked_at=_dt.datetime.utcnow(),
                )
                db.add(_unlock)
                await db.commit()
                logger.info(
                    f"Annual subscriber free unlock granted: rfq={rfq_id} provider={_provider_id_for_sub}"
                )

            frontend_url = getattr(_settings, "FRONTEND_URL", "https://promechdirectory.onrender.com")
            return {
                "checkout_url": None,
                "payment_attempt_id": None,
                "granted_by_subscription": True,
                "redirect_url": f"{frontend_url}/provider/rfq/{rfq_id}",
            }

        # Build redirect URLs
        frontend_url = getattr(_settings, 'FRONTEND_URL', 'https://promechdirectory.onrender.com')
        success_url = f"{frontend_url}/provider/rfq/{rfq_id}?payment=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_url}/provider/rfq/{rfq_id}?payment=cancelled"

        # Ensure rfq_id is UUID for DB storage
        try:
            rfq_uuid = _uuid.UUID(rfq_id)
        except (ValueError, AttributeError):
            rfq_uuid = rfq_id  # fallback to string

        logger.info(f"Creating Stripe checkout for rfq={rfq_id} user={current_user.id}")

        # Resolve provider_id for webhook metadata
        _mem_result = await db.execute(
            select(ProviderMembership).where(
                ProviderMembership.user_id == current_user.id
            )
        )
        _membership = _mem_result.scalar_one_or_none()
        provider_id_for_meta = str(_membership.provider_id) if _membership else ""

        session_data = await create_stripe_checkout_session(
            db=db,
            purpose="rfq_unlock",
            amount=2000,  # $20.00 RFQ unlock fee
            currency="usd",
            user=current_user,
            related_entity_type="rfq",
            related_id=rfq_uuid,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"provider_id": provider_id_for_meta},
        )

        logger.info(f"Stripe checkout created: {session_data.get('session_id')} for rfq={rfq_id}")

        return {
            "checkout_url": session_data["checkout_url"],
            "payment_attempt_id": session_data["payment_attempt_id"],
        }

    except HTTPException:
        raise  # Re-raise HTTP exceptions unchanged
    except RuntimeError as e:
        logger.error(f"unlock_checkout RuntimeError for rfq={rfq_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(
            f"unlock_checkout unexpected error for rfq={rfq_id}: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Checkout failed: {type(e).__name__}: {str(e)}",
        )




@router.post("/provider/rfqs/{rfq_id}/verify-payment")
async def verify_payment(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify payment and fulfill RFQ unlock.

    Looks up the most recent PaymentAttempt for this rfq+user,
    checks Stripe status, and creates RFQUnlock if paid.
    No session_id needed - finds it from the database.
    """
    import logging
    import uuid as _uuid
    _log = logging.getLogger(__name__)

    try:
        _log.info("verify_payment called: rfq_id=%s, user=%s", rfq_id, current_user.id)

        from app.services.config_service import get_runtime_config as _grc
        from app.models.rfq import RFQUnlock
        from app.models.provider import ProviderMembership
        from app.models.payment import PaymentAttempt
        from app.models.enums import PaymentStatus
        from app.services.payment_service import _fulfill_checkout_rfq_unlock
        from sqlalchemy import select
        from datetime import datetime, timezone
        import stripe

        # Step 1: Parse rfq_id
        try:
            rfq_uuid = _uuid.UUID(rfq_id)
        except (ValueError, AttributeError):
            return {"unlocked": False, "reason": "Invalid RFQ ID"}

        # Step 2: Check if already unlocked (fast path)
        mem_result = await db.execute(
            select(ProviderMembership).where(
                ProviderMembership.user_id == current_user.id
            )
        )
        membership = mem_result.scalar_one_or_none()
        provider_id_str = str(membership.provider_id) if membership else ""

        if membership:
            existing_unlock = await db.execute(
                select(RFQUnlock).where(
                    RFQUnlock.rfq_id == rfq_uuid,
                    RFQUnlock.provider_id == membership.provider_id,
                    RFQUnlock.unlock_status == "unlocked"
                )
            )
            if existing_unlock.scalar_one_or_none():
                _log.info("verify-payment: Already unlocked for rfq=%s", rfq_id)
                return {"unlocked": True, "reason": "Already unlocked"}

        # Step 3: Find the most recent PaymentAttempt for this rfq+user
        result = await db.execute(
            select(PaymentAttempt)
            .where(
                PaymentAttempt.related_entity_id == rfq_uuid,
                PaymentAttempt.purpose == "rfq_unlock",
                PaymentAttempt.initiated_by_user_id == current_user.id,
            )
            .order_by(PaymentAttempt.initiated_at.desc())
            .limit(1)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            _log.warning("verify-payment: No payment found for rfq=%s user=%s", rfq_id, current_user.id)
            return {"unlocked": False, "reason": "No payment record found. Please try the unlock button again."}

        # Step 4: If already completed, just fulfill (idempotent)
        if str(payment.payment_status) == str(PaymentStatus.COMPLETED):
            _log.info("verify-payment: Payment already COMPLETED, ensuring unlock exists")
            await _fulfill_checkout_rfq_unlock(
                db=db,
                rfq_id_str=rfq_id,
                user_id_str=str(current_user.id),
                provider_id_str=provider_id_str,
                payment_attempt_id=payment.id,
            )
            await db.commit()
            return {"unlocked": True, "reason": "Payment already verified"}

        # Step 5: Check Stripe status using stored session ID
        stripe_session_id = payment.external_payment_id
        if not stripe_session_id:
            _log.error("verify-payment: No Stripe session ID stored for payment %s", payment.id)
            return {"unlocked": False, "reason": "Payment session not found. Please try again."}

        _cfg = await _grc(db)
        stripe.api_key = _cfg.get('STRIPE_SECRET_KEY', '') or ''
        if not stripe.api_key:
            return {"unlocked": False, "reason": "Payment system not configured."}

        try:
            checkout_session = stripe.checkout.Session.retrieve(stripe_session_id)
            _log.info("Stripe session %s: payment_status=%s, status=%s",
                     stripe_session_id, checkout_session.payment_status, checkout_session.status)
        except Exception as e:
            _log.error("Failed to retrieve Stripe session %s: %s", stripe_session_id, e)
            return {"unlocked": False, "reason": "Could not verify payment with Stripe. Please refresh."}

        # Step 6: Not paid yet
        if checkout_session.payment_status != "paid":
            _log.info("verify-payment: Session %s not paid: %s", stripe_session_id, checkout_session.payment_status)
            return {"unlocked": False, "reason": f"Payment status: {checkout_session.payment_status}. Please complete payment."}

        # Step 7: PAID! Update payment and create unlock atomically
        _log.info("verify-payment: Session %s PAID - fulfilling unlock", stripe_session_id)
        payment.payment_status = PaymentStatus.COMPLETED
        payment.confirmed_at = datetime.now(timezone.utc)

        await _fulfill_checkout_rfq_unlock(
            db=db,
            rfq_id_str=rfq_id,
            user_id_str=str(current_user.id),
            provider_id_str=provider_id_str,
            payment_attempt_id=payment.id,
        )

        await db.commit()
        _log.info("verify-payment: Unlock fulfilled for rfq=%s", rfq_id)
        return {"unlocked": True, "reason": "Payment verified and access granted"}

    except HTTPException:
        raise
    except Exception as e:
        _log.exception("verify-payment: Unexpected error: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return {"unlocked": False, "reason": f"Verification error: {type(e).__name__}: {e}"}


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
    preview = _redact_pii(preview, rfq.business_name or "")

    # Fetch latest NDA status for this RFQ
    from app.models.nda import RFQNDA as _RFQNDA
    _nda_row = (await db.execute(
        select(_RFQNDA.nda_status).where(_RFQNDA.rfq_id == rfq_id).order_by(_RFQNDA.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    _nda_status_val = (_nda_row.value if hasattr(_nda_row, "value") else str(_nda_row)) if _nda_row else ("not_required" if not rfq.nda_required else "payment_pending")

    base_info = {
        "has_membership": True,
        "has_dispatch": dispatch is not None,
        "urgency": rfq.urgency,
        "tollgate_phases": rfq.tollgate_phases or [],
        "nda_required": rfq.nda_required,
        "nda_status": _nda_status_val,
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
            RFQUnlock.unlock_status == "unlocked"
        )
    )
    unlock = result.scalar_one_or_none()

    if unlock:
        # Check if this provider's quote was accepted
        from app.models.quote import Quote as QuoteModel
        quote_result = await db.execute(
            select(QuoteModel).where(
                QuoteModel.rfq_id == rfq_id,
                QuoteModel.provider_id == membership.provider_id,
                QuoteModel.quote_status == "accepted",
            )
        )
        quote_accepted = quote_result.scalar_one_or_none() is not None

        # Check provider NDA signing status (only relevant after quote acceptance)
        provider_nda_signed = False
        if rfq.nda_required:
            from app.models.nda import RFQNDA
            nda_result = await db.execute(
                select(RFQNDA).where(
                    RFQNDA.rfq_id == rfq_id,
                    RFQNDA.provider_id == membership.provider_id,
                )
            )
            provider_nda = nda_result.scalar_one_or_none()
            if provider_nda and provider_nda.provider_signed_at is not None:
                provider_nda_signed = True
            # If still not signed, poll Signwell directly (self-healing fallback)
            if not provider_nda_signed and provider_nda:
                try:
                    from app.services.nda_service import _heal_nda_if_complete
                    healed = await _heal_nda_if_complete(provider_nda, db)
                    if healed:
                        provider_nda_signed = True
                except Exception as _heal_exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "NDA self-heal failed in unlock_status: %s", _heal_exc
                    )
        else:
            # NDA not required - treat as signed
            provider_nda_signed = True

        return {
            "unlocked": True,
            "project_description": rfq.project_description,
            "provider_nda_signed": provider_nda_signed,
            "quote_accepted": quote_accepted,
            **base_info
        }
    else:
        return {"unlocked": False, "provider_nda_signed": False, "quote_accepted": False, **base_info}

@router.get("/provider/rfqs/{rfq_id}/files")
async def get_rfq_files(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get download URLs for RFQ files.

    Access rules:
    - Provider must have paid the $10 unlock fee.
    - If NDA not required: files are accessible immediately after unlock.
    - If NDA required: files are only accessible after customer accepts provider quote
      AND the NDA is fully signed by both parties.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQUnlock, RFQFile, RFQ as _RFQModel
    from app.models.provider import ProviderMembership
    from app.models.nda import RFQNDA
    from app.models.quote import Quote as QuoteModel
    from app.services.file_service import generate_download_url

    # Must have provider membership
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a provider")

    # Must have paid the unlock fee
    result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == membership.provider_id,
            RFQUnlock.unlock_status == "unlocked"
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RFQ not unlocked")

    # Load the RFQ to check NDA requirement
    rfq = (await db.execute(select(_RFQModel).where(_RFQModel.id == rfq_id))).scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ not found")

    # If NDA is required, gate documents behind quote acceptance + fully signed NDA
    if rfq.nda_required:
        # Check if provider's quote was accepted
        quote_result = await db.execute(
            select(QuoteModel).where(
                QuoteModel.rfq_id == rfq_id,
                QuoteModel.provider_id == membership.provider_id,
                QuoteModel.quote_status == "accepted",
            )
        )
        quote_accepted = quote_result.scalar_one_or_none() is not None

        if not quote_accepted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="DOCS_AFTER_ACCEPTANCE: Project documents are available after the customer accepts your quote."
            )

        # Quote was accepted - require fully signed NDA
        # First try to find an existing NDA record and self-heal if Signwell says complete
        nda_any_result = await db.execute(
            select(RFQNDA).where(
                RFQNDA.rfq_id == rfq_id,
                RFQNDA.provider_id == membership.provider_id,
            ).order_by(RFQNDA.created_at.desc()).limit(1)
        )
        provider_nda = nda_any_result.scalar_one_or_none()
        if provider_nda:
            current_nda_status = provider_nda.nda_status.value if hasattr(provider_nda.nda_status, "value") else str(provider_nda.nda_status)
            if current_nda_status != "fully_signed":
                try:
                    from app.services.nda_service import _heal_nda_if_complete
                    await _heal_nda_if_complete(provider_nda, db)
                    current_nda_status = provider_nda.nda_status.value if hasattr(provider_nda.nda_status, "value") else str(provider_nda.nda_status)
                except Exception:
                    pass
            if current_nda_status != "fully_signed":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="NDA_REQUIRED: Please complete the NDA signing process before accessing project files."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="NDA_REQUIRED: Please complete the NDA signing process before accessing project files."
            )

    # All checks passed - return files
    from app.services.config_service import get_runtime_config
    s3_config = await get_runtime_config(db)

    result = await db.execute(select(RFQFile).where(RFQFile.rfq_id == rfq_id))
    files = result.scalars().all()

    file_list = []
    for f in files:
        entry = {
            "file_id": str(f.id),
            "filename": f.original_filename,
            "download_url": None,
            "inline_text": None,
        }
        # text:inline is a special marker meaning the document text is stored in extracted_text column
        if f.s3_key and not f.s3_key.startswith("text:"):
            try:
                entry["download_url"] = generate_download_url_from_config(f.s3_key, s3_config, 3600)
            except Exception as e:
                entry["download_error"] = str(e)
        # For inline text files (no S3): serve the stored extracted_text directly
        if f.s3_key.startswith("text:") or (f.mime_type == "text/plain" and not f.s3_key):
            if f.extracted_text:
                entry["inline_text"] = f.extracted_text
        file_list.append(entry)

    # Fallback for legacy RFQs: if no RFQFile records exist but RFQ has_documents=True,
    # synthesize a virtual file from the project_description so providers see something.
    if not file_list and rfq.has_documents:
        fallback_text = rfq.project_description or ""
        if fallback_text.strip():
            file_list.append({
                "file_id": "virtual-doc",
                "filename": "project_document.txt",
                "download_url": None,
                "inline_text": fallback_text,
            })

    return {"files": file_list}


@router.get("/provider/rfqs/{rfq_id}/files/{file_id}/download")
async def get_rfq_file_download_url(
    rfq_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a fresh presigned download URL for a specific RFQ file."""
    from sqlalchemy import select
    from app.models.rfq import RFQUnlock, RFQFile, RFQ as _RFQModel3
    from app.models.provider import ProviderMembership
    from app.services.file_service import generate_download_url_from_config
    from app.services.config_service import get_runtime_config

    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a provider")

    result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == membership.provider_id,
            RFQUnlock.unlock_status == "unlocked"
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="RFQ not unlocked")

    result = await db.execute(
        select(RFQFile).where(RFQFile.rfq_id == rfq_id, RFQFile.id == file_id)
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    if file.s3_key and file.s3_key.startswith("text:"):
        if file.extracted_text:
            return {"inline_text": file.extracted_text, "filename": file.original_filename}
        raise HTTPException(status_code=404, detail="No content available")

    s3_config = await get_runtime_config(db)
    try:
        url = generate_download_url_from_config(file.s3_key, s3_config, 3600)
        return {"download_url": url, "filename": file.original_filename}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"S3 error: {str(e)}"
        )





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
    # If RFQ was submitted anonymously, the user paying for NDA claims ownership
    if rfq.customer_user_id is None:
        rfq.customer_user_id = current_user.id
        await db.commit()
    elif str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    # Must require NDA
    if not rfq.nda_required:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="NDA not required for this RFQ")

    # Check NDA payment has been completed (status must be past awaiting_nda_payment)
    current_rfq_status = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status)
    if current_rfq_status not in ("awaiting_nda_payment", "awaiting_customer_signature", "draft", "submitted"):
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
        # If no Signwell document yet (payment recorded but signing post-acceptance), return status
        if not existing_nda.signrequest_document_id:
            return {
                "document_id": None,
                "signing_url": None,
                "status": existing_nda.nda_status.value if hasattr(existing_nda.nda_status, "value") else str(existing_nda.nda_status),
                "message": "NDA payment recorded. Signing instructions will be sent to both parties after a provider quote is approved.",
            }
        # Return existing signing URL if still pending (legacy flow with document already created)
        from app.services.nda_service import get_customer_signing_url
        signing_url = await get_customer_signing_url(rfq_id, db)
        return {
            "document_id": existing_nda.signrequest_document_id,
            "signing_url": signing_url,
            "status": existing_nda.nda_status.value if hasattr(existing_nda.nda_status, "value") else str(existing_nda.nda_status),
            "message": "Existing NDA document found",
        }

    try:
        result = await create_customer_nda(rfq_id, current_user, rfq, db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        import logging as _log2
        _log2.getLogger(__name__).error("create_customer_nda failed rfq=%s: %s", rfq_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create NDA document: {str(exc)}",
        )

    # Update RFQ status from awaiting_nda_payment -> awaiting_customer_signature
    if current_rfq_status == "awaiting_nda_payment":
        rfq.rfq_status = "awaiting_customer_signature"
        await db.commit()

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

    # If RFQ was submitted anonymously, the user paying for NDA claims ownership
    if rfq.customer_user_id is None:
        rfq.customer_user_id = current_user.id
        await db.commit()
    elif str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    signing_url = await get_customer_signing_url(rfq_id, db)
    return {"signing_url": signing_url}


@router.post("/rfqs/{rfq_id}/nda/confirm-signed")
async def nda_confirm_signed(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Confirm customer NDA signing without relying on webhook.

    Called by the frontend immediately after the Signwell iframe signals
    completion. Acts as the primary fulfillment path; the webhook is a backup.

    - If customer_signed_at already in DB: advances RFQ and returns.
    - If not yet recorded: polls Signwell API directly to check and heal.
    - Always idempotent and safe to call multiple times.
    """
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.services.nda_service import confirm_customer_signed_from_signwell

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    # If RFQ was submitted anonymously, the user paying for NDA claims ownership
    if rfq.customer_user_id is None:
        rfq.customer_user_id = current_user.id
        await db.commit()
    elif str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    try:
        result_data = await confirm_customer_signed_from_signwell(rfq_id, db)
        current_status = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status)
        return {
            **result_data,
            "rfq_status": current_status,
        }
    except Exception as exc:
        _log.error(f"confirm_signed error rfq={rfq_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error confirming signature: {str(exc)}"
        )


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

    # If RFQ was submitted anonymously, the user paying for NDA claims ownership
    if rfq.customer_user_id is None:
        rfq.customer_user_id = current_user.id
        await db.commit()
    elif str(rfq.customer_user_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your RFQ")

    # Look for most recent NDA for this RFQ (post-acceptance has provider_id set, pre-acceptance has None)
    result = await db.execute(
        select(RFQNDA).where(
            RFQNDA.rfq_id == rfq_id,
        ).order_by(RFQNDA.created_at.desc())
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
        "is_post_acceptance": nda.provider_id is not None,
        "customer_signed_at": nda.customer_signed_at.isoformat() if nda.customer_signed_at else None,
        "provider_signed_at": nda.provider_signed_at.isoformat() if nda.provider_signed_at else None,
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
            RFQUnlock.unlock_status == "unlocked",
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
