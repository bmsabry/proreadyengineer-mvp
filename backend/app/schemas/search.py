"""Search and discovery request and response schemas."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, ResponseSchema


class SearchQueryRequest(BaseSchema):
    """Natural language search query."""
    query: str = Field(..., min_length=3, max_length=2000)
    document_text: Optional[str] = None  # Extracted text from uploaded document
    document_upload_id: Optional[UUID] = None  # If user uploaded document


class LLMStructuredOutput(BaseSchema):
    """LLM extraction output structure."""
    requires_engineering: int = Field(..., ge=0, le=1)
    requires_mechanical: int = Field(..., ge=0, le=1)
    software_mentioned: list[str] = Field(default_factory=list)
    inferred_specialty: Optional[str] = None
    capabilities_needed: list[str] = Field(default_factory=list)


class SearchResultItem(BaseSchema):
    """Individual search result with scoring."""
    provider_id: int
    name: str
    firm_name: str
    tier: Optional[str]
    primary_specialty: Optional[str]
    score: int = Field(..., ge=0, le=100)  # Composite 0-100 score
    explanation: str  # Grounded explanation of match
    capabilities: Optional[list[str]]
    business_description: Optional[str]


class SearchQueryResponse(BaseSchema):
    """Search results response."""
    search_id: UUID
    query: str
    structured_intent: Optional[LLMStructuredOutput]
    results: list[SearchResultItem]
    total_results: int
    fallback_reason: Optional[str]  # If search used fallback logic
    quota_used: int
    quota_remaining: int
    quota_reset_at: Optional[datetime]


class DocumentUploadInitiateRequest(BaseSchema):
    """Request presigned URL for document upload."""
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., gt=0, le=26214400)  # 25MB max


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
    extracted_text: Optional[str]
    extraction_status: str  # processing, completed, failed
    word_count: Optional[int]


class SearchRequestLogResponse(ResponseSchema):
    """Search request audit log entry."""
    id: UUID
    user_id: Optional[UUID]
    ip_address: Optional[str]
    raw_query_text: str
    normalized_query_text: Optional[str]
    llm_structured_output: Optional[dict[str, Any]]
    search_status: Optional[str]
    fallback_reason: Optional[str]
    results_count: Optional[int]


# Aliases for endpoint compatibility
SearchRequest = SearchQueryRequest
SearchResponse = SearchQueryResponse
SearchResult = SearchResultItem


# Additional aliases for service compatibility
SearchQuery = SearchQueryRequest
ProviderMatch = SearchResultItem
