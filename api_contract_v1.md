# =============================================================================
# ProReadyEngineer MVP - API Route Contract
# Generated: 2026-03-08
# Format: HTTP Method | Path | Auth Required | Allowed Roles | Description
# =============================================================================

## =============================================================================
## 32.1 AUTH MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | /auth/register | No | - | Register new user account with email/password |
| POST | /auth/login | No | - | Authenticate and receive access/refresh tokens |
| POST | /auth/refresh | No | - | Exchange valid refresh token for new access token |
| POST | /auth/logout | Yes | any | Revoke current session refresh token |
| POST | /auth/logout-all | Yes | any | Revoke all user refresh tokens (logout everywhere) |
| POST | /auth/password/forgot | No | - | Request password reset email |
| POST | /auth/password/reset | No | - | Reset password using token from email |
| GET | /auth/me | Yes | any | Get current authenticated user profile |

## =============================================================================
## 32.2 PUBLIC SEARCH MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | /search/query | No | - | Submit natural language search query, receive ranked providers |
| POST | /search/upload/initiate | No | - | Get presigned URL for document upload (PDF, DOCX, DWG, STEP) |
| POST | /search/upload/complete | No | - | Confirm document upload completion, trigger text extraction |
| GET | /providers/{provider_id}/public | No | - | Get public provider profile details |
| POST | /providers/claim-search | No | - | Search for provider to claim (fuzzy name matching) |

## =============================================================================
## 32.3 PROVIDER CLAIMS MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | /provider-claims | Yes | any | Submit request to claim ownership of a provider directory record |
| GET | /provider-claims/me | Yes | any | List current user's provider claim requests and status |
| GET | /admin/provider-claims | Yes | admin | List all pending provider claim requests (admin queue) |
| POST | /admin/provider-claims/{id}/approve | Yes | admin | Approve provider ownership claim, create membership |
| POST | /admin/provider-claims/{id}/reject | Yes | admin | Reject provider ownership claim with reason |

## =============================================================================
## 32.4 RFQ MODULE (CUSTOMER)
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | /rfqs | Yes | customer | Create new RFQ draft with project details |
| GET | /rfqs/{rfq_id} | Yes | customer, admin | Get RFQ details and current status |
| POST | /rfqs/{rfq_id}/files/initiate | Yes | customer | Get presigned URL to upload RFQ attachment |
| POST | /rfqs/{rfq_id}/files/complete | Yes | customer | Confirm RFQ file upload, queue extraction |
| POST | /rfqs/{rfq_id}/nda/checkout | Yes | customer | Initiate customer NDA handling fee ($10) — provider-first mutual NDA flow |
| GET | /rfqs/{rfq_id}/status | Yes | customer, admin | Get detailed RFQ lifecycle status |
| POST | /rfqs/{rfq_id}/submit | Yes | customer | Submit RFQ for provider matching and dispatch |

## =============================================================================
## 32.5 PROVIDER RFQ ACCESS MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /provider/rfqs/teasers | Yes | provider | List all RFQ teasers received by provider |
| GET | /provider/rfqs/{rfq_id}/teaser | Yes | provider | Get teaser details for specific RFQ |
| POST | /provider/rfqs/{rfq_id}/unlock/checkout | Yes | provider | Initiate RFQ unlock payment ($10 fee) |
| GET | /provider/rfqs/{rfq_id}/unlock/status | Yes | provider | Check unlock payment status and access |
| GET | /provider/rfqs/{rfq_id}/files | Yes | provider | Get presigned URLs for RFQ documents (after unlock) |
| POST | /provider/rfqs/{rfq_id}/quote | Yes | provider | Submit rough quote for RFQ |

## =============================================================================
## 32.6 QUOTES MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /customer/rfqs/{rfq_id}/quotes | Yes | customer | Get all quotes submitted for customer's RFQ |
| POST | /customer/quotes/{quote_id}/accept | Yes | customer | Accept a quote, reveal contact info to provider |
| POST | /provider/quotes/{quote_id}/withdraw | Yes | provider | Withdraw a submitted quote |
| GET | /provider/quotes/me | Yes | provider | List all quotes submitted by provider user |

## =============================================================================
## 32.7 PROVIDER PROFILE MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /provider/profile | Yes | provider | Get editable provider profile data |
| POST | /provider/profile | Yes | provider | Create new provider profile (for unlisted firms) |
| PATCH | /provider/profile | Yes | provider | Update provider profile (requires subscription) |
| POST | /provider/profile/request-rank-up | Yes | provider | Submit tier evaluation request |
| GET | /provider/memberships | Yes | provider | List user's provider memberships and roles |

## =============================================================================
## 32.8 ADVERTISING MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /ads/software-providers | No | - | Get active software provider advertisements |
| GET | /ads/featured-firms | No | - | Get active featured firm advertisements |
| POST | /ads/checkout | Yes | advertiser | Initiate ad slot subscription checkout ($50/month) |
| GET | /advertiser/ads/me | Yes | advertiser | List advertiser's ad campaigns and status |
| POST | /advertiser/ads/{ad_id}/asset/initiate | Yes | advertiser | Get presigned URL for ad image upload (JPG, PNG, WebP) |
| POST | /advertiser/ads/{ad_id}/asset/complete | Yes | advertiser | Confirm ad image upload and publish ad |
| PATCH | /advertiser/ads/{ad_id} | Yes | advertiser | Update ad content (title, text, URL) |

## =============================================================================
## 32.9 BILLING & WEBHOOKS MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /billing/portal | Yes | any | Redirect to Stripe customer billing portal |
| POST | /webhooks/stripe | No | - | Stripe webhook listener (payment events) |
| POST | /webhooks/paypal | No | - | PayPal/Braintree webhook listener |
| POST | /webhooks/signrequest | No | - | SignRequest webhook listener (signature events) |

## =============================================================================
## 32.10 ADMIN MODULE
## =============================================================================

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| GET | /admin/rfqs | Yes | admin | List all RFQs with filtering and pagination |
| GET | /admin/rfqs/{rfq_id} | Yes | admin | Get full RFQ details including matches and dispatches |
| POST | /admin/rfqs/{rfq_id}/override-status | Yes | admin | Override RFQ status manually |
| GET | /admin/payments | Yes | admin | List all payment attempts with status |
| GET | /admin/webhooks | Yes | admin | List webhook events with processing status |
| POST | /admin/webhooks/{id}/replay | Yes | admin | Replay failed webhook processing |
| GET | /admin/tier-requests | Yes | admin | List pending tier evaluation requests |
| POST | /admin/tier-requests/{id}/approve | Yes | admin | Approve tier upgrade request |
| POST | /admin/tier-requests/{id}/reject | Yes | admin | Reject tier upgrade request |
| GET | /admin/ads | Yes | admin | List all advertisements for moderation |
| POST | /admin/ads/{id}/pause | Yes | admin | Pause an active advertisement |
| POST | /admin/users/{id}/suspend | Yes | admin | Suspend user account |

## =============================================================================
## SUMMARY
## =============================================================================

| Module | Public | Auth Required | Admin Only | Total |
|--------|--------|---------------|------------|-------|
| Auth | 5 | 3 | 0 | 8 |
| Public Search | 4 | 1 | 0 | 5 |
| Provider Claims | 0 | 2 | 3 | 5 |
| RFQ (Customer) | 0 | 7 | 0 | 7 |
| Provider RFQ Access | 0 | 6 | 0 | 6 |
| Quotes | 0 | 4 | 0 | 4 |
| Provider Profile | 0 | 5 | 0 | 5 |
| Advertising | 2 | 5 | 0 | 7 |
| Billing & Webhooks | 3 | 1 | 0 | 4 |
| Admin | 0 | 0 | 12 | 12 |
| **TOTAL** | **14** | **34** | **15** | **63** |

## =============================================================================
## AUTHENTICATION NOTES
## =============================================================================

- **No Auth**: Rate limited by IP, anonymous search quotas enforced
- **Any Role**: Valid JWT access token required, any role accepted
- **Customer**: User must have 'customer' role
- **Provider**: User must have valid provider membership with appropriate permissions
- **Advertiser**: User must have 'advertiser' role
- **Admin**: User must have 'admin' role OR specific capability flag (Section 7)

## =============================================================================
## SECURITY REQUIREMENTS
## =============================================================================

1. All endpoints enforce HTTPS
2. Access tokens in httpOnly cookies (15 min expiry)
3. Refresh tokens in httpOnly cookies (7 day expiry, server-side persisted)
4. Rate limiting: login (5/min), password reset (3/hour), refresh (10/min)
5. CORS restricted to known origins
6. All file uploads validated by MIME type and size
7. SQL injection prevention via parameterized queries
8. XSS prevention via output encoding


## Removed (legacy NDA endpoints, May 2026)

The customer-iframe-first NDA endpoints were removed when the NDA flow was
consolidated into one mutual, provider-first 'sign-to-read' model:
`POST /rfqs/{rfq_id}/nda/initiate`, `GET /rfqs/{rfq_id}/nda/signing-url`,
`POST /rfqs/{rfq_id}/nda/confirm-signed`. Provider NDA signing is now
`POST /provider/rfqs/{rfq_id}/nda/signing-url`. See ARCHITECTURE.md §6.
