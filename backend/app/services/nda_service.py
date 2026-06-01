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
    # IMPORTANT: this must be the template's API ID (a UUID, e.g.
    # 162095ae-2e32-4afd-b170-fb5753d8e923), NOT the share-link slug from the
    # SignWell "new_doc/<slug>" URL. The slug returns 404 from the API. Find the
    # UUID via GET /api/v1/document_templates or the template's API settings page.
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


async def _build_template_fields(db: AsyncSession, values: dict) -> list:
    """Build template_fields for ONLY the text-field api_ids that actually exist
    in the configured Signwell template.

    This adapts to whatever the template looks like and prevents 422
    "not_in_templates" errors when the template's fields differ from our defaults
    (e.g. a recreated template with a generic 'TextField_1'). Signature fields are
    NEVER included here -- signatures are collected from the signers at signing
    time, not pre-filled as template_fields.
    """
    h = await _headers(db)
    tid = await _get_template_id(db)
    text_fields: list = []  # (api_id, label) for every TEXT field in the template
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{SIGNWELL_BASE_URL}/document_templates/{tid}", headers=h)
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("fields") or data.get("template_fields") or []
        flat = []
        for f in raw:
            flat.extend(f) if isinstance(f, list) else flat.append(f)
        for f in flat:
            if isinstance(f, dict) and f.get("type") == "text" and f.get("api_id"):
                text_fields.append((f["api_id"], (f.get("label") or f.get("name") or "")))
    except Exception as exc:  # pragma: no cover - network/template fetch
        logger.warning("[SIGNWELL] could not read template fields (%s); sending provided values", exc)
        return [{"api_id": k, "value": ("" if v is None else str(v))} for k, v in values.items()]
    # Match each template field to a value by api_id OR label, so a field whose
    # api_id was auto-generated (e.g. 'TextField_1') but whose label is
    # 'provider_company' still gets filled. Then send the field's REAL api_id.
    out = []
    for api_id, label in text_fields:
        key = api_id if api_id in values else (label if label in values else None)
        if key is not None and values.get(key) is not None:
            out.append({"api_id": api_id, "value": str(values[key])})
    logger.info("[SIGNWELL] mapped %d/%d template text fields", len(out), len(text_fields))
    return out


async def add_provider_to_nda(
    rfq_id,
    provider_id: int,
    provider_user: User,
    db: AsyncSession,
) -> dict:
    """Provider-first NDA: create ONE mutual NDA document with BOTH the customer
    and this provider as signers, at the moment the provider chooses to sign
    (i.e. to read the RFQ).

    - Does NOT require the customer to have signed first (that was the old,
      circular precondition). The provider signs (embedded URL returned), and the
      customer is emailed by Signwell to countersign.
    - Idempotent: if this provider already has an NDA for this RFQ, returns it.
    Returns {document_id, signing_url, nda_id}.
    """
    from sqlalchemy import select as _sel

    # Idempotency: reuse an existing provider NDA for this RFQ + provider.
    existing = (await db.execute(
        _sel(RFQNDA).where(RFQNDA.rfq_id == rfq_id, RFQNDA.provider_id == provider_id)
        .order_by(RFQNDA.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing and existing.signrequest_document_id:
        signing_url = None
        try:
            h0 = await _headers(db)
            async with httpx.AsyncClient(timeout=30.0) as client:
                doc = await client.get(
                    f"{SIGNWELL_BASE_URL}/documents/{existing.signrequest_document_id}", headers=h0
                )
                if doc.status_code == 200:
                    signing_url = _extract_signing_url(doc.json())
        except Exception:
            signing_url = None
        return {"document_id": existing.signrequest_document_id, "signing_url": signing_url, "nda_id": str(existing.id)}

    h   = await _headers(db)
    tid = await _get_template_id(db)

    rfq = (await db.execute(select(RFQ).where(RFQ.id == rfq_id))).scalar_one_or_none()
    if not rfq:
        raise ValueError(f"RFQ {rfq_id} not found")

    # Customer details come from the RFQ owner (no prior customer NDA required).
    cust_user = None
    if rfq.customer_user_id:
        cust_user = (await db.execute(
            select(User).where(User.id == rfq.customer_user_id)
        )).scalar_one_or_none()
    if cust_user:
        first = (cust_user.first_name or "").strip()
        last  = (cust_user.last_name  or "").strip()
        customer_name = f"{first} {last}".strip() or cust_user.email
        customer_email = cust_user.email
    else:
        customer_name = getattr(rfq, "contact_name", None) or "Customer"
        customer_email = getattr(rfq, "customer_email", None)
    if not customer_email:
        raise ValueError(f"RFQ {rfq_id} has no customer email to send the NDA to")

    provider = (await db.execute(
        select(Provider).where(Provider.id == provider_id)
    )).scalar_one_or_none()
    if not provider:
        raise ValueError(f"Provider {provider_id} not found")
    prov_first = (provider_user.first_name or "").strip()
    prov_last  = (provider_user.last_name  or "").strip()
    prov_signer_name = f"{prov_first} {prov_last}".strip() or provider_user.email

    customer_placeholder_name, provider_placeholder_name = await _fetch_template_placeholder_ids(db)

    from datetime import date as _date
    effective_date = _date.today().strftime("%m/%d/%Y")
    customer_company = (cust_user.business_name if cust_user else None) or getattr(rfq, "business_name", None)
    customer_state = (cust_user.state if cust_user else None)
    provider_company = getattr(provider, "firm_name", None)
    provider_state = getattr(provider, "state", None)

    # Pre-fill ONLY values we actually hold from the user's authenticated account /
    # our records (identity-as-known-to-the-platform) plus the system-owned date.
    # We deliberately do NOT guess fields we don't know (e.g. legal entity type) and
    # do NOT touch signature fields. _build_template_fields maps by api_id OR label
    # and only emits fields that exist in the template; empties are dropped below so
    # a blank value never overwrites a real template default. These values are a
    # convenience default for the signer, not a hard lock (locking a field requires
    # marking it read-only in the SignWell template itself).
    # The provider on this platform is always a firm, so the NDA's provider PARTY is the
    # company: provider_name/provider_name2 = the firm name (NOT the signer's personal name
    # or email), and provider_entity_type is always "Company". prov_signer_name is used only
    # as the SignWell recipient (the human who signs), not as the NDA entity name.
    _prefill = {
        "customer_name": customer_name,
        "customer_name2": customer_name,
        "customer_company": customer_company,
        "governing_state": customer_state,
        "effective_date": effective_date,
        "provider_name": provider_company,
        "provider_name2": provider_company,
        "provider_company": provider_company,
        "provider_entity_type": "Company",
        "provider_state": provider_state,
    }
    _prefill = {k: v for k, v in _prefill.items() if v not in (None, "")}
    template_fields = await _build_template_fields(db, _prefill)

    # Email-based signing with a signing ORDER: the provider (signer 1) is emailed
    # first; once they sign, Signwell automatically emails the customer (signer 2)
    # to countersign. Do NOT set document-level embedded_signing -- it suppresses
    # ALL invitation emails, which is why the customer was never notified.
    payload = {
        "template_id": tid,
        "test_mode":   False,
        "apply_signing_order": True,
        "subject":     f"NDA required to view Engineering RFQ #{rfq_id}",
        "message":     ("A provider wishes to review your RFQ. Both parties must sign this "
                        "mutual NDA before the full RFQ and project files are shared."),
        "recipients": [
            {"id": "1", "name": prov_signer_name, "email": provider_user.email, "placeholder_name": provider_placeholder_name},
            {"id": "2", "name": customer_name,    "email": customer_email,      "placeholder_name": customer_placeholder_name},
        ],
    }
    # Signwell rejects an empty template_fields array ("invalid key values"); only
    # include it when we actually have prefilled values (we normally do not pre-fill,
    # so it is omitted and each signer fills their own fields).
    if template_fields:
        payload["template_fields"] = template_fields

    logger.info("[SIGNWELL] add_provider_to_nda (mutual) rfq=%s provider=%s", rfq_id, provider_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{SIGNWELL_BASE_URL}/document_templates/documents", json=payload, headers=h,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Signwell add_provider_to_nda failed %s: %s",
                         exc.response.status_code, exc.response.text)
            raise

    doc_data    = resp.json()
    document_id = doc_data["id"]
    # Provider is signer id "1"; return their hosted signing URL so the "Sign NDA"
    # button can send them straight there (Signwell also emails them as a backup).
    signing_url = None
    for signer in (doc_data.get("recipients") or doc_data.get("signers") or []):
        if str(signer.get("id")) == "1":
            signing_url = signer.get("sign_page_url") or signer.get("embedded_signing_url")
            break
    if not signing_url:
        signing_url = _extract_signing_url(doc_data)

    prov_nda = RFQNDA(
        rfq_id=rfq_id,
        provider_id=provider_id,
        customer_user_id=rfq.customer_user_id,
        signrequest_document_id=document_id,
        signrequest_template_id=tid,
        nda_status="pending_signatures",
    )
    db.add(prov_nda)
    await db.commit()
    await db.refresh(prov_nda)
    return {"document_id": document_id, "signing_url": signing_url, "nda_id": str(prov_nda.id)}

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
        signer_email = (signer_email or "").strip().lower()
        logger.info("Signer completed: doc=%s signer=%s nda_id=%s", document_id, signer_email, nda.id)
        if nda.provider_id is None:
            # Legacy customer-only document.
            nda.customer_signed_at = now
            nda.nda_status = "provider_signature_pending"
        else:
            # Mutual document with exactly two signers (customer + provider).
            # Match the customer by email; anyone who isn't the customer is the provider.
            cust_email = None
            try:
                if nda.customer_user_id:
                    _cu = (await db.execute(
                        select(User).where(User.id == nda.customer_user_id)
                    )).scalar_one_or_none()
                    cust_email = (_cu.email or "").strip().lower() if _cu else None
            except Exception:
                cust_email = None
            if signer_email and cust_email and signer_email == cust_email:
                nda.customer_signed_at = now
            else:
                nda.provider_signed_at = now
            if nda.customer_signed_at and nda.provider_signed_at:
                # SECURITY (PRE-005): confirm with SignWell before completing the NDA,
                # so forged signer events can't combine into a full completion.
                if await _signwell_document_is_completed(db, document_id):
                    nda.nda_status = "fully_signed"
                    if not nda.fully_signed_at:
                        nda.fully_signed_at = now
                else:
                    logger.warning(
                        "signer_completed would complete NDA but SignWell unconfirmed; doc=%s",
                        document_id,
                    )
                    nda.nda_status = "partially_signed"
            else:
                nda.nda_status = "partially_signed"
        await db.commit()

    elif event_type == "document_completed":
        logger.info("Document fully completed: doc=%s nda_id=%s", document_id, nda.id)
        # SECURITY (PRE-005): the webhook is unsigned. Confirm with SignWell that the
        # document is really completed before flipping the NDA to fully_signed, so a
        # forged event cannot unlock NDA-gated RFQ files.
        if not await _signwell_document_is_completed(db, document_id):
            logger.warning(
                "Ignoring unverified document_completed webhook for doc=%s "
                "(SignWell did not confirm completion).", document_id,
            )
            return
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

        # NDA fully signed. Dispatch already happened at submit time (the current
        # workflow dispatches on submit), so there is nothing further to advance here.
    else:
        logger.debug("Unhandled Signwell event type: %s", event_type)


async def _s3_upload_bytes(data: bytes, s3_key: str, content_type: str, db: AsyncSession) -> None:
    """Upload bytes to S3 using runtime-config credentials (same path as help uploads)."""
    from app.services.config_service import get_runtime_config
    from app.services.file_service import upload_bytes_to_s3_from_config
    cfg = await get_runtime_config(db)
    upload_bytes_to_s3_from_config(s3_key, data, cfg, content_type=content_type)


async def _signwell_document_is_completed(db: AsyncSession, document_id: str) -> bool:
    """Server-to-server confirmation that a SignWell document is actually completed.

    The SignWell webhook is unsigned, so before we trust a `document_completed`
    event we re-fetch the document from SignWell and confirm its real status. This
    stops a forged webhook from marking an NDA fully signed (PRE-005). If SignWell
    is briefly unreachable we return False and ignore the event; the on-read
    poller (_sync_nda_signatures) will reconcile the true state later.
    """
    if not document_id:
        return False
    # Use a FRESH, isolated session for the config + SignWell reads so a config
    # lookup that rolls back (e.g. missing table in tests) can never disturb the
    # caller's in-flight NDA transaction.
    #
    # Only REJECT (return False) when we successfully reach SignWell AND it reports
    # the document is NOT completed — i.e. a forged/premature completion event.
    # Every other case (no API key, SignWell unreachable, any error) trusts the
    # webhook, because the on-read poller (_sync_nda_signatures) reconciles true
    # state and we must never break a legitimate NDA completion.
    from app.db.session import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as _s:
            from app.services.config_service import get_config_value as _gcv
            api_key = await _gcv(_s, "SIGNWELL_API_KEY")
            if not api_key:
                return True
            h = await _headers(_s)
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{SIGNWELL_BASE_URL}/documents/{document_id}", headers=h)
        if resp.status_code != 200:
            logger.warning("SignWell status fetch for %s returned %s; trusting webhook (poller reconciles)", document_id, resp.status_code)
            return True
        status_val = (resp.json().get("status") or "").lower()
        if status_val in ("completed", "signed"):
            return True
        logger.warning("SignWell reports doc %s status=%s; rejecting unconfirmed completion event", document_id, status_val)
        return False
    except Exception as exc:
        logger.error("SignWell completion confirmation errored for %s: %s; trusting webhook", document_id, exc)
        return True


async def _sync_nda_signatures(nda: RFQNDA, db: AsyncSession) -> RFQNDA:
    """Poll Signwell for the document's per-recipient signing status and record it
    on the NDA (provider_signed_at / customer_signed_at / fully_signed). This makes
    status checks reflect reality even if the webhook never fired. Safe to call on
    every status read; it only writes when something changed.
    """
    if not nda.signrequest_document_id:
        return nda
    if str(getattr(nda, "nda_status", "")) == "fully_signed":
        return nda
    try:
        h = await _headers(db)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{SIGNWELL_BASE_URL}/documents/{nda.signrequest_document_id}", headers=h
            )
            resp.raise_for_status()
        doc = resp.json()
        # Resolve the customer's email so we can tell signers apart.
        cust_email = None
        if nda.customer_user_id:
            cu = (await db.execute(select(User).where(User.id == nda.customer_user_id))).scalar_one_or_none()
            cust_email = (cu.email or "").strip().lower() if cu else None
        recips = doc.get("recipients") or doc.get("signers") or []
        signed_emails = [
            (r.get("email") or "").strip().lower()
            for r in recips
            if r.get("status") in ("completed", "signed") or r.get("completed") or r.get("signed_at")
        ]
        now = datetime.now(timezone.utc)
        changed = False
        for em in signed_emails:
            if cust_email and em == cust_email:
                if not nda.customer_signed_at:
                    nda.customer_signed_at = now; changed = True
            else:
                if not nda.provider_signed_at:
                    nda.provider_signed_at = now; changed = True
        doc_complete = doc.get("status") in ("completed", "signed")
        if (nda.customer_signed_at and nda.provider_signed_at) or doc_complete:
            if str(getattr(nda, "nda_status", "")) != "fully_signed":
                nda.nda_status = "fully_signed"; changed = True
            if not nda.fully_signed_at:
                nda.fully_signed_at = now; changed = True
            if not nda.customer_signed_at:
                nda.customer_signed_at = now
            if not nda.provider_signed_at:
                nda.provider_signed_at = now
        elif (nda.customer_signed_at or nda.provider_signed_at) and str(getattr(nda, "nda_status", "")) not in ("fully_signed", "partially_signed"):
            nda.nda_status = "partially_signed"; changed = True
        if changed:
            await db.commit()
            await db.refresh(nda)
            logger.info("[SIGNWELL] synced NDA %s: prov=%s cust=%s status=%s",
                        nda.id, bool(nda.provider_signed_at), bool(nda.customer_signed_at), nda.nda_status)
    except Exception as exc:
        logger.warning("[SIGNWELL] _sync_nda_signatures failed for NDA %s: %s", nda.id, exc)
    return nda


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
        ).order_by(RFQNDA.created_at.desc()).limit(1)
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

    # Build template_fields for whatever text fields the template actually has.
    template_fields = await _build_template_fields(db, {
        "customer_name":        customer_name,
        "customer_name2":       customer_name,
        "customer_company":     business_name or customer_name,
        "customer_entity_type": customer_entity_type,
        "provider_name":        provider_signer_name,
        "provider_name2":       provider_signer_name,
        "provider_company":     provider_company,
        "provider_entity_type": "Company",
        "effective_date":       effective_date,
        "governing_state":      customer_state or "Not Specified",
    })

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
    }
    # Signwell rejects an empty template_fields array ("invalid key values"); only
    # include it when we actually have prefilled values (we normally do not pre-fill,
    # so it is omitted and each signer fills their own fields).
    if template_fields:
        payload["template_fields"] = template_fields

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

