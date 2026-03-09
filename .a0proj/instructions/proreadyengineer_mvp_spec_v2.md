# ProReadyEngineer MVP Implementation Specification
Version: v2  
Status: Ready for implementation planning  
Format: Master build brief for AI coding agent / full-stack architect

---

## 1. Role and Objective

You are an Expert Full-Stack Software Architect and Lead Developer.

Your objective is to design and prepare the Minimum Viable Product (MVP) for a highly scalable B2B Engineering Services Directory and Marketplace called the **ProReadyEngineer ecosystem**.

The platform must:

- Match complex engineering RFQs with a pre-existing, AI-enriched database of 6,000+ service providers.
- Support customer search, provider onboarding, RFQ dispatch, quote intake, NDA handling, subscriptions, and advertising.
- Preserve and migrate all existing SQLite data into PostgreSQL without inventing source schema details.
- Prioritize reliability, auditability, payment safety, and future scalability over unnecessary feature complexity.

Do not begin with frontend implementation. The first focus is database inspection, schema design, migration planning, and API contract design.

---

## 2. Required Working Rules

### 2.1 Existing Database Rule
You have been provided an existing SQLite database file.

Before writing any schema, migration, ORM models, or SQL:
- Open and inspect the SQLite database completely.
- Enumerate every table.
- Enumerate every column in every table.
- Record each column’s SQLite data type.
- Capture a sample row from each major table.
- Capture a 3-row sample specifically from the providers table.

You must preserve the existing schema semantics during PostgreSQL migration.

Do not invent source column names.  
Do not rename existing source columns unless a mapping table is explicitly provided.  
Do not drop existing source data.  
All migration decisions must be based on actual inspection of the SQLite file.

### 2.2 MVP Scope Rule
Implement only the MVP architecture and contract definitions.  
Avoid speculative features that are not necessary for launch.

### 2.3 Reliability Rule
Any process involving:
- money,
- access control,
- quote limits,
- NDAs,
- subscription state,
- file access,
- or webhook events

must be auditable, idempotent, and backed by database state.

### 2.4 Separation Rule
Keep these concepts separate:
- user accounts,
- provider directory records,
- provider ownership claims,
- provider memberships,
- RFQs,
- quote submissions,
- unlock purchases,
- payment events,
- NDA sign flows,
- ad inventory,
- and admin moderation.

Do not collapse unrelated concerns into single tables.

---

## 3. Core Product Scope

The MVP includes three primary public-facing product tracks:

### 3.1 Customer Track
Customers can:
- search engineering providers using natural language,
- optionally upload project documents,
- receive ranked provider matches,
- submit an RFQ,
- require an NDA,
- view incoming rough quotes,
- and select one provider for direct engagement.

### 3.2 Provider Track
Providers can:
- search for their firm in the seeded database,
- claim an existing provider record or create a new one,
- subscribe to edit their profile,
- receive teaser RFQ invitations,
- pay to unlock RFQs,
- sign NDAs when required,
- and submit non-binding rough quotes.

### 3.3 Advertiser Track
Advertisers can:
- purchase public ad placements,
- configure ad creatives,
- manage subscription status,
- and publish software or featured firm advertisements.

---

## 4. Core Tech Stack

### Frontend
- Next.js
- React
- Tailwind CSS

### Backend
- Python FastAPI

### Database
- PostgreSQL
- pgvector extension enabled

### Background Jobs
- Celery
- Redis

### Authentication
- JWT access token + refresh token pattern
- Email/password login only for MVP
- Passwords hashed with bcrypt

### Transactional Email
- Resend or SendGrid
- All outbound system email sent via background jobs

### File Storage
- AWS S3
- Presigned URLs for uploads and downloads

### Hosting
- Render for frontend, backend, PostgreSQL, and Redis

### DNS
- Cloudflare

### Payments
- Stripe for cards, ACH, CashApp, subscriptions, and billing portal
- PayPal/Braintree for PayPal and Venmo support where applicable

### Document Signing
- SignRequest API with embedded signing flow in iframe

### LLM / AI
- OpenAI or Anthropic API for extraction and explanation tasks
- OpenAI text-embedding-3-small for embeddings unless otherwise specified

### Version Control / CI
- GitHub
- CI/CD pipeline required

---

## 5. Architecture Priorities

The implementation must prioritize:

1. Correct data migration from SQLite to PostgreSQL.
2. Explicit database-backed state machines.
3. Safe webhook-driven payment fulfillment.
4. Concurrency-safe RFQ unlocking.
5. Search and ranking transparency.
6. Strong admin visibility and moderation tools.
7. Minimal but production-credible security and auditability.

---

## 6. Authentication and Session Model

### 6.1 Users
Use a unified `users` table.

A single user may hold multiple roles.  
Store roles as `TEXT[]`.

Allowed public roles:
- customer
- provider
- advertiser
- admin

### 6.2 Access Tokens
- Short-lived JWT access token
- Expiration: 15 minutes
- Stored in secure httpOnly cookies

### 6.3 Refresh Tokens
- Long-lived refresh token
- Expiration: 7 days
- Stored in secure httpOnly cookies
- Must support rotation on use
- Must support revocation
- Must support logout-all-sessions
- Must be persisted server-side as hashed records, not trust-only stateless JWT flow

Create a `refresh_tokens` table containing:
- id
- user_id
- token_hash
- issued_at
- expires_at
- revoked_at
- replaced_by_token_id
- created_ip
- user_agent
- last_used_at

### 6.4 Password Reset
Support password reset via email token.

Create `password_reset_tokens` table:
- id
- user_id
- token_hash
- expires_at
- used_at
- created_at
- created_ip

Rules:
- token valid for 1 hour
- token is single-use
- token invalidated after successful reset

### 6.5 Account Security
Add:
- login rate limits
- password reset request rate limits
- refresh endpoint rate limits
- optional account lockout threshold for abuse prevention

---

## 7. User Authorization Model

Public roles are not sufficient for admin operations.

Add internal permission fields or admin capability flags such as:
- is_super_admin
- can_review_claims
- can_moderate_providers
- can_moderate_ads
- can_manage_refunds
- can_override_rfq_status
- can_review_tier_requests

All sensitive actions must be enforced in backend authorization logic.

---

## 8. Provider Data Ownership Model

The seeded provider directory records are not the same thing as user accounts.

### 8.1 Providers
The existing provider records from SQLite should migrate into a `providers` table while preserving source semantics.

A provider record may exist with:
- no claimed owner,
- multiple associated users,
- or pending ownership review.

### 8.2 Provider Memberships
Create `provider_memberships` table to map users to providers.

Fields should include:
- id
- provider_id
- user_id
- membership_role
- created_at
- created_by
- status

Membership roles:
- owner
- editor
- billing_manager
- viewer

### 8.3 Provider Claim Requests
Create `provider_claim_requests` table.

Fields:
- id
- provider_id
- claimant_user_id
- status
- proof_type
- proof_payload
- submitted_notes
- admin_review_notes
- reviewed_by
- reviewed_at
- created_at
- updated_at

Allowed statuses:
- pending
- approved
- rejected
- expired
- cancelled

Provider claim flow:
1. Provider searches for existing firm.
2. Provider submits claim request.
3. Claim request enters admin review queue.
4. Admin approves or rejects.
5. If approved, create provider membership.

Do not auto-assign provider ownership without an explicit rule.

---

## 9. Anonymous and Registered Search Quotas

### 9.1 Anonymous Search
Unregistered users may perform 3 searches per month.

Track by IP in `ip_usage_tracking`:
- id
- ip_address
- usage_month
- search_count
- created_at
- updated_at

Enforce uniqueness on:
- ip_address
- usage_month

### 9.2 Registered Search
Registered free users may perform 10 searches per month.

### 9.3 Paid Search Tiers
- Tier 1: 100 searches/month for $10/month
- Tier 2: 200 searches/month for $20/month

Store subscription linkage on the user and subscription records.

---

## 10. Search and Discovery

### 10.1 Landing Page
The landing page must include:
- centered natural-language search bar,
- document upload option,
- four navigation buttons:
  - For Customers
  - For Providers
  - Software Providers
  - Advertise Your Firm

### 10.2 Tollgate Map
Display a visual engineering project tollgate map:

- TG0: Idea Generation
- TG1: 1D / Basic Engineering Analysis
- Simple Advanced Analysis (MVP)
- Experimental Evaluation (MVP)
- TG3: Intermediate Advanced Analysis
- Experimental Testing of Intermediate Concept
- TG4: Full Scale Modeling
- TG6: Full System Testing

Include supporting copy clarifying:
- phases may include fabrication,
- physical testing,
- data handling,
- customers do not need to complete every phase.

### 10.3 Search Request Persistence
Create a `search_requests` table to log and audit searches.

Suggested fields:
- id
- user_id nullable
- ip_address nullable
- raw_query_text
- extracted_document_text
- normalized_query_text
- llm_structured_output JSONB
- embedding_model
- embedding_version
- llm_model
- search_status
- fallback_reason
- created_at

### 10.4 Document Uploads
Allow document uploads:
- PDF
- DOCX
- DWG
- STEP

Rules:
- max 25MB
- upload to S3 via presigned URL
- server-side extraction pipeline
- extracted text stored or linked for search processing

---

## 11. Embedding and Match Pipeline

### 11.1 Embedded Provider Content
The `business_description` field of each provider record must be embedded.

### 11.2 Embedding Storage
Add:
- `embedding vector(1536)` to providers
- `embedding_model`
- `embedding_generated_at`
- `embedding_version`

### 11.3 Initial Backfill
During initial migration:
- run a background batch process
- generate embeddings for all existing provider records
- do not block migration completion on synchronous embedding generation

### 11.4 Re-Embedding
On provider profile update:
- if description changes, queue re-embedding task asynchronously
- API response must not wait for embedding completion

### 11.5 Query-Time Matching Pipeline
Define the matching pipeline explicitly:

1. Normalize customer input.
2. Extract structured intent using LLM.
3. Apply hard filters.
4. Embed the query.
5. Use pgvector cosine similarity to pre-filter top candidates.
6. Apply deterministic 100-point scoring.
7. Return ranked results.
8. Record search diagnostics.

### 11.6 LLM Structured Output
The extraction output should resemble:

```json
{
  "requires_engineering": 1,
  "requires_mechanical": 1,
  "software_mentioned": ["ANSYS", "SolidWorks"],
  "inferred_specialty": "structural fatigue analysis"
}
```

### 11.7 Hard Filters
Initial examples:
- `is_engineering_service = 1`
- `is_mechanical_focus = 1`

If `software_mentioned` is non-empty:
- filter against provider software tools

### 11.8 Candidate Pool
Use vector similarity to retrieve top 50 candidates before final scoring.

### 11.9 Final Scoring
The 100-point composite score:

- Specialty Match: 25 points
- Capabilities Match: 50 points
- Tier Multiplier: 25 points

Tier scoring:
- A = 25
- B = 20
- C = 15
- D = 10
- E = 5

### 11.10 Result Output
Return Top 5 ranked firms.

Each result should include:
- provider name
- tier
- primary specialty
- score
- explanation inputs

### 11.11 Matching Fallback Rules
Add explicit fallback behavior:
- If LLM extraction fails, continue with vector similarity and reduced logic.
- If software filtering removes all results, relax software filter and record fallback reason.
- If fewer than 5 matches exist, return all valid matches.
- If no valid engineering match exists, return no-match state rather than poor-quality forced results.

### 11.12 Ranking Explainability
Any AI-generated explanation shown to the user must be grounded in stored scoring inputs.  
Do not generate free-form explanations that are disconnected from actual ranking logic.

---

## 12. Customer Monetization

### Search Plans
- Anonymous: 3 free searches/month
- Registered Free: 10 free searches/month
- Paid Tier 1: 100 searches/month at $10/month
- Paid Tier 2: 200 searches/month at $20/month

### NDA Fee
- $5 one-time document handling fee per RFQ when NDA Required is checked

Store payment linkage via subscription and payment tables, not only on users.

---

## 13. Provider Monetization

### 13.1 RFQ Unlock Fee
- $10 one-time fee per RFQ file unlock
- payable through Stripe or PayPal/Braintree

### 13.2 Profile Subscription
- $10/month recurring
- enables provider profile editing
- enables "Request Rank Up"

Provider profile editing access must be controlled by subscription state and provider membership authorization.

---

## 14. RFQ Lifecycle Model

Use explicit RFQ status values.

Create `rfq_status` enum with:
- draft
- submitted
- awaiting_nda_payment
- awaiting_customer_signature
- open_for_dispatch
- dispatching
- open_for_unlock
- quote_limit_reached
- customer_selected_provider
- closed_no_selection
- cancelled

Do not model complex lifecycle state using only booleans.

---

## 15. RFQ Data Model

Create separate RFQ-related tables.

### 15.1 `rfqs`
Suggested fields:
- id
- customer_user_id nullable
- customer_email
- business_name
- contact_name
- project_description
- urgency
- nda_required
- rfq_status
- quote_count default 0
- is_closed default false
- selected_provider_id nullable
- created_at
- updated_at
- submitted_at
- closed_at

### 15.2 `rfq_files`
- id
- rfq_id
- s3_key
- original_filename
- mime_type
- file_size_bytes
- uploaded_by_user_id nullable
- created_at

### 15.3 `rfq_matches`
Stores search ranking snapshot at RFQ creation time:
- id
- rfq_id
- provider_id
- rank_position
- composite_score
- specialty_score
- capabilities_score
- tier_score
- scoring_inputs JSONB
- created_at

### 15.4 `rfq_dispatch_batches`
- id
- rfq_id
- batch_number
- scheduled_for
- dispatched_at
- status
- created_at

### 15.5 `rfq_provider_dispatches`
- id
- rfq_id
- provider_id
- batch_id
- dispatch_status
- teaser_email_sent_at
- email_target
- created_at
- updated_at

### 15.6 `rfq_unlocks`
- id
- rfq_id
- provider_id
- unlocked_by_user_id
- payment_attempt_id
- unlock_status
- unlocked_at
- expires_at nullable
- created_at

### 15.7 `quotes`
- id
- rfq_id
- provider_id
- submitter_user_id
- quote_status
- rough_price_min nullable
- rough_price_max nullable
- currency
- turnaround_estimate_text
- assumptions_text
- scope_notes
- submitted_at
- created_at
- updated_at

### 15.8 `quote_files`
- id
- quote_id
- s3_key
- original_filename
- mime_type
- file_size_bytes
- created_at

---

## 16. RFQ Intake Flow

### 16.1 Intake Form Fields
Capture:
- email
- business name
- contact name
- project description
- file attachments
- urgency: High / Intermediate / Low
- tollgate phases: multi-select
- NDA required checkbox

### 16.2 Tollgate Options
- TG0
- TG1
- TG3
- TG4
- TG6
- All
- Don't Know

### 16.3 NDA Conditional Flow
If NDA not required:
- proceed directly to dispatch

If NDA required:
1. force account creation or login
2. charge $5 NDA handling fee
3. on successful payment, initiate SignRequest embedded signing
4. block progression until customer signature confirmed
5. only then move RFQ to dispatchable state

---

## 17. NDA Model

Create `rfq_ndas` table.

Suggested fields:
- id
- rfq_id
- provider_id nullable
- customer_user_id nullable
- nda_status
- signrequest_document_id
- signrequest_template_id
- signed_pdf_s3_key
- audit_trail_s3_key
- customer_signed_at nullable
- provider_signed_at nullable
- fully_signed_at nullable
- created_at
- updated_at

### NDA Status Enum
- not_required
- payment_pending
- customer_signature_pending
- provider_signature_pending
- fully_signed
- failed
- cancelled

Important:
- customer NDA signing and provider NDA signing may occur at different times
- if providers sign independently, store separate signing instance records or separate rows as needed
- do not assume one NDA row can represent every provider signature lifecycle unless modeled carefully

---

## 18. Dispatch Logic

### 18.1 Teaser Dispatch
Use background jobs to send teaser emails to matched providers.

The teaser must include:
- urgency level
- tollgate phases
- statement that multiple firms were contacted
- statement that only the first five quotes will be shown to the customer
- rough estimate disclaimer
- instruction to state technical assumptions clearly

### 18.2 Dispatch Batching
Batch schedule:
- Hour 0: email top 5
- Hour 24: email next 5
- continue until 5 quotes received or candidate list exhausted

### 18.3 Dispatch Stop Conditions
Stop future dispatch when:
- quote_count reaches 5
- RFQ is closed
- customer cancels RFQ
- admin overrides dispatch state

---

## 19. Concurrency-Safe RFQ Unlock Logic

This is a critical system requirement.

When a provider attempts to unlock an RFQ:
- payment may be initiated while RFQ is open
- actual entitlement must only be granted after verified payment webhook

In the payment fulfillment transaction:
1. lock the RFQ row using `SELECT ... FOR UPDATE`
2. re-check RFQ is still open
3. re-check `quote_count < 5`
4. confirm provider does not already have active unlock for that RFQ
5. create `rfq_unlocks` record
6. increment `quote_count`
7. if limit reached after increment, mark RFQ as closed or quote_limit_reached as appropriate

Rules:
- never increment quote_count optimistically before payment confirmation
- webhook fulfillment must be replay-safe
- duplicate webhook delivery must not create duplicate unlocks
- duplicate provider purchases for same RFQ must be blocked or reconciled

Define refund or failure-handling behavior for successful payment when quota becomes unavailable before fulfillment.

---

## 20. Provider RFQ Access Flow

1. Provider receives teaser.
2. Provider opens teaser link.
3. System checks RFQ availability.
4. If closed, show RFQ closed page.
5. If open, require login or registration.
6. Provider pays unlock fee.
7. On confirmed payment, verify quota lock.
8. If NDA required, initiate embedded provider signing flow.
9. After NDA completion, reveal RFQ files using S3 presigned URLs.
10. Customer contact details remain hidden until quote acceptance.
11. Provider submits quote via platform UI.

---

## 21. Quote Lifecycle

Create `quote_status` enum:
- draft
- submitted
- withdrawn
- customer_viewed
- shortlisted
- accepted
- not_selected
- expired

Rules:
- MVP supports one active submitted quote per provider per RFQ
- drafts may be edited until submission
- submitted quote becomes immutable except for admin intervention or formal withdrawal logic
- customer sees side-by-side quotes in dashboard
- accepted quote reveals direct customer contact only to winning provider

---

## 22. Customer Dashboard

Customer dashboard must include:

### 22.1 RFQ Status
- current RFQ state
- dispatch progress
- number of firms contacted
- number of quotes received

### 22.2 Quote Viewer
- all submitted quotes side by side
- quote assumptions visible
- non-binding estimate disclaimer displayed

### 22.3 NDA Access
- download executed NDA via presigned S3 URL

### 22.4 Billing
- link to Stripe billing portal for subscriptions

### 22.5 Quote Acceptance
Each quote should have an Accept action.

On acceptance:
- notify selected provider
- reveal customer direct contact info only to selected provider
- update RFQ status appropriately
- mark non-winning quotes as not_selected if workflow requires it

Display disclaimer:
- quotes are rough, non-binding, order-of-magnitude estimates
- refined final estimate will follow direct engagement

---

## 23. Provider Dashboard

Provider dashboard must include:

- historical RFQ teasers received
- unlocked RFQs
- submitted quotes and statuses
- payment logs
- NDA downloads
- profile management tab
- subscription status
- rank-up request history

### 23.1 Profile Management Access
Visible only to subscribed provider users with valid provider membership and proper permissions.

Editable scope:
- name
- website
- phone
- address
- city
- state
- postal_code
- primary_specialty
- secondary_specialties
- business_description
- capabilities
- specialties
- software_tools
- notable_clients
- email_addresses
- certifications

On business description save:
- queue embedding regeneration asynchronously

### 23.2 Rank Up Request
Button submits to `tier_evaluation_requests`.

---

## 24. Tier Evaluation Workflow

Create `tier_evaluation_requests` table:
- id
- provider_id
- requested_by_user_id
- current_tier
- requested_reason
- supporting_payload JSONB
- status
- reviewed_by
- reviewed_at
- review_notes
- created_at
- updated_at

Status values:
- pending
- approved
- rejected
- cancelled

This feeds an admin review queue.

---

## 25. Payment Architecture

Do not rely on browser redirects alone for payment state.

All payment fulfillment must be event-driven from verified webhook delivery.

### 25.1 Required Payment Tables

#### `payment_attempts`
Fields:
- id
- provider_name
- external_payment_id
- external_checkout_id nullable
- purpose
- related_entity_type
- related_entity_id
- amount
- currency
- payment_status
- idempotency_key
- initiated_by_user_id nullable
- initiated_at
- confirmed_at nullable
- failed_at nullable
- metadata JSONB

#### `subscriptions`
- id
- user_id nullable
- provider_id nullable
- advertisement_id nullable
- provider_name
- external_subscription_id
- subscription_type
- subscription_status
- current_period_start
- current_period_end
- cancel_at nullable
- cancelled_at nullable
- created_at
- updated_at

#### `webhook_events`
- id
- provider_name
- external_event_id
- event_type
- payload JSONB
- signature_verified
- processing_status
- received_at
- processed_at nullable
- error_message nullable

Enforce uniqueness on:
- provider_name
- external_event_id

### 25.2 Payment Purposes
Allowed purposes include:
- search_subscription
- nda_fee
- rfq_unlock
- provider_profile_subscription
- advertisement_subscription

### 25.3 Idempotency
All outbound payment initiation requests must use stable idempotency keys.  
All inbound webhook handlers must be replay-safe.

---

## 26. Webhook Listener Requirements

Implement webhook listeners for:
- Stripe
- PayPal/Braintree
- SignRequest

### 26.1 General Rules
- verify provider signature
- persist raw event
- deduplicate using external event id
- acknowledge quickly
- process business actions asynchronously
- log processing success or failure
- allow admin replay where safe

### 26.2 Stripe
Listen for at least:
- payment_intent.succeeded
- invoice.paid
- customer.subscription.deleted

### 26.3 PayPal/Braintree
Listen for payment capture completion events as needed.

### 26.4 SignRequest
Listen for signature completion events.

On both-parties-signed completion:
- fetch final signed PDF
- fetch audit trail
- upload both to S3
- persist S3 keys
- update NDA status to fully_signed

---

## 27. Advertising Engine

### 27.1 Public Ad Pages
Create two public pages:
- Software Providers
- Featured Firms

Empty ad blocks should display a placeholder prompting purchase.

Featured Firms placeholder should indicate that placement allows direct customer access outside the RFQ flow.

### 27.2 Pricing
- $50/month recurring subscription per ad slot

### 27.3 Ad Slot Inventory
Create `ad_slots` table:
- id
- page_type
- slot_name
- slot_position
- status
- created_at
- updated_at

### 27.4 Advertisements
Create `advertisements` table:
- id
- ad_slot_id
- advertiser_user_id
- provider_id nullable
- stripe_subscription_id nullable
- title
- promotional_text
- outbound_url
- image_s3_key
- optional_price_text
- ad_status
- started_at
- ended_at nullable
- created_at
- updated_at

### 27.5 Ad Status Values
- empty
- reserved_checkout_pending
- active
- paused
- cancelled
- expired

### 27.6 Ad Asset Rules
Accepted image types:
- JPG
- PNG
- WebP

Max size:
- 5MB

### 27.7 Ad Configuration
After successful payment:
- redirect advertiser to setup dashboard
- upload image to S3
- save promotional text
- validate outbound URL
- publish immediately on save if subscription active

### 27.8 Cancellation
Subscription cancellation must deactivate ad placement and return slot to empty state.

---

## 28. Admin Backoffice Requirements

Admin functionality is required for MVP operations.

### 28.1 Admin Capabilities
Admins must be able to:
- review provider claim requests
- approve or reject rank-up requests
- review payment attempts
- inspect webhook events
- replay failed webhook processing where safe
- override RFQ state when necessary
- view RFQ dispatch history
- review disputes and refund cases
- moderate ads
- suspend users or providers
- inspect audit logs

### 28.2 Audit Logging
Create `audit_logs` table for sensitive operations.

Suggested fields:
- id
- actor_user_id nullable
- entity_type
- entity_id
- action
- before_state JSONB nullable
- after_state JSONB nullable
- metadata JSONB
- created_at

Every critical action should emit an audit log entry.

---

## 29. Data Modeling Rules

### 29.1 PostgreSQL Type Guidance
- Use `JSONB` for flexible nested fields and evolving structured blobs
- Use `TEXT[]` for simple arrays of strings
- Use `vector(1536)` for provider embeddings
- Use proper foreign keys where relationships are known
- Add indexes for common lookups, state filters, and foreign key joins

### 29.2 Flexible Fields
Use `JSONB` where existing SQLite fields contain:
- mixed structures,
- nested objects,
- inconsistent arrays,
- or unpredictable payloads

### 29.3 String Lists
Use `TEXT[]` where the content is a plain list of strings such as:
- certifications
- secondary_specialties
- software_tools
- email_addresses

Only do this after inspecting actual source data and confirming normalization is safe.

### 29.4 Migration Preservation
Add all new fields as nullable when they do not exist in source data.  
Do not destroy or overwrite legacy values during migration.

---

## 30. Data Migration Script Requirements

Write the migration as a standalone Python script using:
- psycopg2
- or SQLAlchemy

The migration script must:
1. inspect SQLite source schema
2. create or verify PostgreSQL target schema
3. map each SQLite field to PostgreSQL equivalent
4. preserve all source rows
5. normalize fields where specified
6. insert migrated data
7. log migration outcomes
8. produce post-migration integrity report

### 30.1 Integrity Report Requirements
After migration, generate:
- row counts per table
- null counts for critical columns
- sample of 5 rows from providers
- summary of rows with parsing or normalization warnings

---

## 31. API Design Requirement

Do not implement the API yet.  
Define the route contract only.

For each route, specify:
- HTTP method
- path
- auth requirement
- allowed roles
- one-line description

---

## 32. Required API Route Structure

### 32.1 Auth
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/logout
- POST /auth/logout-all
- POST /auth/password/forgot
- POST /auth/password/reset
- GET /auth/me

### 32.2 Public Search
- POST /search/query
- POST /search/upload/initiate
- POST /search/upload/complete
- GET /providers/{provider_id}/public
- POST /providers/claim-search

### 32.3 Provider Claims
- POST /provider-claims
- GET /provider-claims/me
- GET /admin/provider-claims
- POST /admin/provider-claims/{id}/approve
- POST /admin/provider-claims/{id}/reject

### 32.4 RFQs
- POST /rfqs
- GET /rfqs/{rfq_id}
- POST /rfqs/{rfq_id}/files/initiate
- POST /rfqs/{rfq_id}/files/complete
- POST /rfqs/{rfq_id}/nda/checkout
- GET /rfqs/{rfq_id}/status
- POST /rfqs/{rfq_id}/submit

### 32.5 Provider RFQ Access
- GET /provider/rfqs/teasers
- GET /provider/rfqs/{rfq_id}/teaser
- POST /provider/rfqs/{rfq_id}/unlock/checkout
- GET /provider/rfqs/{rfq_id}/unlock/status
- GET /provider/rfqs/{rfq_id}/files
- POST /provider/rfqs/{rfq_id}/quote

### 32.6 Quotes
- GET /customer/rfqs/{rfq_id}/quotes
- POST /customer/quotes/{quote_id}/accept
- POST /provider/quotes/{quote_id}/withdraw
- GET /provider/quotes/me

### 32.7 Provider Profile
- GET /provider/profile
- POST /provider/profile
- PATCH /provider/profile
- POST /provider/profile/request-rank-up
- GET /provider/memberships

### 32.8 Ads
- GET /ads/software-providers
- GET /ads/featured-firms
- POST /ads/checkout
- GET /advertiser/ads/me
- POST /advertiser/ads/{ad_id}/asset/initiate
- POST /advertiser/ads/{ad_id}/asset/complete
- PATCH /advertiser/ads/{ad_id}

### 32.9 Billing and Webhooks
- GET /billing/portal
- POST /webhooks/stripe
- POST /webhooks/paypal
- POST /webhooks/signrequest

### 32.10 Admin
- GET /admin/rfqs
- GET /admin/rfqs/{rfq_id}
- POST /admin/rfqs/{rfq_id}/override-status
- GET /admin/payments
- GET /admin/webhooks
- POST /admin/webhooks/{id}/replay
- GET /admin/tier-requests
- POST /admin/tier-requests/{id}/approve
- POST /admin/tier-requests/{id}/reject
- GET /admin/ads
- POST /admin/ads/{id}/pause
- POST /admin/users/{id}/suspend

---

## 33. Output Requirements for the AI Agent

Your first deliverables must be produced in this order:

### Step 1 — Database Inspection
Output:
- every table in the SQLite file
- every column with data type
- a schema summary
- a 3-row sample from the providers table

### Step 2 — PostgreSQL Schema
Generate complete PostgreSQL `CREATE TABLE` statements with:
- constraints
- indexes
- comments
- enums where needed
- pgvector support
- all migrated legacy fields
- all new MVP tables and additions

Schema must include:
- provider ownership workflow
- multi-role users
- refresh token persistence
- RFQ and quote lifecycle support
- S3 file path storage
- payment and webhook tables
- NDA tracking
- ad inventory
- anonymous usage tracking
- tier evaluation requests
- audit logs

### Step 3 — API Route Contract
Output the full API route list grouped by module with:
- method
- path
- auth requirement
- one-line purpose

Do not implement handlers yet.

---

## 34. Important Implementation Notes

- Do not write frontend code in the first phase.
- Do not invent SQLite source columns.
- Do not collapse provider records into users.
- Do not trust browser return URLs as proof of payment.
- Do not unlock RFQs before verified payment event processing.
- Do not expose customer contact info before quote acceptance.
- Do not block profile save while waiting for embedding generation.
- Do not rely on booleans where explicit statuses are required.
- Do not omit admin backoffice controls.
- Do not omit auditability on money and access flows.

---

## 35. Deliverable Quality Bar

All outputs must be:
- implementation-ready,
- production-conscious,
- internally consistent,
- explicit about assumptions,
- and safe for future scaling.

Where ambiguity exists, prefer:
1. explicit status modeling,
2. auditability,
3. replay safety,
4. separation of concerns,
5. and backward-compatible migration decisions.

---
