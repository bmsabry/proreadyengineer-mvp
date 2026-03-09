"""Pydantic schemas for API request/response validation."""

# Base schemas
from app.schemas.base import (
    BaseSchema,
    ResponseSchema,
    PagedResponse,
    TokenRefreshRequest,
)

# Auth schemas
from app.schemas.auth import (
    UserCreateRequest,
    UserLoginRequest,
    TokenPairResponse,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    EmailVerificationRequest,
)

# User schemas
from app.schemas.user import (
    UserResponse,
    UserUpdateRequest,
    UserProfileResponse,
)

# Provider schemas
from app.schemas.provider import (
    ProviderPublicResponse,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderResponse,
)

# Search schemas
from app.schemas.search import (
    SearchQueryRequest,
    LLMStructuredOutput,
    SearchResultItem,
    SearchQueryResponse,
    SearchResponse,
    SearchResult,
    DocumentUploadInitiateRequest,
    DocumentUploadInitiateResponse,
    DocumentUploadCompleteRequest,
    DocumentUploadCompleteResponse,
    SearchRequestLogResponse,
)

# RFQ schemas
from app.schemas.rfq import (
    RFQCreateRequest,
    RFQResponse,
    RFQFileUploadRequest,
    RFQFileResponse,
    RFQStatusResponse,
    RFQTeaserResponse,
    RFQUnlockRequest,
    RFQUnlockResponse,
    RFQDetailForProviderResponse,
)

# Quote schemas
from app.schemas.quote import (
    QuoteSubmitRequest,
    QuoteResponse,
    QuoteFileResponse,
)

# Payment schemas
from app.schemas.payment import (
    PaymentCheckoutRequest,
    PaymentCheckoutResponse,
    SubscriptionResponse,
    BillingPortalResponse,
)

# Advertising schemas
from app.schemas.advertising import (
    AdSlotResponse,
    AdCreateRequest,
    AdResponse,
    AdAssetUploadRequest,
    AdAssetUploadResponse,
)

# Admin schemas
from app.schemas.admin import (
    AdminProviderClaimResponse,
    AdminTierRequestResponse,
    AdminPaymentResponse,
    AdminWebhookResponse,
    AdminRFQResponse,
    AdminUserResponse,
)

# NDA schemas
from app.schemas.nda import (
    NDASigningRequest,
    NDASigningResponse,
    NDADocumentResponse,
)
