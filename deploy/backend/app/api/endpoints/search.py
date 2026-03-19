"""Search API endpoints - production-hardened.

FIX LOG:
  BUG-1: Quota check try/except raised HTTPException(500) on ANY exception.
         FIX -> Non-fatal: log error, continue with default (True, 10).
  BUG-2: ProviderPublicResponse.model_validate() inside unprotected list
         comprehension crashed entire response on one bad provider row.
         FIX -> _safe_validate_provider() helper skips invalid rows.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import UploadFile, File, APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user_optional, get_db
from app.core.config import settings
from app.models.provider import Provider
from app.models.search import SearchRequest as SearchRequestModel
from app.models.user import User
from app.schemas.provider import ProviderPublicResponse
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.file_service import generate_upload_url
from app.services.search_service import (
    check_search_quota,
    increment_search_quota,
    search_providers,
)

router = APIRouter(prefix="/search")
logger = logging.getLogger(__name__)

# In-memory debug store (lightweight, resets on restart)
_last_search_error: dict = {"error": None, "timestamp": None, "query": None}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_validate_provider(provider) -> Optional[ProviderPublicResponse]:
    """Validate one provider against ProviderPublicResponse.

    Returns None instead of raising so that one bad migrated row never kills
    the entire search response (BUG-2 fix).
    """
    try:
        return ProviderPublicResponse.model_validate(provider)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[SEARCH] Skipping provider id=%s - model_validate failed: %s",
            getattr(provider, 'id', '?'),
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Diagnostic / smoke-test endpoints
# ---------------------------------------------------------------------------

@router.get("/test")
async def search_test():
    """Smoke-test: confirms router is mounted and responding."""
    return {"status": "ok", "message": "Search router is working"}


@router.post("/test-db")
async def search_test_db(db: AsyncSession = Depends(get_db)):
    """Verify database connectivity and return provider count."""
    try:
        result = await db.execute(select(func.count()).select_from(Provider))
        count = result.scalar()
        return {"status": "ok", "provider_count": count}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}


@router.get("/debug")
async def search_debug(db: AsyncSession = Depends(get_db)):
    """System diagnostics for Render troubleshooting."""
    logger.info("[SEARCH DEBUG] Debug endpoint called")

    info: dict = {
        "timestamp": datetime.utcnow().isoformat(),
        "database": {
            "connection_ok": False,
            "provider_count": 0,
            "providers_with_embeddings": 0,
            "embedding_coverage_pct": 0.0,
            "sample_provider": None,
        },
        "api_config": {},
        "last_error": _last_search_error if _last_search_error.get("error") is not None else None,
    }

    try:
        result = await db.execute(select(func.count()).select_from(Provider))
        total = result.scalar() or 0
        info["database"]["provider_count"] = total

        result = await db.execute(
            select(func.count()).select_from(Provider).where(Provider.embedding.isnot(None))
        )
        with_emb = result.scalar() or 0
        info["database"]["providers_with_embeddings"] = with_emb
        info["database"]["embedding_coverage_pct"] = round((with_emb / total * 100) if total > 0 else 0.0, 1)

        result = await db.execute(select(Provider).limit(1))
        sample = result.scalar_one_or_none()
        if sample:
            emb_status = "with embedding" if sample.embedding is not None else "no embedding"
            info["database"]["sample_provider"] = f"{sample.name} (id={sample.id}, {emb_status})"
        info["database"]["connection_ok"] = True
    except Exception as exc:  # noqa: BLE001
        logger.error("[SEARCH DEBUG] DB check failed: %s", exc)
        info["database"]["connection_ok"] = False
        info["database"]["error"] = str(exc)

    # Read live config from DB so admin settings changes are reflected immediately
    try:
        from app.services.config_service import get_runtime_config as _get_runtime_config
        cfg = await _get_runtime_config(db)
        api_key = cfg.get("DEEPINFRA_API_KEY") or cfg.get("OPENAI_API_KEY") or settings.OPENAI_API_KEY or ""
        info["api_config"]["openai_configured"] = bool(
            api_key and api_key.strip() not in ("dummy-key", "your-key-here", "none", "null", "")
        )
        info["api_config"]["openai_base_url"] = cfg.get("OPENAI_API_BASE") or settings.OPENAI_API_BASE or None
        info["api_config"]["embedding_model"] = cfg.get("OPENAI_EMBEDDING_MODEL") or settings.OPENAI_EMBEDDING_MODEL
        info["api_config"]["llm_model"] = cfg.get("OPENAI_LLM_MODEL") or settings.OPENAI_LLM_MODEL
    except Exception:
        # Fallback to settings if DB read fails
        info["api_config"]["openai_configured"] = bool(
            settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("dummy-key", "")
        )
        info["api_config"]["openai_base_url"] = settings.OPENAI_API_BASE or None
        info["api_config"]["embedding_model"] = settings.OPENAI_EMBEDDING_MODEL
        info["api_config"]["llm_model"] = settings.OPENAI_LLM_MODEL

    return info


@router.post("/test-quota")
async def test_quota_debug(request: Request, db: AsyncSession = Depends(get_db)):
    """Debug: exercise quota check and return full diagnostics."""
    import traceback
    from sqlalchemy import inspect, text
    from app.services import search_service

    results: dict = {"status": "testing", "tests": {}}

    try:
        inspector = inspect(User)
        columns = [c.name for c in inspector.columns]
        results["tests"]["user_columns"] = {
            "success": True,
            "columns": columns,
            "has_monthly_search_count": "monthly_search_count" in columns,
            "has_search_count_reset_at": "search_count_reset_at" in columns,
        }
    except Exception as exc:
        results["tests"]["user_columns"] = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    try:
        client_ip = get_client_ip(request)
        has_quota, remaining = await search_service.check_search_quota(
            db=db, user=None, ip_address=client_ip
        )
        results["tests"]["quota_check"] = {
            "success": True, "has_quota": has_quota, "remaining": remaining
        }
    except Exception as exc:
        results["tests"]["quota_check"] = {
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    try:
        from sqlalchemy import text
        row = (await db.execute(text("SELECT 1 AS test"))).first()
        results["tests"]["db_connection"] = {"success": True, "result": row.test if row else None}
    except Exception as exc:
        results["tests"]["db_connection"] = {
            "success": False, "error": str(exc), "traceback": traceback.format_exc()
        }

    return results


# ---------------------------------------------------------------------------
# Primary search endpoint
# ---------------------------------------------------------------------------

@router.post("/query", response_model=SearchResponse)
async def search_query(
    request: Request,
    data: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Search providers with natural language query."""
    global _last_search_error

    user_id = current_user.id if current_user else None
    ip = get_client_ip(request)

    logger.info(
        "[SEARCH] Query received: user_id=%s ip=%s query='%s'",
        user_id, ip, data.query[:120],
    )

    # -----------------------------------------------------------------------
    # Step 1: Quota check - ALWAYS NON-FATAL (BUG-1 fix)
    # check_search_quota already catches internally, but we add an outer net
    # so unexpected framework errors (e.g. missing column) never block search.
    # -----------------------------------------------------------------------
    can_search: bool = True
    remaining: int = 10
    try:
        quota_result = await check_search_quota(db, user_id=user_id, ip_address=ip)
        can_search = quota_result.get("allowed", True) if isinstance(quota_result, dict) else bool(quota_result)
        remaining = quota_result.get("remaining", 10) if isinstance(quota_result, dict) else 10
        logger.info("[SEARCH] Quota: can_search=%s remaining=%s", can_search, remaining)
    except Exception as exc:  # noqa: BLE001
        # NON-FATAL: allow search to proceed with generous defaults
        logger.error(
            "[SEARCH] Quota check raised unexpectedly (non-fatal, allowing search): %s",
            exc,
            exc_info=True,
        )
        can_search, remaining = True, 10

    if not can_search:
        logger.warning("[SEARCH] Quota exceeded for user_id=%s ip=%s", user_id, ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Search quota exceeded. Please upgrade your plan.",
        )

    # -----------------------------------------------------------------------
    # Step 2: Execute search
    # -----------------------------------------------------------------------
    pipeline_info = {'pipeline_used': 'error', 'llm_called': False, 'llm_response_received': False,
                     'llm_model': '', 'embedding_called': False, 'embedding_dims': 0,
                     'api_key_source': 'missing', 'fallback_reason': None,
                     'inferred_specialty': None, 'inferred_keywords': []}
    try:
        results, pipeline_info = await search_providers(
            db,
            query=data.query,
            filters=data.filters or {},
            limit=50,
        )
        logger.info("[SEARCH] Search completed: %d results pipeline=%s", len(results), pipeline_info.get('pipeline_used'))

        # -------------------------------------------------------------------
        # Step 3: Increment quota AFTER successful search - NON-FATAL
        # -------------------------------------------------------------------
        try:
            await increment_search_quota(db, user_id=user_id, ip_address=ip)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[SEARCH] Failed to increment quota (non-fatal): %s", exc, exc_info=True
            )

        # -------------------------------------------------------------------
        # Step 3b: Log search request to DB for analytics - NON-FATAL
        # -------------------------------------------------------------------
        try:
            import uuid as _uuid
            sr = SearchRequestModel(
                id=_uuid.uuid4(),
                user_id=user_id,
                ip_address=ip,
                raw_query_text=data.query,
                normalized_query_text=pipeline_info.get("inferred_specialty") or data.query,
                llm_structured_output=pipeline_info.get("llm_structured_output") if isinstance(pipeline_info, dict) else None,
                embedding_model=pipeline_info.get("embedding_model") if isinstance(pipeline_info, dict) else None,
                llm_model=pipeline_info.get("llm_model") if isinstance(pipeline_info, dict) else None,
                search_status=pipeline_info.get("pipeline_used") if isinstance(pipeline_info, dict) else "completed",
                fallback_reason=pipeline_info.get("fallback_reason") if isinstance(pipeline_info, dict) else None,
                results_count=len(results),
            )
            db.add(sr)
            await db.commit()
            logger.info("[SEARCH] Logged search request id=%s", sr.id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[SEARCH] Failed to log search request (non-fatal): %s", exc, exc_info=True
            )
            try:
                await db.rollback()
            except Exception:
                pass

        # -------------------------------------------------------------------
        # Step 4: Build response - validate each provider individually (BUG-2)
        # One bad row is skipped; the rest are returned normally.
        # -------------------------------------------------------------------
        safe_results: List[SearchResult] = []
        for r in results[:5]:
            validated = _safe_validate_provider(r.provider)
            if validated is None:
                continue
            safe_results.append(
                SearchResult(
                    provider=validated,
                    score=r.score,
                    explanation=r.explanation,
                )
            )

        _last_search_error = {"error": None, "timestamp": None, "query": data.query}

        logger.info("[SEARCH] Returning %d validated results", len(safe_results))
        from app.schemas.search import PipelineInfo
        pi = PipelineInfo(**pipeline_info) if pipeline_info else None
        return SearchResponse(
            results=safe_results,
            total_matches=len(results),
            search_quota_remaining=max(0, remaining - 1),
            pipeline_info=pi,
        )

    except HTTPException:
        raise
    except Exception as exc:
        error_msg = str(exc)
        logger.error("[SEARCH] Search failed: %s", error_msg, exc_info=True)
        _last_search_error = {
            "error": error_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "query": data.query,
        }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {error_msg}",
        )



# ---------------------------------------------------------------------------
# Document extract-and-describe endpoint (direct file upload, no S3 needed)
# ---------------------------------------------------------------------------

@router.post("/extract-and-describe")
async def extract_and_describe(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Extract text from uploaded document and use LLM to generate a search query."""
    import io as _io

    filename = file.filename or ""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    allowed_exts = {"pdf", "docx", "doc", "txt", "md"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type .{ext}. Please upload PDF, DOCX, or TXT.",
        )

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    if len(content) > 26_214_400:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum 25 MB.",
        )

    # Extract text in-memory
    extracted_text = ""
    try:
        if ext == "pdf":
            import pypdf as PyPDF2
            reader = PyPDF2.PdfReader(_io.BytesIO(content))
            parts = []
            for page in reader.pages:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
            extracted_text = "\n".join(parts)
        elif ext == "docx":
            from docx import Document as DocxDoc
            doc = DocxDoc(_io.BytesIO(content))
            parts = [p.text for p in doc.paragraphs if p.text.strip()]
            extracted_text = "\n".join(parts)
        else:
            extracted_text = content.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")

    if not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted. Ensure the document contains readable text.",
        )

    text_for_llm = extracted_text

    # Use LLM to generate concise search description
    # Priority: LLM3 (Document Collapse) -> LLM2 (Firm Ranking) -> raw text fallback
    ai_query = ""
    try:
        from app.services.config_service import get_runtime_config as _get_runtime_config
        from openai import AsyncOpenAI
        config = await _get_runtime_config(db)

        # Use LLM3 (Document Collapse) keys first; fall back to LLM2 if not configured
        doc_api_key = config.get("DOC_LLM_API_KEY") or ""
        if doc_api_key:
            llm_api_key = doc_api_key
            llm_base_url = config.get("DOC_LLM_API_BASE") or "https://api.openai.com/v1"
            llm_model = config.get("DOC_LLM_MODEL") or "gpt-4o-mini"
            logger.info("[DOC_LLM] Using LLM3 (Document Collapse) for document summarization")
        else:
            llm_api_key = config.get("OPENAI_API_KEY") or ""
            llm_base_url = config.get("OPENAI_API_BASE") or "https://api.deepinfra.com/v1/openai"
            llm_model = config.get("OPENAI_LLM_MODEL") or "moonshotai/Kimi-K2.5"
            logger.info("[DOC_LLM] LLM3 not configured, falling back to LLM2 (Firm Ranking) for document summarization")

        if not llm_api_key:
            logger.warning("[DOC_LLM] No API key configured for document summarization, will use raw text fallback")
            raise ValueError("No LLM API key configured")

        client = AsyncOpenAI(api_key=llm_api_key, base_url=llm_base_url)
        system_prompt = (
            "You are an engineering project analyst. A customer uploaded a mechanical engineering "
            "scope of work document. Extract and summarize in 2-4 concise technical sentences "
            "suitable as a search query for finding an engineering service provider. "
            "Cover: (1) analysis type such as CFD, FEA, thermal, structural, or fatigue analysis; "
            "(2) the application or system being analyzed; "
            "(3) preparatory work required such as CAD modeling, meshing, or test setup; "
            "(4) applicable compliance standards such as ASME, MIL-SPEC, FAA, or API. "
            "Be specific and technical. Do not include company names or prices."
        )
        response = await client.chat.completions.create(
            model=llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Document:\n\n{text_for_llm}\n\nSearch query:"},
            ],
            
            temperature=0.3,
        )
        msg = response.choices[0].message
        ai_query = (msg.content or "").strip()
        if not ai_query and hasattr(msg, "reasoning_content"):
            ai_query = (getattr(msg, "reasoning_content", "") or "").strip()
        logger.info(f"[DOC_LLM] Document summarization successful, query length: {len(ai_query)}")
    except Exception as e:
        logger.warning(f"[DOC_LLM] LLM summarization failed: {e}. Will use raw text fallback.")

    # Fallback: use beginning of extracted text
    if not ai_query:
        ai_query = extracted_text.strip()

    return {
        "query": ai_query,
        "extracted_text_preview": extracted_text[:500],
        "filename": filename,
    }



# ---------------------------------------------------------------------------
# File upload endpoints
# ---------------------------------------------------------------------------

@router.post("/upload/initiate")
async def upload_initiate(
    filename: str,
    content_type: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Get presigned URL for document upload."""
    import uuid
    key = f"search-uploads/{current_user.id if current_user else 'anon'}/{uuid.uuid4()}/{filename}"
    url_data = generate_upload_url(key, content_type)
    return {"upload_url": url_data["url"], "fields": url_data.get("fields", {}), "key": key}


@router.post("/upload/complete")
async def upload_complete(
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """Process uploaded document for search."""
    from app.services.file_service import extract_document_text
    try:
        text = await extract_document_text(key)
        return {"extracted_text": text[:5000], "key": key}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process document: {exc}",
        )


# ---------------------------------------------------------------------------
# Public provider endpoint
# ---------------------------------------------------------------------------

@router.get("/providers/{provider_id}/public", response_model=ProviderPublicResponse)
async def get_provider_public(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get public provider profile."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return ProviderPublicResponse.model_validate(provider)
