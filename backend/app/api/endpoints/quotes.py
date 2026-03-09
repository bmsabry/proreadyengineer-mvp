"""Quote API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_db, get_current_active_user, require_role
from app.schemas.quote import QuoteResponse, QuoteCreateRequest
from app.models.user import User
from app.services.rfq_service import submit_quote, accept_quote

router = APIRouter()


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
    result = await db.execute(select(RFQ).where(RFQ.id == rfq_id))
    rfq = result.scalar_one_or_none()

    if not rfq:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if rfq.customer_user_id != current_user.id and "admin" not in (current_user.roles or []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Get quotes
    result = await db.execute(
        select(Quote).where(Quote.rfq_id == rfq_id).order_by(Quote.created_at.desc())
    )
    quotes = result.scalars().all()

    return [QuoteResponse.from_orm(q) for q in quotes]


@router.post("/customer/quotes/{quote_id}/accept")
async def accept_quote_endpoint(
    quote_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Accept a quote (customer only)."""
    await accept_quote(db, quote_id, current_user)
    return {"message": "Quote accepted"}


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
