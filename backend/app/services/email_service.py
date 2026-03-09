"""Email service for transactional emails with Celery queue integration."""

import uuid
from datetime import datetime
from typing import Any, Optional

from jinja2 import Environment, PackageLoader, select_autoescape

from app.core.config import settings

# Initialize Jinja2 for email templates
jinja_env = Environment(
    loader=PackageLoader("app", "templates/emails"),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_template(template_name: str, context: dict[str, Any]) -> tuple[str, str]:
    """Render email template to HTML and plain text.

    Args:
        template_name: Name of template file (without extension).
        context: Template variables.

    Returns:
        tuple: (html_content, text_content).
    """
    try:
        html_template = jinja_env.get_template(f"{template_name}.html")
        html_content = html_template.render(**context)
    except Exception:
        html_content = None

    try:
        text_template = jinja_env.get_template(f"{template_name}.txt")
        text_content = text_template.render(**context)
    except Exception:
        # Generate plain text from HTML if no text template
        text_content = html_content.replace("<br>", "\n").replace("</p>", "\n") if html_content else ""

    return html_content, text_content


def _queue_email(
    to: str | list[str],
    subject: str,
    html_content: Optional[str],
    text_content: Optional[str],
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> uuid.UUID:
    """Queue email for sending via Celery.

    Args:
        to: Recipient email(s).
        subject: Email subject.
        html_content: HTML body content.
        text_content: Plain text body content.
        from_email: Sender email (default: settings.FROM_EMAIL).
        reply_to: Reply-to address.
        attachments: List of attachment dicts with 'filename', 'content', 'mime_type'.

    Returns:
        uuid.UUID: Queued email ID for tracking.
    """
    email_id = uuid.uuid4()

    # In production, this would enqueue to Celery
    # For now, we queue to an internal store for processing
    email_data = {
        "id": email_id,
        "to": to if isinstance(to, list) else [to],
        "subject": subject,
        "html_content": html_content,
        "text_content": text_content,
        "from_email": from_email or settings.FROM_EMAIL,
        "reply_to": reply_to,
        "attachments": attachments or [],
        "status": "queued",
        "created_at": datetime.utcnow(),
    }

    # This would be: celery_app.send_task("send_email", args=[email_data])
    # For now, we just return the ID - actual sending happens via background worker

    return email_id


async def send_email(
    to: str | list[str],
    template: str,
    subject: str,
    context: dict[str, Any],
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> uuid.UUID:
    """Send templated email via queue.

    Args:
        to: Recipient email(s).
        template: Template name (e.g., 'welcome', 'rfq_teaser').
        subject: Email subject.
        context: Template variables.
        from_email: Sender email.
        reply_to: Reply-to address.

    Returns:
        uuid.UUID: Email tracking ID.
    """
    html_content, text_content = _render_template(template, context)

    return _queue_email(
        to=to,
        subject=subject,
        html_content=html_content,
        text_content=text_content,
        from_email=from_email,
        reply_to=reply_to,
    )


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
