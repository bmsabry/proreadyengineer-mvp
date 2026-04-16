#!/bin/bash
# Manual API Testing Script for ProReadyEngineer Backend
# Usage: ./test_api_curl.sh [command] [args]

set -e

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
API_PREFIX="/api/v1"
ACCESS_TOKEN=""
REFRESH_TOKEN=""
OUTPUT_FORMAT="json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# API request helpers
api_get() {
    local endpoint="$1"
    curl -s -X GET "${BASE_URL}${API_PREFIX}${endpoint}" \
        -H "Accept: application/json" \
        ${ACCESS_TOKEN:+-H "Authorization: Bearer $ACCESS_TOKEN"} \
        -w "\n%{http_code}"
}

api_post() {
    local endpoint="$1"
    local data="$2"
    curl -s -X POST "${BASE_URL}${API_PREFIX}${endpoint}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        ${ACCESS_TOKEN:+-H "Authorization: Bearer $ACCESS_TOKEN"} \
        -d "$data" \
        -w "\n%{http_code}"
}

api_patch() {
    local endpoint="$1"
    local data="$2"
    curl -s -X PATCH "${BASE_URL}${API_PREFIX}${endpoint}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        ${ACCESS_TOKEN:+-H "Authorization: Bearer $ACCESS_TOKEN"} \
        -d "$data" \
        -w "\n%{http_code}"
}

# Auth Commands
cmd_register() {
    log_info "Registering new user..."
    local response=$(api_post "/auth/register" '{
        "email": "testuser_'$(date +%s)'@example.com",
        "password": "SecurePass123!",
        "first_name": "Test",
        "last_name": "User"
    }')
    log_success "Response: $response"
}

cmd_login() {
    log_info "Logging in..."
    local response=$(curl -s -X POST "${BASE_URL}${API_PREFIX}/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=${1:-test@example.com}" \
        -d "password=${2:-password123}" \
        -c cookies.txt \
        -w "\n%{http_code}")
    log_success "Response: $response"
    log_info "Cookies saved to cookies.txt"
}

cmd_me() {
    log_info "Getting current user..."
    local response=$(api_get "/auth/me")
    log_success "Response: $response"
}

cmd_logout() {
    log_info "Logging out..."
    local response=$(api_post "/auth/logout" '{}')
    log_success "Response: $response"
}

# Search Commands
cmd_search() {
    log_info "Performing search..."
    local query="${1:-mechanical engineering FEA}"
    local response=$(api_post "/search/query" '{
        "query": "'$query'",
        "filters": {
            "specialties": [],
            "capabilities": []
        }
    }')
    log_success "Response: $response"
}

cmd_search_upload_initiate() {
    log_info "Initiating document upload..."
    local response=$(api_post "/search/upload/initiate" '{
        "file_name": "specs.pdf",
        "file_type": "application/pdf",
        "file_size": 1048576
    }')
    log_success "Response: $response"
}

# Provider Commands
cmd_get_provider() {
    local provider_id="${1:-1}"
    log_info "Getting provider $provider_id..."
    local response=$(api_get "/providers/$provider_id/public")
    log_success "Response: $response"
}

cmd_claim_provider_search() {
    log_info "Searching for provider to claim..."
    local query="${1:-Test}"
    local response=$(api_post "/providers/claim-search" '{
        "query": "'$query'"
    }')
    log_success "Response: $response"
}

cmd_create_claim() {
    local provider_id="${1:-1}"
    log_info "Creating claim for provider $provider_id..."
    local response=$(api_post "/provider-claims" '{
        "provider_id": "'$provider_id'",
        "proof_type": "email_domain",
        "proof_payload": {"email": "admin@example.com"},
        "submitted_notes": "I am the owner"
    }')
    log_success "Response: $response"
}

cmd_get_provider_profile() {
    log_info "Getting provider profile..."
    local response=$(api_get "/provider/profile")
    log_success "Response: $response"
}

cmd_update_provider_profile() {
    log_info "Updating provider profile..."
    local response=$(api_patch "/provider/profile" '{
        "business_description": "Updated description '$(date)'"
    }')
    log_success "Response: $response"
}

# RFQ Commands
cmd_create_rfq() {
    log_info "Creating RFQ..."
    local response=$(api_post "/rfqs" '{
        "customer_email": "customer_'$(date +%s)'@example.com",
        "business_name": "Test Corp",
        "contact_name": "Test Contact",
        "project_description": "Need structural analysis for bridge design",
        "urgency": "High",
        "tollgate_phases": ["TG1", "TG3"],
        "nda_required": false
    }')
    log_success "Response: $response"
}

cmd_get_rfq() {
    local rfq_id="${1:-1}"
    log_info "Getting RFQ $rfq_id..."
    local response=$(api_get "/rfqs/$rfq_id")
    log_success "Response: $response"
}

cmd_submit_rfq() {
    local rfq_id="${1:-1}"
    log_info "Submitting RFQ $rfq_id..."
    local response=$(api_post "/rfqs/$rfq_id/submit" '{}')
    log_success "Response: $response"
}

# Provider RFQ Commands
cmd_get_teasers() {
    log_info "Getting RFQ teasers..."
    local response=$(api_get "/provider/rfqs/teasers")
    log_success "Response: $response"
}

cmd_get_teaser() {
    local rfq_id="${1:-1}"
    log_info "Getting teaser for RFQ $rfq_id..."
    local response=$(api_get "/provider/rfqs/$rfq_id/teaser")
    log_success "Response: $response"
}

cmd_unlock_rfq_checkout() {
    local rfq_id="${1:-1}"
    log_info "Creating unlock checkout for RFQ $rfq_id..."
    local response=$(api_post "/provider/rfqs/$rfq_id/unlock/checkout" '{}')
    log_success "Response: $response"
}

cmd_submit_quote() {
    local rfq_id="${1:-1}"
    log_info "Submitting quote for RFQ $rfq_id..."
    local response=$(api_post "/provider/rfqs/$rfq_id/quote" '{
        "rough_price_min": 10000,
        "rough_price_max": 25000,
        "currency": "USD",
        "turnaround_estimate_text": "4-6 weeks",
        "assumptions_text": "Standard materials",
        "scope_notes": "Full scope pending"
    }')
    log_success "Response: $response"
}

# Quote Commands
cmd_get_quotes() {
    local rfq_id="${1:-1}"
    log_info "Getting quotes for RFQ $rfq_id..."
    local response=$(api_get "/customer/rfqs/$rfq_id/quotes")
    log_success "Response: $response"
}

cmd_accept_quote() {
    local quote_id="${1:-1}"
    log_info "Accepting quote $quote_id..."
    local response=$(api_post "/customer/quotes/$quote_id/accept" '{}')
    log_success "Response: $response"
}

cmd_withdraw_quote() {
    local quote_id="${1:-1}"
    log_info "Withdrawing quote $quote_id..."
    local response=$(api_post "/provider/quotes/$quote_id/withdraw" '{}')
    log_success "Response: $response"
}

cmd_get_my_quotes() {
    log_info "Getting my quotes..."
    local response=$(api_get "/provider/quotes/me")
    log_success "Response: $response"
}

# Billing Commands
cmd_billing_portal() {
    log_info "Getting billing portal URL..."
    local response=$(api_get "/billing/portal")
    log_success "Response: $response"
}

# Ad Commands
cmd_get_software_providers() {
    log_info "Getting software providers ads..."
    local response=$(api_get "/ads/software-providers")
    log_success "Response: $response"
}

cmd_get_featured_firms() {
    log_info "Getting featured firms ads..."
    local response=$(api_get "/ads/featured-firms")
    log_success "Response: $response"
}

cmd_ad_checkout() {
    log_info "Creating ad checkout..."
    local response=$(api_post "/ads/checkout" '{
        "ad_slot_id": 1,
        "page_type": "software_providers",
        "title": "My Software"
    }')
    log_success "Response: $response"
}

cmd_get_my_ads() {
    log_info "Getting my ads..."
    local response=$(api_get "/advertiser/ads/me")
    log_success "Response: $response"
}

# Admin Commands
cmd_admin_claims() {
    log_info "Getting provider claims (admin)..."
    local response=$(api_get "/admin/provider-claims")
    log_success "Response: $response"
}

cmd_admin_rfqs() {
    log_info "Getting all RFQs (admin)..."
    local response=$(api_get "/admin/rfqs")
    log_success "Response: $response"
}

cmd_admin_payments() {
    log_info "Getting payments (admin)..."
    local response=$(api_get "/admin/payments")
    log_success "Response: $response"
}

cmd_admin_webhooks() {
    log_info "Getting webhook events (admin)..."
    local response=$(api_get "/admin/webhooks")
    log_success "Response: $response"
}

# Workflow Tests
cmd_workflow_customer() {
    log_info "=== Customer Workflow Test ==="
    cmd_register
    cmd_login "testuser_$(date +%s)@example.com" "SecurePass123!"
    cmd_me
    cmd_search "structural engineering"
    cmd_create_rfq
    log_success "Customer workflow complete!"
}

cmd_workflow_provider() {
    log_info "=== Provider Workflow Test ==="
    cmd_get_teasers
    log_success "Provider workflow complete!"
}

# Help
cmd_help() {
    cat << EOF
ProReadyEngineer API Test Script

Usage: $0 <command> [args]

Auth Commands:
  register                    Register a new user
  login [email] [password]    Login with credentials
  me                          Get current user info
  logout                      Logout current user

Search Commands:
  search [query]              Perform provider search
  search-upload-initiate      Initiate document upload

Provider Commands:
  get-provider [id]           Get public provider info
  claim-search [query]        Search for provider to claim
  create-claim [provider_id]  Create provider claim request
  get-provider-profile        Get provider profile
  update-provider-profile     Update provider profile

RFQ Commands:
  create-rfq                  Create a new RFQ
  get-rfq [id]                Get RFQ details
  submit-rfq [id]             Submit RFQ for dispatch

Provider RFQ Commands:
  get-teasers                 Get RFQ teasers
  get-teaser [rfq_id]         Get teaser details
  unlock-checkout [rfq_id]    Create unlock checkout
  submit-quote [rfq_id]       Submit quote

Quote Commands:
  get-quotes [rfq_id]         Get quotes for RFQ
  accept-quote [quote_id]     Accept a quote
  withdraw-quote [quote_id]   Withdraw a quote
  get-my-quotes               Get provider quotes

Billing Commands:
  billing-portal              Get billing portal URL

Ad Commands:
  software-providers          Get software providers ads
  featured-firms              Get featured firms ads
  ad-checkout                 Create ad checkout
  my-ads                      Get my ads

Admin Commands:
  admin-claims                Get provider claims
  admin-rfqs                  Get all RFQs
  admin-payments              Get payments
  admin-webhooks              Get webhook events

Workflow Tests:
  workflow-customer           Run customer workflow test
  workflow-provider           Run provider workflow test

Environment Variables:
  BASE_URL                    API base URL (default: http://localhost:8000)
  API_PREFIX                  API prefix (default: /api/v1)
  ACCESS_TOKEN                JWT access token for authenticated requests

Examples:
  $0 register
  $0 login test@example.com password123
  $0 search "mechanical engineering"
  $0 create-rfq
  $0 get-teasers
EOF
}

# Main command dispatcher
case "${1:-help}" in
    register) cmd_register ;;
    login) cmd_login "$2" "$3" ;;
    me) cmd_me ;;
    logout) cmd_logout ;;
    search) cmd_search "$2" ;;
    search-upload-initiate) cmd_search_upload_initiate ;;
    get-provider) cmd_get_provider "$2" ;;
    claim-search) cmd_claim_provider_search "$2" ;;
    create-claim) cmd_create_claim "$2" ;;
    get-provider-profile) cmd_get_provider_profile ;;
    update-provider-profile) cmd_update_provider_profile ;;
    create-rfq) cmd_create_rfq ;;
    get-rfq) cmd_get_rfq "$2" ;;
    submit-rfq) cmd_submit_rfq "$2" ;;
    get-teasers) cmd_get_teasers ;;
    get-teaser) cmd_get_teaser "$2" ;;
    unlock-checkout) cmd_unlock_rfq_checkout "$2" ;;
    submit-quote) cmd_submit_quote "$2" ;;
    get-quotes) cmd_get_quotes "$2" ;;
    accept-quote) cmd_accept_quote "$2" ;;
    withdraw-quote) cmd_withdraw_quote "$2" ;;
    get-my-quotes) cmd_get_my_quotes ;;
    billing-portal) cmd_billing_portal ;;
    software-providers) cmd_get_software_providers ;;
    featured-firms) cmd_get_featured_firms ;;
    ad-checkout) cmd_ad_checkout ;;
    my-ads) cmd_get_my_ads ;;
    admin-claims) cmd_admin_claims ;;
    admin-rfqs) cmd_admin_rfqs ;;
    admin-payments) cmd_admin_payments ;;
    admin-webhooks) cmd_admin_webhooks ;;
    workflow-customer) cmd_workflow_customer ;;
    workflow-provider) cmd_workflow_provider ;;
    help|--help|-h) cmd_help ;;
    *) log_error "Unknown command: $1"; cmd_help; exit 1 ;;
esac
