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



