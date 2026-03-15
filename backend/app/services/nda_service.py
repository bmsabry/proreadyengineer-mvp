"""nda_service.py - Signwell NDA integration for ProMechDirectory."""
from __future__ import annotations

import httpx
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.provider import Provider
from app.models.rfq import RFQ
from app.models.nda import RFQNDA

# ---------------------------------------------------------------------------
# Signwell API constants
# ---------------------------------------------------------------------------
SIGNWELL_BASE_URL = "https://www.signwell.com/api/v1"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _headers(db: AsyncSession) -> dict:
    """Return Signwell API auth headers, reading key from DB config."""
    from app.services.config_service import get_config_value
    api_key = await get_config_value(db, "SIGNWELL_API_KEY")
    if not api_key:
        raise ValueError(
            "Signwell API key not configured. "
            "Go to Admin > Settings > Document Signing to add it."
        )
    return {
        "X-Api-Token": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _get_template_id(db: AsyncSession) -> str:
    """Return the Signwell template ID from DB config."""
    from app.services.config_service import get_config_value
    tid = await get_config_value(db, "SIGNWELL_TEMPLATE_ID")
    if not tid:
        raise ValueError(
            "Signwell template ID not configured. "
            "Go to Admin > Settings > Document Signing to add it."
        )
    return tid


def _extract_signing_url(doc: dict) -> Optional[str]:
    """Extract the first available signing URL from a Signwell document dict."""
    for signer in doc.get("signers", []):
        url = signer.get("sign_page_url") or signer.get("embedded_signing_url")
        if url:
            return url
    return None


def _human_date(dt: Optional[datetime]) -> str:
    """Format a datetime as a human-readable date string for NDA documents."""
    if dt is None:
        return datetime.utcnow().strftime("%B %d, %Y")
    return dt.strftime("%B %d, %Y")


async def get_customer_signing_url(rfq_id, db: AsyncSession) -> str:
    """Get fresh embedded signing URL for customer NDA."""
    nda = (await db.execute(
        select(RFQNDA).where(RFQNDA.rfq_id == rfq_id, RFQNDA.provider_id.is_(None))
    )).scalar_one_or_none()
    if not nda or not nda.signrequest_document_id:
        raise ValueError(f"No NDA document found for RFQ {rfq_id}")

    h = await _headers(db)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{SIGNWELL_BASE_URL}/documents/{nda.signrequest_document_id}", headers=h
        )
        resp.raise_for_status()

    url = _extract_signing_url(resp.json())
    if not url:
        raise ValueError(f"No signing URL in Signwell doc {nda.signrequest_document_id}")
    return url


async def add_provider_to_nda(
    rfq_id,
    provider_id: int,
    provider_user: User,
    db: AsyncSession,
) -> dict:
    """Create provider-side NDA document after customer has signed.
    Pre-fills customer fields, adds provider fields.
    Returns {document_id, signing_url}."""
    h   = await _headers(db)
    tid = await _get_template_id(db)

    # Validate customer NDA exists and customer has signed
    customer_nda = (await db.execute(
        select(RFQNDA).where(RFQNDA.rfq_id == rfq_id, RFQNDA.provider_id.is_(None))
    )).scalar_one_or_none()
    if not customer_nda:
        raise ValueError(f"No customer NDA record found for RFQ {rfq_id}")
    if not customer_nda.customer_signed_at:
        raise ValueError(
            f"Customer has not yet signed the NDA for RFQ {rfq_id}. "
            f"Status: {customer_nda.nda_status}"
        )

    rfq = (await db.execute(select(RFQ).where(RFQ.id == rfq_id))).scalar_one_or_none()
    if not rfq:
        raise ValueError(f"RFQ {rfq_id} not found")

    provider = (await db.execute(
        select(Provider).where(Provider.id == provider_id)
    )).scalar_one_or_none()
    if not provider:
        raise ValueError(f"Provider {provider_id} not found")

    # Get customer user for name reconstruction
    cust_user = (await db.execute(
        select(User).where(User.id == customer_nda.customer_user_id)
    )).scalar_one_or_none()
    if cust_user:
        first = (cust_user.first_name or "").strip()
        last  = (cust_user.last_name  or "").strip()
        customer_name = f"{first} {last}".strip() or cust_user.email
    else:
        customer_name = getattr(rfq, "contact_name", None) or "Customer"

    customer_company  = getattr(rfq, "business_name", None) or customer_name
    effective_date    = _human_date(customer_nda.customer_signed_at)

    provider_name     = getattr(provider, "name", None) or getattr(provider, "firm_name", None) or "Provider"
    provider_company  = provider_name

    prov_first = (provider_user.first_name or "").strip()
    prov_last  = (provider_user.last_name  or "").strip()
    prov_signer_name = f"{prov_first} {prov_last}".strip() or provider_user.email

    payload = {
        "test_mode":   False,
        "template_id": tid,
        "subject":     f"NDA for Engineering RFQ #{rfq_id} - Provider Copy",
        "message":     "Please review and sign the NDA to access the full RFQ details.",
        "signers": [{
            "id":               "signer_1",
            "name":             prov_signer_name,
            "email":            provider_user.email,
            "embedded_signing": True,
        }],
        "fields": [
            {"api_id": "customer_name",        "value": customer_name},
            {"api_id": "customer_name2",       "value": customer_name},
            {"api_id": "customer_company",     "value": customer_company},
            {"api_id": "customer_entity_type", "value": "Individual"},
            {"api_id": "customer_signature",   "value": customer_name},
            {"api_id": "effective_date",       "value": effective_date},
            {"api_id": "governing_state",      "value": "Ohio"},
            {"api_id": "provider_name",        "value": prov_signer_name},
            {"api_id": "provider_name2",       "value": prov_signer_name},
            {"api_id": "provider_company",     "value": provider_company},
            {"api_id": "provider_entity_type", "value": "Company"},
            {"api_id": "provider_signature",   "value": ""},
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SIGNWELL_BASE_URL}/documents", json=payload, headers=h
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Signwell add_provider_to_nda failed %s: %s",
                         exc.response.status_code, exc.response.text)
            raise

    doc_data    = resp.json()
    document_id = doc_data["id"]
    signing_url = _extract_signing_url(doc_data)
    logger.info("Created provider NDA doc %s for RFQ %s provider %s",
                document_id, rfq_id, provider_id)

    # Create provider-specific NDA row
    prov_nda = RFQNDA(
        rfq_id=rfq_id,
        provider_id=provider_id,
        customer_user_id=customer_nda.customer_user_id,
        signrequest_document_id=document_id,
        signrequest_template_id=tid,
        nda_status=NdaStatus.PROVIDER_SIGNATURE_PENDING,
    )
    db.add(prov_nda)
    await db.commit()
    await db.refresh(prov_nda)
    return {"document_id": document_id, "signing_url": signing_url}


async def handle_signwell_webhook(event_type: str, payload: dict, db: AsyncSession) -> None:
    """Process Signwell webhook events.
    Handles document_signer_completed and document_completed.
    """
    document_id = (
        payload.get("document", {}).get("id")
        or payload.get("data", {}).get("document", {}).get("id")
        or payload.get("id")
    )
    if not document_id:
        logger.warning("Signwell webhook missing document id, keys: %s", list(payload.keys()))
        return

    result = await db.execute(
        select(RFQNDA).where(RFQNDA.signrequest_document_id == document_id)
    )
    nda = result.scalar_one_or_none()
    if not nda:
        logger.warning("No NDA found for Signwell document_id %s", document_id)
        return

    now = datetime.now(timezone.utc)

    if event_type == "document_signer_completed":
        signer_email = (
            payload.get("signer", {}).get("email")
            or payload.get("data", {}).get("signer", {}).get("email")
        )
        logger.info("Signer completed: doc=%s signer=%s nda_id=%s", document_id, signer_email, nda.id)
        if nda.provider_id is None:
            nda.customer_signed_at = now
            nda.nda_status = NdaStatus.PROVIDER_SIGNATURE_PENDING
        else:
            nda.provider_signed_at = now
        await db.commit()

    elif event_type == "document_completed":
        logger.info("Document fully completed: doc=%s nda_id=%s", document_id, nda.id)
        nda.nda_status = NdaStatus.FULLY_SIGNED
        nda.fully_signed_at = now
        if not nda.customer_signed_at:
            nda.customer_signed_at = now
        if nda.provider_id and not nda.provider_signed_at:
            nda.provider_signed_at = now

        # Download signed PDF from Signwell and upload to S3
        try:
            h = await _headers(db)
            async with httpx.AsyncClient(timeout=60.0) as client:
                pdf_resp = await client.get(
                    f"{SIGNWELL_BASE_URL}/documents/{document_id}/combined_document",
                    params={"file_url": "true"},
                    headers=h,
                )
                pdf_resp.raise_for_status()
                pdf_meta = pdf_resp.json()
                file_url = pdf_meta.get("file_url") or pdf_meta.get("url")

            if file_url:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    dl = await client.get(file_url)
                    dl.raise_for_status()
                    pdf_bytes = dl.content
                s3_key = f"ndas/{nda.rfq_id}/nda_signed_{document_id}.pdf"
                await _s3_upload_bytes(pdf_bytes, s3_key, "application/pdf", db)
                nda.signed_pdf_s3_key = s3_key
                logger.info("Stored signed NDA PDF at %s", s3_key)
            else:
                logger.warning("No file_url in Signwell combined_document for %s", document_id)
        except Exception as exc:
            logger.error("Failed to download/store signed NDA PDF for doc %s: %s", document_id, exc)

        await db.commit()

        # If provider NDA fully signed, try to advance RFQ to dispatch
        if nda.provider_id is not None:
            try:
                await _maybe_open_rfq_for_dispatch(nda.rfq_id, db)
            except Exception as exc:
                logger.error("Error updating RFQ status after NDA completion: %s", exc)
    else:
        logger.debug("Unhandled Signwell event type: %s", event_type)


async def _maybe_open_rfq_for_dispatch(rfq_id, db: AsyncSession) -> None:
    """Advance RFQ to OPEN_FOR_DISPATCH once NDA signing is complete."""
    rfq = (await db.execute(select(RFQ).where(RFQ.id == rfq_id))).scalar_one_or_none()
    if not rfq:
        return
    current = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status)
    if current in ("awaiting_customer_signature", "awaiting_nda_payment"):
        rfq.rfq_status = RfqStatus.OPEN_FOR_DISPATCH
        await db.commit()
        logger.info("RFQ %s moved to OPEN_FOR_DISPATCH after NDA completion", rfq_id)
