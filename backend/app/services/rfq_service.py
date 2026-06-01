"""RFQ lifecycle service with concurrency-safe unlock logic."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
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

    # ------- Link uploaded documents as RFQFile records -------
    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain", "md": "text/markdown", "csv": "text/csv",
        "dwg": "application/acad", "dxf": "application/dxf",
        "step": "model/step", "stp": "model/step",
        "iges": "model/iges", "igs": "model/iges",
        "sldprt": "application/octet-stream", "sldasm": "application/octet-stream",
        "catpart": "application/octet-stream", "catproduct": "application/octet-stream",
        "stl": "model/stl",
        "x_t": "application/octet-stream", "x_b": "application/octet-stream",
        "prt": "application/octet-stream", "asm": "application/octet-stream",
    }

    # Multi-file path (new): list of {filename, s3_key, is_cad}
    doc_s3_keys = getattr(data, "document_s3_keys", None) or []
    # Single-file backward-compat path
    doc_key = getattr(data, "document_s3_key", None)
    if doc_key and not doc_s3_keys:
        # Convert single key to list format for uniform handling
        filename = doc_key.split("/")[-1] if "/" in doc_key else doc_key
        doc_s3_keys = [{"filename": filename, "s3_key": doc_key, "is_cad": False}]

    linked_any = False
    for file_info in doc_s3_keys:
        try:
            s3_key = file_info.get("s3_key") or ""
            filename = file_info.get("filename") or (s3_key.split("/")[-1] if "/" in s3_key else s3_key)
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
            mime = mime_map.get(ext, "application/octet-stream")
            rfq_file = RFQFile(
                rfq_id=rfq.id,
                s3_key=s3_key,
                original_filename=filename,
                mime_type=mime,
                file_size_bytes=0,
                uploaded_by_user_id=user.id if user else None,
            )
            db.add(rfq_file)
            linked_any = True
            logger.info(f"[RFQ] Linked document to RFQ {rfq.id}: {s3_key}")
        except Exception as e:
            logger.warning(f"[RFQ] Failed to link document to RFQ (non-fatal): {e}")

    if linked_any:
        rfq.has_documents = True
        await db.commit()

    # Inline text fallback: if no S3 files but extracted text exists
    extracted_text = getattr(data, "document_extracted_text", None)
    if not linked_any and extracted_text:
        try:
            rfq.has_documents = True
            text_file = RFQFile(
                rfq_id=rfq.id,
                s3_key="text:inline",
                original_filename="project_document.txt",
                mime_type="text/plain",
                file_size_bytes=len(extracted_text.encode("utf-8")),
                extracted_text=extracted_text,
                uploaded_by_user_id=user.id if user else None,
            )
            db.add(text_file)
            await db.commit()
            logger.info(f"[RFQ] Created inline text RFQFile for RFQ {rfq.id} ({len(extracted_text)} chars)")
        except Exception as e:
            logger.warning(f"[RFQ] Failed to create inline text file for RFQ (non-fatal): {e}")

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

        # Capture fields we need before the atomic claim (the ORM object may expire
        # after commit).
        _project_description = rfq.project_description

        # ---- ATOMIC CLAIM (concurrency-safe) --------------------------------------
        # Dispatch can be triggered more than once for the same RFQ, nearly at the
        # same time: the frontend calls submit() AND the backend schedules dispatch
        # after the NDA fee / free credit. A read-then-write guard is NOT safe under
        # that concurrency (two callers both read "no matches" and both run the AI
        # search -> DUPLICATE matches and duplicate teaser emails). Instead we flip
        # the status with a single conditional UPDATE: only the caller whose UPDATE
        # actually changes a row (rowcount == 1) "wins" and proceeds to search +
        # dispatch; every other concurrent caller gets rowcount == 0 and bails.
        #
        # NDA RFQs are included in the claimable set: after the customer pays the NDA
        # fee the RFQ sits in awaiting_nda_payment / awaiting_customer_signature, and
        # the customer signature is collected later (provider-triggered) and must
        # never block dispatch.
        _PRE_DISPATCH = [
            RfqStatus.DRAFT,
            RfqStatus.SUBMITTED,
            RfqStatus.AWAITING_NDA_PAYMENT,
            RfqStatus.AWAITING_CUSTOMER_SIGNATURE,
        ]
        _claim = await db.execute(
            update(RFQ)
            .where(RFQ.id == rfq_id, RFQ.rfq_status.in_(_PRE_DISPATCH))
            .values(
                rfq_status=RfqStatus.OPEN_FOR_DISPATCH,
                submitted_at=func.coalesce(RFQ.submitted_at, datetime.now(timezone.utc)),
                # is_closed is a DB-generated column derived from rfq_status; do NOT write it.
                closed_at=None,
            )
        )
        await db.commit()
        if (_claim.rowcount or 0) == 0:
            # Already dispatching/open/closed/cancelled, OR another concurrent
            # trigger won the claim. Either way, this call must not dispatch again.
            logger.info(
                "submit_rfq: rfq=%s not claimed (already advanced or won by another trigger); skipping",
                rfq_id,
            )
            return
        logger.info("submit_rfq: rfq=%s claimed for dispatch", rfq_id)

        # Belt-and-suspenders: if matches already exist (a prior winner crashed after
        # claiming, or a manual rescue), do NOT re-run the AI search or duplicate rows.
        _existing_matches = (
            await db.execute(
                select(func.count()).select_from(RFQMatch).where(RFQMatch.rfq_id == rfq_id)
            )
        ).scalar() or 0

        if _existing_matches == 0:
            from app.services.search_service import search_providers
            logger.info("submit_rfq: running AI search rfq_id=%s", rfq_id)
            # search_providers returns a tuple (results_list, pipeline_info)
            match_results, _pipeline_info = await search_providers(
                db,
                query=_project_description,
                filters={},
                limit=9999,
                top_n=None,  # Get ALL ranked providers for dispatch
            )
            logger.info("submit_rfq: search returned %d results rfq_id=%s", len(match_results), rfq_id)

            # match_results is a list of SearchResultItem dataclasses, not dicts
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
        else:
            await db.commit()
            logger.info(
                "submit_rfq: %d matches already exist for rfq=%s; skipping AI search (idempotent)",
                _existing_matches, rfq_id,
            )

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

    # populate_existing=True forces a fresh load of all columns (incl. the DB-computed
    # is_closed) within this await; without it, reading the Computed column on an object
    # expired by the prior Core UPDATE triggers a sync lazy-load -> MissingGreenlet.
    rfq = await db.get(RFQ, rfq_id, populate_existing=True)
    if not rfq:
        return []
    if rfq.is_closed:
        return []

    # Guard: only dispatch for RFQs in a valid dispatchable state.
    # This prevents emails being sent for cancelled, draft, NDA-pending, or any
    # other non-dispatchable RFQ, even if is_closed was not set correctly.
    _DISPATCHABLE_STATUSES = {
        RfqStatus.OPEN_FOR_DISPATCH,
        RfqStatus.DISPATCHING,
        RfqStatus.OPEN_FOR_UNLOCK,
    }
    _cur_status = rfq.rfq_status
    # Handle both enum and string storage
    if isinstance(_cur_status, str):
        try:
            _cur_status = RfqStatus(_cur_status)
        except ValueError:
            _cur_status = None
    if _cur_status not in _DISPATCHABLE_STATUSES:
        logger.warning(
            "dispatch_next_batch: BLOCKED rfq=%s status=%s not in dispatchable set - no emails sent",
            rfq_id, rfq.rfq_status,
        )
        return []

    if rfq.quote_count >= settings.RFQ_MAX_QUOTES:
        # Close RFQ when quote limit is reached in case it slipped through
        if rfq.rfq_status != RfqStatus.QUOTE_LIMIT_REACHED:
            rfq.rfq_status = RfqStatus.QUOTE_LIMIT_REACHED  # validator syncs is_closed
            rfq.closed_at = datetime.utcnow()
            await db.commit()
        return []

    # ----------------------------------------------------------------
    # INTERVAL GUARD: self-protecting rate-limit inside the function.
    # Prevents re-dispatch if last batch was within the configured
    # interval, regardless of which caller triggered this function.
    # This is belt-and-suspenders on top of scheduler interval checks.
    # ----------------------------------------------------------------
    try:
        _cfg = await _get_runtime_config(db)
        _interval_hours = float(_cfg.get('RFQ_BATCH_INTERVAL_HOURS', settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS))
    except Exception:
        _interval_hours = float(settings.RFQ_DISPATCH_BATCH_INTERVAL_HOURS)

    # Enforce minimum interval floor - NEVER allow interval=0 to bypass the guard.
    # interval=0 in DB would otherwise let every scheduler poll fire a new batch,
    # flooding providers with emails every 5 minutes.
    _MIN_INTERVAL_HOURS = 0.25  # 15 minutes absolute minimum
    if _interval_hours < _MIN_INTERVAL_HOURS:
        logger.warning(
            "dispatch_next_batch: rfq=%s configured interval %.2fh is below minimum %.2fh - enforcing floor",
            rfq_id, _interval_hours, _MIN_INTERVAL_HOURS,
        )
        _interval_hours = _MIN_INTERVAL_HOURS

    # Always check the interval (interval is guaranteed >= 0.25h due to floor above)
    _last_batch_res = await db.execute(
        select(RFQDispatchBatch)
        .where(RFQDispatchBatch.rfq_id == rfq_id)
        .order_by(RFQDispatchBatch.batch_number.desc())
        .limit(1)
    )
    _last_batch = _last_batch_res.scalar_one_or_none()
    if _last_batch is not None and _last_batch.dispatched_at is not None:
        _ld = _last_batch.dispatched_at
        if _ld.tzinfo is None:
            _ld = _ld.replace(tzinfo=timezone.utc)
        _elapsed = datetime.now(timezone.utc) - _ld
        _interval_delta = timedelta(hours=_interval_hours)
        if _elapsed < _interval_delta:
            _remaining_min = (_interval_delta - _elapsed).total_seconds() / 60
            logger.info(
                "dispatch_next_batch: rfq=%s interval guard - %.1f min remaining, skipping",
                rfq_id, _remaining_min,
            )
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
        # Distinguish "the AI search found no providers" from "submit_rfq is still running
        # the AI search and hasn't committed the matches yet". The claim flips the RFQ to
        # OPEN_FOR_DISPATCH and commits BEFORE the search runs, so a concurrent dispatcher
        # (the 5-min backup loop or the 15-min cron) can fire during the search window, see
        # zero matches, and wrongly close a perfectly good RFQ as CLOSED_NO_SELECTION. Only
        # close when there are genuinely NO matches AND enough time has passed for the search
        # to have finished; otherwise defer (submit_rfq dispatches once its matches commit).
        total_matches = (await db.execute(
            select(func.count()).select_from(RFQMatch).where(RFQMatch.rfq_id == rfq_id)
        )).scalar() or 0
        if total_matches == 0:
            _ref = rfq.submitted_at or getattr(rfq, "created_at", None)
            if _ref is None:
                logger.info("dispatch_next_batch: rfq=%s has 0 matches and no claim time; deferring close.", rfq_id)
                return []
            _ref = _ref if _ref.tzinfo else _ref.replace(tzinfo=timezone.utc)
            _age = (datetime.now(timezone.utc) - _ref).total_seconds()
            if _age < 300:  # 5-min grace — AI search is almost certainly still running
                logger.info(
                    "dispatch_next_batch: rfq=%s has 0 matches but was claimed %.0fs ago; "
                    "AI search likely still running — deferring close.", rfq_id, _age,
                )
                return []
        rfq.rfq_status = RfqStatus.CLOSED_NO_SELECTION  # validator syncs is_closed
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
        # Determine if this provider has an existing user account at dispatch time.
        # Compare against the users table - exactly what the admin Users panel shows.
        #
        # Check 0 (PRIMARY): invite email exists in users table
        #   → The email we are sending this invite to is a registered user.
        # Check 1 (FALLBACK): user.linked_provider_id == provider.id
        #   → User registered via a previous invite and was explicitly linked.
        # Check 2 (FALLBACK): active ProviderMembership for provider.id
        #   → User has an approved claim on this provider record.
        #
        # mode=login   → provider has an existing account
        # mode=register → provider has no account (form pre-filled with firm data)
        _has_account = False
        try:
            # Check 0: does the invite email exist in the users table?
            if email_target:
                _email_res = await db.execute(
                    select(User.id).where(
                        func.lower(User.email) == email_target.lower().strip(),
                        User.email.notlike("removed_%@deleted.invalid"),
                    ).limit(1)
                )
                if _email_res.scalar_one_or_none() is not None:
                    _has_account = True

            # Check 1: linked via invite-based registration — exclude removed accounts
            if not _has_account:
                _link_res = await db.execute(
                    select(User.id).where(
                        User.linked_provider_id == provider.id,
                        User.email.notlike("removed_%@deleted.invalid"),
                    ).limit(1)
                )
                if _link_res.scalar_one_or_none() is not None:
                    _has_account = True

            # Check 2: active membership claim — exclude removed accounts
            if not _has_account:
                _mem_res = await db.execute(
                    select(User.id)
                    .join(ProviderMembership, ProviderMembership.user_id == User.id)
                    .where(
                        ProviderMembership.provider_id == provider.id,
                        ProviderMembership.status == "active",
                        User.email.notlike("removed_%@deleted.invalid"),
                    )
                    .limit(1)
                )
                _has_account = _mem_res.scalar_one_or_none() is not None

            logger.info(
                "dispatch_next_batch: provider %s email=%s has_account=%s",
                provider.id, email_target, _has_account,
            )
        except Exception as _acct_exc:
            logger.warning(
                "dispatch_next_batch: account check failed for provider %s, defaulting to register mode: %s",
                provider.id, _acct_exc,
            )
            _has_account = False



        # Generate invite token now (pre-commit) - pure computation, no side effects
        # Embed firm data AND has_existing_account so frontend knows instantly
        _invite_token = None
        if email_target:
            _invite_token = _cit(
                rfq_id=str(rfq_id),
                provider_id=match.provider_id,
                dispatch_id=str(uuid.uuid4()),
                sent_to_email=email_target or "",
                firm_name=getattr(provider, 'firm_name', None) or getattr(provider, 'name', None) or "",
                phone=getattr(provider, 'phone', None) or "",
                city=getattr(provider, 'city', None) or "",
                state=getattr(provider, 'state', None) or "",
                has_existing_account=_has_account,
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
            "mode": "login" if _has_account else "register",
        }

        # Create dispatch record (status set optimistically; email follows post-commit)
        dispatch = RFQDispatch(
            rfq_id=rfq_id,
            provider_id=match.provider_id,
            batch_id=batch.id,
            dispatch_status=DispatchStatus.SENT if email_target else DispatchStatus.BOUNCED,
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
        if rfq.rfq_status != RfqStatus.CLOSED_NO_SELECTION:
            rfq.rfq_status = RfqStatus.CLOSED_NO_SELECTION  # validator syncs is_closed
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




async def unlock_rfq_founding_access(
    db: AsyncSession,
    rfq_id: uuid.UUID,
    provider_id: int,
    user: "User",
) -> "RFQUnlock":
    """Grant immediate RFQ access for founding-member providers.

    Skips payment entirely — creates an UNLOCKED record directly.
    Must only be called after check_founding_access() returns True.

    Uses SELECT FOR UPDATE on the RFQ row and verifies quota before creating
    the unlock record (same concurrency-safety as complete_rfq_unlock).
    """
    from sqlalchemy import text
    from app.services.campaign_service import check_founding_access

    # Verify founding access is still valid
    has_founding = await check_founding_access(db, provider_id=provider_id)
    if not has_founding:
        raise PermissionError("No active founding access grant for this provider")

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

    # Lock RFQ row (concurrency-safe quota check)
    lock_result = await db.execute(
        text("SELECT * FROM rfqs WHERE id = :rfq_id FOR UPDATE"),
        {"rfq_id": str(rfq_id)},
    )
    rfq_row = lock_result.fetchone()
    if not rfq_row:
        raise ValueError("RFQ not found")
    if rfq_row.is_closed:
        raise ValueError("RFQ is closed")

    # Check quota
    from sqlalchemy import func as _func2
    from app.models.quote import Quote as _QuoteModel2
    _sq_res2 = await db.execute(
        select(_func2.count()).select_from(_QuoteModel2).where(
            _QuoteModel2.rfq_id == rfq_id,
            _QuoteModel2.quote_status.in_(["submitted", "accepted"])
        )
    )
    if (_sq_res2.scalar() or 0) >= settings.RFQ_MAX_QUOTES:
        raise ValueError("Quote limit reached")

    # Check for existing unlock (idempotent — return existing if already unlocked)
    existing_result = await db.execute(
        select(RFQUnlock).where(
            RFQUnlock.rfq_id == rfq_id,
            RFQUnlock.provider_id == provider_id,
            RFQUnlock.unlock_status.in_([UnlockStatus.UNLOCKED, UnlockStatus.PAYMENT_PENDING]),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        if existing.unlock_status == UnlockStatus.UNLOCKED:
            return existing  # Already unlocked — idempotent
        raise ValueError("RFQ already unlocked for this provider (payment pending)")

    # Create unlock record in UNLOCKED state — no payment required
    from datetime import datetime
    unlock = RFQUnlock(
        rfq_id=rfq_id,
        provider_id=provider_id,
        unlocked_by_user_id=user.id,
        unlock_status=UnlockStatus.UNLOCKED,
        unlocked_at=datetime.utcnow(),
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

    # CRITICAL: Extract all needed strings NOW, before any await db.commit().
    # After db.commit(), SQLAlchemy expires all ORM objects (expire_on_commit=True).
    # Accessing attributes on expired objects in async context raises MissingGreenlet.
    _cust_first = (customer.first_name or '').strip()
    _cust_last  = (customer.last_name  or '').strip()
    _customer_fullname  = (customer.full_name or '').strip()
    _contact_name        = rfq.contact_name or ""    # pre-extract: used after commit
    _customer_name  = f'{_cust_first} {_cust_last}'.strip() or _customer_fullname or _contact_name or customer.email
    _customer_email = customer.email
    _customer_id    = customer.id
    _business_name  = (rfq.business_name or rfq.contact_name or '').strip()
    _rfq_id              = rfq.id
    _nda_required        = rfq.nda_required
    _selected_provider_id = quote.provider_id
    _customer_email_addr = rfq.customer_email        # pre-extract: used after commit
    _customer_entity_type = (getattr(customer, 'entity_type', None) or 'Individual')  # pre-extract for NDA
    _customer_state       = (getattr(customer, 'state', None) or '').strip()            # pre-extract for NDA governing_state

    # Verify customer owns this RFQ
    # If submitted anonymously, the user accepting the quote claims ownership
    if rfq.customer_user_id is None:
        rfq.customer_user_id = customer.id
        await db.commit()
    elif rfq.customer_user_id != customer.id:
        if "admin" not in (customer.roles or []):
            raise PermissionError("Not authorized to accept this quote")

    if rfq.is_closed and rfq.rfq_status != RfqStatus.QUOTE_LIMIT_REACHED:
        raise ValueError("RFQ is already closed")

    # Update quote status
    quote.quote_status = QuoteStatus.ACCEPTED

    # Close RFQ and mark selected provider
    rfq.rfq_status = RfqStatus.CUSTOMER_SELECTED_PROVIDER  # validator syncs is_closed
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
                to=_customer_email_addr,
                template="customer_quote_selected",
                subject="You have selected a provider - Next Steps",
                context={
                    "customer_name": _contact_name or "Customer",
                    "provider_name": p.firm_name,
                    "provider_email": provider_email or "(contact via platform)",
                    "provider_phone": p.phone or "Not provided",
                    "provider_website": p.website or "Not provided",
                    "provider_city": p.city or "",
                    "provider_state": p.state or "",
                    "rfq_url": f"{settings.FRONTEND_URL}/customer/rfq/{_rfq_id}",
                },
                db=db,
            )
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).error(f"Failed to send quote selected email to customer: {e}")

    # Trigger post-acceptance NDA if required
    # DIAGNOSTIC: Log NDA requirement check
    logger.info(
        "[NDA_DEBUG] RFQ %s: nda_required=%s, selected_provider_id=%s",
        _rfq_id, _nda_required, _selected_provider_id,
    )
    
    if _nda_required:
        logger.info("[NDA_DEBUG] RFQ %s: NDA is required, starting creation process", _rfq_id)
        try:
            # Find a user account linked to the selected provider
            from app.models.provider import ProviderMembership
            from app.services.nda_service import create_post_acceptance_nda

            logger.info(
                "[NDA_DEBUG] RFQ %s: Looking up active membership for provider_id=%s",
                _rfq_id, _selected_provider_id,
            )

            # Join with User to filter out removed/inactive accounts
            prov_membership_result = await db.execute(
                select(ProviderMembership)
                .join(User, User.id == ProviderMembership.user_id)
                .where(
                    ProviderMembership.provider_id == _selected_provider_id,
                    ProviderMembership.status == "active",
                    ~User.email.like("removed_%"),
                )
                .order_by(ProviderMembership.created_at.desc())
                .limit(1)
            )
            prov_membership = prov_membership_result.scalar_one_or_none()

            logger.info(
                "[NDA_DEBUG] RFQ %s: Membership lookup result: %s",
                _rfq_id, prov_membership.id if prov_membership else "None",
            )

            if prov_membership:
                provider_user_result = await db.execute(
                    select(User).where(
                        User.id == prov_membership.user_id,
                        )
                )
                provider_user = provider_user_result.scalar_one_or_none()

                logger.info(
                    "[NDA_DEBUG] RFQ %s: Provider user loaded: %s (email=%s)",
                    _rfq_id,
                    provider_user.id if provider_user else "None",
                    provider_user.email if provider_user else "None",
                )

                provider_result = await db.execute(
                    select(Provider).where(Provider.id == _selected_provider_id)
                )
                selected_provider = provider_result.scalar_one_or_none()

                logger.info(
                    "[NDA_DEBUG] RFQ %s: Selected provider loaded: %s (firm=%s)",
                    _rfq_id,
                    selected_provider.id if selected_provider else "None",
                    selected_provider.firm_name if selected_provider else "None",
                )

                if provider_user and selected_provider:
                        # Resolve provider strings from freshly-loaded objects (safe - not expired)
                        _prov_first = (provider_user.first_name or '').strip()
                        _prov_last  = (provider_user.last_name  or '').strip()
                        _prov_fullname = (provider_user.full_name or '').strip()
                        _prov_signer = f'{_prov_first} {_prov_last}'.strip() or _prov_fullname or getattr(selected_provider, 'firm_name', None) or provider_user.email
                        _prov_co = (
                            getattr(selected_provider, 'firm_name', None) or
                            getattr(selected_provider, 'name', None) or
                            'Provider'
                        )
                        
                        # DIAGNOSTIC: Log all arguments before calling Signwell
                        logger.info(
                            "[NDA_DEBUG] RFQ %s: About to call create_post_acceptance_nda with: "
                            "customer_name=%s, customer_email=%s, business_name=%s, "
                            "provider_id=%s, provider_signer_name=%s, provider_email=%s, provider_company=%s",
                            _rfq_id, _customer_name, _customer_email, _business_name,
                            selected_provider.id, _prov_signer, provider_user.email, _prov_co,
                        )
                        
                        result = await create_post_acceptance_nda(
                            rfq_id=_rfq_id,
                            customer_user_id=_customer_id,
                            customer_name=_customer_name,
                            customer_email=_customer_email,
                            business_name=_business_name,
                            provider_id=selected_provider.id,
                            provider_signer_name=_prov_signer,
                            provider_email=provider_user.email,
                            provider_company=_prov_co,
                            customer_entity_type=_customer_entity_type,
                            customer_state=_customer_state,
                            db=db,
                        )
                        logger.info(
                            "[NDA_DEBUG] RFQ %s: create_post_acceptance_nda returned: %s",
                            _rfq_id, result,
                        )
                        logger.info(
                            "Post-acceptance NDA created for RFQ %s provider %s",
                            _rfq_id, selected_provider.id,
                        )
                        provider_contact["nda_triggered"] = True
                        provider_contact["nda_error"] = None
                        provider_contact["nda_result"] = result
                else:
                    logger.warning(
                        "[NDA_DEBUG] RFQ %s: provider_user=%s, provider=%s - one or both missing",
                        _rfq_id, provider_user, selected_provider,
                    )
                    provider_contact["nda_triggered"] = False
                    provider_contact["nda_error"] = f"Missing provider_user or provider: user={provider_user}, provider={selected_provider}"
            else:
                logger.warning(
                    "[NDA_DEBUG] RFQ %s: No active membership found for provider %s",
                    _rfq_id, _selected_provider_id,
                )
                provider_contact["nda_triggered"] = False
                provider_contact["nda_error"] = f"No active membership for provider {_selected_provider_id}"
        except Exception as nda_exc:
            # NDA creation failure should NOT block quote acceptance
            import traceback as _tb
            _tb_str = _tb.format_exc()
            logger.error(
                "[NDA_DEBUG] RFQ %s: NDA creation FAILED with exception: %s | Traceback: %s",
                _rfq_id, nda_exc, _tb_str,
            )
            logger.error(
                "Failed to create post-acceptance NDA for RFQ %s: %s",
                _rfq_id, nda_exc, exc_info=True,
            )
            provider_contact["nda_error"] = f"{type(nda_exc).__name__}: {str(nda_exc)}"
            provider_contact["nda_triggered"] = False
            provider_contact["nda_traceback"] = _tb_str
    else:
        logger.info("[NDA_DEBUG] RFQ %s: NDA not required, skipping", _rfq_id)
        provider_contact["nda_triggered"] = False
        provider_contact["nda_error"] = None

    return provider_contact

