"""Email-failure recording and admin alerting.

Every email delivery failure (sync send error or async Resend webhook bounce)
is persisted via `record_email_failure` and triggers an immediate admin alert.

Recursion guard: when the admin alert itself fails, we log to stderr only —
we do NOT call back into this module. That's why `_send_admin_alert` opens
its own DB session and uses email_service with `is_admin_alert=True`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.email_failure import EmailFailure

logger = logging.getLogger(__name__)

# Truncation caps so a misbehaving provider response can't blow up a column.
_MAX_RESP_CHARS = 4000
_MAX_MSG_CHARS = 1000
_MAX_SUBJ_CHARS = 510


def _truncate(s: Optional[str], n: int) -> Optional[str]:
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= n else s[:n] + "...[truncated]"


async def _resolve_admin_email(db: Optional[AsyncSession] = None) -> Optional[str]:
    """Find the admin notification address. Runtime config first, env fallback."""
    try:
        if db is not None:
            from app.services.config_service import get_runtime_config
            cfg = await get_runtime_config(db)
            v = cfg.get("ADMIN_EMAIL") or cfg.get("admin_email")
            if v:
                return str(v).strip()
    except Exception:
        pass
    return getattr(settings, "ADMIN_EMAIL", None) or getattr(settings, "FROM_EMAIL", None) or None


async def record_email_failure(
    *,
    to_email: str,
    subject: Optional[str],
    source: str,
    error_code: Optional[int] = None,
    error_message: Optional[str] = None,
    provider_response: Optional[str] = None,
    resend_email_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
    fire_admin_alert: bool = True,
) -> Optional[str]:
    """
    Persist an EmailFailure row and (optionally) fire an admin alert.

    Returns the new row id (str) or None if persistence failed for any reason
    — we never raise here, because email_service callers must continue working
    even if the DB is down.
    """
    failure_id: Optional[str] = None

    async def _do_insert(session: AsyncSession) -> Optional[str]:
        try:
            row = EmailFailure(
                to_email=(to_email or "")[:320] or "unknown@unknown",
                subject=_truncate(subject, _MAX_SUBJ_CHARS),
                source=(source or "unknown")[:48],
                error_code=int(error_code) if error_code is not None else None,
                error_message=_truncate(error_message, _MAX_MSG_CHARS),
                provider_response=_truncate(provider_response, _MAX_RESP_CHARS),
                resend_email_id=(resend_email_id or None) and str(resend_email_id)[:128],
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return str(row.id)
        except Exception as exc:
            logger.exception("[email_failure_service] persist failed: %s", exc)
            await session.rollback()
            return None

    try:
        if db is not None:
            failure_id = await _do_insert(db)
        else:
            async with AsyncSessionLocal() as s2:
                failure_id = await _do_insert(s2)
    except Exception as exc:
        logger.exception("[email_failure_service] could not open session: %s", exc)

    if fire_admin_alert:
        # Fire-and-forget so the original send path is not blocked by alert latency.
        try:
            asyncio.create_task(_send_admin_alert(
                to_email=to_email,
                subject=subject,
                source=source,
                error_code=error_code,
                error_message=error_message,
                failure_id=failure_id,
            ))
        except RuntimeError:
            # No running loop (e.g. called from sync context) — best-effort skip.
            logger.warning("[email_failure_service] no event loop for admin alert")

    return failure_id


async def _send_admin_alert(
    *,
    to_email: str,
    subject: Optional[str],
    source: str,
    error_code: Optional[int],
    error_message: Optional[str],
    failure_id: Optional[str],
) -> None:
    """Send a one-off email to the admin about a delivery failure."""
    # Open our own session so we don't share lifecycle with the caller's.
    try:
        async with AsyncSessionLocal() as s:
            admin_email = await _resolve_admin_email(s)
    except Exception:
        admin_email = await _resolve_admin_email(None)

    if not admin_email:
        logger.warning("[email_failure_service] no admin email configured; skipping alert")
        return

    # Guard: if the failed recipient IS the admin, don't notify (it'll just fail again).
    try:
        if to_email and str(to_email).strip().lower() == admin_email.strip().lower():
            logger.info("[email_failure_service] suppressing self-alert for admin address")
            return
    except Exception:
        pass

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subj_str = (subject or "(no subject)").strip()
    src_str = source or "unknown"
    err_str = (error_message or "").strip() or "(no message)"
    code_str = f" (code {error_code})" if error_code is not None else ""

    text = (
        f"Email delivery failure on ProReadyEngineer\n"
        f"=========================================\n\n"
        f"Time: {ts}\n"
        f"Recipient: {to_email}\n"
        f"Subject: {subj_str}\n"
        f"Source: {src_str}{code_str}\n"
        f"Error: {err_str}\n"
        f"Failure ID: {failure_id or '(not persisted)'}\n\n"
        f"Open the Debugging panel to review and resolve:\n"
        f"  {getattr(settings, 'FRONTEND_URL', '').rstrip('/')}/admin/debugging\n"
    )
    html = (
        "<div style=\"font-family:system-ui,sans-serif;font-size:14px;color:#111\">"
        "<h2 style=\"color:#b91c1c;margin:0 0 12px\">Email delivery failure</h2>"
        f"<p><strong>Time:</strong> {ts}<br>"
        f"<strong>Recipient:</strong> {to_email}<br>"
        f"<strong>Subject:</strong> {subj_str}<br>"
        f"<strong>Source:</strong> {src_str}{code_str}</p>"
        f"<p><strong>Error:</strong><br><code>{err_str}</code></p>"
        f"<p><strong>Failure ID:</strong> {failure_id or '(not persisted)'}</p>"
        f"<p><a href=\"{getattr(settings, 'FRONTEND_URL', '').rstrip('/')}/admin/debugging\" "
        "style=\"background:#dc2626;color:#fff;padding:8px 14px;border-radius:6px;"
        "text-decoration:none\">Open Debugging panel</a></p>"
        "</div>"
    )

    # Lazy import to avoid a circular import at module load.
    from app.services import email_service
    try:
        await email_service._send_email_now(
            to=[admin_email],
            subject=f"[ProReadyEngineer] Email failed: {to_email}",
            html_content=html,
            text_content=text,
            is_admin_alert=True,  # recursion guard — see _send_email_now
        )
    except Exception as exc:
        # Last resort: log only. Never recurse into record_email_failure.
        logger.exception("[email_failure_service] admin alert send failed: %s", exc)


async def unresolved_count(db: AsyncSession) -> int:
    """Return the count of unresolved email failures (used by the nav red dot)."""
    try:
        result = await db.execute(
            select(func.count(EmailFailure.id)).where(EmailFailure.resolved.is_(False))
        )
        return int(result.scalar() or 0)
    except Exception:
        return 0
