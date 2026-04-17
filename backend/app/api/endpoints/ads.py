"""Advertising API endpoints.

Supports:
  - Ad submission with LLM3-powered content extraction
  - LLM-powered ad search with relevance reordering
  - Click tracking + impression counting
  - Presigned upload for brochures/flyers
  - Advertiser self-service (my ads, update, asset upload)
  - Admin review/approval flow
  - Public ad listing (unlimited, paginated)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_active_user, get_current_user_optional, require_role
from app.models.user import User
from app.schemas.advertising import (
    AdAssetUploadInitiateRequest,
    AdAssetUploadInitiateResponse,
    AdClickRequest,
    AdCreateRequest,
    AdSearchRequest,
    AdSearchResponse,
    AdSubmissionRequest,
    AdSubmissionResponse,
    AdUpdateRequest,
    AdminAdCreateRequest,
    AdminAdEditRequest,
    AdminAdReviewRequest,
    AdminAdReviewResponse,
    AdvertisementPublicResponse,
    AdvertisementResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM3 helpers for ad content extraction
# ---------------------------------------------------------------------------

async def _get_llm3_client(db: AsyncSession):
    """Get LLM3 client using runtime config (same pattern as search.py)."""
    from app.services.config_service import get_runtime_config as _get_runtime_config
    from openai import AsyncOpenAI

    config = await _get_runtime_config(db)
    doc_api_key = config.get("DOC_LLM_API_KEY") or ""
    if doc_api_key:
        llm_api_key = doc_api_key
        llm_base_url = config.get("DOC_LLM_API_BASE") or "https://api.openai.com/v1"
        llm_model = config.get("DOC_LLM_MODEL") or "gpt-4o-mini"
    else:
        llm_api_key = config.get("OPENAI_API_KEY") or ""
        llm_base_url = config.get("OPENAI_API_BASE") or "https://api.deepinfra.com/v1/openai"
        llm_model = config.get("OPENAI_LLM_MODEL") or "moonshotai/Kimi-K2.5"

    client = AsyncOpenAI(api_key=llm_api_key, base_url=llm_base_url)
    return client, llm_model


async def _extract_ad_content(
    db: AsyncSession,
    website_text: str | None,
    description_text: str | None,
    page_type: str,
) -> Dict[str, Any]:
    """Use LLM3 to extract structured ad content from materials."""
    combined_text = ""
    if website_text:
        combined_text += f"=== WEBSITE CONTENT ===\n{website_text}\n\n"
    if description_text:
        combined_text += f"=== UPLOADED MATERIALS / DESCRIPTION ===\n{description_text}\n\n"

    if not combined_text.strip():
        raise ValueError("No content provided for ad extraction")

    # Truncate to 80k chars
    combined_text = combined_text[:80000]

    ad_type_context = (
        "a software product/tool" if page_type == "software-providers"
        else "an engineering firm"
    )

    prompt = f"""You are an expert B2B copywriter for an engineering-services marketplace. Your job: turn the source content into a punchy, lead-generating advertisement that helps a qualified buyer SEE — within a few seconds — the full range of problems THIS firm is uniquely qualified to solve. The ad must be 100% truthful (every claim grounded in the source) AND must faithfully represent the firm's COMPLETE expertise — not a single narrow sub-specialty.

=====================================================================
THE TWO FAILURE MODES YOU MUST AVOID
=====================================================================

FAILURE MODE A — Generic / vague (the "any-firm" trap)
  Writing sentences that could describe any engineering company ("specialized engineering solutions", "experienced team", "tailored services"). If a competitor could copy your ad and it would still be true of them, your ad is broken.

FAILURE MODE B — Narrow / amputated (the "one-specialty" trap)
  Picking ONE technical domain from the source and ignoring the rest. If the firm does AI + experimental work + gas turbine combustion + thermal fluid sciences, and your ad only talks about CFD of rotating machinery, you have MISREPRESENTED the firm by omission. A buyer searching for thermal-fluid or combustion work will scroll past. This is just as harmful as hallucinating — you are amputating real capability.

Your ad must avoid BOTH. Specific AND comprehensive. That is the bar.

=====================================================================
CORE RULES
=====================================================================

[1] TRUTHFULNESS — non-negotiable
- Every noun, number, name, credential, and technical term you write MUST come from the source content (verbatim, or a close paraphrase that keeps the meaning identical).
- If a fact is not in the source, leave that field empty (null / empty list). Never invent plausible-sounding filler.
- Company name: verbatim from source.
- Proof points: real credentials only — specific degrees, named employers, certifications, patents, awards, years of experience, named projects/clients, quantified outcomes. NEVER platitudes ("experienced team", "client-focused").

[2] BREADTH — equally non-negotiable
- You MUST represent the full technical breadth present in the source. If the source names multiple distinct technical domains (e.g., AI / machine learning, experimental testing, gas turbine combustion, thermal-fluid sciences, CFD, FEA, design, emissions, rotating machinery, pressure vessels, HVAC, combustion diagnostics, heat transfer, etc.), EVERY distinct domain must appear in at least one of: headline, value_proposition, specialties, capabilities, OR promotional_summary.
- Do NOT collapse a multi-disciplinary firm into a single sub-specialty ad. That is a failure.
- "Distinct technical domain" = a technical area a buyer would search for separately. "AI-driven diagnostics" and "gas turbine combustion" are distinct. "CFD" and "rotating machinery" together are a single coupled specialty. Use engineering judgment.

[3] SPECIFICITY — equally non-negotiable
- Use the MOST specific technical terms present in the source. Prefer "gas turbine combustion diagnostics" over "combustion"; prefer "pressure-vessel FEA to ASME Sec VIII" over "structural analysis"; prefer "LES of swirl-stabilized flames" over "CFD". Do NOT substitute a more generic term when a specific one is available.
- FORBIDDEN PHRASES — if any field contains these or close variants, reject your own output and rewrite that field with specifics from the source:
  * "engineering solutions for complex challenges"
  * "specialized engineering services"
  * "precise and innovative solutions"
  * "tailored to complex engineering problems"
  * "cutting-edge", "world-class", "state-of-the-art", "industry-leading"
  * "experienced professionals", "trusted partner", "your success is our priority"
  * any sentence that could describe literally any engineering firm.

[4] MARKETING STRUCTURE
- Headline (5–12 words): Must either (a) name a concrete buyer outcome, OR (b) name the firm's 2–3 strongest technical domains joined naturally. For a multi-disciplinary firm, prefer (b) — e.g. "AI-Driven CFD & Experimental Combustion Engineering", "Gas-Turbine Thermal-Fluid Analysis + Experimental Validation", "Pressure Vessel FEA & Rotating-Machinery CFD". Do NOT write a single-domain headline for a multi-domain firm.
- Tagline (<=15 words): One crisp buyer-facing sentence drawn from the source's own language. NOT a paraphrase of the headline.
- Value proposition (2–3 sentences): (who this firm is for) + (the specific problems it solves across its full scope) + (what makes it qualified). MUST name the firm's multiple technical areas, not just one.
- Promotional summary (3–5 sentences): target buyer -> pain points they have -> what this firm does SPECIFICALLY across its full domain set -> proof signal -> implicit/explicit CTA. At least one sentence must enumerate the firm's cross-disciplinary breadth.

[5] HARD MINIMUMS (meet these unless the source is truly silent on that dimension)
- specialties: MUST contain every distinct technical domain you enumerated in Silent Workflow step 1 (cap at 8 — if more exist, pick the 8 most buyer-relevant). Minimum 4 if the firm spans multiple areas.
- capabilities: at least 4 entries if the source names any services/deliverables; each capability is a specific service a buyer could purchase (e.g., "CFD of swirl-stabilized combustors", "Experimental rig design & instrumentation", "AI surrogate-model development for thermal systems").
- industry_keywords: at least 8 buyer-searchable technical terms spanning the firm's full domain set.
- proof_points: at least 2 entries if ANY credentials/years/clients/projects are mentioned.

=====================================================================
SILENT WORKFLOW — do this internally BEFORE writing any JSON
=====================================================================

Step 1 — ENUMERATE (do not filter yet). Read the source and list, as a raw inventory:
   a) Every distinct TECHNICAL DOMAIN named (e.g., AI/ML, experimental testing, gas turbine combustion, thermal-fluid sciences, CFD, FEA, rotating machinery, emissions, heat transfer, pressure vessels, HVAC, controls, etc.).
   b) Every SERVICE or DELIVERABLE named (design, analysis, simulation, experimental validation, rig build, instrumentation, surrogate model development, report generation).
   c) Every CREDENTIAL, NUMBER, CLIENT, PROJECT, YEAR, CERTIFICATION, PATENT.
   d) Any TARGET-BUYER or PAIN-POINT language.
  Do not drop items because they seem secondary. Completeness first.

Step 2 — ORGANIZE.
  Group the domains from (a) into the firm's top-level positioning. For a multi-disciplinary firm this is typically a cluster of 3–5 areas, NOT a single one.

Step 3 — DRAFT the ad so that every domain from step 1(a) appears somewhere in the final output (headline, tagline, value_proposition, specialties, capabilities, or promotional_summary). The headline and value proposition should reflect the firm's breadth when it is genuinely multi-disciplinary.

Step 4 — SELF-CHECK before returning:
  - For each domain you listed in step 1(a): does it appear in at least one output field? If not, rewrite.
  - For each field: does it contain a forbidden phrase or could it describe any firm? If yes, rewrite with specifics.
  - Is the headline representing the firm's true breadth, or have you narrowed to a single sub-specialty? If narrowed on a multi-domain firm, rewrite.

=====================================================================
CONTEXT
Advertisement is for: {ad_type_context}.

SOURCE CONTENT
{combined_text}
=====================================================================

Return a JSON object with EXACTLY these fields and nothing else:
{{
  "company_name": "Exact company name as written in the source",
  "headline": "5-12 words. For a multi-domain firm, combine 2-3 strongest domains (source terminology). No forbidden phrases.",
  "tagline": "One sentence, max 15 words, drawn from source language. Not a paraphrase of the headline.",
  "value_proposition": "2-3 sentences naming the firm's full technical scope, the buyer problems it solves across that scope, and its qualifications — all in source terminology.",
  "specialties": ["EVERY distinct technical domain from the source (cap 8)", "..."],
  "capabilities": ["specific purchasable service/deliverable from source", "..."],
  "proof_points": ["specific credential with the concrete number or name from source", "..."],
  "cta_label": "3-4 word call-to-action that fits THIS firm (e.g. 'Discuss Your Turbine Challenge', 'Request CFD Consult', 'Scope Experimental Test')",
  "industry_keywords": ["buyer search term spanning the firm's full domain set", "..."],
  "contact_info": {{
    "phone": "phone number if found in source, else null",
    "email": "email if found in source, else null",
    "location": "city/state/country if found in source, else null"
  }},
  "promotional_summary": "3-5 sentences: buyer -> pain -> specific what-we-do across the firm's FULL domain set -> proof -> CTA. Must reflect breadth, not a single sub-specialty."
}}

Return ONLY valid JSON. No markdown. No explanation."""

    client, model = await _get_llm3_client(db)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.35,
    )
    content = response.choices[0].message.content
    return json.loads(content)


async def _draft_ad_decision_email(
    db: AsyncSession,
    *,
    decision: str,          # "approved" | "rejected"
    ad_title: str,
    ad_content: Optional[Dict[str, Any]],
    admin_reason: Optional[str],
    recipient_name: str,
) -> Dict[str, str]:
    """Use LLM3 to draft a subject + body for an ad decision email.

    Returns a dict with keys: subject, body_html, body_text.
    The body is written as real copy a provider will receive — explains
    the decision (and reason, if rejection) and gives clear next steps.
    """
    decision = decision.lower().strip()
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")

    context_block = {
        "ad_title": ad_title or "",
        "ad_extracted_content": ad_content or {},
        "admin_reason": admin_reason or "",
        "decision": decision,
        "recipient_name": recipient_name or "",
    }

    if decision == "approved":
        instruction = (
            "Write a short (4-6 sentence) APPROVAL notification email body. "
            "Confirm that the advertisement has been APPROVED by our review team. "
            "Explicitly state that the ad is NOT yet live on the directory — it will "
            "go live as soon as the provider completes the $50/month subscription. "
            "Tell them to click the \"Pay & Publish Ad\" button in this email (or visit "
            "their dashboard) to complete payment via Stripe. Mention the ad's headline "
            "in a natural way. Close warmly. Do NOT invent pricing, URLs, or numbers "
            "not in the source (other than the $50/month subscription that is already stated)."
        )
    else:
        instruction = (
            "Write a short (4-6 sentence) REJECTION notification email body. "
            "Open with a polite, professional tone. Reference the ad's title. "
            "Explain the reason (rephrased into clear, respectful language "
            "drawn from the admin_reason field — do NOT copy the admin's "
            "raw words verbatim if they are blunt or internal-sounding). "
            "Give 1-3 concrete suggestions for what the provider should fix "
            "before resubmitting, grounded in the reason. Close with an "
            "invitation to resubmit an updated version."
        )

    prompt = f"""You are writing a customer-facing email on behalf of the ProReadyEngineer marketplace operator.

CONTEXT (JSON):
{json.dumps(context_block, indent=2, default=str)}

TASK:
{instruction}

RULES:
- The email is addressed to "{recipient_name or 'there'}" — do NOT include a greeting line (the template adds one).
- Do NOT include a sign-off (the template closes the email).
- Do NOT include subject-line text in the body.
- Use plain, direct language — no corporate platitudes, no "we hope this message finds you well".
- Output HTML only for the body — you may use <p>, <strong>, <em>, <ul>, <li>. No other tags.

Return ONLY a valid JSON object with EXACTLY these fields:
{{
  "subject": "A clear, specific email subject line under 70 characters",
  "body_html": "Email body as HTML (paragraphs, lists ok — no greeting, no sign-off)",
  "body_text": "Same content as plain text, newline-separated paragraphs"
}}

Return ONLY valid JSON. No markdown. No explanation."""

    client, model = await _get_llm3_client(db)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    parsed = json.loads(response.choices[0].message.content)
    # sanity defaults in case the LLM omits a field
    return {
        "subject": (parsed.get("subject") or f"Your advertisement {decision}").strip()[:140],
        "body_html": parsed.get("body_html") or f"<p>Your advertisement was {decision}.</p>",
        "body_text": parsed.get("body_text") or f"Your advertisement was {decision}.",
    }


async def _send_ad_decision_email(
    db: AsyncSession,
    *,
    ad,                      # Advertisement instance (needs .title, .llm_extracted_content, .advertiser_user_id)
    decision: str,           # "approved" | "rejected"
    admin_reason: Optional[str],
) -> None:
    """Look up advertiser, draft email via LLM3, and send it. Best-effort; logs on failure."""
    from app.services.email_service import send_email
    from app.core.config import settings

    try:
        user_row = await db.execute(select(User).where(User.id == ad.advertiser_user_id))
        advertiser = user_row.scalar_one_or_none()
        if not advertiser or not advertiser.email:
            logger.warning("Skipping ad decision email — advertiser_user_id=%s has no email", ad.advertiser_user_id)
            return

        recipient_name = advertiser.full_name or advertiser.email.split("@")[0]

        draft = await _draft_ad_decision_email(
            db,
            decision=decision,
            ad_title=ad.title or "",
            ad_content=ad.llm_extracted_content,
            admin_reason=admin_reason,
            recipient_name=recipient_name,
        )

        template = "ad_approved" if decision == "approved" else "ad_rejected"
        frontend = (settings.FRONTEND_URL or "").rstrip("/")
        context = {
            "email_subject": draft["subject"],
            "recipient_name": recipient_name,
            "email_body_html": draft["body_html"],
            "email_body_text": draft["body_text"],
            "advertise_url": f"{frontend}/provider/advertise",
            "dashboard_url": f"{frontend}/provider/dashboard",
        }

        await send_email(
            to=advertiser.email,
            template=template,
            subject=draft["subject"],
            context=context,
            db=db,
        )
        logger.info("Ad decision email sent decision=%s ad_id=%s to=%s", decision, ad.id, advertiser.email)
    except Exception as exc:
        logger.exception("Failed to send ad decision email ad_id=%s err=%s", getattr(ad, "id", None), exc)


async def _fetch_full_website_for_ad(url: str) -> str:
    """Crawl the full website — same approach as admin 'add firm' workflow."""
    from app.api.endpoints.admin import _admin_fetch_website_text
    return await _admin_fetch_website_text(url)


# ---------------------------------------------------------------------------
# Ad Submission (new workflow)
# ---------------------------------------------------------------------------

async def _process_ad_in_background(
    ad_id: uuid.UUID,
    source_url: Optional[str],
    description_text: Optional[str],
    page_type: str,
    advertiser_email: str,
    advertiser_name: str,
) -> None:
    """Background task: crawl website + LLM extraction, then update ad record."""
    from app.db.session import AsyncSessionLocal
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    async with AsyncSessionLocal() as bg_db:
        try:
            # ── Step 1: Crawl the website ──────────────────────────────────
            website_text: str | None = None
            if source_url:
                logger.info("Ad bg starting crawl ad_id=%s url=%s", ad_id, source_url)
                try:
                    raw = await _fetch_full_website_for_ad(source_url)
                    website_text = raw if raw and raw.strip() else None
                    logger.info("Ad bg crawl done ad_id=%s url=%s chars=%d",
                                ad_id, source_url, len(website_text or ""))
                except Exception as exc:
                    logger.warning("Ad bg crawl failed ad_id=%s url=%s err=%s", ad_id, source_url, exc)

            if not website_text and description_text:
                logger.info("Ad %s crawl empty — using description_text only", ad_id)

            if not website_text and not description_text:
                logger.error("Ad %s has no content (url=%s) — marking rejected", ad_id, source_url)
                await bg_db.execute(
                    update(Advertisement)
                    .where(Advertisement.id == ad_id)
                    .values(ad_status=AdStatus.REJECTED,
                            title="No content found — please re-submit with a description or brochure")
                )
                await bg_db.commit()
                return

            # ── Step 2: LLM extraction ─────────────────────────────────────
            extracted = await _extract_ad_content(
                bg_db,
                website_text=website_text,
                description_text=description_text,
                page_type=page_type,
            )
            headline = extracted.get("headline") or extracted.get("company_name") or "Advertisement"
            promo_summary = extracted.get("promotional_summary") or extracted.get("value_proposition") or ""

            # ── Step 3: Commit to DB ───────────────────────────────────────
            await bg_db.execute(
                update(Advertisement)
                .where(Advertisement.id == ad_id)
                .values(
                    ad_status=AdStatus.PENDING_REVIEW,
                    title=headline[:200],
                    promotional_text=promo_summary[:2000] if promo_summary else None,
                    llm_extracted_content=extracted,
                )
            )
            await bg_db.commit()
            logger.info("Ad %s processing complete → pending_review", ad_id)

            # ── Step 4: Notify admin ───────────────────────────────────────
            try:
                from app.services.email_service import send_ad_pending_review_alert
                await send_ad_pending_review_alert(
                    ad_id=str(ad_id),
                    advertiser_email=advertiser_email,
                    advertiser_name=advertiser_name,
                    ad_title=headline,
                    page_type=page_type,
                    db=bg_db,
                )
                logger.info("Admin notification sent for ad %s", ad_id)
            except Exception as notify_exc:
                logger.warning("Admin notify failed for ad %s err=%s", ad_id, notify_exc)

        except Exception as exc:
            # ── Any crash → mark REJECTED so ad never stays stuck in processing ──
            logger.exception("Ad background processing failed ad_id=%s err=%s", ad_id, exc)
            try:
                await bg_db.rollback()
                await bg_db.execute(
                    update(Advertisement)
                    .where(Advertisement.id == ad_id)
                    .values(ad_status=AdStatus.REJECTED,
                            title="Ad generation failed — please re-submit")
                )
                await bg_db.commit()
            except Exception as cleanup_exc:
                logger.error("Ad %s cleanup also failed: %s", ad_id, cleanup_exc)


@router.post("/ads/submit", response_model=AdSubmissionResponse)
async def submit_ad(
    data: AdSubmissionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Submit a new advertisement for review.

    Creates the ad record immediately (status=processing) and returns success
    right away. The full website crawl + LLM3 extraction run in a background
    task — same deep crawl as admin "add firm". Ad moves to pending_review
    when processing completes.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.models.provider import Provider, ProviderMembership

    # Resolve provider membership
    provider_id: int | None = None
    membership_result = await db.execute(
        select(ProviderMembership.provider_id).where(
            ProviderMembership.user_id == current_user.id,
            ProviderMembership.status == "active",
        ).limit(1)
    )
    membership_row = membership_result.scalar_one_or_none()
    if membership_row:
        provider_id = membership_row

    # Resolve source URL
    source_url = data.website_url
    if source_url and not source_url.startswith("http"):
        source_url = "https://" + source_url

    if not source_url and provider_id:
        provider_result = await db.execute(
            select(Provider.website).where(Provider.id == provider_id)
        )
        existing_website = provider_result.scalar_one_or_none()
        if existing_website:
            source_url = existing_website
            if not source_url.startswith("http"):
                source_url = "https://" + source_url

    if not source_url and not data.description_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a website URL or a description to generate your ad.",
        )

    # Create the ad record immediately with PROCESSING status
    ad_id = uuid.uuid4()
    ad = Advertisement(
        id=ad_id,
        advertiser_user_id=current_user.id,
        provider_id=provider_id,
        page_type=data.page_type,
        title="Generating your ad…",
        ad_status=AdStatus.PROCESSING,
        source_website_url=source_url,
        outbound_url=data.outbound_url or source_url,
        uploaded_materials_s3_keys=data.uploaded_material_keys,
        click_count=0,
        impression_count=0,
    )
    db.add(ad)

    if "advertiser" not in (current_user.roles or []):
        current_user.roles = list(current_user.roles or []) + ["advertiser"]

    await db.commit()

    # Kick off crawl + LLM in background — full website read like admin "add firm"
    background_tasks.add_task(
        _process_ad_in_background,
        ad_id=ad_id,
        source_url=source_url,
        description_text=data.description_text,
        page_type=data.page_type,
        advertiser_email=current_user.email or "",
        advertiser_name=current_user.full_name or current_user.email or "Advertiser",
    )

    return AdSubmissionResponse(
        ad_id=ad_id,
        ad_status=AdStatus.PROCESSING,
        title="Generating your ad…",
        promotional_text=None,
        llm_extracted_content=None,
        message="Your ad is being generated. Our AI is reading your website now. This takes 1-2 minutes — you can close this page and check back shortly.",
    )


# ---------------------------------------------------------------------------
# Presigned upload for ad materials (brochures, flyers, PDFs)
# ---------------------------------------------------------------------------

@router.post("/ads/materials/upload-url", response_model=AdAssetUploadInitiateResponse)
async def get_material_upload_url(
    data: AdAssetUploadInitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a presigned S3 URL for uploading ad materials (brochures, flyers, etc.)."""
    from app.services.file_service import generate_upload_url

    key = f"ad-materials/{current_user.id}/{uuid.uuid4()}/{data.filename}"
    url_data = generate_upload_url(key, data.mime_type, max_file_size=data.file_size_bytes)

    return AdAssetUploadInitiateResponse(
        upload_url=url_data["url"],
        fields=url_data.get("fields", {}),
        s3_key=key,
    )


# ---------------------------------------------------------------------------
# Document text extraction (brochures / flyers / PDFs / DOCX)
# ---------------------------------------------------------------------------

@router.post("/ads/parse-doc")
async def parse_ad_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """Extract plain text from an uploaded PDF, DOCX, or TXT file.

    Returns: { "text": "..." }  Max file size: 10 MB.
    """
    from io import BytesIO

    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    try:
        if filename.endswith(".pdf") or "pdf" in content_type:
            import pypdf
            reader = pypdf.PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p for p in pages if p.strip())

        elif filename.endswith(".docx") or "wordprocessingml" in content_type or "msword" in content_type:
            import docx as _docx
            doc = _docx.Document(BytesIO(content))
            text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())

        elif filename.endswith(".txt") or "text/plain" in content_type:
            text = content.decode("utf-8", errors="replace")

        else:
            raise HTTPException(
                status_code=415,
                detail="Unsupported file type. Please upload a PDF, Word document (.docx), or plain text file.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Doc parse failed filename=%s err=%s", filename, exc)
        raise HTTPException(status_code=422, detail="Could not extract text from this file.")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No readable text found in this file.")

    return {"text": text[:50000]}  # cap at 50k chars


# ---------------------------------------------------------------------------
# Public ad listing (unlimited, paginated)
# ---------------------------------------------------------------------------

@router.get("/ads/software-providers")
async def get_software_provider_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get active software provider advertisements — unlimited, paginated."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Count total
    count_result = await db.execute(
        select(func.count()).select_from(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "software-providers",
        )
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
            Advertisement.page_type == "software-providers",
        ).order_by(Advertisement.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    ads = result.scalars().all()

    # Increment impression counts
    ad_ids = [a.id for a in ads]
    if ad_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(ad_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    return {
        "advertisements": [_to_public_response(a) for a in ads],
        "total_count": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/ads/_status_summary")
async def ads_status_summary(db: AsyncSession = Depends(get_db)):
    """PUBLIC diagnostic. Lists how many ads are in each status and each
    page_type, plus the N most recently touched ads (title/status/
    page_type only, no PII). Lets us debug 'my ad is active but not
    showing' from a browser without admin access.

    Includes an `endpoint_version` string so we can verify which build
    of the backend is actually serving.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    status_counts: dict = {}
    for st in AdStatus:
        r = await db.execute(
            select(func.count()).select_from(Advertisement).where(
                Advertisement.ad_status == st.value
            )
        )
        c = r.scalar() or 0
        if c:
            status_counts[st.value] = c

    page_type_counts: dict = {}
    r = await db.execute(
        select(Advertisement.page_type, func.count()).group_by(Advertisement.page_type)
    )
    for pt, c in r.all():
        page_type_counts[pt or "<null>"] = c

    r = await db.execute(
        select(Advertisement)
        .order_by(Advertisement.created_at.desc())
        .limit(10)
    )
    recents = []
    for a in r.scalars().all():
        recents.append({
            "id": str(a.id),
            "title": (a.title or "")[:80],
            "ad_status": str(a.ad_status),
            "page_type": a.page_type,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "started_at": a.started_at.isoformat() if a.started_at else None,
        })

    return {
        "endpoint_version": "v3_2026_04_17_show_all_active_with_diagnostics",
        "status_counts": status_counts,
        "page_type_counts": page_type_counts,
        "recent_ads": recents,
        "total_ads": sum(status_counts.values()),
        "active_count": status_counts.get("active", 0),
    }


@router.get("/ads/featured-firms")
async def get_featured_firm_ads(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get ALL active, paid advertisements — the canonical premium firms
    listing. We show every ACTIVE ad here regardless of its `page_type`
    so a provider who just paid can always find their ad on the public
    directory. The narrower /ads/software-providers endpoint continues
    to filter by page_type for the software-specific subpage.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    count_result = await db.execute(
        select(func.count()).select_from(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
        )
    )
    total = count_result.scalar() or 0

    # Order by started_at desc (most-recently-paid first), with created_at
    # as a tie-breaker for ads where started_at is NULL.
    result = await db.execute(
        select(Advertisement).where(
            Advertisement.ad_status == AdStatus.ACTIVE,
        ).order_by(
            Advertisement.started_at.desc().nullslast(),
            Advertisement.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    ads = result.scalars().all()

    ad_ids = [a.id for a in ads]
    if ad_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(ad_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    # Always include a small diagnostics block so /featured-firms empty state
    # can tell the user WHY there are no ads (deploy not live, no active ads
    # yet, ads still in reserved_checkout_pending because Stripe webhook did
    # not fire, etc.). This makes the empty state actionable instead of a
    # dead end.
    diag_status_counts: dict = {}
    for st in AdStatus:
        r = await db.execute(
            select(func.count()).select_from(Advertisement).where(
                Advertisement.ad_status == st.value
            )
        )
        c = r.scalar() or 0
        if c:
            diag_status_counts[st.value] = c

    return {
        "advertisements": [_to_public_response(a) for a in ads],
        "total_count": total,
        "page": page,
        "page_size": page_size,
        "diagnostics": {
            "endpoint_version": "v3_2026_04_17_show_all_active",
            "status_counts": diag_status_counts,
            "total_in_db": sum(diag_status_counts.values()),
        },
    }


# ---------------------------------------------------------------------------
# LLM-powered ad search
# ---------------------------------------------------------------------------

@router.post("/ads/search", response_model=AdSearchResponse)
async def search_ads(
    data: AdSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Search active ads using LLM to reorder by relevance to the query.

    The LLM receives the query and all active ad summaries, then returns
    a ranked ordering based on service/capability matching.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Determine page_type filter
    conditions = [Advertisement.ad_status == AdStatus.ACTIVE]
    if data.page_type:
        conditions.append(Advertisement.page_type == data.page_type)

    result = await db.execute(
        select(Advertisement).where(*conditions)
    )
    all_ads = result.scalars().all()

    if not all_ads:
        return AdSearchResponse(query=data.query, advertisements=[], total_count=0)

    # Build summaries for LLM ranking
    ad_summaries = []
    for i, ad in enumerate(all_ads):
        content = ad.llm_extracted_content or {}
        summary = {
            "index": i,
            "title": ad.title,
            "specialties": content.get("specialties", []),
            "capabilities": content.get("capabilities", []),
            "industry_keywords": content.get("industry_keywords", []),
            "value_proposition": content.get("value_proposition", ""),
        }
        ad_summaries.append(summary)

    # Ask LLM to rank
    try:
        client, model = await _get_llm3_client(db)
        ranking_prompt = f"""You are ranking advertisements by relevance to a user's search query.

Search query: "{data.query}"

Advertisements:
{json.dumps(ad_summaries, indent=2)}

Return a JSON object with a single key "ranked_indices" containing an array of the advertisement indices
ordered from most relevant to least relevant based on how well they match the search query.
Only include ads that have at least some relevance to the query.

Example: {{"ranked_indices": [2, 0, 5, 1]}}

Return ONLY valid JSON."""

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": ranking_prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        ranking = json.loads(response.choices[0].message.content)
        ranked_indices = ranking.get("ranked_indices", list(range(len(all_ads))))
    except Exception as exc:
        logger.warning("Ad search LLM ranking failed, using default order: %s", exc)
        ranked_indices = list(range(len(all_ads)))

    # Build ordered response
    ranked_ads = []
    for idx in ranked_indices:
        if 0 <= idx < len(all_ads):
            ranked_ads.append(all_ads[idx])

    # Increment impressions on returned ads
    shown_ids = [a.id for a in ranked_ads]
    if shown_ids:
        await db.execute(
            update(Advertisement)
            .where(Advertisement.id.in_(shown_ids))
            .values(impression_count=Advertisement.impression_count + 1)
        )
        await db.commit()

    return AdSearchResponse(
        query=data.query,
        advertisements=[_to_public_response(a) for a in ranked_ads],
        total_count=len(ranked_ads),
    )


# ---------------------------------------------------------------------------
# Click tracking
# ---------------------------------------------------------------------------

@router.post("/ads/{ad_id}/click")
async def record_ad_click(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Record an ad click. Returns the outbound URL for redirect."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    ad.click_count = (ad.click_count or 0) + 1
    await db.commit()

    return {"outbound_url": ad.outbound_url, "click_count": ad.click_count}


# ---------------------------------------------------------------------------
# Advertiser self-service
# ---------------------------------------------------------------------------

@router.get("/advertiser/ads/me", response_model=List[AdvertisementResponse])
async def get_my_ads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's advertisements."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement)
        .where(Advertisement.advertiser_user_id == current_user.id)
        .order_by(Advertisement.created_at.desc())
    )
    ads = result.scalars().all()

    return [AdvertisementResponse.model_validate(a) for a in ads]


@router.patch("/advertiser/ads/{ad_id}", response_model=AdvertisementResponse)
async def update_ad(
    ad_id: str,
    data: AdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update advertisement content."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ad, field, value)

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


@router.post("/advertiser/ads/{ad_id}/asset/initiate")
async def initiate_ad_asset_upload(
    ad_id: str,
    filename: str,
    content_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get presigned URL for ad image upload."""
    from app.models.advertising import Advertisement
    from app.services.file_service import generate_upload_url

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Ad not found")

    key = f"ads/{ad_id}/assets/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)

    return {"upload_url": url_data["url"], "fields": url_data["fields"], "key": key}


@router.post("/advertiser/ads/{ad_id}/asset/complete")
async def complete_ad_asset_upload(
    ad_id: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record uploaded ad asset."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    ad.image_s3_key = key
    await db.commit()

    return {"message": "Asset uploaded", "ad_id": ad_id}


# ---------------------------------------------------------------------------
# Ad checkout (Stripe subscription for $50/month)
# ---------------------------------------------------------------------------

@router.post("/ads/{ad_id}/checkout-session")
async def create_ad_checkout_session(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a Stripe-hosted Checkout Session for an approved ad ($50/month).

    Returns { checkout_url, payment_attempt_id }. The frontend should redirect
    the provider to checkout_url. On successful payment, the Stripe webhook
    (checkout.session.completed -> _fulfill_advertisement_subscription)
    flips ad_status to ACTIVE and sets started_at, making the ad live on
    the public directory.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.services.payment_service import create_stripe_checkout_session
    from app.core.config import settings

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    # Only allow checkout for ads that have been approved by admin and are
    # awaiting payment. If the ad is already ACTIVE, the provider has already
    # paid; nothing to do here.
    if ad.ad_status != AdStatus.RESERVED_CHECKOUT_PENDING:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ad is not awaiting payment. Current status: {ad.ad_status}. "
                "Checkout is only available after admin approval."
            ),
        )

    frontend = (settings.FRONTEND_URL or "").rstrip("/")
    success_url = f"{frontend}/provider/advertise?payment=success&ad_id={ad.id}"
    cancel_url = f"{frontend}/provider/advertise?payment=cancelled&ad_id={ad.id}"

    session_info = await create_stripe_checkout_session(
        db=db,
        purpose="advertisement_subscription",
        amount=5000,  # $50.00 in cents
        currency="usd",
        user=current_user,
        related_entity_type="advertisement",
        related_id=str(ad.id),
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"ad_id": str(ad.id), "ad_title": ad.title or ""},
    )

    return {
        "checkout_url": session_info.get("checkout_url", ""),
        "payment_attempt_id": session_info.get("payment_attempt_id"),
        "already_paid": session_info.get("already_paid", False),
    }


@router.post("/ads/checkout")
async def create_ad_checkout(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create Stripe checkout for an approved ad ($50/month subscription)."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status != AdStatus.ACTIVE and ad.ad_status != AdStatus.RESERVED_CHECKOUT_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Ad must be approved before checkout. Current status: {ad.ad_status}",
        )

    from app.services.payment_service import create_payment_intent
    intent = await create_payment_intent(
        db, "advertisement_subscription", 5000, "usd", current_user, str(ad.id)
    )

    return {"client_secret": intent["client_secret"], "payment_intent_id": intent["id"]}


# ---------------------------------------------------------------------------
# Admin: Ad Review/Approval
# ---------------------------------------------------------------------------

@router.get("/admin/ads/pending", response_model=List[AdvertisementResponse])
async def get_pending_ads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get all ads pending admin review."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement)
        .where(Advertisement.ad_status == AdStatus.PENDING_REVIEW)
        .order_by(Advertisement.created_at.asc())
    )
    ads = result.scalars().all()
    return [AdvertisementResponse.model_validate(a) for a in ads]


@router.post("/admin/ads/{ad_id}/review", response_model=AdminAdReviewResponse)
async def review_ad(
    ad_id: str,
    data: AdminAdReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin approves or rejects an ad submission."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status != AdStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=400,
            detail=f"Ad is not pending review. Current status: {ad.ad_status}",
        )

    now = datetime.utcnow()

    if data.action == "approve":
        # Approval reserves the slot; ad goes ACTIVE only after the provider
        # completes the $50/month subscription checkout (handled by the
        # Stripe webhook -> _fulfill_advertisement_subscription).
        ad.ad_status = AdStatus.RESERVED_CHECKOUT_PENDING
        message = "Ad approved — awaiting provider payment before it goes live."
    else:
        ad.ad_status = AdStatus.REJECTED
        message = "Ad has been rejected."

    ad.admin_review_notes = data.notes
    ad.reviewed_by_user_id = current_user.id
    ad.reviewed_at = now

    await db.commit()
    await db.refresh(ad)

    # Send email notification to advertiser (best-effort, non-blocking)
    try:
        await _send_ad_decision_email(
            db,
            ad=ad,
            decision="approved" if data.action == "approve" else "rejected",
            admin_reason=data.notes,
        )
    except Exception as exc:
        logger.exception("review_ad: email dispatch failed ad_id=%s err=%s", ad.id, exc)


    return AdminAdReviewResponse(
        ad_id=ad.id,
        ad_status=ad.ad_status,
        reviewed_at=ad.reviewed_at,
        message=message,
    )


# ---------------------------------------------------------------------------
# Admin: Reject Pending Ad + Notify Provider + Delete
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _PydBase


class AdminAdRejectNotifyRequest(_PydBase):
    reason: str


@router.post("/admin/ads/{ad_id}/reject-and-notify")
async def admin_reject_and_notify(
    ad_id: str,
    data: AdminAdRejectNotifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin rejects a submitted ad with a reason. LLM3 drafts + sends an
    email to the provider explaining the rejection and suggesting next steps.
    The ad is then deleted — no lingering 'rejected' row in the directory."""
    from app.models.advertising import Advertisement

    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    # Fire email FIRST (while the record still exists, so we can reference
    # its title/content). Best-effort — failure is logged but does not block.
    await _send_ad_decision_email(
        db,
        ad=ad,
        decision="rejected",
        admin_reason=reason,
    )

    await db.delete(ad)
    await db.commit()

    return {
        "message": "Ad rejected, provider notified, and record removed.",
        "ad_id": ad_id,
    }


# ---------------------------------------------------------------------------
# Admin: Create Ad on behalf of a provider
# ---------------------------------------------------------------------------

@router.post("/admin/ads/create", response_model=AdSubmissionResponse)
async def admin_create_ad(
    data: AdminAdCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin creates an advertisement for a registered provider.

    Uses LLM3 to scrape the provider's website and/or supplied text to
    generate structured ad content. The ad is auto-approved (active).
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus
    from app.models.provider import Provider

    # Verify provider exists
    provider_result = await db.execute(
        select(Provider).where(Provider.id == data.provider_id)
    )
    provider = provider_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Gather content
    website_text: str | None = None
    source_url = data.website_url or provider.website

    if source_url:
        if not source_url.startswith("http"):
            source_url = "https://" + source_url
        try:
            website_text = await _fetch_full_website_for_ad(source_url)
        except Exception as exc:
            logger.warning("Admin ad website fetch failed url=%s err=%s", source_url, exc)

    if not website_text and not data.description_text:
        raise HTTPException(
            status_code=422,
            detail="Provider has no website and no description text was provided.",
        )

    # LLM3 extraction
    try:
        extracted = await _extract_ad_content(
            db,
            website_text=website_text,
            description_text=data.description_text,
            page_type=data.page_type,
        )
    except Exception as exc:
        logger.error("Admin ad LLM extraction failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"LLM extraction failed: {exc}")

    headline = extracted.get("headline", provider.name or "Advertisement")
    promo_summary = extracted.get("promotional_summary") or extracted.get("value_proposition", "")

    # Find the user associated with this provider (if any)
    from app.models.provider import ProviderMembership
    membership_result = await db.execute(
        select(ProviderMembership.user_id).where(
            ProviderMembership.provider_id == data.provider_id,
            ProviderMembership.status == "active",
        ).limit(1)
    )
    advertiser_user_id = membership_result.scalar_one_or_none() or current_user.id

    now = datetime.utcnow()
    ad = Advertisement(
        id=uuid.uuid4(),
        advertiser_user_id=advertiser_user_id,
        provider_id=data.provider_id,
        page_type=data.page_type,
        title=headline[:200],
        promotional_text=promo_summary[:2000] if promo_summary else None,
        outbound_url=data.outbound_url or source_url,
        ad_status=AdStatus.ACTIVE,  # Admin-created → auto-approved
        llm_extracted_content=extracted,
        source_website_url=source_url,
        click_count=0,
        impression_count=0,
        reviewed_by_user_id=current_user.id,
        reviewed_at=now,
        started_at=now,
        admin_review_notes="Auto-approved: created by admin",
    )
    db.add(ad)
    await db.commit()
    await db.refresh(ad)

    return AdSubmissionResponse(
        ad_id=ad.id,
        ad_status=ad.ad_status,
        title=ad.title,
        promotional_text=ad.promotional_text,
        llm_extracted_content=extracted,
        message="Ad created and auto-approved by admin.",
    )


# ---------------------------------------------------------------------------
# Admin: Edit Ad
# ---------------------------------------------------------------------------

@router.patch("/admin/ads/{ad_id}", response_model=AdvertisementResponse)
async def admin_edit_ad(
    ad_id: str,
    data: AdminAdEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin edits any field on an advertisement."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    update_data = data.model_dump(exclude_unset=True)

    # Handle status changes
    if "ad_status" in update_data:
        new_status = update_data["ad_status"]
        if new_status == "active" and not ad.started_at:
            ad.started_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(ad, field, value)

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


# ---------------------------------------------------------------------------
# Admin: Delete Ad
# ---------------------------------------------------------------------------

@router.delete("/admin/ads/{ad_id}")
async def admin_delete_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin permanently deletes an advertisement."""
    from app.models.advertising import Advertisement

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    await db.delete(ad)
    await db.commit()

    return {"message": "Ad deleted", "ad_id": ad_id}


# ---------------------------------------------------------------------------
# Admin: Reactivate Ad
# ---------------------------------------------------------------------------

@router.post("/admin/ads/{ad_id}/reactivate", response_model=AdvertisementResponse)
async def admin_reactivate_ad(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin reactivates a paused, cancelled, or rejected ad."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(Advertisement.id == ad_id)
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    if ad.ad_status == AdStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Ad is already active")

    ad.ad_status = AdStatus.ACTIVE
    if not ad.started_at:
        ad.started_at = datetime.utcnow()
    ad.ended_at = None
    ad.reviewed_by_user_id = current_user.id
    ad.reviewed_at = datetime.utcnow()
    ad.admin_review_notes = (ad.admin_review_notes or "") + f"\nReactivated by admin at {datetime.utcnow().isoformat()}"

    await db.commit()
    await db.refresh(ad)

    return AdvertisementResponse.model_validate(ad)


# ---------------------------------------------------------------------------
# Admin: Ad Analytics
# ---------------------------------------------------------------------------

@router.get("/admin/ads/analytics")
async def ad_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Ad performance analytics for admin dashboard."""
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    # Total counts by status
    status_counts = {}
    for st in AdStatus:
        count_result = await db.execute(
            select(func.count()).select_from(Advertisement).where(
                Advertisement.ad_status == st.value
            )
        )
        cnt = count_result.scalar() or 0
        if cnt > 0:
            status_counts[st.value] = cnt

    # Total clicks and impressions
    totals_result = await db.execute(
        select(
            func.sum(Advertisement.click_count),
            func.sum(Advertisement.impression_count),
        )
    )
    totals = totals_result.one()
    total_clicks = totals[0] or 0
    total_impressions = totals[1] or 0

    return {
        "status_counts": status_counts,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_public_response(ad) -> dict:
    """Convert Advertisement model to public response dict."""
    from app.services.file_service import generate_download_url

    image_url = None
    if ad.image_s3_key:
        try:
            image_url = generate_download_url(ad.image_s3_key)
        except Exception:
            pass

    content = ad.llm_extracted_content or {}

    return {
        "id": str(ad.id),
        "title": ad.title,
        "promotional_text": ad.promotional_text,
        "outbound_url": ad.outbound_url,
        "image_url": image_url,
        "optional_price_text": ad.optional_price_text,
        "provider_id": ad.provider_id,
        "page_type": ad.page_type,
        "llm_extracted_content": content,
        "click_count": ad.click_count or 0,
        "impression_count": ad.impression_count or 0,
    }


# ---------------------------------------------------------------------------


@router.post("/me/promotions/{ad_id}/cancel", response_model=AdvertisementResponse)
async def cancel_my_promotion(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Provider cancels their OWN ad if it is stuck in processing or
    pending_review. Ad is marked CANCELLED so it disappears from the
    provider dashboard card and stops showing 'Generating your ad...'.
    """
    from app.models.advertising import Advertisement
    from app.models.enums import AdStatus

    result = await db.execute(
        select(Advertisement).where(
            Advertisement.id == ad_id,
            Advertisement.advertiser_user_id == current_user.id,
        )
    )
    ad = result.scalar_one_or_none()
    if not ad:
        raise HTTPException(status_code=404, detail="Ad not found")

    # Only allow cancelling ads that are in a pre-payment state.
    if ad.ad_status not in (
        AdStatus.PROCESSING,
        AdStatus.PENDING_REVIEW,
        AdStatus.REJECTED,
        AdStatus.RESERVED_CHECKOUT_PENDING,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel ad in status {ad.ad_status}",
        )

    ad.ad_status = AdStatus.CANCELLED
    ad.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ad)
    return AdvertisementResponse.model_validate(ad)


# ad-blocker-safe aliases
# ---------------------------------------------------------------------------
# Some ad-blockers (uBlock, Brave, AdBlock Plus, pi-hole) block any request
# whose URL contains "/ads/" or "/advertiser/". That silently kills the
# provider dashboard's ad-status card with "Network Error" in axios.
# These aliases expose the same handlers at paths that don't match ad-
# blocker rules. The original /advertiser/ads/* and /ads/* routes are kept
# for backward compatibility.

@router.get("/me/promotions", response_model=List[AdvertisementResponse])
async def get_my_promotions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Ad-blocker-safe alias of GET /advertiser/ads/me."""
    return await get_my_ads(db=db, current_user=current_user)


@router.post("/me/promotions/{ad_id}/checkout-session")
async def create_promotion_checkout_session_alias(
    ad_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Ad-blocker-safe alias of POST /ads/{ad_id}/checkout-session."""
    return await create_ad_checkout_session(
        ad_id=ad_id, db=db, current_user=current_user,
    )

