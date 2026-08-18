"""Support ticket API endpoints.

Route groups:
  Public : POST /webhooks/resend-inbound, POST /support/contact
  Auth   : POST /support/contact-authenticated
  Admin  : GET|POST /admin/support/tickets/...
"""

import httpx
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_db, get_optional_user, require_role
from app.models.enums import SupportTicketStatus
from app.models.support import SupportTicket, SupportTicketEvent, SupportTicketMessage
from app.models.user import User
from app.services.support_service import (
    _emit_event,
    escalate_ticket,
    find_or_create_ticket_from_inbound,
    process_inbound_email,
    send_support_email,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Cross-brand isolation
# ---------------------------------------------------------------------------
#
# Resend webhooks subscribe to EVENT TYPES, not domains — there is no
# per-domain filter in the dashboard or the API. Every `email.received` in
# the Resend account is fanned out to EVERY endpoint listening for that
# event, including endpoints belonging to a different product.
#
# This Resend account also serves proreadyengineer.com, which runs its own
# support desk on its own inbound webhook. Without checking who the mail
# was addressed to, this desk would open tickets for that business's
# customers and auto-reply to them as ProMechDirectory Support.

RECEIVING_DOMAINS = {
    "mail.promechdirectory.com",
    "promechdirectory.com",
}


def _addressed_to_us(payload: Dict[str, Any], data: Dict[str, Any], headers: Dict[str, Any]) -> bool:
    """True when an inbound email was addressed to one of our domains.

    `received_for` is Resend's own "which of your addresses caught this",
    so it is checked first; to/cc/bcc and the To header are fallbacks for
    older payload shapes.

    A message with no recognisable recipient returns True: one we cannot
    attribute is better seen by a human than dropped silently, and the
    cross-brand fan-out this guards against always carries an explicit
    recipient.
    """
    values: List[str] = []
    for key in ("received_for", "to", "cc", "bcc"):
        for src in (data, payload):
            if not isinstance(src, dict):
                continue
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                values.append(v)
            elif isinstance(v, list):
                values.extend(x for x in v if isinstance(x, str))
    if not values and isinstance(headers, dict):
        for key in ("to", "To", "delivered-to", "Delivered-To", "x-original-to"):
            v = headers.get(key)
            if isinstance(v, str) and v.strip():
                values.append(v)
                break

    seen_any = False
    for entry in values:
        for part in entry.split(","):
            part = part.strip().lower()
            if "<" in part and ">" in part:
                part = part.split("<", 1)[1].split(">", 1)[0].strip()
            if "@" not in part:
                continue
            seen_any = True
            if part.rsplit("@", 1)[-1] in RECEIVING_DOMAINS:
                return True
    return not seen_any





# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ContactFormRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str
    website: str = ""  # honeypot

class AuthContactRequest(BaseModel):
    """Request model for authenticated portal contact form - name/email are optional (taken from user)."""
    subject: str
    message: str
    category: str = "general"
    name: Optional[str] = None
    email: Optional[str] = None
    website: str = ""  # honeypot


class ContactFormResponse(BaseModel):
    ticket_id: str
    message: str


class AdminReplyRequest(BaseModel):
    body_html: str
    body_text: Optional[str] = None


class AdminResolveRequest(BaseModel):
    resolution_note: Optional[str] = None


class AdminEscalateRequest(BaseModel):
    reason: str


class AdminAssignRequest(BaseModel):
    assign_to_user_id: Optional[str] = None


class TicketMessageOut(BaseModel):
    id: str
    sender_type: str
    sender_name: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    direction: str
    email_delivered: Optional[bool] = None
    created_at: str


class TicketEventOut(BaseModel):
    id: str
    event_type: str
    actor_user_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: str


class SupportTicketOut(BaseModel):
    id: str
    submitter_email: str
    submitter_name: Optional[str] = None
    subject: str
    body: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    status: str
    source: str
    is_spam: bool
    llm_attempt_count: int
    assigned_to_user_id: Optional[str] = None
    first_responded_at: Optional[str] = None
    resolved_at: Optional[str] = None
    last_customer_message_at: Optional[str] = None
    created_at: str
    updated_at: str
    messages: List[TicketMessageOut] = []
    events: List[TicketEventOut] = []


class SupportTicketListOut(BaseModel):
    items: List[SupportTicketOut]
    total: int
    page: int
    size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _msg_out(m: SupportTicketMessage) -> TicketMessageOut:
    return TicketMessageOut(
        id=str(m.id), sender_type=m.sender_type, sender_name=m.sender_name,
        body_text=m.body_text, body_html=m.body_html, direction=m.direction,
        email_delivered=m.email_delivered, created_at=_dt(m.created_at) or "",
    )


def _evt_out(e: SupportTicketEvent) -> TicketEventOut:
    return TicketEventOut(
        id=str(e.id), event_type=e.event_type,
        actor_user_id=str(e.actor_user_id) if e.actor_user_id else None,
        payload=e.payload, created_at=_dt(e.created_at) or "",
    )


def _ticket_out(t: SupportTicket, msgs: bool = False, evts: bool = False) -> SupportTicketOut:
    return SupportTicketOut(
        id=str(t.id), submitter_email=t.submitter_email,
        submitter_name=t.submitter_name, subject=t.subject, body=t.body,
        category=t.category, priority=t.priority, status=t.status,
        source=t.source, is_spam=t.is_spam,
        llm_attempt_count=t.llm_attempt_count,
        assigned_to_user_id=str(t.assigned_to_user_id) if t.assigned_to_user_id else None,
        first_responded_at=_dt(t.first_responded_at),
        resolved_at=_dt(t.resolved_at),
        last_customer_message_at=_dt(t.last_customer_message_at),
        created_at=_dt(t.created_at) or "", updated_at=_dt(t.updated_at) or "",
        messages=[_msg_out(m) for m in t.messages] if msgs and t.messages else [],
        events=[_evt_out(e) for e in t.events] if evts and t.events else [],
    )


async def _get_ticket_or_404(ticket_id: str, db: AsyncSession) -> SupportTicket:
    try:
        tid = uuid.UUID(ticket_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Ticket not found")
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == tid)
        .options(selectinload(SupportTicket.messages), selectinload(SupportTicket.events))
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


# ---------------------------------------------------------------------------
# 1. Resend inbound email webhook  (NO auth)
# ---------------------------------------------------------------------------

@router.post("/webhooks/resend-inbound", status_code=200, tags=["Support Webhooks"])
async def resend_inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Receive inbound email from Resend and route to a support ticket."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    # Log FULL raw payload to diagnose Resend format
    logger.info("[inbound_webhook] FULL_RAW_PAYLOAD: %s", str(body)[:3000])

    # Resend inbound webhook may send flat format {"object":"email","id":...} 
    # OR wrapped {"type":"email.received","data":{...}}
    # Handle both formats
    data = body.get("data") if isinstance(body.get("data"), dict) else body

    # Extract sender — check both data level and headers for name
    from_raw = data.get("from") or body.get("from") or ""
    from_email, from_name = "", ""
    if "<" in from_raw and ">" in from_raw:
        from_name = from_raw.split("<")[0].strip().strip('"')
        from_email = from_raw.split("<")[1].rstrip(">").strip()
    else:
        from_email = from_raw.strip()
        # Try to get display name from headers.from
        hdr_from = (data.get("headers") or body.get("headers") or {}).get("from", "")
        if hdr_from and "<" in hdr_from:
            from_name = hdr_from.split("<")[0].strip().strip('"')
        else:
            from_name = from_email
    if not from_email:
        logger.warning("[inbound_webhook] no from_email found in payload: %s", list(body.keys()))
        return {"ok": True}

    # CRITICAL: Block emails sent FROM our own support address to prevent feedback loops
    OUR_SUPPORT_EMAILS = {
        "info@mail.promechdirectory.com",
        "noreply@mail.promechdirectory.com",
        "support@mail.promechdirectory.com",
    }
    if from_email.lower() in OUR_SUPPORT_EMAILS:
        logger.info("[inbound_webhook] ignoring email from our own address: %s", from_email)
        return {"ok": True}

    # CRITICAL: Resend fans email.received out to every endpoint in the
    # account, across products. Drop anything not addressed to us, or this
    # desk answers another brand's customers. See RECEIVING_DOMAINS above.
    _hdrs = data.get("headers") or body.get("headers") or {}
    if not isinstance(_hdrs, dict):
        _hdrs = {}
    if not _addressed_to_us(body, data, _hdrs):
        logger.info(
            "[inbound_webhook] ignoring email not addressed to our domains "
            "(from=%s, received_for=%s, to=%s)",
            from_email, data.get("received_for"), data.get("to"),
        )
        return {"ok": True}


    # Extract subject and body — try every known field name in both body and data
    subject = (
        data.get("subject") or body.get("subject") or "(no subject)"
    )
    body_text = (
        data.get("text") or body.get("text")
        or data.get("plain") or body.get("plain")
        or data.get("textBody") or body.get("textBody")
        or data.get("body") or body.get("body") or ""
    )
    body_html = (
        data.get("html") or body.get("html")
        or data.get("htmlBody") or body.get("htmlBody") or ""
    )

    # Email ID for Resend Receiving API fallback
    email_id = (
        data.get("email_id") or body.get("email_id")
        or data.get("id") or body.get("id") or ""
    )

    logger.info(
        "[inbound_webhook] extracted: from=%s subject=%r text_len=%d html_len=%d email_id=%s",
        from_email, subject, len(body_text), len(body_html), email_id
    )

    # If body is still empty, fetch from Resend Receiving API using email_id
    if (not body_text and not body_html) and email_id:
        try:
            from app.services.config_service import get_runtime_config
            rt_cfg = await get_runtime_config(db)
            resend_key = rt_cfg.get("RESEND_API_KEY") or rt_cfg.get("resend_api_key") or ""
            if resend_key:
                # Try standard emails endpoint first, then receiving-specific
                for url in [
                    f"https://api.resend.com/emails/{email_id}",
                    f"https://api.resend.com/emails/receiving/{email_id}",
                ]:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        api_resp = await client.get(url, headers={"Authorization": f"Bearer {resend_key}"})
                    if api_resp.status_code == 200:
                        full = api_resp.json()
                        subject = full.get("subject") or subject
                        body_text = full.get("text") or body_text
                        body_html = full.get("html") or body_html
                        logger.info("[inbound_webhook] fetched via API %s text_len=%d", url, len(body_text or ""))
                        break
                    logger.warning("[inbound_webhook] API %s → %s", url, api_resp.status_code)
            else:
                logger.warning("[inbound_webhook] No RESEND_API_KEY — cannot fetch email body from API")
        except Exception as fetch_exc:
            logger.error("[inbound_webhook] API fetch error: %s", fetch_exc)

    # Extract threading headers — Resend puts these inside the 'headers' object
    headers_dict = data.get("headers") or body.get("headers") or {}
    in_reply_to = (
        headers_dict.get("in-reply-to") or headers_dict.get("In-Reply-To")
        or data.get("inReplyTo") or data.get("in_reply_to")
        or body.get("inReplyTo") or ""
    )
    references = (
        headers_dict.get("references") or headers_dict.get("References")
        or data.get("references") or body.get("references") or ""
    )
    message_id = (
        headers_dict.get("message-id") or headers_dict.get("Message-ID")
        or data.get("messageId") or data.get("message_id")
        or body.get("messageId") or body.get("message_id") or ""
    )
    logger.info("[inbound_webhook] threading: in_reply_to=%r references=%r message_id=%r",
                in_reply_to[:80] if in_reply_to else None,
                references[:80] if references else None,
                message_id[:80] if message_id else None)



    try:
        ticket, is_new = await find_or_create_ticket_from_inbound(
            from_email=from_email, from_name=from_name, subject=subject,
            body_text=body_text, body_html=body_html,
            in_reply_to=in_reply_to or None, references=references or None,
            message_id=message_id or None, db=db,
        )
        await db.commit()
        ticket_id_copy = ticket.id

        async def _bg_pipeline():
            from app.db.session import AsyncSessionLocal
            try:
                async with AsyncSessionLocal() as bg_db:
                    await process_inbound_email(ticket_id_copy, bg_db)
            except Exception as bg_exc:
                logger.error("[inbound_bg_pipeline] UNCAUGHT ERROR for ticket %s: %s",
                             ticket_id_copy, bg_exc, exc_info=True)

        if is_new:
            background_tasks.add_task(_bg_pipeline)
        logger.info("[inbound_webhook] %s ticket %s from %s",
                    "created" if is_new else "updated (skipping pipeline)", ticket.id, from_email)
    except Exception as exc:
        logger.error("[inbound_webhook] error: %s", exc, exc_info=True)

    return {"ok": True}


# ---------------------------------------------------------------------------
# 2. Public contact form  (NO auth)
# ---------------------------------------------------------------------------

@router.post("/support/contact", response_model=ContactFormResponse,
             status_code=201, tags=["Support"])
async def public_contact_form(
    request: Request,
    data: ContactFormRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Submit support ticket from the public contact form."""
    if data.website:
        return ContactFormResponse(
            ticket_id="00000000",
            message="Thank you! We will be in touch soon.",
        )
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    ticket = SupportTicket(
        id=uuid.uuid4(), submitter_email=data.email.lower().strip(),
        submitter_name=data.name.strip() or None,
        subject=data.subject.strip() or "Support Request",
        body=data.message.strip(), status=SupportTicketStatus.NEW.value,
        source="contact_form", last_customer_message_at=datetime.now(timezone.utc),
        metadata_json={"ip": client_ip, "ua": request.headers.get("user-agent", "")},
    )
    db.add(ticket)
    await db.flush()
    db.add(SupportTicketMessage(
        id=uuid.uuid4(), ticket_id=ticket.id, sender_type="customer",
        sender_name=data.name.strip() or data.email,
        body_text=data.message.strip(),
        body_html="<p>" + data.message.strip() + "</p>",
        direction="form",
    ))
    await db.commit()
    tid = ticket.id

    async def _bg_pub():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            await process_inbound_email(tid, bg_db)

    background_tasks.add_task(_bg_pub)
    logger.info("[contact_form] new ticket %s from %s", ticket.id, data.email)
    return ContactFormResponse(
        ticket_id=str(ticket.id)[:8].upper(),
        message="Thank you! We have received your message and will respond shortly.",
    )


# ---------------------------------------------------------------------------
# 3. Authenticated contact form
# ---------------------------------------------------------------------------

@router.post("/support/contact-authenticated", response_model=ContactFormResponse,
             status_code=201, tags=["Support"])
async def authenticated_contact_form(
    request: Request,
    data: AuthContactRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit support ticket from an authenticated user portal."""
    if data.website:
        return ContactFormResponse(ticket_id="00000000", message="Thank you!")
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    email = data.email.lower().strip() if data.email else current_user.email
    name = (
        (data.name.strip() if data.name else None)
        or getattr(current_user, "full_name", None)
        or current_user.email
    )
    ticket = SupportTicket(
        id=uuid.uuid4(), user_id=current_user.id,
        submitter_email=email, submitter_name=name,
        subject=data.subject.strip() or "Support Request",
        body=data.message.strip(), status=SupportTicketStatus.NEW.value,
        source="contact_form_auth",
        last_customer_message_at=datetime.now(timezone.utc),
        metadata_json={"ip": client_ip, "ua": request.headers.get("user-agent", "")},
    )
    db.add(ticket)
    await db.flush()
    db.add(SupportTicketMessage(
        id=uuid.uuid4(), ticket_id=ticket.id, sender_type="customer",
        sender_name=name, body_text=data.message.strip(),
        body_html="<p>" + data.message.strip() + "</p>",
        direction="form",
    ))
    await db.commit()
    tid = ticket.id

    async def _bg_auth():
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            await process_inbound_email(tid, bg_db)

    background_tasks.add_task(_bg_auth)
    return ContactFormResponse(
        ticket_id=str(ticket.id)[:8].upper(),
        message="Thank you! We have received your message and will respond shortly.",
    )


# ---------------------------------------------------------------------------
# 4. Admin: list tickets
# ---------------------------------------------------------------------------

@router.get("/admin/support/tickets", response_model=SupportTicketListOut,
            tags=["Admin Support"])
async def admin_list_tickets(
    page: int = 1,
    size: int = 50,
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """List all support tickets with optional filters (admin only)."""
    query = select(SupportTicket).order_by(desc(SupportTicket.created_at))
    if status_filter:
        query = query.where(SupportTicket.status == status_filter)
    if category:
        query = query.where(SupportTicket.category == category)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    offset = (page - 1) * size
    result = await db.execute(query.offset(offset).limit(size))
    tickets = result.scalars().all()
    return SupportTicketListOut(
        items=[_ticket_out(t) for t in tickets], total=total, page=page, size=size,
    )


# ---------------------------------------------------------------------------
# 5. Admin: get ticket detail
# ---------------------------------------------------------------------------

@router.get("/admin/support/tickets/{ticket_id}", response_model=SupportTicketOut,
            tags=["Admin Support"])
async def admin_get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    """Get full ticket detail including messages and events (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    return _ticket_out(ticket, msgs=True, evts=True)


# ---------------------------------------------------------------------------
# 6. Admin: reply to ticket
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/reply", tags=["Admin Support"])
async def admin_reply_ticket(
    ticket_id: str,
    data: AdminReplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Send an admin reply email to the support ticket customer."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    admin_name = getattr(current_user, "full_name", None) or current_user.email
    body_text = data.body_text or data.body_html
    msg = SupportTicketMessage(
        id=uuid.uuid4(), ticket_id=ticket.id,
        sender_type="admin", sender_user_id=current_user.id,
        sender_name=admin_name, body_html=data.body_html,
        body_text=body_text, direction="outbound",
    )
    db.add(msg)
    delivered = await send_support_email(
        to_email=ticket.submitter_email,
        to_name=ticket.submitter_name or ticket.submitter_email,
        subject="Re: " + ticket.subject,
        body_html=data.body_html,
        reply_to_message_id=ticket.email_message_id,
        db=db,
    )
    msg.email_delivered = delivered
    if not ticket.first_responded_at:
        ticket.first_responded_at = datetime.now(timezone.utc)
    if ticket.status not in (
        SupportTicketStatus.RESOLVED.value,
        SupportTicketStatus.ARCHIVED.value,
    ):
        old_status = ticket.status
        ticket.status = SupportTicketStatus.AWAITING_CUSTOMER.value
        await _emit_event(ticket, "admin_reply", db,
                          actor_user_id=current_user.id,
                          payload={"delivered": delivered, "from": old_status})
    await db.commit()
    return {"ok": True, "delivered": delivered}


# ---------------------------------------------------------------------------
# 7. Admin: resolve ticket
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/resolve", tags=["Admin Support"])
async def admin_resolve_ticket(
    ticket_id: str,
    data: AdminResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Mark a ticket as resolved (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    old_status = ticket.status
    ticket.status = SupportTicketStatus.RESOLVED.value
    ticket.resolved_at = datetime.now(timezone.utc)
    await _emit_event(
        ticket, "status_change", db,
        actor_user_id=current_user.id,
        payload={
            "from": old_status,
            "to": SupportTicketStatus.RESOLVED.value,
            "note": data.resolution_note,
        },
    )
    await db.commit()
    return {"ok": True, "status": ticket.status}


# ---------------------------------------------------------------------------
# 8. Admin: escalate ticket
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/escalate", tags=["Admin Support"])
async def admin_escalate_ticket(
    ticket_id: str,
    data: AdminEscalateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Manually escalate a ticket (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    await escalate_ticket(ticket, data.reason, db, actor_user_id=current_user.id)
    await db.commit()
    return {"ok": True, "status": ticket.status}


# ---------------------------------------------------------------------------
# 9. Admin: assign ticket
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/assign", tags=["Admin Support"])
async def admin_assign_ticket(
    ticket_id: str,
    data: AdminAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Assign (or unassign) a ticket to an admin user (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    old_assignee = str(ticket.assigned_to_user_id) if ticket.assigned_to_user_id else None
    if data.assign_to_user_id:
        try:
            ticket.assigned_to_user_id = uuid.UUID(data.assign_to_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user id")
    else:
        ticket.assigned_to_user_id = None
    await _emit_event(
        ticket, "assigned", db,
        actor_user_id=current_user.id,
        payload={
            "from": old_assignee,
            "to": data.assign_to_user_id,
        },
    )
    await db.commit()
    return {"ok": True, "assigned_to": data.assign_to_user_id}


# ---------------------------------------------------------------------------
# 10. Admin: archive ticket
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/archive", tags=["Admin Support"])
async def admin_archive_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Archive a resolved or spam ticket (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    old_status = ticket.status
    ticket.status = SupportTicketStatus.ARCHIVED.value
    await _emit_event(
        ticket, "status_change", db,
        actor_user_id=current_user.id,
        payload={"from": old_status, "to": SupportTicketStatus.ARCHIVED.value},
    )
    await db.commit()
    return {"ok": True, "status": ticket.status}


# ---------------------------------------------------------------------------
# 10b. Admin: archive ALL tickets at once
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/archive-all", tags=["Admin Support"])
async def admin_archive_all_tickets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Archive every non-archived ticket in bulk (admin only)."""
    from sqlalchemy import update as sa_update
    result = await db.execute(
        sa_update(SupportTicket)
        .where(SupportTicket.status != SupportTicketStatus.ARCHIVED.value)
        .values(status=SupportTicketStatus.ARCHIVED.value)
        .execution_options(synchronize_session=False)
    )
    archived_count = result.rowcount
    await db.commit()
    logger.info("[admin] archive-all: archived %d tickets by user %s", archived_count, current_user.id)
    return {"ok": True, "archived_count": archived_count}

# ---------------------------------------------------------------------------
# 11. Admin: flag as spam
# ---------------------------------------------------------------------------

@router.post("/admin/support/tickets/{ticket_id}/spam", tags=["Admin Support"])
async def admin_flag_spam(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Flag a ticket as spam and close it (admin only)."""
    ticket = await _get_ticket_or_404(ticket_id, db)
    ticket.is_spam = True
    ticket.status = SupportTicketStatus.SPAM.value
    await _emit_event(
        ticket, "spam_flagged", db,
        actor_user_id=current_user.id,
    )
    await db.commit()
    return {"ok": True, "status": ticket.status}
