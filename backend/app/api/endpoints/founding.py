"""Founding-provider invitation endpoints (public).

Powers the "Join ProMechDirectory as a Founding Provider" flow on the About page:
  - GET  /founding/status   -> how many of the limited invitations remain (and whether closed)
  - GET  /founding/search   -> public provider-name search (lets the applicant check
                               whether their firm is already listed)
  - POST /founding/apply    -> validated multipart application; emails info@promechdirectory.com
                               (subject "Give free provider account") with the applicant's
                               business documents attached, then decrements the invitation count.

The invitation count is a config-backed counter (FOUNDING_INVITE_LIMIT / FOUNDING_INVITE_SENT)
so an admin can view / raise / reset it from Settings. Once all invitations are used the
apply endpoint returns 409 and the page shows the offer as closed.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

FOUNDING_INBOX = "info@promechdirectory.com"
FOUNDING_SUBJECT = "Give free provider account"

DEFAULT_LIMIT = 50
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "png", "jpg", "jpeg", "gif", "webp", "txt", "csv", "rtf", "odt",
}

_WEBSITE_RE = re.compile(
    r"^(https?://)?(www\.)?([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}(/[^\s]*)?$", re.IGNORECASE
)
_URLISH_RE = re.compile(r"(https?://|www\.|@|\.[a-z]{2,}(/|$))", re.IGNORECASE)


async def _counts(db: AsyncSession) -> Dict[str, int]:
    from app.services.config_service import get_config_value

    raw_limit = await get_config_value(db, "FOUNDING_INVITE_LIMIT")
    raw_sent = await get_config_value(db, "FOUNDING_INVITE_SENT")
    try:
        limit = int(raw_limit) if raw_limit is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    try:
        sent = int(raw_sent) if raw_sent is not None else 0
    except (TypeError, ValueError):
        sent = 0
    sent = max(0, sent)
    remaining = max(0, limit - sent)
    return {"limit": limit, "sent": sent, "remaining": remaining}


@router.get("/founding/status")
async def founding_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Public: remaining founding invitations and whether the offer is closed."""
    c = await _counts(db)
    return {**c, "closed": c["remaining"] <= 0}


@router.get("/founding/search")
async def founding_search(query: str, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Public: search the directory by firm name so an applicant can see whether
    their business is already listed."""
    q = (query or "").strip()
    if len(q) < 2:
        return {"results": []}
    from app.models.provider import Provider

    rows = (await db.execute(
        select(Provider).where(Provider.name.ilike("%" + q + "%")).limit(10)
    )).scalars().all()
    results = []
    for p in rows:
        loc = ", ".join([x for x in [getattr(p, "city", None), getattr(p, "state", None)] if x])
        results.append({
            "name": p.name,
            "location": loc or None,
            "website": getattr(p, "website", None),
        })
    return {"results": results}


def _bad(detail: str):
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _validate_website(website: str) -> str:
    w = (website or "").strip()
    if not w:
        _bad("A business website is required.")
    if not _WEBSITE_RE.match(w):
        _bad("Please enter a valid website (e.g. example.com or https://example.com).")
    return w


def _validate_name(name: str) -> str:
    n = (name or "").strip()
    if len(n) < 2:
        _bad("Please enter your full name.")
    if len(n) > 100:
        _bad("Name is too long.")
    if _URLISH_RE.search(n):
        _bad("Name should be a person's name, not a website or email.")
    if not re.search(r"[A-Za-z]", n):
        _bad("Please enter a valid name.")
    return n


def _validate_business(business_name: str) -> str:
    b = (business_name or "").strip()
    if len(b) < 2:
        _bad("Please enter your business name.")
    if len(b) > 150:
        _bad("Business name is too long.")
    if _URLISH_RE.search(b):
        _bad("Business name should be a name, not a website or email.")
    return b


@router.post("/founding/apply")
async def founding_apply(
    applicant_name: str = Form(...),
    business_name: str = Form(...),
    website: str = Form(...),
    already_listed: bool = Form(False),
    matched_firms: str = Form(""),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Public: submit a founding-provider application. All fields and at least one
    business document are required. Emails info@promechdirectory.com with the docs
    attached, then decrements the invitation counter."""
    c = await _counts(db)
    if c["remaining"] <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Founding provider invitations are closed.")

    name = _validate_name(applicant_name)
    biz = _validate_business(business_name)
    site = _validate_website(website)

    real_files = [f for f in (files or []) if f and (f.filename or "").strip()]
    if not real_files:
        _bad("Please attach at least one business document (brochure, capability statement, etc.).")

    attachments: List[Dict[str, str]] = []
    total = 0
    for f in real_files:
        ext = (f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "")
        if ext not in ALLOWED_EXT:
            _bad("Unsupported file type: " + f.filename + ". Allowed: PDF, Word, PowerPoint, Excel, images, text.")
        data = await f.read()
        if len(data) == 0:
            _bad("The file " + f.filename + " is empty.")
        if len(data) > MAX_FILE_BYTES:
            _bad(f.filename + " is too large (max 8 MB per file).")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            _bad("Attachments are too large in total (max 20 MB).")
        attachments.append({
            "filename": f.filename,
            "content": base64.b64encode(data).decode("ascii"),
        })

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    listed_note = ""
    if already_listed:
        firms = (matched_firms or "").strip()
        listed_note = (
            "<p style='color:#b45309'><strong>Note:</strong> The applicant indicated their firm "
            "may already be listed in the directory"
            + ((" (matched: " + firms + ")") if firms else "")
            + ".</p>"
        )
    docnames = ", ".join(a["filename"] for a in attachments)
    html = (
        "<div style=\"font-family:Arial,sans-serif;font-size:14px;color:#0f172a\">"
        "<h2>Founding Provider Application</h2>" + listed_note +
        "<table cellpadding=\"6\" style=\"border-collapse:collapse\">"
        "<tr><td><strong>Applicant name</strong></td><td>" + name + "</td></tr>"
        "<tr><td><strong>Business name</strong></td><td>" + biz + "</td></tr>"
        "<tr><td><strong>Website</strong></td><td>" + site + "</td></tr>"
        "<tr><td><strong>Already listed?</strong></td><td>" + ("Yes" if already_listed else "No") + "</td></tr>"
        "<tr><td><strong>Documents</strong></td><td>" + docnames + "</td></tr>"
        "<tr><td><strong>Submitted</strong></td><td>" + now + "</td></tr>"
        "</table>"
        "<p style=\"color:#64748b\">Sent automatically from the ProMechDirectory founding-provider form.</p>"
        "</div>"
    )
    text = (
        "Founding Provider Application\n"
        + (("** Applicant may already be listed"
            + ((" (matched: " + matched_firms + ")") if matched_firms else "") + " **\n") if already_listed else "")
        + "Applicant name: " + name + "\nBusiness name: " + biz + "\nWebsite: " + site + "\n"
        + "Already listed: " + ("Yes" if already_listed else "No") + "\n"
        + "Documents: " + docnames + "\nSubmitted: " + now + "\n"
    )

    from app.services.email_service import send_email_with_attachments

    delivered = await send_email_with_attachments(
        to=FOUNDING_INBOX,
        subject=FOUNDING_SUBJECT,
        html_content=html,
        text_content=text,
        attachments=attachments,
        reply_to=None,
        db=db,
    )
    if not delivered:
        logger.error("Founding application email failed to send for %s / %s", name, biz)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="We couldn't submit your application right now. Please try again shortly.",
        )

    from app.services.config_service import save_config_values
    c2 = await _counts(db)
    new_sent = c2["sent"] + 1
    await save_config_values(db, {"FOUNDING_INVITE_SENT": str(new_sent)}, None)
    remaining = max(0, c2["limit"] - new_sent)
    logger.info("Founding application accepted: %s (%s). remaining=%s", biz, name, remaining)
    return {"success": True, "remaining": remaining, "closed": remaining <= 0}
