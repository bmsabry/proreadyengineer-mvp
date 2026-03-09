"""Payment and webhook API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.services.payment_service import (
    handle_stripe_webhook, handle_paypal_webhook,
    create_billing_portal_session
)

router = APIRouter()


@router.get("/billing/portal")
async def get_billing_portal(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get Stripe billing portal URL for user."""
    from sqlalchemy import select
    from app.models.payment import Subscription

    # Find user's subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found")

    portal_url = await create_billing_portal_session(subscription.external_customer_id)
    return {"portal_url": portal_url}


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhooks."""
    payload = await request.body()

    try:
        await handle_stripe_webhook(db, payload, stripe_signature)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle PayPal/Braintree webhooks."""
    payload = await request.json()

    try:
        await handle_paypal_webhook(db, payload)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/webhooks/signrequest")
async def signrequest_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle SignRequest signature completion webhooks."""
    from sqlalchemy import select
    from app.models.nda import RFQNDA
    from app.services.file_service import generate_upload_url
    import httpx

    payload = await request.json()

    # Extract document info
    document_id = payload.get("document", {}).get("uuid")
    status = payload.get("document", {}).get("status")

    if status == "signed":
        # Find NDA
        result = await db.execute(
            select(RFQNDA).where(RFQNDA.signrequest_document_id == document_id)
        )
        nda = result.scalar_one_or_none()

        if nda:
            nda.nda_status = "fully_signed"
            nda.fully_signed_at = datetime.utcnow()

            # Fetch signed PDF (async)
            async with httpx.AsyncClient() as client:
                pdf_response = await client.get(
                    f"https://signrequest.com/api/v1/documents/{document_id}/download",
                    headers={"Authorization": f"Token {settings.SIGNREQUEST_API_KEY}"}
                )
                # Upload to S3
                key = f"ndas/{nda.rfq_id}/{document_id}.pdf"
                # ... upload logic
                nda.signed_pdf_s3_key = key

            await db.commit()

    return {"status": "processed"}
