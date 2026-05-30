"""AI Help Assistant endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str
    error: Optional[str] = None
    remaining_today: Optional[int] = None


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
    )

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
    except Exception as exc:
        logger.warning("[help_chat] Could not persist log: %s", exc)
        await db.rollback()

    remaining = None
    if current_user is not None and "admin" not in set(current_user.roles or []):
        remaining = max(0, DAILY_MESSAGE_LIMIT - used_today - 1)

    return ChatResponse(
        reply=result.get("reply") or "Sorry - I couldn't produce an answer just now. Please try again.",
        error=result.get("error"),
        remaining_today=remaining,
    )


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
            }
            for r in rows
        ],
    }
