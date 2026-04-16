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
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _load_email_config_from_db(db: AsyncSession) -> dict:
    """Load email configuration from the system_config DB table.

    Calls get_runtime_config() from config_service and maps email-relevant
    keys to the _get_email_config() dict format.

    Returns an empty dict on any error so callers fall back gracefully to
    environment variables (existing behaviour).
    """
    try:
        from app.services.config_service import get_runtime_config
        runtime = await get_runtime_config(db)
        result: dict = {}
        if runtime.get("RESEND_API_KEY"):
            result["resend_api_key"] = runtime["RESEND_API_KEY"]
        if runtime.get("RESEND_FROM_EMAIL"):
            result["resend_from_email"] = runtime["RESEND_FROM_EMAIL"]
        if runtime.get("SMTP_HOST"):
            result["smtp_host"] = runtime["SMTP_HOST"]
        if runtime.get("SMTP_PORT"):
            try:
                result["smtp_port"] = int(runtime["SMTP_PORT"])
            except (ValueError, TypeError):
                pass
        if runtime.get("SMTP_USER"):
            result["smtp_user"] = runtime["SMTP_USER"]
        if runtime.get("SMTP_PASSWORD"):
            result["smtp_password"] = runtime["SMTP_PASSWORD"]
        if runtime.get("SMTP_TLS") is not None:
            result["smtp_tls"] = str(runtime["SMTP_TLS"]).lower() == "true"
        if runtime.get("SMTP_SSL") is not None:
            result["smtp_ssl"] = str(runtime["SMTP_SSL"]).lower() == "true"
        logger.debug(f"[EMAIL] Loaded {len(result)} email config keys from DB")
        return result
    except Exception as exc:
        logger.warning(f"[EMAIL] Failed to load email config from DB: {exc}")
        return {}


def _get_email_config(override: Optional[dict] = None) -> dict:
    """Get email configuration from environment / settings.

    Args:
        override: Optional dict of values that take priority over env vars.
                  Typically loaded from the system_config DB table via
                  _load_email_config_from_db(). When None, falls back to
                  environment variables only (original behaviour).
    """
    _ov = override or {}
    return {
        "resend_api_key": _ov.get("resend_api_key") or os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None),
        "resend_from_email": _ov.get("resend_from_email") or os.environ.get("RESEND_FROM_EMAIL") or getattr(settings, "EMAIL_FROM", "info@promechdirectory.com"),
        "smtp_host": _ov.get("smtp_host") or os.environ.get("SMTP_HOST"),
        "smtp_port": _ov.get("smtp_port") or int(os.environ.get("SMTP_PORT", "587")),
        "smtp_user": _ov.get("smtp_user") or os.environ.get("SMTP_USER"),
        "smtp_password": _ov.get("smtp_password") or os.environ.get("SMTP_PASSWORD"),
        "smtp_tls": _ov["smtp_tls"] if "smtp_tls" in _ov else os.environ.get("SMTP_TLS", "true").lower() == "true",
        "smtp_ssl": _ov["smtp_ssl"] if "smtp_ssl" in _ov else os.environ.get("SMTP_SSL", "false").lower() == "true",
        "from_email": _ov.get("from_email") or os.environ.get("FROM_EMAIL") or getattr(settings, "FROM_EMAIL", "info@promechdirectory.com"),
        "from_name": _ov.get("from_name") or os.environ.get("EMAIL_FROM_NAME") or getattr(settings, "EMAIL_FROM_NAME", "ProReadyEngineer"),
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
    db: Optional[AsyncSession] = None,
) -> bool:
    """
    Attempt to deliver an email immediately.

    Priority:
      1. Resend API  (if RESEND_API_KEY is set)
      2. SMTP        (if SMTP_HOST is set)
      3. Console WARNING  (fallback — email is NOT sent)

    Args:
        db: Optional AsyncSession. When provided, email configuration is
            loaded from the system_config DB table (admin panel settings)
            and takes priority over environment variables.

    Returns True if the email was actually delivered.
    """
    # Load DB config override when a session is available
    db_override: Optional[dict] = None
    if db is not None:
        db_override = await _load_email_config_from_db(db)

    cfg = _get_email_config(override=db_override)
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
        "Set RESEND_API_KEY or SMTP_HOST environment variables "
        "(or configure via admin panel) to enable delivery."
    )
    if text_content:
        logger.warning(f"Email body preview:\n{text_content[:500]}")
    return False


async def send_email(
    to: str | list[str],
    template: str,
    subject: str,
    context: dict[str, Any],
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> uuid.UUID:
    """Send templated email immediately via Resend / SMTP / console fallback.

    Args:
        to: Recipient email(s).
        template: Template name (e.g. 'welcome', 'password_reset').
        subject: Email subject.
        context: Template variables.
        from_email: Sender email override.
        reply_to: Reply-to address.
        db: Optional AsyncSession for loading config from DB (admin panel
            settings take priority over environment variables when provided).

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
        db=db,
    )

    if not delivered:
        logger.warning(f"Email {email_id} was NOT delivered (no transport configured)")
    else:
        logger.info(f"Email {email_id} delivered successfully")

    return email_id


async def send_teaser_email(
    provider_email: str,
    rfq_teaser: dict[str, Any],
    db: Optional[AsyncSession] = None,
    invite_token: Optional[str] = None,
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
        "rfq_url": (
            f"{settings.FRONTEND_URL}/provider/rfq/{rfq_teaser.get('rfq_id')}?invite={invite_token}&mode={rfq_teaser.get('mode', 'register')}"
            if invite_token
            else f"{settings.FRONTEND_URL}/provider/rfq/{rfq_teaser.get('rfq_id')}"
        ),
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
        db=db,
    )


async def send_quote_notification(
    customer_email: str,
    quote: Any,  # Quote model
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_nda_ready_email(
    email: str,
    nda_id: uuid.UUID,
    is_customer: bool = True,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_welcome_email(
    email: str,
    first_name: str,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_password_reset_email(
    email: str,
    reset_token: str,
    db: Optional[AsyncSession] = None,
) -> uuid.UUID:
    """Send password reset email.

    Args:
        email: User email.
        reset_token: Password reset token.
        db: Optional AsyncSession for loading email config from DB
            (admin panel settings take priority over env vars when provided).

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
        db=db,
    )


async def send_quote_accepted_notification(
    provider_email: str,
    quote: Any,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_subscription_confirmation(
    email: str,
    subscription_type: str,
    amount: float,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_provider_claim_approved_email(
    email: str,
    provider_name: str,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_tier_evaluation_result_email(
    email: str,
    provider_name: str,
    old_tier: Optional[str],
    new_tier: str,
    approved: bool,
    db: Optional[AsyncSession] = None,
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
        db=db,
    )


async def send_listing_inquiry_email(
    db: AsyncSession,
    user_email: str,
    user_name: str,
    firm_name: str,
    firm_description: str,
) -> bool:
    """Send AI-assisted listing inquiry email to ops team."""
    subject = f"AI-Assisted Listing Inquiry: {firm_name}"
    html_content = f"""
    <h2>New AI-Assisted Listing Inquiry ($750)</h2>
    <p><strong>Contact:</strong> {user_name} ({user_email})</p>
    <p><strong>Firm Name:</strong> {firm_name}</p>
    <p><strong>Description:</strong></p>
    <p>{firm_description}</p>
    <hr/>
    <p>Please follow up with the customer within 1 business day to proceed with the
    AI-assisted listing service.</p>
    """
    import re
    text_content = re.sub(r"<[^>]+>", " ", html_content).strip()
    delivered = await _send_email_now(
        to=["info@promechdirectory.com"],
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        from_email=None,
        reply_to=user_email,
        db=db,
    )
    return delivered


async def send_security_alert_email(email: str, db=None) -> None:
    """Send security alert when 5 failed login attempts detected.

    Only called at exactly the 5th failed login attempt.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    subject = 'Security Alert: Multiple failed login attempts on your ProMechDirectory account'
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#dc2626;padding:20px;border-radius:8px 8px 0 0;">
    <h1 style="color:white;margin:0;font-size:22px;">&#9888; Security Alert</h1>
  </div>
  <div style="background:#f9fafb;padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
    <p style="margin:0 0 16px;">We detected <strong>5 failed login attempts</strong> on your ProMechDirectory account.</p>
    <p style="margin:0 0 16px;"><strong>Time:</strong> {now}</p>
    <p style="margin:0 0 16px;">If this was not you, please <a href="{settings.FRONTEND_URL}/forgot-password" style="color:#2563eb;">reset your password immediately</a>.</p>
    <p style="margin:0 0 8px;color:#6b7280;font-size:14px;">Note: Your account will be temporarily locked after 10 failed attempts.</p>
    <p style="margin:0;color:#6b7280;font-size:14px;">If you are having trouble logging in, use the forgot password link on the login page.</p>
  </div>
</body></html>"""
    text_content = (
        f"Security Alert: 5 failed login attempts detected on your ProMechDirectory account at {now}.\n"
        "If this was not you, please reset your password immediately.\n"
        f"Visit: {settings.FRONTEND_URL}/forgot-password\n"
        "Your account will be temporarily locked after 10 failed attempts."
    )
    try:
        email_config = await _get_email_config(db=db)
        await _send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            email_config=email_config,
        )
        logger.info('[EMAIL] Security alert sent to %s', email)
    except Exception as exc:
        logger.error('[EMAIL] Failed to send security alert to %s: %s', email, exc)


async def send_email_verification(email: str, token: str, db=None) -> None:
    """Send email verification link to new user.

    Only called when REQUIRE_EMAIL_VERIFICATION=True.
    Token expires in 24 hours.
    """
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = 'Verify your ProMechDirectory account email'
    html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <div style="background:#2563eb;padding:20px;border-radius:8px 8px 0 0;">
    <h1 style="color:white;margin:0;font-size:22px;">Verify Your Email</h1>
  </div>
  <div style="background:#f9fafb;padding:24px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
    <p style="margin:0 0 16px;">Thank you for registering with ProMechDirectory. Please verify your email address to activate your account.</p>
    <div style="text-align:center;margin:24px 0;">
      <a href="{verify_url}" style="background:#2563eb;color:white;padding:12px 32px;text-decoration:none;border-radius:6px;font-weight:bold;font-size:16px;">Verify Email Address</a>
    </div>
    <p style="margin:16px 0 8px;color:#6b7280;font-size:14px;">This link expires in 24 hours.</p>
    <p style="margin:0;color:#6b7280;font-size:14px;">If you did not create an account, you can safely ignore this email.</p>
    <p style="margin:16px 0 0;color:#9ca3af;font-size:12px;">If the button does not work, copy this link into your browser:<br>{verify_url}</p>
  </div>
</body></html>"""
    text_content = (
        f"Please verify your ProMechDirectory email address.\n"
        f"Click or copy this link: {verify_url}\n"
        "This link expires in 24 hours.\n"
        "If you did not create an account, ignore this email."
    )
    try:
        email_config = await _get_email_config(db=db)
        await _send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            email_config=email_config,
        )
        logger.info('[EMAIL] Verification email sent to %s', email)
    except Exception as exc:
        logger.error('[EMAIL] Failed to send verification email to %s: %s', email, exc)
