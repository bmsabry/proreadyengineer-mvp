"""AI Help Assistant endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, get_db, require_role
from app.core.rate_limiter import limiter
from app.models.help_chat import HelpChatLog
from app.models.user import User
from app.services.help_service import answer_question, user_has_chatbot_access

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatAttachment(BaseModel):
    key: str = Field(..., max_length=512)
    filename: Optional[str] = Field(None, max_length=255)
    mime: Optional[str] = Field(None, max_length=100)
    size_bytes: Optional[int] = None
    excerpt: Optional[str] = Field(None, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatTurn] = Field(default_factory=list)
    page: Optional[str] = Field(None, max_length=200)  # current page path for context-awareness
    attachments: List[ChatAttachment] = Field(default_factory=list)  # staged /help/upload docs


class ChatResponse(BaseModel):
    reply: str
    error: Optional[str] = None
    remaining_today: Optional[int] = None
    links: Optional[List[Dict[str, str]]] = None  # in-app navigation buttons
    action: Optional[Dict[str, Any]] = None       # a confirm-then-execute proposal (inert)
    action_result: Optional[Dict[str, Any]] = None  # result of an auto-executed action (autonomous mode)
    log_id: Optional[str] = None                    # id of this turn's log row, for feedback


class ActionRequest(BaseModel):
    type: str = Field(..., max_length=64)
    quote_id: Optional[str] = Field(None, max_length=64)
    rfq_id: Optional[str] = Field(None, max_length=64)
    attachments: List["ChatAttachment"] = Field(default_factory=list)
    project_description: Optional[str] = Field(None, max_length=10000)
    ticket_id: Optional[str] = Field(None, max_length=64)
    page: Optional[str] = Field(None, max_length=200)


class ActionResponse(BaseModel):
    ok: bool
    message: str
    link: Optional[Dict[str, str]] = None  # optional in-app link (e.g. review the created RFQ)


# The ONLY actions the assistant may execute. All are reversible, non-financial,
# non-signature, non-destructive, and re-authorized server-side. Anything else is
# navigation-only (Phase 3). Adding to this set is a deliberate security decision.
_EXECUTABLE_ACTIONS = {"mark_contacted", "undo_mark_contacted"}


class StatusResponse(BaseModel):
    authenticated: bool
    has_access: bool
    reason: str
    remaining_today: Optional[int] = None
    daily_limit: int


class ManualResponse(BaseModel):
    markdown: str


DAILY_MESSAGE_LIMIT = 50


async def _messages_used_today(db: AsyncSession, user_id) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(func.count(HelpChatLog.id)).where(
            HelpChatLog.user_id == user_id,
            HelpChatLog.created_at >= since,
            HelpChatLog.error.is_(None),
        )
    )
    return int(result.scalar() or 0)


@router.get("/help/status", response_model=StatusResponse)
async def help_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    has_access, reason = await user_has_chatbot_access(db, current_user)
    remaining: Optional[int] = None
    if has_access and current_user is not None:
        used = await _messages_used_today(db, current_user.id)
        remaining = max(0, DAILY_MESSAGE_LIMIT - used)
    return StatusResponse(
        authenticated=current_user is not None,
        has_access=has_access,
        reason=reason,
        remaining_today=remaining,
        daily_limit=DAILY_MESSAGE_LIMIT,
    )


@router.get("/help/manual", response_model=ManualResponse)
async def help_manual():
    from app.services.help_service import _load_manual
    return ManualResponse(markdown=_load_manual())


@limiter.limit("20/minute")
@router.post("/help/chat", response_model=ChatResponse)
async def help_chat(
    request: Request,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    has_access, reason = await user_has_chatbot_access(db, current_user)
    if not has_access:
        detail = {
            "reason": reason,
            "message": (
                "The AI Help Assistant is available to subscribers only. "
                "Subscribe to a customer Search plan or a provider Profile/Annual plan to unlock it."
            )
            if reason == "no_active_subscription"
            else "Please sign in to use the AI Help Assistant.",
        }
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)

    used_today = 0
    if current_user is not None and "admin" not in set(current_user.roles or []):
        used_today = await _messages_used_today(db, current_user.id)
        if used_today >= DAILY_MESSAGE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "reason": "daily_limit_reached",
                    "message": (
                        f"You've used your {DAILY_MESSAGE_LIMIT} help messages for today. "
                        "Please try again tomorrow or browse the full help page."
                    ),
                },
            )

    history_dicts = [t.model_dump() for t in data.history]
    result = await answer_question(
        db=db,
        user=current_user,
        history=history_dicts,
        user_message=data.message,
        page=(data.page or None),
        attachments=[a.model_dump() for a in (data.attachments or [])],
    )

    _log_id = None
    try:
        log = HelpChatLog(
            user_id=current_user.id if current_user else None,
            user_role=",".join(current_user.roles or []) if current_user else None,
            user_email=current_user.email if current_user else None,
            user_message=data.message[:2000],
            assistant_reply=(result.get("reply") or "")[:8000],
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            model=(result.get("model") or "")[:128] or None,
            error=(result.get("error") or None),
            latency_ms=result.get("latency_ms"),
            cost_usd=result.get("cost_usd"),
        )
        db.add(log)
        await db.commit()
        _log_id = str(log.id)
    except Exception as exc:
        logger.warning("[help_chat] Could not persist log: %s", exc)
        await db.rollback()
        _log_id = None

    remaining = None
    if current_user is not None and "admin" not in set(current_user.roles or []):
        remaining = max(0, DAILY_MESSAGE_LIMIT - used_today - 1)

    return ChatResponse(
        reply=result.get("reply") or "Sorry - I couldn't produce an answer just now. Please try again.",
        error=result.get("error"),
        remaining_today=remaining,
        links=result.get("links") or None,
        action=result.get("action") or None,
        action_result=result.get("action_result") or None,
        log_id=_log_id,
    )


_ASSIST_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
_ASSIST_UPLOAD_EXTS = ("pdf", "docx", "txt")


def assistant_upload_prefix(user_id) -> str:
    return f"assistant-uploads/{user_id}/"


@limiter.limit("30/minute")
@router.post("/help/upload")
async def help_upload(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Stage a document the user wants the assistant to work with.

    Stores it in S3 under assistant-uploads/<user_id>/ (so ownership is provable by
    key prefix), extracts text, and returns {key, filename, mime, excerpt, chars}. The
    file is just staged here; it is only attached to an RFQ/quote when the user asks the
    assistant to run that workflow and (if not autonomous) confirms.
    """
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    has_access, _ = await user_has_chatbot_access(db, current_user)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Uploads require an active subscription.")

    filename = (file.filename or "upload").strip()
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in _ASSIST_UPLOAD_EXTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF, DOCX, and TXT files are supported.")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")
    if len(file_bytes) > _ASSIST_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Maximum 10MB.")

    # Extract text (best-effort; extraction failure must not block staging).
    import io as _io
    doc_text = ""
    try:
        if ext == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(_io.BytesIO(file_bytes))
            doc_text = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif ext == "docx":
            from docx import Document as _Docx
            d = _Docx(_io.BytesIO(file_bytes))
            parts = [p.text for p in d.paragraphs if p.text]
            for t in d.tables:
                for row in t.rows:
                    for cell in row.cells:
                        if cell.text:
                            parts.append(cell.text)
            doc_text = "\n".join(parts)
        else:
            doc_text = file_bytes.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.info("[help_upload] text extraction failed: %s", exc)
        doc_text = ""

    import uuid as _uuid
    import mimetypes as _mt
    mime = _mt.guess_type(filename)[0] or "application/octet-stream"
    key = assistant_upload_prefix(current_user.id) + f"{_uuid.uuid4()}/{filename}"
    try:
        from app.services.config_service import get_runtime_config
        from app.services.file_service import upload_bytes_to_s3_from_config
        cfg = await get_runtime_config(db)
        upload_bytes_to_s3_from_config(key, file_bytes, cfg, content_type=mime)
    except Exception as exc:
        logger.warning("[help_upload] S3 upload failed: %s", exc)
        # Without S3 we cannot attach the file to a workflow; surface a clean error.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not store the file right now. Please try again.")

    excerpt = (doc_text or "").strip()[:1500]
    return {
        "key": key,
        "filename": filename,
        "mime": mime,
        "size_bytes": len(file_bytes),
        "chars": len(doc_text or ""),
        "excerpt": excerpt,
    }


class AgentEnableRequest(BaseModel):
    accept_risk: bool = False


class AgentStatusResponse(BaseModel):
    autonomous_enabled: bool
    consented_at: Optional[str] = None


@router.get("/help/agent/status", response_model=AgentStatusResponse)
async def agent_status(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user is None:
        return AgentStatusResponse(autonomous_enabled=False)
    ts = getattr(current_user, "agent_autonomous_consented_at", None)
    return AgentStatusResponse(
        autonomous_enabled=bool(getattr(current_user, "agent_autonomous_enabled", False)),
        consented_at=ts.isoformat() if ts else None,
    )


@router.post("/help/agent/enable", response_model=AgentStatusResponse)
async def agent_enable(
    data: AgentEnableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Turn ON autonomous mode. Requires explicit risk acceptance in the body."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    has_access, _ = await user_has_chatbot_access(db, current_user)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Autonomous mode requires an active subscription.")
    if not data.accept_risk:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You must accept the risk to enable autonomous mode.")
    from datetime import datetime, timezone
    current_user.agent_autonomous_enabled = True
    current_user.agent_autonomous_consented_at = datetime.now(timezone.utc)
    db.add(current_user)
    await db.commit()
    try:
        from app.models.admin import AuditLog
        db.add(AuditLog(actor_user_id=current_user.id, entity_type="user", entity_id=str(current_user.id),
                        action="agent_autonomous_enabled", extra_data={"via": "help_assistant"}))
        await db.commit()
    except Exception:
        await db.rollback()
    return AgentStatusResponse(autonomous_enabled=True,
                               consented_at=current_user.agent_autonomous_consented_at.isoformat())


@router.post("/help/agent/disable", response_model=AgentStatusResponse)
async def agent_disable(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """HARD STOP — instantly turns OFF autonomous mode. Idempotent."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    current_user.agent_autonomous_enabled = False
    db.add(current_user)
    await db.commit()
    try:
        from app.models.admin import AuditLog
        db.add(AuditLog(actor_user_id=current_user.id, entity_type="user", entity_id=str(current_user.id),
                        action="agent_autonomous_disabled", extra_data={"via": "help_assistant_hard_stop"}))
        await db.commit()
    except Exception:
        await db.rollback()
    return AgentStatusResponse(autonomous_enabled=False)


@limiter.limit("20/minute")
@router.post("/help/action", response_model=ActionResponse)
async def help_action(
    request: Request,
    data: ActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Execute a confirm-then-execute assistant action.

    SECURITY: this is the ONLY path that performs a write on the assistant's behalf,
    and it is the source of truth for authorization. It (1) requires an authenticated
    user, (2) only allows the tiny `_EXECUTABLE_ACTIONS` allowlist of reversible,
    non-financial actions, (3) re-checks resource ownership inside the executor, and
    (4) audit-logs the result. The LLM can only *propose* an action; nothing runs until
    the user explicitly confirms, which is what calls this endpoint.
    """
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    has_access, _reason = await user_has_chatbot_access(db, current_user)
    if not has_access:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Assistant actions require an active subscription.")

    from app.services.help_actions import execute_action
    # Autonomous flag is read FRESH from the DB row so a hard-stop takes effect immediately.
    autonomous = bool(getattr(current_user, "agent_autonomous_enabled", False))
    _ticket_id = data.ticket_id
    if not _ticket_id and data.page:
        import re as _re
        _m = _re.search(r"/admin/support/([0-9a-fA-F-]{8,})", data.page)
        _ticket_id = _m.group(1) if _m else None
    params = {
        "quote_id": data.quote_id,
        "rfq_id": data.rfq_id,
        "attachments": [a.model_dump() for a in (data.attachments or [])],
        "project_description": data.project_description,
        "ticket_id": _ticket_id,
    }
    result = await execute_action(db, current_user, (data.type or "").strip(), params, autonomous)
    return ActionResponse(ok=bool(result.get("ok")), message=result.get("message") or "Done.", link=result.get("link"))


class FeedbackRequest(BaseModel):
    log_id: str = Field(..., max_length=64)
    rating: int = Field(..., ge=-1, le=1)  # 1 up, -1 down (0 clears)


@limiter.limit("60/minute")
@router.post("/help/feedback")
async def help_feedback(
    request: Request,
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Record a thumbs up/down on one assistant turn. Ownership-checked: a user may
    only rate their OWN chat log rows. Idempotent (re-rating overwrites)."""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    import uuid as _uuid
    try:
        lid = _uuid.UUID(str(data.log_id))
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid log id")
    row = (await db.execute(
        select(HelpChatLog).where(HelpChatLog.id == lid, HelpChatLog.user_id == current_user.id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    row.feedback = data.rating if data.rating in (1, -1) else None
    await db.commit()
    return {"ok": True, "log_id": str(lid), "feedback": row.feedback}


@router.get("/admin/help/logs")
async def admin_help_logs(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    rows = (await db.execute(
        select(HelpChatLog).order_by(HelpChatLog.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    total = int((await db.execute(select(func.count(HelpChatLog.id)))).scalar() or 0)
    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": str(r.user_id) if r.user_id else None,
                "user_email": r.user_email,
                "user_role": r.user_role,
                "user_message": r.user_message,
                "assistant_reply": r.assistant_reply,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "error": r.error,
                "latency_ms": r.latency_ms,
                "feedback": getattr(r, "feedback", None),
                "cost_usd": getattr(r, "cost_usd", None),
            }
            for r in rows
        ],
    }
