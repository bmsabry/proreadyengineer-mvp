"""Admin campaign management API endpoints.

All routes require is_super_admin=True or can_moderate_providers=True.
"""

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.models.campaign import FoundingAccessGrant, ProviderCampaign, ProviderCampaignInvite
from app.models.enums import CampaignStatus, InviteStatus
from app.models.provider import Provider
from app.models.user import User
from app.services import campaign_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth dependency: super admin OR can_moderate_providers
# ---------------------------------------------------------------------------

def require_campaign_admin():
    """Require super admin or moderate-providers capability."""
    async def _check(user: User = Depends(require_role(["admin"]))) -> User:
        if not (getattr(user, "is_super_admin", False) or getattr(user, "can_moderate_providers", False)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin or provider moderation permission required",
            )
        return user
    return _check


# ---------------------------------------------------------------------------
# Pydantic schemas (inline — no separate schemas file needed for MVP)
# ---------------------------------------------------------------------------

class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email_subject: str = Field(default="You're invited to join ProReadyEngineer")
    email_body_html: str = Field(default="")
    founding_slots_total: int = Field(default=250, ge=1, le=10000)
    founding_duration_days: int = Field(default=90, ge=1, le=365)
    batch_size_per_day: int = Field(default=150, ge=1, le=1000)
    target_provider_ids: List[int] = Field(default_factory=list)


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = None
    email_subject: Optional[str] = None
    email_body_html: Optional[str] = None
    founding_slots_total: Optional[int] = Field(None, ge=1, le=10000)
    founding_duration_days: Optional[int] = Field(None, ge=1, le=365)
    batch_size_per_day: Optional[int] = Field(None, ge=1, le=1000)


class PreviewEmailRequest(BaseModel):
    firm_name: str = Field(default="Acme Engineering LLC")
    city: str = Field(default="Houston")
    state: str = Field(default="TX")
    specialty: str = Field(default="Structural Fatigue Analysis")


def _campaign_to_dict(c: ProviderCampaign) -> Dict[str, Any]:
    """Serialize a ProviderCampaign ORM object to response dict."""
    return {
        "id": str(c.id),
        "name": c.name,
        "status": c.status,
        "email_subject": c.email_subject,
        "email_body_html": c.email_body_html,
        "founding_slots_total": c.founding_slots_total,
        "founding_slots_claimed": c.founding_slots_claimed,
        "founding_duration_days": c.founding_duration_days,
        "batch_size_per_day": c.batch_size_per_day,
        "target_mode": c.target_mode,
        "total_providers": c.total_providers,
        "total_sent": c.total_sent,
        "total_bounced": c.total_bounced,
        "total_opened": c.total_opened,
        "total_clicked": c.total_clicked,
        "total_registered": c.total_registered,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "created_by": str(c.created_by),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        # Computed analytics
        "registration_rate_pct": (
            round((c.total_registered / c.total_sent * 100), 1)
            if c.total_sent and c.total_sent > 0 else 0.0
        ),
        "founding_slots_remaining": max(0, c.founding_slots_total - c.founding_slots_claimed),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/admin/campaigns/provider-search")
async def provider_search(
    q: str = Query(default="", min_length=0, max_length=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Search providers by firm name for campaign targeting.

    Returns up to 20 providers matching the query that have a valid email address.
    """
    if not q or not q.strip():
        return {"providers": []}

    try:
        result = await db.execute(
            select(Provider)
            .where(
                or_(
                    Provider.firm_name.ilike(f"%{q.strip()}%"),
                    Provider.name.ilike(f"%{q.strip()}%"),
                )
            )
            .order_by(Provider.firm_name)
            .limit(20)
        )
        providers = result.scalars().all()
    except Exception as exc:
        logger.error("provider_search DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed")

    return {
        "providers": [
            {
                "id": p.id,
                "firm_name": p.firm_name,
                "city": p.city or "",
                "state": p.state or "",
                "primary_specialty": p.primary_specialty or "",
                "email": (p.email_addresses[0] if p.email_addresses else ""),
            }
            for p in providers
        ]
    }


@router.post("/admin/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Create a campaign and populate invite rows for all eligible providers.

    Eligible = have email_addresses AND not already registered as a user.
    Campaign starts in DRAFT status; no emails sent until /start is called.
    """
    try:
        campaign = await campaign_service.create_campaign(
            db,
            name=body.name,
            email_subject=body.email_subject,
            email_body_html=body.email_body_html,
            founding_slots_total=body.founding_slots_total,
            founding_duration_days=body.founding_duration_days,
            batch_size_per_day=body.batch_size_per_day,
            admin_user=current_user,
            target_provider_ids=body.target_provider_ids,
        )
        return {"campaign": _campaign_to_dict(campaign)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/admin/campaigns")
async def list_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """List all campaigns, newest first."""
    result = await db.execute(
        select(ProviderCampaign)
        .order_by(ProviderCampaign.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    campaigns = result.scalars().all()
    total_result = await db.execute(select(func.count()).select_from(ProviderCampaign))
    total = total_result.scalar() or 0
    return {
        "campaigns": [_campaign_to_dict(c) for c in campaigns],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/admin/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Get campaign details and per-status invite stats."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    invite_stats = await campaign_service.get_campaign_invite_stats(db, campaign_id)
    data = _campaign_to_dict(campaign)
    data["invite_status_breakdown"] = invite_stats
    return {"campaign": data}


@router.patch("/admin/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Update campaign config. Only allowed in DRAFT or PAUSED status."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update campaign in '{campaign.status}' status. Only DRAFT/PAUSED allowed.",
        )
    if body.name is not None:
        campaign.name = body.name
    if body.email_subject is not None:
        campaign.email_subject = body.email_subject
    if body.email_body_html is not None:
        campaign.email_body_html = body.email_body_html
    if body.founding_slots_total is not None:
        campaign.founding_slots_total = body.founding_slots_total
    if body.founding_duration_days is not None:
        campaign.founding_duration_days = body.founding_duration_days
    if body.batch_size_per_day is not None:
        campaign.batch_size_per_day = body.batch_size_per_day
    campaign.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(campaign)
    return {"campaign": _campaign_to_dict(campaign)}


@router.post("/admin/campaigns/{campaign_id}/start")
async def start_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Start or resume campaign — triggers first batch immediately via Celery."""
    try:
        campaign = await campaign_service.start_campaign(db, campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Dispatch first batch immediately via Celery
    try:
        from app.tasks.email_tasks import process_campaign_batch_task
        process_campaign_batch_task.apply_async(args=[str(campaign_id)])
    except Exception as exc:
        # Celery may not be available in all environments — log and continue
        import logging
        logging.getLogger(__name__).warning(
            "[campaigns] Could not enqueue batch task: %s", exc
        )

    return {"campaign": _campaign_to_dict(campaign), "message": "Campaign started — first batch dispatched"}


@router.post("/admin/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Pause an active campaign."""
    try:
        campaign = await campaign_service.pause_campaign(db, campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"campaign": _campaign_to_dict(campaign), "message": "Campaign paused"}


@router.post("/admin/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Cancel a campaign permanently."""
    try:
        campaign = await campaign_service.cancel_campaign(db, campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"campaign": _campaign_to_dict(campaign), "message": "Campaign cancelled"}


@router.get("/admin/campaigns/{campaign_id}/invites")
async def list_campaign_invites(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> Dict[str, Any]:
    """Paginated invite list with provider details."""
    # Verify campaign exists
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    conditions = [ProviderCampaignInvite.campaign_id == campaign_id]
    if status_filter:
        try:
            conditions.append(ProviderCampaignInvite.status == InviteStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status filter: {status_filter}")

    result = await db.execute(
        select(ProviderCampaignInvite, Provider)
        .join(Provider, ProviderCampaignInvite.provider_id == Provider.id)
        .where(and_(*conditions))
        .order_by(ProviderCampaignInvite.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    count_result = await db.execute(
        select(func.count())
        .select_from(ProviderCampaignInvite)
        .where(and_(*conditions))
    )
    total = count_result.scalar() or 0

    items = []
    for invite, provider in rows:
        emails = provider.email_addresses or []
        items.append({
            "id": str(invite.id),
            "provider_id": provider.id,
            "firm_name": getattr(provider, 'name', None) or getattr(provider, 'firm_name', None) or "",
            "city": provider.city or "",
            "state": provider.state or "",
            "email": emails[0] if emails else "",
            "status": invite.status,
            "sent_at": invite.sent_at.isoformat() if invite.sent_at else None,
            "opened_at": invite.opened_at.isoformat() if invite.opened_at else None,
            "clicked_at": invite.clicked_at.isoformat() if invite.clicked_at else None,
            "registered_at": invite.registered_at.isoformat() if invite.registered_at else None,
            "resend_message_id": invite.resend_message_id,
            "invite_token": invite.invite_token,
            "created_at": invite.created_at.isoformat() if invite.created_at else None,
        })

    return {"invites": items, "total": total, "skip": skip, "limit": limit}


@router.get("/admin/campaigns/{campaign_id}/invites/export")
async def export_campaign_invites(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> StreamingResponse:
    """Export all campaign invites as CSV."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    result = await db.execute(
        select(ProviderCampaignInvite, Provider)
        .join(Provider, ProviderCampaignInvite.provider_id == Provider.id)
        .where(ProviderCampaignInvite.campaign_id == campaign_id)
        .order_by(ProviderCampaignInvite.created_at)
    )
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Firm Name", "City", "State", "Email",
        "Status", "Sent At", "Opened At", "Clicked At", "Registered At",
        "Resend Message ID",
    ])
    for invite, provider in rows:
        emails = provider.email_addresses or []
        writer.writerow([
            getattr(provider, 'name', None) or getattr(provider, 'firm_name', None) or "",
            provider.city or "",
            provider.state or "",
            emails[0] if emails else "",
            invite.status,
            invite.sent_at.isoformat() if invite.sent_at else "",
            invite.opened_at.isoformat() if invite.opened_at else "",
            invite.clicked_at.isoformat() if invite.clicked_at else "",
            invite.registered_at.isoformat() if invite.registered_at else "",
            invite.resend_message_id or "",
        ])

    output.seek(0)
    filename = f"campaign_{campaign_id}_invites.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/campaigns/{campaign_id}/preview-email")
async def preview_email(
    campaign_id: uuid.UUID,
    body: PreviewEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
) -> Dict[str, Any]:
    """Render a preview of the campaign email with sample provider data."""
    campaign = await db.get(ProviderCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    sample_token = "preview_token_sample_abc123xyz"
    from app.services.campaign_service import _build_invite_link, _render_email_body
    invite_link = _build_invite_link(sample_token)
    slots_remaining = max(0, campaign.founding_slots_total - campaign.founding_slots_claimed)

    context = {
        "firm_name": body.firm_name,
        "city": body.city,
        "state": body.state,
        "specialty": body.specialty,
        "invite_link": invite_link,
        "founding_slots_remaining": slots_remaining,
        "unsubscribe_link": f"{invite_link}&action=unsubscribe",
    }

    if campaign.email_body_html and campaign.email_body_html.strip():
        html_body = _render_email_body(campaign.email_body_html, context)
    else:
        try:
            from app.services.email_service import jinja_env
            tmpl = jinja_env.get_template("provider_campaign_invite.html")
            html_body = tmpl.render(**context)
        except Exception as exc:
            html_body = f"<p>Template render error: {exc}</p>"

    subject = campaign.email_subject or "You're invited to join ProReadyEngineer"
    return {
        "subject": subject,
        "html_preview": html_body,
        "variables_used": list(context.keys()),
    }
