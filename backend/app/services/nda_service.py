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
    """Create a customer-side NDA document with embedded signing flow.
    Fetches the template to get placeholder IDs, pre-fills text fields
    using template_fields, and returns {document_id, signing_url}.
    """
    h   = await _headers(db)
    tid = await _get_template_id(db)

    # Resolve customer display name
    first = (customer_user.first_name or "").strip()
    last  = (customer_user.last_name  or "").strip()
    customer_name    = f"{first} {last}".strip() or customer_user.email
    customer_company = getattr(rfq, "business_name", None) or customer_name
    effective_date   = _human_date(datetime.utcnow())

    # Fetch actual placeholder names from template (must match exactly)
    customer_placeholder_name, _provider_placeholder_name = await _fetch_template_placeholder_ids(db)

    # Build template_fields to pre-fill customer-side values ONLY.
    # Do NOT include provider fields here - provider has not been assigned yet.
    # Sending empty provider fields causes Signwell 422 validation errors.
    template_fields = [
        {"api_id": "customer_name",        "value": customer_name},
        {"api_id": "customer_name2",       "value": customer_name},
        {"api_id": "customer_company",     "value": customer_company},
        {"api_id": "customer_entity_type", "value": "Individual"},
        {"api_id": "effective_date",       "value": effective_date},
        {"api_id": "governing_state",      "value": "Ohio"},
    ]

    # Signwell REST API uses "recipients" and "template_fields" (per official SDK)
    payload = {
            "template_id": tid,
        "test_mode": False,
        "subject": f"NDA for Engineering RFQ #{rfq_id}",
        "message": "Please review and sign the Non-Disclosure Agreement to proceed with your RFQ.",
        "recipients": [{
            "id":               "1",
            "name":             customer_name,
            "email":            customer_user.email,
            "placeholder_name": customer_placeholder_name,
            "send_email":       False,
            "embedded_signing": True,
        }],
        "template_fields": template_fields,
    }

    logger.info("[SIGNWELL] create_customer_nda payload: %s", json.dumps(payload, default=str)[:1000])

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SIGNWELL_BASE_URL}/document_templates/documents",
            json=payload,
            headers=h,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Signwell create_customer_nda failed %s: %s",
                         exc.response.status_code, exc.response.text)
            raise

    doc_data    = resp.json()
    document_id = doc_data["id"]
    signing_url = _extract_signing_url(doc_data)
    logger.info("Created customer NDA doc %s for RFQ %s", document_id, rfq_id)

    # Persist NDA record
    nda = RFQNDA(
        rfq_id=rfq_id,
        provider_id=None,
        customer_user_id=customer_user.id,
        signrequest_document_id=document_id,
        signrequest_template_id=tid,
        nda_status="customer_signature_pending",
    )
    db.add(nda)
    await db.commit()
    await db.refresh(nda)
    return {"document_id": document_id, "signing_url": signing_url}

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

    customer_company  = getattr(rfq, "business_name", None) or customer_name
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
        {"api_id": "customer_entity_type", "value": "Individual"},
        {"api_id": "effective_date",       "value": effective_date},
        {"api_id": "governing_state",      "value": "Ohio"},
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
            "send_email":       False,
            "embedded_signing": True,
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


async def _maybe_open_rfq_for_dispatch(rfq_id, db: AsyncSession) -> None:
    """Advance RFQ to OPEN_FOR_DISPATCH once NDA signing is complete, then run AI search + dispatch."""
    rfq = (await db.execute(select(RFQ).where(RFQ.id == rfq_id))).scalar_one_or_none()
    if not rfq:
        return
    current = rfq.rfq_status.value if hasattr(rfq.rfq_status, "value") else str(rfq.rfq_status)
    if current in ("awaiting_customer_signature", "awaiting_nda_payment"):
        rfq.rfq_status = "open_for_dispatch"
        await db.commit()
        logger.info("RFQ %s moved to OPEN_FOR_DISPATCH after NDA completion", rfq_id)

        # Run AI search to find provider matches, then dispatch first batch of teaser emails
        try:
            from app.services.search_service import search_providers
            from app.services.rfq_service import dispatch_next_batch
            from app.models.rfq import RFQMatch

            query = rfq.project_description or ""
            if rfq.business_name:
                query = f"{rfq.business_name}: {query}"

            logger.info("RFQ %s NDA complete - running AI search", rfq_id)
            match_results, _pipeline_info = await search_providers(query, top_n=100)

            for rank_idx, result in enumerate(match_results, 1):
                match = RFQMatch(
                    rfq_id=rfq_id,
                    provider_id=result.provider_id,
                    rank_position=rank_idx,
                    composite_score=float(result.composite_score or 0),
                    specialty_score=float(result.specialty_score or 0),
                    capabilities_score=float(result.capabilities_score or 0),
                    tier_score=float(result.tier_score or 0),
                    scoring_inputs=result.explanation or {},
                )
                db.add(match)
            await db.commit()
            logger.info("RFQ %s: stored %d matches after NDA, dispatching first batch", rfq_id, len(match_results))
            await dispatch_next_batch(db, rfq_id)
        except Exception as exc:
            logger.error("RFQ %s: search/dispatch after NDA failed: %s", rfq_id, exc, exc_info=True)


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
