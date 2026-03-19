"""Email service - actually sends transactional emails via Resend API or SMTP."""

import asyncio
import logging
import os
import smtplib
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx
from jinja2 import Environment, PackageLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Jinja2 for email templates
jinja_env = Environment(
    loader=PackageLoader("app", "templates/emails"),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_template(template_name: str, context: dict[str, Any]) -> tuple[str, str]:
    """Render email template to HTML and plain text."""
    try:
        html_template = jinja_env.get_template(f"{template_name}.html")
        html_content = html_template.render(**context)
    except Exception:
        html_content = None

    try:
        text_template = jinja_env.get_template(f"{template_name}.txt")
        text_content = text_template.render(**context)
    except Exception:
        text_content = html_content.replace("<br>", "\n").replace("</p>", "\n") if html_content else ""

    return html_content, text_content


def _get_email_config() -> dict:
    """Get email configuration from environment / settings."""
    return {
        "resend_api_key": os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None),
        "resend_from_email": os.environ.get("RESEND_FROM_EMAIL") or getattr(settings, "EMAIL_FROM", "info@promechdirectory.com"),
        "smtp_host": os.environ.get("SMTP_HOST"),
        "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user": os.environ.get("SMTP_USER"),
        "smtp_password": os.environ.get("SMTP_PASSWORD"),
        "smtp_tls": os.environ.get("SMTP_TLS", "true").lower() == "true",
        "smtp_ssl": os.environ.get("SMTP_SSL", "false").lower() == "true",
        "from_email": os.environ.get("FROM_EMAIL") or getattr(settings, "FROM_EMAIL", "info@promechdirectory.com"),
        "from_name": os.environ.get("EMAIL_FROM_NAME") or getattr(settings, "EMAIL_FROM_NAME", "ProReadyEngineer"),
    }


async def _send_via_resend(
    api_key: str,
    from_email: str,
    from_name: str,
    to: list[str],
    subject: str,
    html_content: Optional[str],
    text_content: Optional[str],
    reply_to: Optional[str] = None,
) -> bool:
    """Send email via Resend API. Returns True on success."""
    from_addr = f"{from_name} <{from_email}>" if from_name else from_email
    payload: dict[str, Any] = {
        "from": from_addr,
        "to": to,
        "subject": subject,
    }
    if html_content:
        payload["html"] = html_content
    if text_content:
        payload["text"] = text_content
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code in (200, 201):
            logger.info(f"Email sent via Resend to {to}: {subject}")
            return True
        else:
            logger.error(f"Resend API error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Resend API exception: {e}")
        return False


def _send_via_smtp_sync(
    smtp_host: str,
    smtp_port: int,
    smtp_user: Optional[str],
    smtp_password: Optional[str],
    use_tls: bool,
    use_ssl: bool,
    from_email: str,
    from_name: str,
    to: list[str],
    subject: str,
    html_content: Optional[str],
    text_content: Optional[str],
    reply_to: Optional[str] = None,
) -> bool:
    """Send email via SMTP (synchronous). Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        msg["To"] = ", ".join(to)
        if reply_to:
            msg["Reply-To"] = reply_to

        if text_content:
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
        if html_content:
            msg.attach(MIMEText(html_content, "html", "utf-8"))

        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            if use_tls:
                server.starttls()

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)

        server.sendmail(from_email, to, msg.as_string())
        server.quit()
        logger.info(f"Email sent via SMTP to {to}: {subject}")
        return True
    except Exception as e:
        logger.error(f"SMTP send exception: {e}")
        return False


async def _send_email_now(
    to: list[str],
    subject: str,
    html_content: Optional[str],
    text_content: Optional[str],
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    Attempt to deliver an email immediately.

    Priority:
      1. Resend API  (if RESEND_API_KEY is set)
      2. SMTP        (if SMTP_HOST is set)
      3. Console WARNING  (fallback — email is NOT sent)

    Returns True if the email was actually delivered.
    """
    cfg = _get_email_config()
    effective_from = from_email or cfg["from_email"]
    from_name = cfg["from_name"]

    # --- 1. Try Resend ---
    if cfg["resend_api_key"]:
        sent = await _send_via_resend(
            api_key=cfg["resend_api_key"],
            from_email=cfg["resend_from_email"],
            from_name=from_name,
            to=to,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            reply_to=reply_to,
        )
        if sent:
            return True
        logger.warning("Resend failed — attempting SMTP fallback")

    # --- 2. Try SMTP ---
    if cfg["smtp_host"]:
        sent = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _send_via_smtp_sync(
                smtp_host=cfg["smtp_host"],
                smtp_port=cfg["smtp_port"],
                smtp_user=cfg["smtp_user"],
                smtp_password=cfg["smtp_password"],
                use_tls=cfg["smtp_tls"],
                use_ssl=cfg["smtp_ssl"],
                from_email=effective_from,
                from_name=from_name,
                to=to,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                reply_to=reply_to,
            ),
        )
        if sent:
            return True
        logger.warning("SMTP also failed — email was NOT delivered")

    # --- 3. Console fallback ---
    logger.warning(
        "EMAIL NOT SENT (no delivery method configured). "
        f"To={to} | Subject={subject!r} | "
        "Set RESEND_API_KEY or SMTP_HOST environment variables to enable delivery."
    )
    if text_content:
        logger.warning(f"Email body preview:
{text_content[:500]}")
    return False

async def send_email(
    to: str | list[str],
    template: str,
    subject: str,
    context: dict[str, Any],
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> uuid.UUID:
    """Send templated email immediately via Resend / SMTP / console fallback.

    Args:
        to: Recipient email(s).
        template: Template name (e.g. 'welcome', 'password_reset').
        subject: Email subject.
        context: Template variables.
        from_email: Sender email override.
        reply_to: Reply-to address.

    Returns:
        uuid.UUID: Email tracking ID (generated locally).
    """
    email_id = uuid.uuid4()
    to_list = to if isinstance(to, list) else [to]

    html_content, text_content = _render_template(template, context)

    delivered = await _send_email_now(
        to=to_list,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        from_email=from_email,
        reply_to=reply_to,
    )

    if not delivered:
        logger.warning(f"Email {email_id} was NOT delivered (no transport configured)")
    else:
        logger.info(f"Email {email_id} delivered successfully")

    return email_id


async def send_teaser_email(
    provider_email: str,
    rfq_teaser: dict[str, Any],
) -> uuid.UUID:
    """Send RFQ teaser email to provider.

    Args:
        provider_email: Provider email address.
        rfq_teaser: RFQ teaser data including urgency, tollgates, etc.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = f"New RFQ Opportunity - {rfq_teaser.get('urgency', 'Medium')} Priority"

    context = {
        "provider_name": rfq_teaser.get("provider_name", "Engineering Provider"),
        "rfq_id": str(rfq_teaser.get("rfq_id")),
        "urgency": rfq_teaser.get("urgency", "Medium"),
        "tollgate_phases": rfq_teaser.get("tollgate_phases", []),
        "project_description_preview": rfq_teaser.get("project_description", "")[:200] + "...",
        "unlock_url": f"{settings.FRONTEND_URL}/rfqs/{rfq_teaser.get('rfq_id')}/unlock",
        "disclaimer": rfq_teaser.get(
            "disclaimer",
            "This is a rough estimate opportunity. Only the first 5 quotes will be shown to the customer.",
        ),
    }

    return await send_email(
        to=provider_email,
        template="rfq_teaser",
        subject=subject,
        context=context,
    )


async def send_quote_notification(
    customer_email: str,
    quote: Any,  # Quote model
) -> uuid.UUID:
    """Send notification to customer that a new quote was received.

    Args:
        customer_email: Customer email address.
        quote: Quote model instance.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = "New Quote Received for Your RFQ"

    context = {
        "customer_name": quote.rfq.contact_name if hasattr(quote, 'rfq') else "Customer",
        "provider_name": quote.provider.firm_name if hasattr(quote, 'provider') else "Provider",
        "rfq_id": str(quote.rfq_id),
        "quote_id": str(quote.id),
        "price_range": f"${quote.rough_price_min} - ${quote.rough_price_max}" if quote.rough_price_min else "Contact for pricing",
        "turnaround": quote.turnaround_estimate_text or "Not specified",
        "view_quotes_url": f"{settings.FRONTEND_URL}/customer/rfqs/{quote.rfq_id}/quotes",
    }

    return await send_email(
        to=customer_email,
        template="quote_received",
        subject=subject,
        context=context,
    )


async def send_nda_ready_email(
    email: str,
    nda_id: uuid.UUID,
    is_customer: bool = True,
) -> uuid.UUID:
    """Send NDA ready for signing notification.

    Args:
        email: Recipient email.
        nda_id: NDA record UUID.
        is_customer: True if customer, False if provider.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    if is_customer:
        subject = "Action Required: Sign NDA for Your RFQ"
        template = "nda_customer_ready"
        sign_url = f"{settings.FRONTEND_URL}/nda/{nda_id}/sign"
    else:
        subject = "Action Required: Sign NDA to Access RFQ Details"
        template = "nda_provider_ready"
        sign_url = f"{settings.FRONTEND_URL}/provider/nda/{nda_id}/sign"

    context = {
        "sign_url": sign_url,
        "nda_id": str(nda_id),
        "expires_in": "7 days",
    }

    return await send_email(
        to=email,
        template=template,
        subject=subject,
        context=context,
    )


async def send_welcome_email(
    email: str,
    first_name: str,
) -> uuid.UUID:
    """Send welcome email to new user.

    Args:
        email: User email.
        first_name: User's first name.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = "Welcome to ProReadyEngineer"

    context = {
        "first_name": first_name,
        "login_url": f"{settings.FRONTEND_URL}/login",
        "support_email": settings.SUPPORT_EMAIL,
    }

    return await send_email(
        to=email,
        template="welcome",
        subject=subject,
        context=context,
    )


async def send_password_reset_email(
    email: str,
    reset_token: str,
) -> uuid.UUID:
    """Send password reset email.

    Args:
        email: User email.
        reset_token: Password reset token.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = "Password Reset Request"

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    context = {
        "reset_url": reset_url,
        "expires_in": "1 hour",
    }

    return await send_email(
        to=email,
        template="password_reset",
        subject=subject,
        context=context,
    )


async def send_quote_accepted_notification(
    provider_email: str,
    quote: Any,
) -> uuid.UUID:
    """Notify provider that their quote was accepted.

    Args:
        provider_email: Provider email.
        quote: Accepted quote.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = "Congratulations! Your Quote Was Accepted"

    context = {
        "provider_name": quote.provider.firm_name if hasattr(quote, 'provider') else "Provider",
        "rfq_id": str(quote.rfq_id),
        "customer_name": quote.rfq.contact_name if hasattr(quote, 'rfq') else "Customer",
        "customer_email": quote.rfq.customer_email if hasattr(quote, 'rfq') else None,
        "next_steps_url": f"{settings.FRONTEND_URL}/provider/quotes/{quote.id}",
    }

    return await send_email(
        to=provider_email,
        template="quote_accepted",
        subject=subject,
        context=context,
    )


async def send_subscription_confirmation(
    email: str,
    subscription_type: str,
    amount: float,
) -> uuid.UUID:
    """Send subscription confirmation email.

    Args:
        email: User email.
        subscription_type: Type of subscription.
        amount: Payment amount.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = "Subscription Confirmed"

    context = {
        "subscription_type": subscription_type.replace("_", " ").title(),
        "amount": f"${amount:.2f}",
        "billing_portal_url": f"{settings.FRONTEND_URL}/billing",
    }

    return await send_email(
        to=email,
        template="subscription_confirmed",
        subject=subject,
        context=context,
    )


async def send_provider_claim_approved_email(
    email: str,
    provider_name: str,
) -> uuid.UUID:
    """Notify provider that their claim was approved.

    Args:
        email: User email.
        provider_name: Provider firm name.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    subject = f"Provider Claim Approved - {provider_name}"

    context = {
        "provider_name": provider_name,
        "profile_url": f"{settings.FRONTEND_URL}/provider/profile",
    }

    return await send_email(
        to=email,
        template="claim_approved",
        subject=subject,
        context=context,
    )


async def send_tier_evaluation_result_email(
    email: str,
    provider_name: str,
    old_tier: Optional[str],
    new_tier: str,
    approved: bool,
) -> uuid.UUID:
    """Notify provider of tier evaluation result.

    Args:
        email: User email.
        provider_name: Provider firm name.
        old_tier: Previous tier or None.
        new_tier: New tier assigned.
        approved: Whether request was approved.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    if approved:
        subject = f"Tier Upgrade Approved - {provider_name}"
        template = "tier_upgraded"
    else:
        subject = f"Tier Evaluation Result - {provider_name}"
        template = "tier_evaluation_rejected"

    context = {
        "provider_name": provider_name,
        "old_tier": old_tier or "N/A",
        "new_tier": new_tier,
        "profile_url": f"{settings.FRONTEND_URL}/provider/profile",
    }

    return await send_email(
        to=email,
        template=template,
        subject=subject,
        context=context,
    )
