"""Pydantic schemas for API request/response validation."""

# Base schemas
from app.schemas.base import (
    BaseSchemaConfig,
    BaseSchema,
    IDSchema,
    TimestampSchema,
    ResponseSchema,
    PaginationParams,
    PaginatedResponse,
    PagedResponse,
    TokenRefreshRequest,
)

# Auth schemas
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenPairResponse,
    RefreshTokenRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    LogoutResponse,
    LoginResponse,
    RegisterResponse,
    AuthMeResponse,
)

# User schemas
from app.schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserRoleUpdateRequest,
    UserResponse,
    UserListResponse,
    UserSearchQuotaResponse,
)

# Provider schemas
from app.schemas.provider import (
    ProviderPublicResponse,
    ProviderSearchResult,
    ProviderClaimSearchRequest,
    ProviderClaimSearchResult,
    ProviderClaimCreateRequest,
    ProviderClaimResponse,
    ProviderMembershipCreateRequest,
    ProviderMembershipResponse,
    ProviderProfileCreateRequest,
    ProviderProfileUpdateRequest,
    ProviderProfileResponse,
    TierEvaluationCreateRequest,
    TierEvaluationResponse,
    TierEvaluationAdminResponse,
    ProviderUpdateRequest,
    ProviderClaimRequest,
    ProviderResponse,
)

# Search schemas
from app.schemas.search import (
    SearchQueryRequest,
    LLMStructuredOutput,
    SearchResultItem,
    SearchQueryResponse,
    DocumentUploadInitiateRequest,
    DocumentUploadInitiateResponse,
    DocumentUploadCompleteRequest,
    DocumentUploadCompleteResponse,
    SearchRequestLogResponse,
    SearchResult,
    SearchResponse,
)

# RFQ schemas
from app.schemas.rfq import (
    RFQCreateRequest,
    RFQUpdateRequest,
    RFQSubmitRequest,
    RFQResponse,
    RFQStatusResponse,
    RFQFileCreateRequest,
    RFQFileResponse,
    RFQFileUploadInitiateResponse,
    RFQMatchResponse,
    RFQDispatchBatchResponse,
    RFQDispatchResponse,
    RFQUnlockResponse,
    RFQUnlockStatusResponse,
    RFQTeaserResponse,
    RFQDetailForProviderResponse,
    RFQFileUploadInitiateRequest,
    RFQFileUploadCompleteRequest,
    RFQFileUploadResponse,
    RFQNDACheckoutRequest,
    RFQNDACheckoutResponse,
    RFQStatusOverrideRequest,
    RFQAdminResponse,
)

# Quote schemas
from app.schemas.quote import (
    QuoteCreateRequest,
    QuoteSubmitRequest,
    QuoteFileCreateRequest,
    QuoteFileResponse,
    QuoteProviderInfo,
    QuoteResponse,
    QuoteForCustomerResponse,
    QuoteForProviderResponse,
    QuoteListResponse,
    QuoteAcceptRequest,
    QuoteAcceptResponse,
    QuoteWithdrawRequest,
    QuoteWithdrawResponse,
)

# Payment schemas
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentResponse,
    PaymentCheckoutResponse,
    BillingPortalResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionListResponse,
    WebhookEventResponse,
    WebhookReplayRequest,
    WebhookReplayResponse,
    PaymentIntentResponse,
    PaymentAttemptResponse,
)

# Advertising schemas
from app.schemas.advertising import (
    AdSlotResponse,
    AdvertisementCreateRequest,
    AdvertisementUpdateRequest,
    AdvertisementResponse,
    AdvertisementPublicResponse,
    AdvertisementListResponse,
    AdAssetUploadInitiateRequest,
    AdAssetUploadInitiateResponse,
    AdAssetUploadCompleteRequest,
    AdAssetUploadCompleteResponse,
    SoftwareProvidersAdsResponse,
    FeaturedFirmsAdsResponse,
    AdCreateRequest,
    AdCheckoutRequest,
    AdCheckoutResponse,
    AdUpdateRequest,
)

# Admin schemas
from app.schemas.admin import (
    AdminRFQListParams,
    AdminRFQListItem,
    AdminRFQListResponse,
    AdminRFQDetailResponse,
    AdminRFQStatusOverrideRequest,
    AdminRFQStatusOverrideResponse,
    AdminProviderClaimListParams,
    AdminProviderClaimListItem,
    AdminProviderClaimListResponse,
    AdminProviderClaimDetailResponse,
    AdminProviderClaimApproveRequest,
    AdminProviderClaimApproveResponse,
    AdminProviderClaimRejectRequest,
    AdminProviderClaimRejectResponse,
    AdminTierRequestListParams,
    AdminTierRequestListItem,
    AdminTierRequestListResponse,
    AdminTierRequestDetailResponse,
    AdminTierRequestApproveRequest,
    AdminTierRequestApproveResponse,
    AdminTierRequestRejectRequest,
    AdminTierRequestRejectResponse,
    AdminPaymentListParams,
    AdminPaymentListItem,
    AdminPaymentListResponse,
    AdminWebhookListParams,
    AdminWebhookListItem,
    AdminWebhookListResponse,
    AdminWebhookDetailResponse,
    AdminWebhookReplayResponse,
    AdminAdListParams,
    AdminAdListItem,
    AdminAdListResponse,
    AdminAdPauseRequest,
    AdminAdPauseResponse,
    AdminUserSuspendRequest,
    AdminUserSuspendResponse,
    AdminAuditLogListParams,
    AdminAuditLogListItem,
    AdminAuditLogListResponse,
)

# NDA schemas
from app.schemas.nda import (
    NDACheckoutRequest,
    NDACheckoutResponse,
    NDAResponse,
    NDACustomerStatusResponse,
    NDAProviderStatusResponse,
    NDASigningCompleteRequest,
    NDASigningCompleteResponse,
)
