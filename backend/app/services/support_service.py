"""Semi-automated customer support service.

Responsibilities:
- Classify inbound support tickets using LLM
- Generate and send auto-responses for low-priority tickets
- Escalate to human admin when required
- Send transactional emails via Resend API
- Process inbound email webhooks from Resend
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import os
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    SupportTicketCategory,
    SupportTicketPriority,
    SupportTicketStatus,
)
from app.models.support import SupportTicket, SupportTicketEvent, SupportTicketMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORT_FROM_EMAIL = "info@mail.promechdirectory.com"
SUPPORT_FROM_NAME = "ProMechDirectory Support"
SUPPORT_ADMIN_EMAIL = "info@mail.promechdirectory.com"

# Categories that should be auto-handled by LLM (not immediately escalated)
LLM_HANDLEABLE_CATEGORIES = {
    SupportTicketCategory.GENERAL.value,
    SupportTicketCategory.ADD_FIRM.value,
    SupportTicketCategory.COLLABORATION.value,
}

# Categories that require immediate human review
ESCALATE_IMMEDIATELY = {
    SupportTicketCategory.PAYMENT.value,
    SupportTicketCategory.BUG.value,
    SupportTicketCategory.RFQ_NDA.value,
}

# Maximum LLM auto-response attempts before forcing escalation
MAX_LLM_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# Category → Priority mapping
# ---------------------------------------------------------------------------

CATEGORY_PRIORITY_MAP: Dict[str, int] = {
    SupportTicketCategory.PAYMENT.value: SupportTicketPriority.P1_PAYMENT.value,
    SupportTicketCategory.BUG.value: SupportTicketPriority.P2_BUG.value,
    SupportTicketCategory.ADD_FIRM.value: SupportTicketPriority.P3_ADD_FIRM.value,
    SupportTicketCategory.RFQ_NDA.value: SupportTicketPriority.P4_RFQ_NDA.value,
    SupportTicketCategory.GENERAL.value: SupportTicketPriority.P5_GENERAL.value,
    SupportTicketCategory.COLLABORATION.value: SupportTicketPriority.P6_COLLABORATION.value,
}


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

async def send_support_email(
    to_email: str,
    to_name: str,
    subject: str,
    body_html: str,
    reply_to_message_id: Optional[str] = None,
    db: Optional[Any] = None,
) -> bool:
    """Send a support email via Resend API.

    Returns True on success, False on failure.
    Failure is logged but never raised so callers can continue.
    """
    # Try reading from DB system_config first (where Admin Settings stores the key)
    api_key = None
    key_source = "none"
    if db is not None:
        try:
            from app.services.config_service import get_runtime_config
            cfg = await get_runtime_config(db)
            api_key = cfg.get("RESEND_API_KEY")
            if api_key:
                key_source = "db_config"
        except Exception as _e:
            logger.warning("[support_email] DB config read failed: %s", _e)
    # Fallback to env var / Pydantic settings
    if not api_key:
        api_key = getattr(settings, "RESEND_API_KEY", None) or os.environ.get("RESEND_API_KEY")
        if api_key:
            key_source = "env_var"
    if not api_key:
        logger.warning("[support_email] RESEND_API_KEY not configured — email not sent to %s", to_email)
        return False
    logger.info("[support_email] using API key from=%s prefix=%s to=%s", key_source, api_key[:6] + "***", to_email)

    from_field = f"{SUPPORT_FROM_NAME} <{SUPPORT_FROM_EMAIL}>"

    payload: Dict[str, Any] = {
        "from": from_field,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }

    # Thread the reply using In-Reply-To for proper email client grouping
    if reply_to_message_id:
        payload["headers"] = {
            "In-Reply-To": reply_to_message_id,
            "References": reply_to_message_id,
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code in (200, 201):
            logger.info("[support_email] sent to %s subject=%r", to_email, subject)
            return True
        else:
            logger.error(
                "[support_email] Resend returned %s: %s",
                resp.status_code,
                resp.text[:400],
            )
            return False
    except Exception as exc:
        logger.error("[support_email] httpx error sending to %s: %s", to_email, exc)
        return False


async def _notify_admin_new_ticket(ticket: SupportTicket, db: Optional[Any] = None) -> None:
    """Send a brief notification email to the admin inbox for escalated tickets."""
    subject = f"[Support #{str(ticket.id)[:8]}] {ticket.subject}"
    body_html = f"""
    <p>A new support ticket requires your attention.</p>
    <table style="border-collapse:collapse;font-family:sans-serif;font-size:14px">
      <tr><td style="padding:4px 12px 4px 0"><strong>Ticket ID</strong></td><td>{ticket.id}</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><strong>From</strong></td><td>{ticket.submitter_name or 'Unknown'} &lt;{ticket.submitter_email}&gt;</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><strong>Subject</strong></td><td>{ticket.subject}</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><strong>Category</strong></td><td>{ticket.category}</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><strong>Priority</strong></td><td>P{ticket.priority}</td></tr>
      <tr><td style="padding:4px 12px 4px 0"><strong>Status</strong></td><td>{ticket.status}</td></tr>
    </table>
    <p><em>Log in to the admin panel to review and reply.</em></p>
    """
    await send_support_email(
        to_email=SUPPORT_ADMIN_EMAIL,
        to_name="Admin",
        subject=subject,
        body_html=body_html,
        db=db,
    )


# ---------------------------------------------------------------------------
# LLM classification + response
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM_PROMPT = """\
You are a support triage assistant for ProMechDirectory, a B2B engineering services marketplace.

CRITICAL RULE: Base your classification ENTIRELY on the EMAIL BODY content. The subject line is
often vague (e.g. "help with issue", "question") and must NOT be used to determine category.
Only read the body to decide.

Category definitions — match keywords in the body:
- "payment"    : any mention of payment, charge, transaction, refund, billing, invoice, fee, money, double charge, withdrawal, credit card, stripe, subscription cost
- "bug"        : site error, broken feature, page not loading, 500 error, crash, unexpected behaviour
- "add_firm"   : wants to add, list, or register their company/firm in the directory
- "rfq_nda"    : questions about RFQ process, NDA signing, quoting, project requests
- "collaboration" : partnership, business deal, integration, affiliate
- "general"    : anything that does not clearly fit the above

Priority rules (1=highest urgency):
1 = payment issues (money involved — always P1 regardless of subject line)
2 = bugs / broken functionality
3 = add firm request
4 = rfq / nda questions
5 = general enquiries
6 = collaboration proposals

Respond with ONLY a JSON object (no markdown, no code block):
{
  "category": one of ["payment", "bug", "add_firm", "rfq_nda", "general", "collaboration"],
  "priority": integer 1-6,
  "is_spam": boolean,
  "confidence": float 0.0-1.0,
  "summary": one sentence summary of the issue based on the body,
  "suggested_response": a polite, helpful, concise HTML response to send to the customer.
    - For payment/bug/rfq_nda: acknowledge and say a team member will follow up within 1 business day.
    - For general/add_firm/collaboration: provide a direct, helpful answer where possible.
    - Use <p> tags for paragraphs. Keep it under 200 words.
    - Sign off as 'ProMechDirectory Support Team'.
  "can_auto_resolve": boolean — true only if the response fully answers the customer without needing human review.
}
"""


async def classify_and_respond(
    ticket: SupportTicket,
    messages: List[SupportTicketMessage],
    db: AsyncSession,
) -> Dict[str, Any]:
    """Classify ticket with LLM and generate a suggested or automatic response.

    Returns the parsed LLM output dict. Callers are responsible for persisting
    the result and acting on can_auto_resolve.

    On LLM error: returns a safe fallback dict that triggers escalation.
    """
    # Read LLM3 (DOC_LLM) config from Admin Settings database, fall back to env vars
    from app.services.config_service import get_runtime_config
    rt_cfg = await get_runtime_config(db)
    api_key = (
        rt_cfg.get("DOC_LLM_API_KEY") or rt_cfg.get("doc_llm_api_key")
        or rt_cfg.get("OPENAI_API_KEY") or rt_cfg.get("openai_api_key")
        or getattr(settings, "DOC_LLM_API_KEY", None)
        or getattr(settings, "OPENAI_API_KEY", None)
    )
    if not api_key:
        logger.warning("[support_classify] No LLM API key configured (DOC_LLM_API_KEY or OPENAI_API_KEY) — using fallback")
        return _fallback_classification(ticket)

    llm_model = (
        rt_cfg.get("DOC_LLM_MODEL") or rt_cfg.get("doc_llm_model")
        or rt_cfg.get("OPENAI_LLM_MODEL") or rt_cfg.get("openai_llm_model")
        or getattr(settings, "DOC_LLM_MODEL", None)
        or getattr(settings, "OPENAI_LLM_MODEL", "gpt-4o-mini")
    )
    openai_base = (
        rt_cfg.get("DOC_LLM_API_BASE") or rt_cfg.get("doc_llm_api_base")
        or rt_cfg.get("OPENAI_API_BASE") or rt_cfg.get("openai_api_base")
        or getattr(settings, "DOC_LLM_API_BASE", None)
        or getattr(settings, "OPENAI_API_BASE", None)
        or "https://api.openai.com/v1"
    )
    logger.info("[support_classify] using model=%s base=%s", llm_model, openai_base)

    # Build conversation context from existing messages
    history_text = ""
    for msg in messages:
        sender = msg.sender_type.upper()
        body = (msg.body_text or "").strip()
        if body:
            history_text += f"\n--- {sender} ---\n{body}\n"

    user_prompt = (
        f"SUBJECT (often vague — do NOT use to determine category): {ticket.subject}\n\n"
        f"EMAIL BODY (use this to classify):\n{ticket.body or '(no body)'}\n"
    )
    if history_text:
        user_prompt += f"\nThread history (for context only):{history_text}"

    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }

    try:
        import asyncio
        import json

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{openai_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("[support_classify] OpenAI returned %s: %s", resp.status_code, resp.text[:300])
            return _fallback_classification(ticket)

        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
        # Strip markdown code fences that some LLMs wrap around JSON
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.rsplit("```", 1)[0].strip()
        if not content:
            logger.warning("[support_classify] LLM returned empty content for ticket %s — using fallback", ticket.id)
            return _fallback_classification(ticket)
        result = json.loads(content)

        # Sanitise / coerce types
        # Gemini/LLM sometimes returns ": category" with a colon prefix — strip it
        category_raw = str(result.get("category", SupportTicketCategory.GENERAL.value))
        category_clean = category_raw.lstrip(":").strip().lower().replace(" ", "_")
        valid_cats = [c.value for c in SupportTicketCategory]
        result["category"] = category_clean if category_clean in valid_cats else SupportTicketCategory.GENERAL.value
        result["priority"] = int(result.get("priority", SupportTicketPriority.P5_GENERAL.value))
        result["is_spam"] = bool(result.get("is_spam", False))
        result["can_auto_resolve"] = bool(result.get("can_auto_resolve", False))
        result["confidence"] = float(result.get("confidence", 0.5))
        result["suggested_response"] = str(result.get("suggested_response", ""))
        result["summary"] = str(result.get("summary", ""))

        logger.info(
            "[support_classify] ticket=%s category=%s priority=%s spam=%s auto_resolve=%s",
            ticket.id, result["category"], result["priority"],
            result["is_spam"], result["can_auto_resolve"],
        )
        return result

    except Exception as exc:
        logger.error("[support_classify] LLM error for ticket %s: %s", ticket.id, exc, exc_info=True)
        return _fallback_classification(ticket)


def _fallback_classification(ticket: SupportTicket) -> Dict[str, Any]:
    """Safe fallback when LLM is unavailable — escalates all tickets."""
    return {
        "category": SupportTicketCategory.GENERAL.value,
        "priority": SupportTicketPriority.P5_GENERAL.value,
        "is_spam": False,
        "confidence": 0.0,
        "summary": "Automatic classification unavailable — manual review required.",
        "suggested_response": (
            "<p>Thank you for reaching out to ProMechDirectory Support.</p>"
            "<p>We have received your message and a team member will follow up with you "
            "within 1 business day.</p>"
            "<p>Best regards,<br>ProMechDirectory Support Team</p>"
        ),
        "can_auto_resolve": False,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _emit_event(
    ticket: SupportTicket,
    event_type: str,
    db: AsyncSession,
    actor_user_id: Optional[uuid.UUID] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> SupportTicketEvent:
    """Persist an immutable audit event for a support ticket."""
    event = SupportTicketEvent(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        payload=payload or {},
    )
    db.add(event)
    return event


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

async def escalate_ticket(
    ticket: SupportTicket,
    reason: str,
    db: AsyncSession,
    actor_user_id: Optional[uuid.UUID] = None,
) -> None:
    """Mark a ticket as ESCALATED, emit an event, and notify admin."""
    old_status = ticket.status
    ticket.status = SupportTicketStatus.ESCALATED.value
    await _emit_event(
        ticket,
        "escalated",
        db,
        actor_user_id=actor_user_id,
        payload={"reason": reason, "from_status": old_status},
    )
    await db.flush()
    logger.info("[support] ticket %s escalated: %s", ticket.id, reason)
    # Fire-and-forget admin notification (failure is non-fatal)
    try:
        await _notify_admin_new_ticket(ticket, db=db)
    except Exception as exc:
        logger.warning("[support] admin notify failed for ticket %s: %s", ticket.id, exc)


# ---------------------------------------------------------------------------
# Core inbound processing pipeline
# ---------------------------------------------------------------------------

async def process_inbound_email(
    ticket_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Full pipeline for a newly created or updated support ticket.

    Called after the ticket + initial customer message have been persisted:
    1. Load ticket + messages
    2. Call LLM to classify and generate a suggested response
    3. Apply classification to ticket
    4. If spam → mark SPAM, stop
    5. If immediately-escalatable category → escalate, send ack, stop
    6. If LLM can auto-resolve → send response, mark AUTO_RESOLVED
    7. If max LLM attempts exceeded → escalate
    8. Otherwise → send LLM response, mark LLM_HANDLING, await customer reply
    """
    import asyncio

    # Load ticket
    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        logger.error("[support_pipeline] ticket %s not found", ticket_id)
        return

    # Load messages
    msg_result = await db.execute(
        select(SupportTicketMessage)
        .where(SupportTicketMessage.ticket_id == ticket_id)
        .order_by(SupportTicketMessage.created_at)
    )
    messages = list(msg_result.scalars().all())

    # ------------------------------------------------------------------
    # Step 1: LLM classification
    # ------------------------------------------------------------------
    ticket.status = SupportTicketStatus.LLM_HANDLING.value
    ticket.llm_attempt_count = (ticket.llm_attempt_count or 0) + 1

    llm_result = await classify_and_respond(ticket, messages, db)

    category = llm_result.get("category", SupportTicketCategory.GENERAL.value)
    priority = llm_result.get("priority", SupportTicketPriority.P5_GENERAL.value)
    is_spam = llm_result.get("is_spam", False)
    suggested_response = llm_result.get("suggested_response", "")
    can_auto_resolve = llm_result.get("can_auto_resolve", False)
    summary = llm_result.get("summary", "")

    # Apply classification
    ticket.category = category
    ticket.priority = priority
    ticket.is_spam = is_spam
    # Store LLM result in session for auditing
    ticket.llm_session = {
        "last_result": llm_result,
        "attempt": ticket.llm_attempt_count,
    }

    await _emit_event(
        ticket, "llm_classified", db,
        payload={
            "category": category,
            "priority": priority,
            "is_spam": is_spam,
            "can_auto_resolve": can_auto_resolve,
            "summary": summary,
            "confidence": llm_result.get("confidence", 0.0),
        },
    )

    # ------------------------------------------------------------------
    # Step 2: Spam gate
    # ------------------------------------------------------------------
    if is_spam:
        ticket.status = SupportTicketStatus.SPAM.value
        await _emit_event(ticket, "spam_flagged", db, payload={"summary": summary})
        await db.commit()
        logger.info("[support_pipeline] ticket %s flagged as spam", ticket_id)
        return

    # ------------------------------------------------------------------
    # Step 3: Immediate escalation for sensitive categories
    # ------------------------------------------------------------------
    if category in ESCALATE_IMMEDIATELY:
        # Send acknowledgement first
        ack_html = (
            f"<p>Thank you for contacting ProMechDirectory Support.</p>"
            f"<p>We have received your message regarding <strong>{ticket.subject}</strong> "
            f"and a team member will follow up with you within 1 business day.</p>"
            f"<p>Your ticket reference: <code>{str(ticket.id)[:8].upper()}</code></p>"
            f"<p>Best regards,<br>ProMechDirectory Support Team</p>"
        )
        delivered = await send_support_email(
            to_email=ticket.submitter_email,
            to_name=ticket.submitter_name or ticket.submitter_email,
            subject=f"Re: {ticket.subject}",
            body_html=ack_html,
            reply_to_message_id=ticket.email_message_id,
            db=db,
        )
        if not ticket.first_responded_at:
            ticket.first_responded_at = datetime.now(timezone.utc)

        # Persist ack message
        ack_msg = SupportTicketMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            sender_type="llm",
            sender_name="ProMechDirectory Support",
            body_html=ack_html,
            body_text="Thank you for contacting ProMechDirectory Support. A team member will follow up within 1 business day.",
            direction="outbound",
            email_delivered=delivered,
        )
        db.add(ack_msg)

        await escalate_ticket(
            ticket,
            f"Category '{category}' requires human review",
            db,
        )
        await db.commit()
        return

    # ------------------------------------------------------------------
    # Step 4: Max attempts guard — force escalation
    # ------------------------------------------------------------------
    if ticket.llm_attempt_count > MAX_LLM_ATTEMPTS:
        await escalate_ticket(
            ticket,
            f"Max LLM attempts ({MAX_LLM_ATTEMPTS}) exceeded",
            db,
        )
        await db.commit()
        return

    # ------------------------------------------------------------------
    # Step 5: Send LLM-generated response
    # ------------------------------------------------------------------
    if suggested_response:
        delivered = await send_support_email(
            to_email=ticket.submitter_email,
            to_name=ticket.submitter_name or ticket.submitter_email,
            subject=f"Re: {ticket.subject}",
            body_html=suggested_response,
            reply_to_message_id=ticket.email_message_id,
            db=db,
        )
        if not ticket.first_responded_at:
            ticket.first_responded_at = datetime.now(timezone.utc)

        llm_msg = SupportTicketMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            sender_type="llm",
            sender_name="ProMechDirectory Support",
            body_html=suggested_response,
            body_text=suggested_response,  # HTML used as fallback text
            direction="outbound",
            email_delivered=delivered,
        )
        db.add(llm_msg)
        await _emit_event(ticket, "llm_response", db, payload={"delivered": delivered})

    # ------------------------------------------------------------------
    # Step 6: Update status
    # ------------------------------------------------------------------
    if can_auto_resolve:
        ticket.status = SupportTicketStatus.AUTO_RESOLVED.value
        ticket.resolved_at = datetime.now(timezone.utc)
        await _emit_event(ticket, "auto_resolved", db)
    else:
        ticket.status = SupportTicketStatus.AWAITING_CUSTOMER.value
        await _emit_event(ticket, "awaiting_customer", db)

    # ------------------------------------------------------------------
    # Safety net: if nothing was sent yet, always send a fallback ACK
    # ------------------------------------------------------------------
    if not ticket.first_responded_at:
        fallback_ack = (
            f"<p>Thank you for contacting ProMechDirectory Support.</p>"
            f"<p>We have received your message and a team member will review it shortly.</p>"
            f"<p>Your ticket reference: <code>{str(ticket.id)[:8].upper()}</code></p>"
            f"<p>Best regards,<br>ProMechDirectory Support Team</p>"
        )
        await send_support_email(
            to_email=ticket.submitter_email,
            to_name=ticket.submitter_name or ticket.submitter_email,
            subject=f"Re: {ticket.subject}",
            body_html=fallback_ack,
            reply_to_message_id=ticket.email_message_id,
            db=db,
        )
        ticket.first_responded_at = datetime.now(timezone.utc)
        fallback_msg = SupportTicketMessage(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            sender_type="llm",
            sender_name="ProMechDirectory Support",
            body_html=fallback_ack,
            body_text="Thank you for contacting ProMechDirectory Support. A team member will review it shortly.",
            direction="outbound",
            email_delivered=True,
        )
        db.add(fallback_msg)
        logger.info("[support_pipeline] fallback ACK sent to %s", ticket.submitter_email)

    await db.commit()
    logger.info(
        "[support_pipeline] ticket %s → status=%s category=%s",
        ticket_id, ticket.status, ticket.category,
    )


# ---------------------------------------------------------------------------
# Utility: find or create ticket from inbound email payload
# ---------------------------------------------------------------------------

async def find_or_create_ticket_from_inbound(
    from_email: str,
    from_name: str,
    subject: str,
    body_text: str,
    body_html: str,
    in_reply_to: Optional[str],
    references: Optional[str],
    message_id: Optional[str],
    db: AsyncSession,
) -> tuple[SupportTicket, bool]:
    """Find an existing ticket thread or create a new one.

    Returns (ticket, is_new) where is_new=True means a brand-new ticket.
    Thread matching: look for ticket whose email_message_id appears in
    the inbound In-Reply-To or References headers.
    """
    ticket: Optional[SupportTicket] = None

    # DEDUPLICATION: check if we already have a message with this exact email_message_id
    # This prevents duplicate tickets from Svix webhook retries
    if message_id:
        dup_result = await db.execute(
            select(SupportTicketMessage).where(
                SupportTicketMessage.email_message_id == message_id
            ).limit(1)
        )
        existing_msg = dup_result.scalar_one_or_none()
        if existing_msg:
            logger.info("[find_or_create_ticket] duplicate message_id=%s — skipping", message_id)
            # Load and return the parent ticket without creating anything new
            ticket_result = await db.execute(
                select(SupportTicket).where(SupportTicket.id == existing_msg.ticket_id)
            )
            existing_ticket = ticket_result.scalar_one_or_none()
            if existing_ticket:
                return existing_ticket, False

    # Try to match existing thread via In-Reply-To / References
    ref_ids = []
    if in_reply_to:
        ref_ids.append(in_reply_to.strip())
    if references:
        ref_ids.extend(r.strip() for r in references.split() if r.strip())

    for ref_id in ref_ids:
        if not ref_id:
            continue
        # 1. Check original ticket message_id
        result = await db.execute(
            select(SupportTicket).where(SupportTicket.email_message_id == ref_id)
        )
        ticket = result.scalar_one_or_none()
        if ticket:
            logger.info("[find_or_create_ticket] threaded via ticket.email_message_id=%s", ref_id[:40])
            break
        # 2. Check any individual message in ANY ticket thread
        msg_result = await db.execute(
            select(SupportTicketMessage)
            .where(SupportTicketMessage.email_message_id == ref_id)
            .limit(1)
        )
        msg = msg_result.scalar_one_or_none()
        if msg:
            ticket_result = await db.execute(
                select(SupportTicket).where(SupportTicket.id == msg.ticket_id)
            )
            ticket = ticket_result.scalar_one_or_none()
            if ticket:
                logger.info("[find_or_create_ticket] threaded via message.email_message_id=%s", ref_id[:40])
                break

    # 3. Fallback: match by sender email + normalized subject (catches cases where headers are missing)
    if ticket is None and subject:
        norm = subject.strip().lower()
        for pfx in ("re:", "fwd:", "fw:"):
            if norm.startswith(pfx):
                norm = norm[len(pfx):].strip()
        if norm:
            fb_result = await db.execute(
                select(SupportTicket).where(
                    SupportTicket.submitter_email == from_email.lower().strip(),
                    SupportTicket.status.not_in([
                        SupportTicketStatus.ARCHIVED.value,
                        SupportTicketStatus.SPAM.value,
                    ]),
                    func.lower(SupportTicket.subject) == norm,
                ).order_by(SupportTicket.created_at.desc()).limit(1)
            )
            ticket = fb_result.scalar_one_or_none()
            if ticket:
                logger.info("[find_or_create_ticket] threaded via subject fallback norm=%r from=%s", norm, from_email)


    is_new = ticket is None
    if is_new:
        # Create new ticket
        clean_subject = subject.strip()
        if clean_subject.lower().startswith("re:"):
            clean_subject = clean_subject[3:].strip()
        ticket = SupportTicket(
            id=uuid.uuid4(),
            submitter_email=from_email.lower().strip(),
            submitter_name=from_name or None,
            subject=clean_subject or "(no subject)",
            body=body_text or body_html or "",
            status=SupportTicketStatus.NEW.value,
            source="inbound_email",
            email_message_id=message_id,
            inbound_in_reply_to=in_reply_to,
        )
        db.add(ticket)
        await db.flush()  # get ticket.id

    # Append inbound message
    inbound_msg = SupportTicketMessage(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        sender_type="customer",
        sender_name=from_name or from_email,
        body_text=body_text or "",
        body_html=body_html or "",
        email_message_id=message_id,
        direction="inbound",
    )
    db.add(inbound_msg)
    ticket.last_customer_message_at = datetime.now(timezone.utc)

    if not is_new:
        # Reopen if resolved/archived
        if ticket.status in (
            SupportTicketStatus.AUTO_RESOLVED.value,
            SupportTicketStatus.RESOLVED.value,
            SupportTicketStatus.ARCHIVED.value,
        ):
            ticket.status = SupportTicketStatus.NEW.value
            await _emit_event(
                ticket, "customer_reply_reopened", db,
                payload={"message_id": str(message_id)},
            )

    await db.flush()
    return ticket, is_new
