"""Quote API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.quote import QuoteResponse, QuoteCreateRequest, QuoteAcceptResponse
from app.models.user import User
from app.services.rfq_service import submit_quote, accept_quote

router = APIRouter()


@router.post("/provider/rfqs/{rfq_id}/quote", response_model=QuoteResponse)
async def submit_provider_quote(
    rfq_id: str,
    data: QuoteCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Submit a quote for an unlocked RFQ (provider only)."""
    from sqlalchemy import select, func
    from app.models.provider import ProviderMembership
    from app.models.rfq import RFQ
    from app.models.quote import Quote
    from app.models.enums import RfqStatus
    from app.core.config import settings

    # 1. Get provider membership
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No provider firm linked to your account"
        )

    # 2. Parse rfq_id
    try:
        rfq_uuid = uuid.UUID(rfq_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid RFQ ID format"
        )

    # 3. Submit the quote (validates unlock, duplicate check, RFQ open status)
    try:
        quote = await submit_quote(
            db=db,
            data=data,
            rfq_id=rfq_uuid,
            provider_id=membership.provider_id,
            user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 4. Update quote_count using live SQL count (prevents stale-counter corruption)
    rfq_result = await db.execute(select(RFQ).where(RFQ.id == rfq_uuid))
    rfq = rfq_result.scalar_one_or_none()
    if rfq:
        from sqlalchemy import func as _qfunc
        _live_res = await db.execute(
            select(_qfunc.count()).select_from(Quote).where(
                Quote.rfq_id == rfq_uuid,
                Quote.quote_status.in_(["submitted", "accepted"]),
            )
        )
        rfq.quote_count = _live_res.scalar() or 0
        max_quotes = getattr(settings, "RFQ_MAX_QUOTES", 5)
        if rfq.quote_count >= max_quotes:
            rfq.rfq_status = RfqStatus.QUOTE_LIMIT_REACHED
            rfq.is_closed = True
        await db.commit()
        await db.refresh(rfq)

    # 5. Send customer notification email in background
    async def _notify_customer():
        try:
            from app.services.email_service import send_quote_notification
            from sqlalchemy.orm import joinedload
            # Re-fetch quote with relationships for email
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as notify_db:
                q_result = await notify_db.execute(
                    select(Quote)
                    .options(
                        joinedload(Quote.rfq),
                        joinedload(Quote.provider)
                    )
                    .where(Quote.id == quote.id)
                )
                full_quote = q_result.scalar_one_or_none()
                if full_quote and full_quote.rfq and full_quote.rfq.customer_email:
                    await send_quote_notification(
                        db=notify_db,
                        recipient_email=full_quote.rfq.customer_email,
                        quote=full_quote,
                    )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Quote notification email failed: {e}")

    background_tasks.add_task(_notify_customer)

    return QuoteResponse.from_orm(quote)


@router.get("/customer/rfqs/{rfq_id}/quotes", response_model=List[QuoteResponse])
async def get_customer_quotes(
    rfq_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get all quotes for customer's RFQ."""
    from sqlalchemy import select
    from app.models.rfq import RFQ
    from app.models.quote import Quote

    # Verify RFQ ownership
    # Parse rfq_id to UUID for correct PostgreSQL comparison
    try:
        rfq_uuid_q = uuid.UUID(rfq_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid RFQ ID")

    result = await db.execute(select(RFQ).where(RFQ.id == rfq_uuid_q))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Get quotes
    result = await db.execute(
        select(Quote).where(Quote.rfq_id == rfq_uuid_q).order_by(Quote.created_at.desc())
    )
    quotes = result.scalars().all()

    return [QuoteResponse.from_orm(q) for q in quotes]


@router.post("/customer/quotes/{quote_id}/accept", response_model=QuoteAcceptResponse)
async def accept_quote_endpoint(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Accept a quote (customer only). Returns provider contact info on success."""
    try:
        quote_uuid = uuid.UUID(quote_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid quote ID")

    try:
        provider_contact = await accept_quote(db, quote_uuid, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Accept quote error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Re-fetch the accepted quote to get rfq_id and provider_id
    from sqlalchemy import select as _select
    from app.models.quote import Quote as _Quote
    result = await db.execute(_select(_Quote).where(_Quote.id == quote_uuid))
    quote = result.scalar_one_or_none()

    return QuoteAcceptResponse(
        success=True,
        message="Quote accepted successfully. Provider contact details are now revealed.",
        rfq_id=quote.rfq_id,
        selected_quote_id=quote.id,
        selected_provider_id=quote.provider_id,
        provider_contact_revealed=True,
        provider_name=provider_contact.get("provider_name"),
        provider_email=provider_contact.get("provider_email"),
        provider_phone=provider_contact.get("provider_phone"),
        provider_website=provider_contact.get("provider_website"),
        provider_city=provider_contact.get("provider_city"),
        provider_state=provider_contact.get("provider_state"),
        provider_address=provider_contact.get("provider_address"),
    )


@router.post("/provider/quotes/{quote_id}/withdraw")
async def withdraw_quote(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Withdraw a submitted quote (provider only)."""
    from sqlalchemy import select
    from app.models.quote import Quote
    from app.models.provider import ProviderMembership

    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    # Verify provider owns this quote
    result = await db.execute(
        select(ProviderMembership).where(
            ProviderMembership.provider_id == quote.provider_id,
            ProviderMembership.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    quote.quote_status = "withdrawn"
    await db.commit()

    return {"message": "Quote withdrawn"}


@router.get("/provider/quotes/me", response_model=List[QuoteResponse])
async def get_provider_quotes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["provider"])),
):
    """Get all quotes submitted by provider."""
    from sqlalchemy import select
    from app.models.quote import Quote
    from app.models.provider import ProviderMembership

    # Get user's provider
    result = await db.execute(
        select(ProviderMembership).where(ProviderMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()

    if not membership:
        return []

    result = await db.execute(
        select(Quote).where(Quote.provider_id == membership.provider_id)
    )
    quotes = result.scalars().all()

    return [QuoteResponse.from_orm(q) for q in quotes]
