"""RFQ lifecycle service with concurrency-safe unlock logic."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.services.config_service import get_runtime_config as _get_runtime_config
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


logger = logging.getLogger(__name__)


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
    """Background task: AI search -> store matches -> dispatch batch 1."""
    # FIX 1: coerce string rfq_id to UUID
    if isinstance(rfq_id, str):
        rfq_id = uuid.UUID(rfq_id)

    logger.info("submit_rfq starting for rfq_id=%s", rfq_id)

    try:
        rfq = await get_rfq(db, rfq_id)
        if not rfq:
            logger.error("submit_rfq: RFQ not found rfq_id=%s", rfq_id)
            raise ValueError("RFQ not found")
        logger.info("submit_rfq: found rfq status=%s nda=%s", rfq.rfq_status, rfq.nda_required)

        if rfq.rfq_status != RfqStatus.DRAFT:
            raise ValueError("RFQ is not in draft status")

        if rfq.nda_required:
            rfq.rfq_status = RfqStatus.AWAITING_NDA_PAYMENT
            await db.commit()
            return

        rfq.rfq_status = RfqStatus.OPEN_FOR_DISPATCH
        rfq.submitted_at = datetime.now(timezone.utc)

        from app.services.search_service import search_providers
        logger.info("submit_rfq: running AI search rfq_id=%s", rfq_id)
        # FIX: search_providers returns a tuple (results_list, pipeline_info)
        match_results, _pipeline_info = await search_providers(
            db,
            query=rfq.project_description,
            filters={},
            limit=9999,
            top_n=None,  # Get ALL ranked providers for dispatch
        )
        logger.info("submit_rfq: search returned %d results rfq_id=%s", len(match_results), rfq_id)

        # FIX: match_results is a list of SearchResultItem dataclasses, not dicts
        for rank_idx, result in enumerate(match_results, 1):
            provider = result.provider  # dataclass attribute, not dict key
            rfq_match = RFQMatch(
                rfq_id=rfq.id,
                provider_id=provider.id,
                rank_position=rank_idx,
                composite_score=int(result.score),  # .score is the float total
                specialty_score=int(result.specialty_score),
                capabilities_score=int(result.capabilities_score),
                tier_score=int(result.tier_score),
                scoring_inputs={},  # SearchResultItem has no scoring_inputs field
            )
            db.add(rfq_match)

        await db.commit()
        logger.info("submit_rfq: stored %d matches rfq_id=%s", len(match_results), rfq_id)

        logger.info("submit_rfq: calling dispatch_next_batch rfq_id=%s", rfq_id)
        await dispatch_next_batch(db, rfq_id)
        logger.info("submit_rfq: completed rfq_id=%s", rfq_id)

    except Exception:
        logger.error("submit_rfq: exception rfq_id=%s", rfq_id, exc_info=True)
        raise


async def dispatch_next_batch(
    db: AsyncSession,
    rfq_id: uuid.UUID,
) -> list:
    """
    Dispatch next batch of un-dispatched ranked providers for an RFQ.

    OUTBOX PATTERN - ensures no infinite re-dispatch loop:
      PHASE 1: Build all DB records (batch, dispatches, mark matches) and
               collect emails_to_send list.  No emails sent here.
      COMMIT:  Persist everything before any side effects.
      PHASE 2: Send emails AFTER commit.  Failures are logged but never
               re-raise, so the committed batch record remains intact and
               the interval guard works correctly on the next scheduler tick.
      PHASE 3: Close the RFQ if no undispatched matches remain.
    """
    from app.models import DispatchStatus
    from app.services.email_service import send_teaser_email
    from app.services.auth_service import create_invite_token as _cit
    import json as _json

    # Coerce string rfq_id to UUID
    if isinstance(rfq_id, str):
        rfq_id = uuid.UUID(rfq_id)

    rfq = await db.get(RFQ, rfq_id)
    if not rfq:
        return []
    if rfq.is_closed:
        return []
    if rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        # Close RFQ when quote limit is reached in case it slipped through
        if not rfq.is_closed:
            rfq.rfq_status = RfqStatus.QUOTE_LIMIT_REACHED
            rfq.is_closed = True
            rfq.closed_at = datetime.utcnow()
            await db.commit()
        return []

    # Read batch size from admin config (default 5)
    try:
        cfg = await _get_runtime_config(db)
        batch_size = int(cfg.get('RFQ_BATCH_SIZE', settings.RFQ_DISPATCH_BATCH_SIZE))
    except Exception:
        batch_size = settings.RFQ_DISPATCH_BATCH_SIZE

    result = await db.execute(
        select(RFQMatch)
        .where(
            RFQMatch.rfq_id == rfq_id,
            RFQMatch.is_dispatched == False,
        )
        .order_by(RFQMatch.rank_position)
        .limit(batch_size)
    )
    matches = result.scalars().all()

    if not matches:
        rfq.rfq_status = RfqStatus.CLOSED_NO_SELECTION
        rfq.is_closed = True
        rfq.closed_at = datetime.utcnow()
        await db.commit()
        return []

    batch_result = await db.execute(
        select(func.count()).where(RFQDispatchBatch.rfq_id == rfq_id)
    )
    batch_count = batch_result.scalar() or 0
    batch_number = batch_count + 1

    # -------------------------------------------------------------------------
    # PHASE 1: Build all DB records - NO email sending yet
    # -------------------------------------------------------------------------
    batch = RFQDispatchBatch(
        rfq_id=rfq_id,
        batch_number=batch_number,
        scheduled_for=datetime.utcnow(),
        dispatched_at=datetime.utcnow(),
        status="dispatched",
    )
    db.add(batch)
    await db.flush()  # populate batch.id without committing
    if batch.id is None:
        await db.refresh(batch)

    dispatched = []
    # Collect (email_target, rfq_data, invite_token) tuples for Phase 2
    emails_to_send = []

    for match in matches:
        provider = await db.get(Provider, match.provider_id)
        if not provider:
            match.is_dispatched = True
            continue

        # Parse email_addresses - may be stored as JSON string or list
        email_target = None
        if provider.email_addresses:
            emails = provider.email_addresses
            if isinstance(emails, str):
                try:
                    emails = _json.loads(emails)
                except Exception:
                    emails = [emails]
            if isinstance(emails, list) and emails:
                email_target = emails[0]
            elif isinstance(emails, str) and emails:
                email_target = emails

        # Idempotency: skip if this provider was already dispatched for this RFQ
        existing_chk = await db.execute(
            select(RFQDispatch).where(
                RFQDispatch.rfq_id == rfq_id,
                RFQDispatch.provider_id == match.provider_id,
            ).limit(1)
        )
        if existing_chk.scalars().first() is not None:
            match.is_dispatched = True
            continue

        # Generate invite token now (pre-commit) - pure computation, no side effects
        _invite_token = None
        if email_target:
            _invite_token = _cit(
                rfq_id=str(rfq_id),
                provider_id=match.provider_id,
                dispatch_id=str(uuid.uuid4()),
                sent_to_email=email_target or "",
            )

        # Build RFQ data snapshot (capture before any future mutations)
        rfq_data = {
            "rfq_id": str(rfq_id),
            "urgency": rfq.urgency,
            "tollgate_phases": rfq.tollgate_phases or [],
            "project_description": (
                rfq.project_description[:200] + '...'
                if len(rfq.project_description) > 200
                else rfq.project_description
            ),
            "nda_required": rfq.nda_required,
            "batch_number": batch_number,
        }

        # Create dispatch record (status set optimistically; email follows post-commit)
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

        dispatched.append(dispatch)

        # Queue email for Phase 2 (only if we have a target and token)
        if email_target and _invite_token:
            emails_to_send.append((email_target, rfq_data, _invite_token))

    rfq.rfq_status = RfqStatus.OPEN_FOR_UNLOCK

    # -------------------------------------------------------------------------
    # COMMIT - all DB records persisted before any email is sent
    # If this commit fails, no emails have gone out, no infinite loop possible
    # -------------------------------------------------------------------------
    await db.commit()
    logger.info(
        "dispatch_next_batch: committed batch %d for RFQ %s (%d dispatches, %d emails queued)",
        batch_number, rfq_id, len(dispatched), len(emails_to_send),
    )

    # -------------------------------------------------------------------------
    # PHASE 2: Send emails AFTER commit (side effects outside the transaction)
    # If an email fails, the batch record already exists so the interval guard
    # will prevent re-dispatch on the next scheduler tick.
    # -------------------------------------------------------------------------
    send_failures = 0
    for (email_target, rfq_data, invite_token) in emails_to_send:
        try:
            await send_teaser_email(email_target, rfq_data, db=db, invite_token=invite_token)
        except Exception as exc:
            send_failures += 1
            logger.error(
                "dispatch_next_batch: failed to send teaser email to %s (rfq=%s): %s",
                email_target, rfq_id, exc,
            )
            # Do NOT re-raise - batch record is committed; no re-dispatch loop

    if send_failures:
        logger.warning(
            "dispatch_next_batch: %d/%d emails failed for RFQ %s. "
            "Batch record is committed; failures will not cause re-dispatch.",
            send_failures, len(emails_to_send), rfq_id,
        )

    # -------------------------------------------------------------------------
    # PHASE 3: Close RFQ immediately if this was the last batch
    # -------------------------------------------------------------------------
    remaining_result = await db.execute(
        select(func.count()).where(
            RFQMatch.rfq_id == rfq_id,
            RFQMatch.is_dispatched == False,
        )
    )
    remaining_count = remaining_result.scalar() or 0
    if remaining_count == 0:
        await db.refresh(rfq)
        if not rfq.is_closed:
            rfq.rfq_status = RfqStatus.CLOSED_NO_SELECTION
            rfq.is_closed = True
            rfq.closed_at = datetime.utcnow()
            await db.commit()
            logger.info(
                "dispatch_next_batch: all matches dispatched for RFQ %s, closing.",
                rfq_id,
            )

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

    from sqlalchemy import func as _func
    from app.models.quote import Quote as _QuoteModel
    _sq_res = await db.execute(
        select(_func.count()).select_from(_QuoteModel).where(
            _QuoteModel.rfq_id == rfq_id,
            _QuoteModel.quote_status.in_(["submitted", "accepted"])
        )
    )
    if (_sq_res.scalar() or 0) >= settings.RFQ_MAX_QUOTES:
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

    from sqlalchemy import func as _func2
    from app.models.quote import Quote as _QuoteModel2
    _sq_res2 = await db.execute(
        select(_func2.count()).select_from(_QuoteModel2).where(
            _QuoteModel2.rfq_id == unlock.rfq_id,
            _QuoteModel2.quote_status.in_(["submitted", "accepted"])
        )
    )
    if (_sq_res2.scalar() or 0) >= settings.RFQ_MAX_QUOTES:
        raise ValueError("Quote limit reached - unlock cannot be completed")

    # Update unlock
    unlock.unlock_status = UnlockStatus.UNLOCKED
    unlock.unlocked_at = datetime.utcnow()

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

    # Use live SQL count instead of stale rfq.quote_count to prevent false rejections
    from sqlalchemy import func as _csq_func
    _live_count_res = await db.execute(
        select(_csq_func.count()).select_from(Quote).where(
            Quote.rfq_id == rfq_id,
            Quote.quote_status.in_([QuoteStatus.SUBMITTED, QuoteStatus.ACCEPTED]),
        )
    )
    _live_quote_count = _live_count_res.scalar() or 0
    if _live_quote_count >= settings.RFQ_MAX_QUOTES:
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
        submitted_at=datetime.now(timezone.utc),
    )

    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    return quote


async def accept_quote(
    db: AsyncSession,
    quote_id: uuid.UUID,
    customer: User,
) -> dict:
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

    # Load provider for contact details and email notification
    from sqlalchemy.orm import joinedload as _jl
    from app.services.email_service import (
        send_quote_accepted_notification,
        send_email,
    )

    # Reload quote with provider relationship
    q_result = await db.execute(
        select(Quote)
        .options(_jl(Quote.provider))
        .where(Quote.id == quote_id)
    )
    accepted_quote = q_result.scalar_one_or_none()

    provider_contact = {}
    if accepted_quote and accepted_quote.provider:
        p = accepted_quote.provider
        # Parse provider email - stored as JSON array or plain string
        provider_email = None
        if p.email_addresses:
            import json as _json
            try:
                emails = _json.loads(p.email_addresses) if isinstance(p.email_addresses, str) else p.email_addresses
                provider_email = emails[0] if emails else None
            except Exception:
                provider_email = str(p.email_addresses)

        provider_contact = {
            "provider_name": p.firm_name,
            "provider_email": provider_email,
            "provider_phone": p.phone,
            "provider_website": p.website,
            "provider_city": p.city,
            "provider_state": p.state,
            "provider_address": p.address,
        }

        # Send notification email to provider
        if provider_email:
            try:
                await send_quote_accepted_notification(
                    provider_email=provider_email,
                    quote=accepted_quote,
                    db=db,
                )
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).error(f"Failed to send quote accepted email to provider: {e}")

        # Send confirmation email to customer
        try:
            await send_email(
                to=rfq.customer_email,
                template="customer_quote_selected",
                subject="You have selected a provider - Next Steps",
                context={
                    "customer_name": rfq.contact_name or "Customer",
                    "provider_name": p.firm_name,
                    "provider_email": provider_email or "(contact via platform)",
                    "provider_phone": p.phone or "Not provided",
                    "provider_website": p.website or "Not provided",
                    "provider_city": p.city or "",
                    "provider_state": p.state or "",
                    "rfq_url": f"{settings.FRONTEND_URL}/customer/rfq/{rfq.id}",
                },
                db=db,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).error(f"Failed to send quote selected email to customer: {e}")

    return provider_contact


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
