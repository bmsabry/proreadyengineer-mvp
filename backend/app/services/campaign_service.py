"""Campaign service - mass email invite system for provider onboarding.

Handles campaign lifecycle: creation, batch sending via Resend, founding
access grant management, and per-invite status tracking.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.campaign import FoundingAccessGrant, ProviderCampaign, ProviderCampaignInvite
from app.models.enums import CampaignStatus, InviteStatus, SubscriptionStatus, SubscriptionType
from app.models.payment import Subscription
from app.models.provider import Provider
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _generate_invite_token() -> str:
    """Generate a cryptographically secure URL-safe invite token."""
    return secrets.token_urlsafe(32)


def _build_invite_link(token: str) -> str:
    """Build the pre-filled registration URL for a given invite token."""
    base = getattr(settings, "FRONTEND_URL", "https://proreadyengineer.com")
    return f"{base}/register?invite={token}&role=provider"


def _build_unsubscribe_url(token: str) -> str:
    """One-click unsubscribe URL handled by the backend (no login required)."""
    import os
    api_base = (os.environ.get("API_PUBLIC_URL")
                or getattr(settings, "API_PUBLIC_URL", None)
                or "https://proreadyengineer-api.onrender.com")
    return f"{api_base.rstrip('/')}/api/v1/campaigns/unsubscribe/{token}"


def _render_email_body(html_template: str, context: Dict[str, Any]) -> str:
    """Simple template variable substitution for {{variable}} placeholders."""
    result = html_template
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", str(value or ""))
    return result


async def _get_resend_config() -> Tuple[Optional[str], str]:
    """Return (api_key, from_address) from environment / settings."""
    import os
    api_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None)
    from_addr = (
        os.environ.get("RESEND_FROM_EMAIL")
        or getattr(settings, "EMAIL_FROM", "info@proreadyengineer.com")
    )
    return api_key, from_addr


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------

async def create_campaign(
    db: AsyncSession,
    *,
    name: str,
    email_subject: str,
    email_body_html: str,
    founding_slots_total: int = 250,
    founding_duration_days: int = 90,
    batch_size_per_day: int = 150,
    admin_user: User,
    target_provider_ids: List[int] = [],
) -> ProviderCampaign:
    """Create a campaign and pre-populate invite rows for eligible providers.

    If target_provider_ids is non-empty, only those specific providers are
    targeted (selected mode). Otherwise all eligible providers are targeted
    (all mode: have email_addresses AND not already registered).

    Invite rows start in PENDING status; no email is sent at creation time.
    """
    target_mode = "selected" if target_provider_ids else "all"

    # --- Fetch providers based on targeting mode ---
    if target_provider_ids:
        providers_result = await db.execute(
            select(Provider).where(
                and_(
                    Provider.id.in_(target_provider_ids),
                    Provider.email_addresses.isnot(None),
                    func.json_array_length(Provider.email_addresses) > 0,
                )
            )
        )
    else:
        providers_result = await db.execute(
            select(Provider).where(
                and_(
                    Provider.email_addresses.isnot(None),
                    func.json_array_length(Provider.email_addresses) > 0,
                )
            )
        )
    all_providers: List[Provider] = providers_result.scalars().all()

    # --- Fetch all registered user emails for deduplication ---
    users_result = await db.execute(select(User.email))
    registered_emails = {row[0].lower() for row in users_result.fetchall() if row[0]}

    # --- Create campaign record ---
    campaign = ProviderCampaign(
        name=name,
        status=CampaignStatus.DRAFT,
        email_subject=email_subject,
        email_body_html=email_body_html,
        founding_slots_total=founding_slots_total,
        founding_slots_claimed=0,
        founding_duration_days=founding_duration_days,
        batch_size_per_day=batch_size_per_day,
        target_mode=target_mode,
        total_providers=0,
        total_sent=0,
        created_by=admin_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(campaign)
    await db.flush()  # get campaign.id

    # --- Build invite rows (exclude already-registered providers) ---
    invite_count = 0
    for provider in all_providers:
        emails: List[str] = provider.email_addresses or []
        # Use the first email as the invite target
        primary_email = emails[0].strip().lower() if emails else None
        if not primary_email:
            continue
        if primary_email in registered_emails:
            logger.debug(
                "Skipping provider %s — email %s already registered",
                provider.id, primary_email,
            )
            continue

        invite = ProviderCampaignInvite(
            campaign_id=campaign.id,
            provider_id=provider.id,
            invite_token=_generate_invite_token(),
            status=InviteStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        db.add(invite)
        invite_count += 1

    campaign.total_providers = invite_count
    await db.commit()
    await db.refresh(campaign)

    logger.info(
        "Campaign '%s' created with %d eligible invites (total providers=%d, excluded=%d)",
        name, invite_count, len(all_providers), len(all_providers) - invite_count,
    )
    return campaign


async def start_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> ProviderCampaign:
    """Transition campaign to ACTIVE and record started_at timestamp."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
        raise ValueError(f"Cannot start campaign in status '{campaign.status}'")

    campaign.status = CampaignStatus.ACTIVE
    if campaign.started_at is None:
        campaign.started_at = datetime.now(timezone.utc)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def pause_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> ProviderCampaign:
    """Pause an active campaign (stops batch dispatch)."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.status != CampaignStatus.ACTIVE:
        raise ValueError(f"Cannot pause campaign in status '{campaign.status}'")

    campaign.status = CampaignStatus.PAUSED
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def cancel_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> ProviderCampaign:
    """Cancel a campaign permanently."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.status == CampaignStatus.COMPLETED:
        raise ValueError("Cannot cancel a completed campaign")

    campaign.status = CampaignStatus.CANCELLED
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)
    return campaign


# ---------------------------------------------------------------------------
# Batch email sending
# ---------------------------------------------------------------------------

async def send_next_batch(db: AsyncSession, campaign_id: uuid.UUID) -> Dict[str, Any]:
    """Send the next batch of pending invites via Resend.

    Sends up to `campaign.batch_size_per_day` pending invites.
    Updates campaign counters and individual invite statuses.
    If no pending invites remain, marks campaign as COMPLETED.

    Returns a summary dict with sent/failed counts.
    """
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.status != CampaignStatus.ACTIVE:
        logger.info("Campaign %s is not active (status=%s), skipping batch", campaign_id, campaign.status)
        return {"sent": 0, "failed": 0, "skipped": True, "reason": campaign.status}

    # Fetch batch of pending invites with provider data
    result = await db.execute(
        select(ProviderCampaignInvite, Provider)
        .join(Provider, ProviderCampaignInvite.provider_id == Provider.id)
        .where(
            and_(
                ProviderCampaignInvite.campaign_id == campaign_id,
                ProviderCampaignInvite.status == InviteStatus.PENDING,
            )
        )
        .limit(campaign.batch_size_per_day)
    )
    rows = result.all()

    if not rows:
        # All invites processed — mark completed
        campaign.status = CampaignStatus.COMPLETED
        campaign.completed_at = datetime.now(timezone.utc)
        campaign.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Campaign %s completed — all invites processed", campaign_id)
        return {"sent": 0, "failed": 0, "completed": True}

    # Suppression list: any provider who unsubscribed in ANY campaign is never emailed again.
    suppressed_result = await db.execute(
        select(ProviderCampaignInvite.provider_id)
        .where(ProviderCampaignInvite.status == InviteStatus.UNSUBSCRIBED)
        .distinct()
    )
    suppressed_provider_ids = {r[0] for r in suppressed_result.all()}

    api_key, from_addr = await _get_resend_config()
    slots_remaining = max(0, campaign.founding_slots_total - campaign.founding_slots_claimed)

    sent_count = 0
    failed_count = 0

    async with httpx.AsyncClient(timeout=15.0) as client:
        for invite, provider in rows:
            emails: List[str] = provider.email_addresses or []
            target_email = emails[0].strip() if emails else None
            if not target_email:
                invite.status = InviteStatus.BOUNCED
                failed_count += 1
                continue

            if invite.provider_id in suppressed_provider_ids:
                invite.status = InviteStatus.UNSUBSCRIBED
                continue

            invite_link = _build_invite_link(invite.invite_token)
            firm_name = provider.name or provider.firm_name or "Your Firm"
            city = provider.city or ""
            state = provider.state or ""
            specialty = provider.primary_specialty or ""

            # Build email content from campaign template
            context = {
                "firm_name": firm_name,
                "city": city,
                "state": state,
                "specialty": specialty,
                "invite_link": invite_link,
                "founding_slots_remaining": slots_remaining,
                "unsubscribe_link": f"{_build_invite_link(invite.invite_token)}&action=unsubscribe",
            }

            # Use campaign custom template if set, otherwise fallback to default
            if campaign.email_body_html and campaign.email_body_html.strip():
                html_body = _render_email_body(campaign.email_body_html, context)
            else:
                # Render default Jinja2 template
                try:
                    from app.services.email_service import jinja_env
                    tmpl = jinja_env.get_template("provider_campaign_invite.html")
                    html_body = tmpl.render(**context)
                except Exception as tmpl_exc:
                    logger.warning("Failed to render default template: %s", tmpl_exc)
                    html_body = f"<p>You are invited to join ProReadyEngineer. <a href='{invite_link}'>Register here</a>.</p>"

            subject = _render_email_body(
                campaign.email_subject or "You're invited to join ProMechDirectory",
                context,
            )

            # Wrap the authored body in the deliverability-safe shell (CAN-SPAM footer +
            # physical address + unsubscribe) and attach a plain-text alternative.
            from app.services.campaign_email import (
                body_to_html, wrap_campaign_email, html_to_text, build_unsubscribe_headers,
            )
            unsub_url = _build_unsubscribe_url(invite.invite_token)
            wrapped_html = wrap_campaign_email(
                body_to_html(html_body),
                unsubscribe_url=unsub_url,
                preheader=subject,
            )
            text_body = html_to_text(wrapped_html)
            unsub_headers = build_unsubscribe_headers(unsub_url, mailto="unsubscribe@promechdirectory.com")

            message_id = None
            try:
                if api_key:
                    resp = await client.post(
                        "https://api.resend.com/emails",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={
                            "from": from_addr,
                            "to": [target_email],
                            "subject": subject,
                            "html": wrapped_html,
                            "text": text_body,
                            "headers": unsub_headers,
                        }
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        message_id = data.get("id")
                        invite.status = InviteStatus.SENT
                        invite.sent_at = datetime.now(timezone.utc)
                        invite.resend_message_id = message_id
                        sent_count += 1
                    else:
                        logger.warning(
                            "Resend API error for invite %s: %s %s",
                            invite.id, resp.status_code, resp.text[:200],
                        )
                        invite.status = InviteStatus.BOUNCED
                        failed_count += 1
                else:
                    # No API key configured — log only (test/dev mode)
                    logger.warning(
                        "[CAMPAIGN] No Resend API key — skipping actual send for invite %s (to: %s)",
                        invite.id, target_email,
                    )
                    invite.status = InviteStatus.SENT
                    invite.sent_at = datetime.now(timezone.utc)
                    sent_count += 1
            except Exception as exc:
                logger.error("Failed to send invite %s: %s", invite.id, exc)
                invite.status = InviteStatus.BOUNCED
                failed_count += 1

    # Update campaign aggregate counters
    campaign.total_sent = (campaign.total_sent or 0) + sent_count
    campaign.total_bounced = (campaign.total_bounced or 0) + failed_count
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "Campaign %s batch complete: sent=%d failed=%d total_sent=%d",
        campaign_id, sent_count, failed_count, campaign.total_sent,
    )
    return {
        "sent": sent_count,
        "failed": failed_count,
    }


# ---------------------------------------------------------------------------
# Founding access grant management
# ---------------------------------------------------------------------------

async def grant_founding_access(
    db: AsyncSession,
    *,
    provider_id: int,
    user_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> FoundingAccessGrant:
    """Atomically check founding slot availability and create access grant.

    Uses row-level locking on the campaign to prevent race conditions when
    multiple providers register simultaneously near the slot limit.

    Raises ValueError if:
    - Campaign not found
    - Founding slots exhausted
    - Provider already has an active grant from this campaign
    """
    # Lock campaign row for atomic slot check + increment
    result = await db.execute(
        select(ProviderCampaign)
        .where(ProviderCampaign.id == campaign_id)
        .with_for_update()
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    if campaign.founding_slots_claimed >= campaign.founding_slots_total:
        raise ValueError(
            f"Founding slots exhausted: {campaign.founding_slots_claimed}/{campaign.founding_slots_total}"
        )

    # Check for existing active grant for this provider from this campaign
    existing = await db.execute(
        select(FoundingAccessGrant).where(
            and_(
                FoundingAccessGrant.provider_id == provider_id,
                FoundingAccessGrant.campaign_id == campaign_id,
                FoundingAccessGrant.is_active == True,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(
            f"Provider {provider_id} already has an active founding grant for campaign {campaign_id}"
        )

    # Increment slot counter
    campaign.founding_slots_claimed += 1
    campaign.total_registered = (campaign.total_registered or 0) + 1
    campaign.updated_at = datetime.now(timezone.utc)

    # Compute expiry
    expires_at = datetime.now(timezone.utc) + timedelta(days=campaign.founding_duration_days)

    grant = FoundingAccessGrant(
        provider_id=provider_id,
        user_id=user_id,
        campaign_id=campaign_id,
        granted_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(grant)

    # Mark the invite as registered if one exists
    invite_result = await db.execute(
        select(ProviderCampaignInvite).where(
            and_(
                ProviderCampaignInvite.campaign_id == campaign_id,
                ProviderCampaignInvite.provider_id == provider_id,
            )
        )
    )
    invite = invite_result.scalar_one_or_none()
    if invite:
        invite.status = InviteStatus.REGISTERED
        invite.registered_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(grant)

    logger.info(
        "Founding access granted: provider=%s user=%s campaign=%s expires=%s slot=%d/%d",
        provider_id, user_id, campaign_id, expires_at.date(),
        campaign.founding_slots_claimed, campaign.founding_slots_total,
    )
    return grant


FOUNDING_SUBSCRIPTION_MARKER = "founding_campaign"


async def redeem_campaign_invite(
    db: AsyncSession,
    *,
    token: str,
    user_id: uuid.UUID,
) -> Optional[int]:
    """Redeem a campaign invite token at registration time.

    Looks the random per-invite token up in ``provider_campaign_invites``. If it
    belongs to a real campaign invite, this atomically:
      * locks the campaign row, checks founding-slot availability,
      * grants the provider a REAL PROVIDER_ANNUAL ($1000 tier) subscription whose
        ``current_period_end`` is ``now + founding_duration_days`` (the 3-month promo),
        tagged with provider_name = FOUNDING_SUBSCRIPTION_MARKER so the daily expiry
        job cancels it exactly at the end date,
      * marks the invite REGISTERED and increments the slot counter.

    Idempotent: re-redeeming an already-REGISTERED invite (or a provider who already
    has an active founding subscription) does not double-grant or double-count.

    Returns the linked provider_id, or ``None`` if the token is not a campaign invite.
    """
    invite_result = await db.execute(
        select(ProviderCampaignInvite).where(
            ProviderCampaignInvite.invite_token == token
        )
    )
    invite = invite_result.scalar_one_or_none()
    if invite is None:
        return None  # not a campaign token (caller falls back to other paths)

    provider_id = invite.provider_id
    campaign_id = invite.campaign_id

    # Idempotency: already redeemed → just return the provider link.
    if invite.status == InviteStatus.REGISTERED:
        return provider_id

    # Lock the campaign row for an atomic slot check + increment.
    camp_result = await db.execute(
        select(ProviderCampaign)
        .where(ProviderCampaign.id == campaign_id)
        .with_for_update()
    )
    campaign = camp_result.scalar_one_or_none()
    if campaign is None:
        return provider_id  # invite orphaned; still link the provider

    # Only consume a slot if one is available; if exhausted, still link the
    # account but do not grant the promo subscription.
    slots_available = campaign.founding_slots_claimed < campaign.founding_slots_total

    # Create the promo PROVIDER_ANNUAL subscription (idempotent).
    existing_sub = await db.execute(
        select(Subscription).where(
            Subscription.provider_id == provider_id,
            Subscription.subscription_type == SubscriptionType.PROVIDER_ANNUAL,
            Subscription.subscription_status == SubscriptionStatus.ACTIVE,
        )
    )
    has_active_annual = existing_sub.scalar_one_or_none() is not None

    if slots_available and not has_active_annual:
        now = datetime.now(timezone.utc)
        period_days = campaign.founding_duration_days or 90
        db.add(Subscription(
            provider_id=provider_id,
            user_id=user_id,
            provider_name=FOUNDING_SUBSCRIPTION_MARKER,
            external_subscription_id=f"founding:{campaign_id}",
            subscription_type=SubscriptionType.PROVIDER_ANNUAL,
            subscription_status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=period_days),
        ))
        campaign.founding_slots_claimed += 1
        campaign.total_registered = (campaign.total_registered or 0) + 1
        campaign.updated_at = now
        logger.info(
            "Founding promo: provider=%s user=%s campaign=%s tier=PROVIDER_ANNUAL days=%d slot=%d/%d",
            provider_id, user_id, campaign_id, period_days,
            campaign.founding_slots_claimed, campaign.founding_slots_total,
        )

    # Mark the invite redeemed regardless (links the account to the campaign).
    invite.status = InviteStatus.REGISTERED
    invite.registered_at = datetime.now(timezone.utc)

    await db.commit()
    return provider_id


async def check_founding_access(db: AsyncSession, *, provider_id: int) -> bool:
    """Return True if provider has an active, non-expired founding access grant.

    Called in the RFQ unlock flow BEFORE the payment gate.
    Founding access grants RFQ unlock only — not profile editing or rank-up.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(FoundingAccessGrant).where(
            and_(
                FoundingAccessGrant.provider_id == provider_id,
                FoundingAccessGrant.is_active == True,
                FoundingAccessGrant.expires_at > now,
            )
        ).limit(1)
    )
    grant = result.scalar_one_or_none()
    return grant is not None


async def get_campaign_invite_stats(db: AsyncSession, campaign_id: uuid.UUID) -> dict:
    """Return per-status counts for all invites in a campaign."""
    result = await db.execute(
        select(ProviderCampaignInvite.status, func.count())
        .where(ProviderCampaignInvite.campaign_id == campaign_id)
        .group_by(ProviderCampaignInvite.status)
    )
    return {row[0]: row[1] for row in result.all()}
