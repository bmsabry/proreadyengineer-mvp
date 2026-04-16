"""Search and discovery request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema
from app.schemas.provider import ProviderPublicResponse  # needed by SearchResult


class SearchQueryRequest(BaseSchema):
    """Natural language search query."""
    query: str = Field(..., min_length=3, max_length=2000)
    document_text: Optional[str] = None
    document_upload_id: Optional[UUID] = None
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)


class LLMStructuredOutput(BaseSchema):
    """LLM extraction output structure."""
    requires_engineering: int = Field(..., ge=0, le=1)
    requires_mechanical: int = Field(..., ge=0, le=1)
    software_mentioned: List[str] = Field(default_factory=list)
    inferred_specialty: Optional[str] = None
    capabilities_needed: List[str] = Field(default_factory=list)


class SearchResultItem(BaseSchema):
    """Individual search result with full scoring breakdown."""
    provider_id: int
    name: str
    firm_name: str
    tier: Optional[str] = None
    primary_specialty: Optional[str] = None
    score: int = Field(..., ge=0, le=100)
    explanation: str
    capabilities: Optional[List[str]] = None
    business_description: Optional[str] = None


class SearchQueryResponse(BaseSchema):
    """Full structured search results response."""
    search_id: UUID
    query: str
    structured_intent: Optional[LLMStructuredOutput] = None
    results: List[SearchResultItem]
    total_results: int
    fallback_reason: Optional[str] = None
    quota_used: int
    quota_remaining: int
    quota_reset_at: Optional[datetime] = None


class DocumentUploadInitiateRequest(BaseSchema):
    """Request presigned URL for document upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., gt=0, le=26214400)


class DocumentUploadInitiateResponse(BaseSchema):
    """Presigned upload URL response."""
    upload_id: UUID
    presigned_url: str
    s3_key: str
    expires_in_seconds: int


class DocumentUploadCompleteRequest(BaseSchema):
    """Confirm document upload and trigger extraction."""
    upload_id: UUID


class DocumentUploadCompleteResponse(BaseSchema):
    """Document extraction result."""
    upload_id: UUID
    original_filename: str
    extracted_text: Optional[str] = None
    extraction_status: str
    word_count: Optional[int] = None


class SearchRequestLogResponse(ResponseSchema):
    """Search request audit log entry."""
    id: UUID
    user_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    raw_query_text: str
    normalized_query_text: Optional[str] = None
    llm_structured_output: Optional[Dict[str, Any]] = None
    search_status: Optional[str] = None
    fallback_reason: Optional[str] = None
    results_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Endpoint-facing schemas used by app/api/endpoints/search.py
# ---------------------------------------------------------------------------

class SearchResult(BaseSchema):
    """Single provider search result returned by the /search/query endpoint."""
    provider: ProviderPublicResponse
    score: float
    explanation: str


class PipelineInfo(BaseSchema):
    """AI pipeline execution diagnostics - shown in search results debug panel."""
    pipeline_used: str = "unknown"  # 'ai_vector', 'keyword_fallback', 'no_api_key'
    llm_called: bool = False
    llm_response_received: bool = False
    llm_model: str = ""
    embedding_called: bool = False
    embedding_dims: int = 0
    api_key_source: str = "missing"  # 'database', 'env_var', 'missing'
    fallback_reason: Optional[str] = None
    inferred_specialty: Optional[str] = None
    inferred_keywords: Optional[List[str]] = None


class SearchResponse(BaseSchema):
    """Response envelope from the /search/query endpoint."""
    results: List[SearchResult]
    total_matches: int
    search_quota_remaining: int
    pipeline_info: Optional[PipelineInfo] = None


# ---------------------------------------------------------------------------
# Backward-compatibility aliases
# ---------------------------------------------------------------------------
SearchRequest = SearchQueryRequest
SearchQuery = SearchQueryRequest
ProviderMatch = SearchResultItem
