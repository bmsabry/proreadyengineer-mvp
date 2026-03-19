"""RFQ lifecycle service with concurrency-safe unlock logic."""

import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    NdaStatus,
    Provider,
    ProviderMembership,
    ProviderMembership,
    Quote,
    QuoteStatus,
    RFQ,
    RFQDispatch,
    RFQDispatchBatch,
    RFQFile,
    RFQMatch,
    RFQNDA,
    RfqStatus,
    RFQUnlock,
    UnlockStatus,
    User,
)
from app.schemas.quote import QuoteCreateRequest
from app.schemas.rfq import RFQCreateRequest


async def create_rfq(
    db: AsyncSession,
    data: RFQCreateRequest,
    user: Optional[User] = None,
) -> RFQ:
    """Create a new RFQ draft.

    Args:
        db: Database session.
        data: RFQ creation data.
        user: Authenticated user or None for guest.

    Returns:
        RFQ: Created RFQ record.
    """
    rfq = RFQ(
        customer_user_id=user.id if user else None,
        customer_email=data.customer_email,
        business_name=data.business_name,
        contact_name=data.contact_name,
        project_description=data.project_description,
        urgency=data.urgency,
        tollgate_phases=data.tollgate_phases,
        nda_required=data.nda_required,
        rfq_status=RfqStatus.DRAFT,
    )

    db.add(rfq)
    await db.commit()
    await db.refresh(rfq)

    return rfq


async def get_rfq(db: AsyncSession, rfq_id: uuid.UUID) -> Optional[RFQ]:
    """Get RFQ by ID with related data.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.

    Returns:
        RFQ | None: RFQ record with loaded relationships.
    """
    result = await db.execute(
        select(RFQ)
        .options(
            selectinload(RFQ.files),
            selectinload(RFQ.matches),
            selectinload(RFQ.quotes),
        )
        .where(RFQ.id == rfq_id)
    )
    return result.scalar_one_or_none()


async def submit_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> None:
    """Submit RFQ: run full search, store ALL matches, schedule dispatch."""
    rfq = await get_rfq(db, rfq_id)
    if not rfq:
        raise ValueError("RFQ not found")
    if rfq.rfq_status != RfqStatus.DRAFT:
        raise ValueError("RFQ is not in draft status")

    # Check NDA flow
    if rfq.nda_required:
        rfq.rfq_status = RfqStatus.AWAITING_NDA_PAYMENT
        await db.commit()
        return

    rfq.rfq_status = RfqStatus.OPEN_FOR_DISPATCH
    rfq.submitted_at = datetime.utcnow()

    # Run full AI search - NO LIMIT, get ALL relevant providers
    from app.services.search_service import search_providers
    match_results = await search_providers(
        db,
        query=rfq.project_description,
        filters={},
        limit=9999,
    )

    # Store ALL ranked matches
    for idx, result in enumerate(match_results, 1):
        provider = result["provider"]
        rfq_match = RFQMatch(
            rfq_id=rfq.id,
            provider_id=provider.id,
            rank_position=idx,
            composite_score=result["composite_score"],
            specialty_score=result.get("specialty_score", 0),
            capabilities_score=result.get("capabilities_score", 0),
            tier_score=result.get("tier_score", 0),
            scoring_inputs=result.get("scoring_inputs", {}),
        )
        db.add(rfq_match)

    await db.commit()

    # Dispatch Batch 1 immediately
    await dispatch_next_batch(db, rfq_id)


async def dispatch_next_batch(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> list:
    """Dispatch the next 5 un-dispatched providers for an RFQ.

    Called at submit time for Batch 1, then every 24h if quote_count < 5.
    """
    from app.models import DispatchStatus

    # Check RFQ is still open
    rfq = await db.get(RFQ, rfq_id)
    if not rfq or rfq.is_closed or rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        return []

    # Get next 5 un-dispatched matches ordered by rank
    result = await db.execute(
        select(RFQMatch)
        .where(
            RFQMatch.rfq_id == rfq_id,
            RFQMatch.is_dispatched == False,
        )
        .order_by(RFQMatch.rank_position)
        .limit(5)
    )
    matches = result.scalars().all()

    if not matches:
        # All providers contacted and still < 5 quotes - close as no-selection
        rfq.rfq_status = RfqStatus.CLOSED_NO_SELECTION
        rfq.is_closed = True
        rfq.closed_at = datetime.utcnow()
        await db.commit()
        return []

    # Determine current batch number
    batch_result = await db.execute(
        select(func.count()).where(RFQDispatchBatch.rfq_id == rfq_id)
    )
    batch_count = batch_result.scalar() or 0
    batch_number = batch_count + 1

    # Create batch record
    batch = RFQDispatchBatch(
        rfq_id=rfq_id,
        batch_number=batch_number,
        scheduled_for=datetime.utcnow(),
        dispatched_at=datetime.utcnow(),
        status="dispatched",
    )
    db.add(batch)
    await db.flush()

    dispatched = []
    for match in matches:
        provider = await db.get(Provider, match.provider_id)
        if not provider:
            continue

        email_target = None
        if provider.email_addresses:
            if isinstance(provider.email_addresses, list) and provider.email_addresses:
                email_target = provider.email_addresses[0]
            elif isinstance(provider.email_addresses, str) and provider.email_addresses:
                email_target = provider.email_addresses

        dispatch = RFQDispatch(
            rfq_id=rfq_id,
            provider_id=match.provider_id,
            batch_id=batch.id,
            dispatch_status=DispatchStatus.SENT if email_target else DispatchStatus.FAILED,
            email_target=email_target,
            teaser_email_sent_at=datetime.utcnow() if email_target else None,
        )
        db.add(dispatch)

        match.is_dispatched = True
        match.dispatched_at = datetime.utcnow()

        if email_target:
            try:
                from app.services.email_service import send_teaser_email
                rfq_data = {
                    "rfq_id": str(rfq_id),
                    "urgency": rfq.urgency,
                    "tollgate_phases": rfq.tollgate_phases or [],
                    "project_description": (
                        rfq.project_description[:200] + "..."
                        if len(rfq.project_description) > 200
                        else rfq.project_description
                    ),
                    "nda_required": rfq.nda_required,
                    "batch_number": batch_number,
                }
                await send_teaser_email(email_target, rfq_data, db=db)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error(
                    "Failed to send teaser email to %s: %s", email_target, exc
                )

        dispatched.append(dispatch)

    # Advance RFQ status to accepting unlocks
    rfq.rfq_status = RfqStatus.OPEN_FOR_UNLOCK
    await db.commit()
    return dispatched


async def get_rfq_matches(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> list[RFQMatch]:
    """Get all matches for an RFQ.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.

    Returns:
        list[RFQMatch]: Ordered list of matches.
    """
    result = await db.execute(
        select(RFQMatch)
        .where(RFQMatch.rfq_id == rfq_id)
        .order_by(RFQMatch.rank_position)
    )
    return list(result.scalars().all())


async def unlock_rfq(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
    user: User,
) -> RFQUnlock:
    """Unlock RFQ for a provider with concurrency-safe logic.

    CRITICAL: Uses SELECT FOR UPDATE to prevent race conditions.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.
        provider_id: Provider ID.
        user: Provider user requesting unlock.

    Returns:
        RFQUnlock: Created unlock record.

    Raises:
        ValueError: If RFQ closed, quota reached, or already unlocked.
        PermissionError: If user not authorized for provider.
    """
    from sqlalchemy import text

    # Verify user has membership with provider
    membership_result = await db.execute(
        select(ProviderMembership).where(
            ProviderMembership.provider_id == provider_id,
            ProviderMembership.user_id == user.id,
            ProviderMembership.status == "active",
        )
    )
    if not membership_result.scalar_one_or_none():
        raise PermissionError("User not authorized for this provider")

    # Lock the RFQ row to prevent concurrent modifications
    # Using raw SQL for SELECT FOR UPDATE
    lock_result = await db.execute(
        text("SELECT * FROM rfqs WHERE id = :rfq_id FOR UPDATE"),
        {"rfq_id": str(rfq_id)},
    )
    rfq_row = lock_result.fetchone()

    if not rfq_row:
        raise ValueError("RFQ not found")

    # Re-check conditions after acquiring lock
    if rfq_row.is_closed:
        raise ValueError("RFQ is closed")

    if rfq_row.quote_count >= settings.RFQ_MAX_QUOTES:
        raise ValueError("Quote limit reached")

    # Check for existing unlock
    existing_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status.in_([UnlockStatus.UNLOCKED, UnlockStatus.PAYMENT_PENDING]),
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError("RFQ already unlocked for this provider")

    # Create unlock record
    unlock = RFQUnlock(
        rfq_id=rfq_id,
        provider_id=provider_id,
        unlocked_by_user_id=user.id,
        unlock_status=UnlockStatus.PAYMENT_PENDING,
    )
    db.add(unlock)

    await db.commit()
    await db.refresh(unlock)

    return unlock


async def complete_rfq_unlock(
    db: AsyncSession,
    unlock_id: uuid.UUID,
) -> RFQUnlock:
    """Complete unlock after payment verification.

    Called by payment webhook handler.

    Args:
        db: Database session.
        unlock_id: Unlock record UUID.

    Returns:
        RFQUnlock: Updated unlock record.
    """
    unlock = await db.get(RFQUnlock, unlock_id)
    if not unlock:
        raise ValueError("Unlock record not found")

    if unlock.unlock_status != UnlockStatus.PAYMENT_PENDING:
        raise ValueError("Unlock not in payment pending state")

    # Lock RFQ and increment quote_count
    from sqlalchemy import text
    await db.execute(
        text("SELECT * FROM rfqs WHERE id = :rfq_id FOR UPDATE"),
        {"rfq_id": str(unlock.rfq_id)},
    )

    # Re-verify conditions
    rfq = await db.get(RFQ, unlock.rfq_id)
    if not rfq or rfq.is_closed:
        raise ValueError("RFQ is closed or no longer available")

    if rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        raise ValueError("Quote limit reached - unlock cannot be completed")

    # Update unlock
    unlock.unlock_status = UnlockStatus.UNLOCKED
    unlock.unlocked_at = datetime.utcnow()

    # Increment quote_count
    rfq.quote_count += 1

    # Check if limit reached
    if rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        rfq.rfq_status = RfqStatus.QUOTE_LIMIT_REACHED
        rfq.is_closed = True
        rfq.closed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(unlock)

    return unlock


async def can_submit_quote(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
) -> tuple[bool, str]:
    """Check if provider can submit a quote for this RFQ.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.
        provider_id: Provider ID.

    Returns:
        tuple[bool, str]: (can_submit, reason).
    """
    rfq = await db.get(RFQ, rfq_id)
    if not rfq:
        return False, "RFQ not found"

    if rfq.is_closed:
        return False, "RFQ is closed"

    if rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        return False, "Quote limit reached"

    # Check for valid unlock
    unlock_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status == UnlockStatus.UNLOCKED,
        )
    )
    unlock = unlock_result.scalar_one_or_none()
    if not unlock:
        return False, "RFQ not unlocked for this provider"

    # Check if already submitted a quote
    existing_result = await db.execute(
        select(Quote).where(
            Quote.rfq_id == rfq_id,
            Quote.provider_id == provider_id,
            Quote.quote_status.in_([QuoteStatus.SUBMITTED, QuoteStatus.ACCEPTED]),
        )
    )
    if existing_result.scalar_one_or_none():
        return False, "Quote already submitted"

    return True, "OK"


async def submit_quote(
    db: AsyncSession,
    data: QuoteCreateRequest,
    rfq_id: uuid.UUID,
    provider_id: int,
    user: User,
) -> Quote:
    """Submit a quote for an RFQ.

    Args:
        db: Database session.
        data: Quote data.
        rfq_id: RFQ UUID.
        provider_id: Provider ID.
        user: Submitting user.

    Returns:
        Quote: Created quote record.

    Raises:
        ValueError: If submission not allowed.
    """
    can_submit, reason = await can_submit_quote(db, rfq_id, provider_id)
    if not can_submit:
        raise ValueError(f"Cannot submit quote: {reason}")

    quote = Quote(
        rfq_id=rfq_id,
        provider_id=provider_id,
        submitter_user_id=user.id,
        quote_status=QuoteStatus.SUBMITTED,
        rough_price_min=data.rough_price_min,
        rough_price_max=data.rough_price_max,
        currency=data.currency,
        turnaround_estimate_text=data.turnaround_estimate_text,
        assumptions_text=data.assumptions_text,
        scope_notes=data.scope_notes,
        submitted_at=datetime.utcnow(),
    )

    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    return quote


async def accept_quote(
    db: AsyncSession,
    quote_id: uuid.UUID,
    customer: User,
) -> None:
    """Accept a quote and close the RFQ.

    Args:
        db: Database session.
        quote_id: Quote UUID.
        customer: Customer user accepting the quote.

    Raises:
        ValueError: If quote not found or RFQ not accessible.
        PermissionError: If customer doesn't own the RFQ.
    """
    from sqlalchemy.orm import joinedload

    result = await db.execute(
        select(Quote)
        .options(joinedload(Quote.rfq))
        .where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise ValueError("Quote not found")

    rfq = quote.rfq

    # Verify customer owns this RFQ
    if rfq.customer_user_id != customer.id:
        raise PermissionError("Not authorized to accept this quote")

    if rfq.is_closed and rfq.rfq_status != RfqStatus.QUOTE_LIMIT_REACHED:
        raise ValueError("RFQ is already closed")

    # Update quote status
    quote.quote_status = QuoteStatus.ACCEPTED

    # Close RFQ and mark selected provider
    rfq.is_closed = True
    rfq.rfq_status = RfqStatus.CUSTOMER_SELECTED_PROVIDER
    rfq.selected_provider_id = quote.provider_id
    rfq.closed_at = datetime.utcnow()

    # Mark other quotes as not_selected
    result = await db.execute(
        select(Quote).where(
            Quote.rfq_id == rfq.id,
            Quote.id != quote_id,
            Quote.quote_status.in_([QuoteStatus.SUBMITTED, QuoteStatus.CUSTOMER_VIEWED]),
        )
    )
    other_quotes = result.scalars().all()
    for other in other_quotes:
        other.quote_status = QuoteStatus.NOT_SELECTED

    await db.commit()

    # Notify provider (via email service)
    # This would queue Celery task in production


async def check_rfq_nda_status(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> Optional[RFQNDA]:
    """Get NDA status for an RFQ.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.

    Returns:
        RFQNDA | None: NDA record if exists.
    """
    result = await db.execute(
        select(RFQNDA).where(RFQNDA.rfq_id == rfq_id)
    )
    return result.scalar_one_or_none()


async def create_customer_nda(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    customer: User,
) -> RFQNDA:
    """Create NDA record for customer signing.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.
        customer: Customer user.

    Returns:
        RFQNDA: Created NDA record.
    """
    nda = RFQNDA(
        rfq_id=rfq_id,
        customer_user_id=customer.id,
        nda_status=NdaStatus.CUSTOMER_SIGNATURE_PENDING,
    )

    db.add(nda)

    # Update RFQ status
    rfq = await db.get(RFQ, rfq_id)
    rfq.rfq_status = RfqStatus.AWAITING_CUSTOMER_SIGNATURE

    await db.commit()
    await db.refresh(nda)

    return nda


async def get_provider_unlocked_rfq_files(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
) -> list[RFQFile]:
    """Get RFQ files for a provider who has unlocked.

    Args:
        db: Database session.
        rfq_id: RFQ UUID.
        provider_id: Provider ID.

    Returns:
        list[RFQFile]: RFQ files if unlocked.

    Raises:
        PermissionError: If RFQ not unlocked.
    """
    # Verify unlock exists
    unlock_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status == UnlockStatus.UNLOCKED,
        )
    )
    if not unlock_result.scalar_one_or_none():
        raise PermissionError("RFQ not unlocked")

    # Get files
    result = await db.execute(
        select(RFQFile).where(RFQFile.rfq_id == rfq_id)
    )
    return list(result.scalars().all())
