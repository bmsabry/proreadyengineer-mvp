"""nda_service.py - Signwell NDA integration for ProMechDirectory."""
from __future__ import annotations

import httpx
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.provider import Provider
from app.models.rfq import RFQ
from app.models.nda import RFQNDA

logger = logging.getLogger(__name__)

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
    api_key = api_key.strip()
    logger.info("[SIGNWELL] Using API key: length=%d, prefix=%s...", len(api_key), api_key[:8])
    return {
        "X-Api-Key": api_key,
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
    return tid.strip()


def _extract_signing_url(doc: dict) -> Optional[str]:
    """Extract the first available signing URL from a Signwell document dict."""
    for signer in (doc.get("recipients") or doc.get("signees") or doc.get("signers") or []):
        url = signer.get("sign_page_url") or signer.get("embedded_signing_url")
        if url:
            return url
    return None


def _human_date(dt: Optional[datetime]) -> str:
    """Format a datetime as a human-readable date string for NDA documents."""
    if dt is None:
        return datetime.utcnow().strftime("%B %d, %Y")
    return dt.strftime("%B %d, %Y")


async def _fetch_template_placeholder_ids(db: AsyncSession) -> tuple:
    """Fetch Signwell template and return (customer_placeholder_name, provider_placeholder_name).

    Returns the EXACT placeholder names as they appear in the Signwell template.
    These must be passed as placeholder_name in the recipients array.
    Falls back to ("Customer", "Provider") if template cannot be fetched.
    """
    h = await _headers(db)
    tid = await _get_template_id(db)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{SIGNWELL_BASE_URL}/document_templates/{tid}", headers=h,
        )
        resp.raise_for_status()
    tmpl = resp.json()
    logger.info("[SIGNWELL] Template keys: %s", list(tmpl.keys()))

    # Extract template placeholders (signers/roles) - try all known field names
    tmpl_placeholders = (
        tmpl.get("placeholder_signers")
        or tmpl.get("template_signers")
        or tmpl.get("placeholders")
        or tmpl.get("roles")
        or tmpl.get("recipients")
        or []
    )
    logger.info(
        "[SIGNWELL] Template placeholders (%d): %s",
        len(tmpl_placeholders),
        json.dumps(tmpl_placeholders, default=str)[:500],
    )

    # Extract the EXACT placeholder name from the template (could be any case)
    # The name field may be called 'name', 'placeholder_name', or 'role'
    def get_placeholder_name(p):
        return (
            p.get("name")
            or p.get("placeholder_name")
            or p.get("role")
            or p.get("title")
            or None
        )

    if len(tmpl_placeholders) >= 2:
        customer_name = get_placeholder_name(tmpl_placeholders[0]) or "Customer"
        provider_name = get_placeholder_name(tmpl_placeholders[1]) or "Provider"
    elif len(tmpl_placeholders) == 1:
        customer_name = get_placeholder_name(tmpl_placeholders[0]) or "Customer"
        provider_name = "Provider"
    else:
        logger.warning("[SIGNWELL] No template placeholders found! Using fallback names.")
        customer_name = "Customer"
        provider_name = "Provider"

    logger.info("[SIGNWELL] Placeholder names from template: customer=%r, provider=%r",
                customer_name, provider_name)
    return customer_name, provider_name


async def _get_template_signing_elements(db: AsyncSession) -> dict:
    """Fetch Signwell template and return its signing_elements.

    Checklist comparison with the prior root-cause fix shows these must be
    passed through from the template. When omitted, Signwell returns:
    `Invalid parameter: signing_elements must be present`.
    """
    h = await _headers(db)
    tid = await _get_template_id(db)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{SIGNWELL_BASE_URL}/document_templates/{tid}", headers=h,
        )
        resp.raise_for_status()

    tmpl = resp.json()
    logger.info("[SIGNWELL] Template keys for signing elements: %s", list(tmpl.keys()))

    elements = (
        tmpl.get("signing_elements")
        or tmpl.get("fields")
        or tmpl.get("form_fields")
        or tmpl.get("elements")
        or []
    )

    logger.info("[SIGNWELL] Found %d signing_elements", len(elements))
    if not elements:
        logger.error("[SIGNWELL] No signing_elements found in template response")
        for k, v in tmpl.items():
            if isinstance(v, (list, dict)) and v:
                logger.info(
                    "[SIGNWELL] tmpl[%s] type=%s len=%s",
                    k,
                    type(v).__name__,
                    len(v) if isinstance(v, list) else "dict",
                )
    if isinstance(elements, dict):
        return elements

    elements_dict = {}
    if isinstance(elements, list):
        for idx, el in enumerate(elements):
            if isinstance(el, dict):
                key = el.get("id") or el.get("api_id") or f"element_{idx}"
                elements_dict[key] = el
    return elements_dict


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

async def create_customer_nda(
    rfq_id,
    customer_user: User,
    rfq: "RFQ",
    db: AsyncSession,
) -> dict:
    """Record NDA payment for an RFQ.

    Does NOT call Signwell. The actual NDA signing (via create_post_acceptance_nda)
    is triggered only after the customer approves a specific provider quote,
    at which point both parties are fully known and all 12 template fields
    can be populated with real data.

    Creates an RFQNDA record to track that payment was received.
    Returns {document_id: None, signing_url: None, status: 'payment_recorded'}.
    """
    from sqlalchemy import select as _sel

    # Idempotency: if a record already exists, return it
    existing = (await db.execute(
        _sel(RFQNDA).where(
            RFQNDA.rfq_id == rfq_id,
            RFQNDA.provider_id == None,  # noqa: E711
        )
    )).scalar_one_or_none()

    if existing:
        logger.info(
            "[NDA] Payment record already exists for RFQ %s (status=%s) - returning existing",
            rfq_id, existing.nda_status,
        )
        return {
            "document_id": None,
            "signing_url": None,
            "status": existing.nda_status.value if hasattr(existing.nda_status, "value") else str(existing.nda_status),
            "message": "NDA payment already recorded. Signing instructions will be sent after a provider quote is approved.",
        }

    # Create a record to track that payment was received
    # signrequest_document_id is None - no Signwell doc yet
    nda = RFQNDA(
        rfq_id=rfq_id,
        provider_id=None,
        customer_user_id=customer_user.id,
        signrequest_document_id=None,
        signrequest_template_id=None,
        nda_status="customer_signature_pending",
    )
    db.add(nda)
    await db.commit()
    await db.refresh(nda)

    logger.info("[NDA] Payment recorded for RFQ %s - Signwell will be triggered post-acceptance", rfq_id)
    return {
        "document_id": None,
        "signing_url": None,
        "status": "customer_signature_pending",
        "message": "NDA payment recorded. Signing instructions will be sent to both parties after a provider quote is approved.",
    }

async def add_provider_to_nda(
    rfq_id,
    provider_id: int,
    provider_user: User,
    db: AsyncSession,
) -> dict:
    """Create provider-side NDA document after customer has signed.
    Pre-fills customer fields, adds provider fields using template_fields.
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

    # Use user account business_name first, then RFQ business_name, then person name
    customer_company  = (
        (cust_user.business_name if cust_user else None)
        or getattr(rfq, "business_name", None)
        or customer_name
    )
    effective_date    = _human_date(customer_nda.customer_signed_at)

    provider_name     = getattr(provider, "name", None) or getattr(provider, "firm_name", None) or "Provider"
    provider_company  = provider_name

    prov_first = (provider_user.first_name or "").strip()
    prov_last  = (provider_user.last_name  or "").strip()
    prov_signer_name = f"{prov_first} {prov_last}".strip() or provider_user.email

    # Fetch actual placeholder names from template (must match exactly)
    _customer_placeholder_name, provider_placeholder_name = await _fetch_template_placeholder_ids(db)

    # Build template_fields to pre-fill ALL text values (NOT signing_elements)
    template_fields = [
        {"api_id": "customer_name",        "value": customer_name},
        {"api_id": "customer_name2",       "value": customer_name},
        {"api_id": "customer_company",     "value": customer_company},
        {"api_id": "customer_entity_type", "value": customer_entity_type},
        {"api_id": "effective_date",       "value": effective_date},
        {"api_id": "governing_state",      "value": (cust_user.state if cust_user else None) or "Not Specified"},
        {"api_id": "provider_name",        "value": prov_signer_name},
        {"api_id": "provider_name2",       "value": prov_signer_name},
        {"api_id": "provider_company",     "value": provider_company},
        {"api_id": "provider_entity_type", "value": "Company"},
        {"api_id": "customer_signature",   "value": ""},
        {"api_id": "provider_signature",   "value": ""},
    ]

    # Signwell REST API uses "recipients" and "template_fields" (per official SDK)
    payload = {
            "template_id": tid,
        "test_mode":   False,
        "subject":     f"NDA for Engineering RFQ #{rfq_id} - Provider Copy",
        "message":     "Please review and sign the NDA to access the full RFQ details.",
        "recipients": [{
            "id":               "1",
            "name":             prov_signer_name,
            "email":            provider_user.email,
            "placeholder_name": provider_placeholder_name,
        }],
        "template_fields": template_fields,
    }

    logger.info("[SIGNWELL] add_provider_to_nda payload: %s", json.dumps(payload, default=str)[:1000])

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SIGNWELL_BASE_URL}/document_templates/documents",
            json=payload,
            headers=h,
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
        nda_status="provider_signature_pending",
    )
    db.add(prov_nda)
    await db.commit()
    await db.refresh(prov_nda)
    return {"document_id": document_id, "signing_url": signing_url}

async def handle_signwell_webhook(event_type: str, payload: dict, db: AsyncSession) -> None:
    """Process Signwell webhook events.
    Handles document_signer_completed and document_completed.
    """
    # Signwell sends: {"event": "...", "data": {"id": "...", "document": {...}}}
    # or: {"document": {"id": "..."}, ...}
    data = payload.get("data", {})
    # Signwell standard payload: {"event":"...","data":{"object":{"id":"DOC_ID",...},...}}
    document_id = (
        data.get("object", {}).get("id")      # Standard Signwell format: data.object.id
        or payload.get("document", {}).get("id")
        or data.get("document", {}).get("id")
        or data.get("id")
        or payload.get("id")
    )
    if not document_id:
        logger.warning(
            "Signwell webhook missing document id, keys: %s, data_keys: %s",
            list(payload.keys()),
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
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
            nda.nda_status = "provider_signature_pending"
        else:
            nda.provider_signed_at = now
        await db.commit()

    elif event_type == "document_completed":
        logger.info("Document fully completed: doc=%s nda_id=%s", document_id, nda.id)
        nda.nda_status = "fully_signed"
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


async def _s3_upload_bytes(data: bytes, s3_key: str, content_type: str, db: AsyncSession) -> None:
    """Upload bytes to S3 using the file_service."""
    from app.services.file_service import upload_file_bytes
    await upload_file_bytes(data, s3_key, content_type)


async def _check_and_heal_customer_signed(customer_nda: RFQNDA, db: AsyncSession) -> bool:
    """Check Signwell API for the customer NDA document status.
    If signed remotely but webhook was missed, updates customer_signed_at and returns True.
    Returns False if genuinely unsigned."""
    if not customer_nda.signrequest_document_id:
        return False
    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/documents/{customer_nda.signrequest_document_id}",
                headers=h,
            )
            resp.raise_for_status()
        doc = resp.json()
        doc_status = doc.get("status", "")
        # Check document-level status
        is_signed = doc_status in ("completed", "signed")
        # Also check individual signers
        if not is_signed:
            for signer in (doc.get("recipients") or doc.get("signers") or []):
                if signer.get("status") in ("completed", "signed"):
                    is_signed = True
                    break
        if is_signed:
            now = datetime.now(timezone.utc)
            customer_nda.customer_signed_at = now
            if customer_nda.nda_status not in ("fully_signed", "provider_signature_pending"):
                customer_nda.nda_status = "provider_signature_pending"
            await db.commit()
            logger.info(
                "[SIGNWELL] Self-healed customer_signed_at for NDA %s (doc %s, remote status=%s)",
                customer_nda.id, customer_nda.signrequest_document_id, doc_status,
            )
            return True
        return False
    except Exception as exc:
        logger.warning("[SIGNWELL] _check_and_heal_customer_signed failed for NDA %s: %s",
                       customer_nda.id, exc)
        return False


async def _heal_nda_if_complete(nda: RFQNDA, db: AsyncSession) -> bool:
    """Check Signwell API to see if the document is fully completed by all parties.
    If yes, updates nda_status to 'fully_signed' and saves to DB.
    Returns True if fully signed, False otherwise."""
    if not nda.signrequest_document_id:
        return False
    if str(getattr(nda, 'nda_status', '')) == 'fully_signed':
        return True
    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/documents/{nda.signrequest_document_id}",
                headers=h,
            )
            resp.raise_for_status()
        doc = resp.json()
        doc_status = doc.get("status", "")
        is_complete = doc_status in ("completed", "signed")
        if not is_complete:
            # Check if ALL recipients have signed
            recipients = doc.get("recipients") or doc.get("signers") or []
            if recipients and all(
                r.get("status") in ("completed", "signed") for r in recipients
            ):
                is_complete = True
        if is_complete:
            now = datetime.now(timezone.utc)
            nda.nda_status = "fully_signed"
            nda.fully_signed_at = nda.fully_signed_at or now
            if not nda.customer_signed_at:
                nda.customer_signed_at = now
            if nda.provider_id and not nda.provider_signed_at:
                nda.provider_signed_at = now
            await db.commit()
            logger.info(
                "[SIGNWELL] Self-healed NDA %s to fully_signed (doc=%s status=%s)",
                nda.id, nda.signrequest_document_id, doc_status,
            )
            return True
        return False
    except Exception as exc:
        logger.warning("[SIGNWELL] _heal_nda_if_complete failed for NDA %s: %s", nda.id, exc)
        return False


async def _maybe_open_rfq_for_dispatch(rfq_id, db: AsyncSession) -> None:
    """Legacy: No-op placeholder. Dispatch now happens at submit_rfq time."""
    # NOTE: In the new workflow, AI search + dispatch happens when the RFQ is first submitted.
    # This function is kept for backward compatibility with webhook handlers but does nothing.
    logger.info("_maybe_open_rfq_for_dispatch called for RFQ %s (no-op in new workflow)", rfq_id)




async def create_post_acceptance_nda(
    rfq_id,
    customer_user_id,
    customer_name: str,
    customer_email: str,
    business_name: str,
    provider_id,
    provider_signer_name: str,
    provider_email: str,
    provider_company: str,
    db: AsyncSession,
    customer_entity_type: str = "Individual",
    customer_state: str = "",
) -> dict:
    """Create a post-acceptance NDA with BOTH customer and provider as real signers.

    Accepts plain string values (NOT ORM objects) to avoid expired-object errors
    after db.commit() calls in the caller. Mirrors the admin test endpoint exactly.
    Both parties receive signing emails from Signwell (no iframe required).
    Returns {document_id, nda_id}.
    """
    from sqlalchemy import select as _sel

    # Idempotency: check if NDA already exists for this RFQ + provider
    existing = (await db.execute(
        _sel(RFQNDA).where(
            RFQNDA.rfq_id == rfq_id,
            RFQNDA.provider_id == provider_id,
        )
    )).scalar_one_or_none()
    if existing:
        logger.info(
            "[SIGNWELL] Post-acceptance NDA already exists for RFQ %s provider %s (status=%s) - skipping",
            rfq_id, provider_id, existing.nda_status,
        )
        return {"document_id": existing.signrequest_document_id, "nda_id": str(existing.id)}

    # Step 1: Get Signwell credentials (exactly like admin test)
    try:
        h   = await _headers(db)
        tid = await _get_template_id(db)
    except Exception as exc:
        logger.error("[SIGNWELL] create_post_acceptance_nda: credentials error: %s", exc)
        raise RuntimeError(f"Signwell not configured: {exc}") from exc

    from datetime import date as _date
    effective_date = _date.today().strftime("%m/%d/%Y")

    # Step 2: Fetch template to get placeholder names (exactly like admin test)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            tmpl_resp = await client.get(
                f"{SIGNWELL_BASE_URL}/document_templates/{tid}", headers=h
            )
            tmpl_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("[SIGNWELL] Template fetch failed %s: %s", exc.response.status_code, exc.response.text)
        raise RuntimeError(
            f"Failed to fetch Signwell template {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        logger.error("[SIGNWELL] Template fetch error: %s", exc)
        raise RuntimeError(f"Template fetch failed: {exc}") from exc

    tmpl_data = tmpl_resp.json()

    # Extract placeholder names exactly like admin test
    tmpl_placeholders = (
        tmpl_data.get("placeholder_signers") or
        tmpl_data.get("template_signers") or
        tmpl_data.get("placeholders") or
        tmpl_data.get("roles") or
        tmpl_data.get("recipients") or
        []
    )

    def get_ph_name(p):
        return (
            p.get("name") or p.get("placeholder_name") or
            p.get("role") or p.get("title") or None
        )

    if len(tmpl_placeholders) >= 2:
        customer_placeholder_name = get_ph_name(tmpl_placeholders[0]) or "Customer"
        provider_placeholder_name = get_ph_name(tmpl_placeholders[1]) or "Provider"
    elif len(tmpl_placeholders) == 1:
        customer_placeholder_name = get_ph_name(tmpl_placeholders[0]) or "Customer"
        provider_placeholder_name = "Provider"
    else:
        customer_placeholder_name = "Customer"
        provider_placeholder_name = "Provider"

    # Step 3: Build 12 template_fields (exactly like admin test)
    template_fields = [
        {"api_id": "customer_name",        "value": customer_name},
        {"api_id": "customer_name2",       "value": customer_name},
        {"api_id": "customer_company",     "value": business_name or customer_name},
        {"api_id": "customer_entity_type", "value": customer_entity_type},
        {"api_id": "provider_name",        "value": provider_signer_name},
        {"api_id": "provider_name2",       "value": provider_signer_name},
        {"api_id": "provider_company",     "value": provider_company},
        {"api_id": "provider_entity_type", "value": "Company"},
        {"api_id": "effective_date",       "value": effective_date},
        {"api_id": "governing_state",      "value": customer_state or "Not Specified"},
        {"api_id": "customer_signature",   "value": ""},
        {"api_id": "provider_signature",   "value": ""},
    ]

    # Step 4: Build payload (exactly like admin test)
    payload = {
        "template_id": tid,
        "test_mode": False,
        "subject": "NDA for Engineering Project - Action Required",
        "message": (
            "Your quote has been accepted. Please sign this Non-Disclosure Agreement "
            "to proceed with the project. Both parties must sign before project files are shared."
        ),
        "recipients": [
            {
                "id": "1",
                "name": customer_name,
                "email": customer_email,
                "placeholder_name": customer_placeholder_name,
            },
            {
                "id": "2",
                "name": provider_signer_name,
                "email": provider_email,
                "placeholder_name": provider_placeholder_name,
            },
        ],
        "template_fields": template_fields,
    }

    logger.info(
        "[SIGNWELL] create_post_acceptance_nda: RFQ=%s customer=%s provider=%s placeholders=(%s, %s)",
        rfq_id, customer_email, provider_email,
        customer_placeholder_name, provider_placeholder_name,
    )

    # Step 5: Create document from template (exactly like admin test)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SIGNWELL_BASE_URL}/document_templates/documents",
                json=payload,
                headers=h,
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "[SIGNWELL] create_post_acceptance_nda failed %s: %s",
            exc.response.status_code, exc.response.text,
        )
        raise RuntimeError(
            f"Signwell document creation failed {exc.response.status_code}: {exc.response.text}"
        ) from exc
    except Exception as exc:
        logger.error("[SIGNWELL] create_post_acceptance_nda unexpected error: %s", exc)
        raise RuntimeError(f"Document creation failed: {exc}") from exc

    doc_data    = resp.json()
    document_id = doc_data["id"]
    logger.info("[SIGNWELL] Created post-acceptance NDA doc %s for RFQ %s", document_id, rfq_id)

    # Step 6: Persist NDA record
    nda = RFQNDA(
        rfq_id=rfq_id,
        provider_id=provider_id,
        customer_user_id=customer_user_id,
        signrequest_document_id=document_id,
        signrequest_template_id=tid,
        nda_status="customer_signature_pending",
    )
    db.add(nda)
    await db.commit()
    await db.refresh(nda)
    return {"document_id": document_id, "nda_id": str(nda.id)}


async def confirm_customer_signed_from_signwell(rfq_id, db: AsyncSession) -> dict:
    """Primary path (not webhook) to confirm customer NDA signing.
    Called by the frontend after iframe signals completion.
    - If already signed in DB, just advances RFQ and returns.
    - If not yet signed, polls Signwell API and heals if confirmed signed.
    - Advances RFQ from awaiting_customer_signature -> open_for_dispatch.
    Returns a status dict.
    """
    customer_nda = (await db.execute(
        select(RFQNDA).where(RFQNDA.rfq_id == rfq_id, RFQNDA.provider_id.is_(None))
    )).scalar_one_or_none()

    if not customer_nda:
        return {"confirmed": False, "reason": "No NDA record found for this RFQ"}

    # If already recorded as signed, just advance RFQ
    if customer_nda.customer_signed_at:
        await _maybe_open_rfq_for_dispatch(rfq_id, db)
        return {
            "confirmed": True,
            "nda_status": str(customer_nda.nda_status),
            "healed": False,
            "message": "Customer signature already recorded; RFQ advanced.",
        }

    # Check Signwell directly
    healed = await _check_and_heal_customer_signed(customer_nda, db)
    if healed:
        await _maybe_open_rfq_for_dispatch(rfq_id, db)
        return {
            "confirmed": True,
            "nda_status": str(customer_nda.nda_status),
            "healed": True,
            "message": "Customer signature confirmed via Signwell API; RFQ dispatching.",
        }

    return {
        "confirmed": False,
        "nda_status": str(customer_nda.nda_status),
        "healed": False,
        "message": "Customer has not yet completed signing in Signwell.",
    }
