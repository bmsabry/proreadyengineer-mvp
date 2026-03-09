"""Business logic services for the ProReadyEngineer MVP.

This module contains all business logic services that power the API endpoints.
Each service is designed to be testable, idempotent where required, and
handles complex operations with proper error handling.

Services:
    auth_service: Authentication, JWT tokens, password management
    search_service: Provider search with embeddings and ranking
    rfq_service: RFQ lifecycle management with concurrency-safe unlocks
    payment_service: Stripe/PayPal payments with webhook fulfillment
    file_service: S3 file operations and document extraction
    email_service: Transactional email queue management
"""

# Auth Service
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    create_refresh_token_record,
    decode_token,
    hash_password,
    register_user,
    reset_password,
    revoke_all_user_tokens,
    rotate_refresh_token,
    verify_password,
    verify_password_reset_token,
)

# Search Service
from app.services.search_service import (
    calculate_match_score,
    check_search_quota,
    extract_structured_intent,
    generate_embedding,
    increment_search_quota,
)

# RFQ Service
from app.services.rfq_service import (
    accept_quote,
    can_submit_quote,
    check_rfq_nda_status,
    complete_rfq_unlock,
    create_customer_nda,
    create_dispatch_batch,
    create_rfq,
    dispatch_teaser_batch,
    get_provider_unlocked_rfq_files,
    get_rfq,
    get_rfq_matches,
    submit_quote,
    submit_rfq,
    unlock_rfq,
)

# Payment Service
from app.services.payment_service import (
    cancel_subscription,
    create_payment_intent,
    create_stripe_billing_portal_session,
    create_subscription,
    fulfill_payment_purpose,
    handle_paypal_webhook,
    handle_stripe_webhook,
)

# File Service
from app.services.file_service import (
    check_file_exists,
    delete_file,
    extract_document_text,
    generate_download_url,
    generate_unique_key,
    generate_upload_url,
    get_mime_type,
    validate_file_type,
)

# Email Service
from app.services.email_service import (
    send_email,
    send_nda_ready_email,
    send_password_reset_email,
    send_provider_claim_approved_email,
    send_quote_accepted_notification,
    send_quote_notification,
    send_subscription_confirmation,
    send_teaser_email,
    send_tier_evaluation_result_email,
    send_welcome_email,
)

__all__ = [
    # Auth
    "authenticate_user",
    "create_access_token",
    "create_password_reset_token",
    "create_refresh_token",
    "create_refresh_token_record",
    "decode_token",
    "hash_password",
    "register_user",
    "reset_password",
    "revoke_all_user_tokens",
    "rotate_refresh_token",
    "verify_password",
    "verify_password_reset_token",
    # Search
    "calculate_match_score",
    "check_search_quota",
    "extract_structured_intent",
    "generate_embedding",
    "increment_search_quota",
    # RFQ
    "accept_quote",
    "can_submit_quote",
    "check_rfq_nda_status",
    "complete_rfq_unlock",
    "create_customer_nda",
    "create_dispatch_batch",
    "create_rfq",
    "dispatch_teaser_batch",
    "get_provider_unlocked_rfq_files",
    "get_rfq",
    "get_rfq_matches",
    "submit_quote",
    "submit_rfq",
    "unlock_rfq",
    # Payment
    "cancel_subscription",
    "create_payment_intent",
    "create_stripe_billing_portal_session",
    "create_subscription",
    "fulfill_payment_purpose",
    "handle_paypal_webhook",
    "handle_stripe_webhook",
    # File
    "check_file_exists",
    "delete_file",
    "extract_document_text",
    "generate_download_url",
    "generate_unique_key",
    "generate_upload_url",
    "get_mime_type",
    "validate_file_type",
    # Email
    "send_email",
    "send_nda_ready_email",
    "send_password_reset_email",
    "send_provider_claim_approved_email",
    "send_quote_accepted_notification",
    "send_quote_notification",
    "send_subscription_confirmation",
    "send_teaser_email",
    "send_tier_evaluation_result_email",
    "send_welcome_email",
]
