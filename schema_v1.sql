-- =============================================================================
-- ProReadyEngineer MVP - PostgreSQL Schema
-- Generated: 2026-03-08
-- Source: SQLite engineering_directory.db (companies table, 6,766 rows)
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- SECTION 1: ENUMERATION TYPES
-- =============================================================================

-- RFQ Status Enum (Section 14)
CREATE TYPE rfq_status AS ENUM (
    'draft',
    'submitted',
    'awaiting_nda_payment',
    'awaiting_customer_signature',
    'open_for_dispatch',
    'dispatching',
    'open_for_unlock',
    'quote_limit_reached',
    'customer_selected_provider',
    'closed_no_selection',
    'cancelled'
);

-- Quote Status Enum (Section 21)
CREATE TYPE quote_status AS ENUM (
    'draft',
    'submitted',
    'withdrawn',
    'customer_viewed',
    'shortlisted',
    'accepted',
    'not_selected',
    'expired'
);

-- NDA Status Enum (Section 17)
CREATE TYPE nda_status AS ENUM (
    'not_required',
    'payment_pending',
    'customer_signature_pending',
    'provider_signature_pending',
    'fully_signed',
    'failed',
    'cancelled'
);

-- Provider Claim Status (Section 8.3)
CREATE TYPE claim_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'expired',
    'cancelled'
);

-- Membership Roles (Section 8.2)
CREATE TYPE membership_role AS ENUM (
    'owner',
    'editor',
    'billing_manager',
    'viewer'
);

-- Membership Status
CREATE TYPE membership_status AS ENUM (
    'active',
    'inactive',
    'suspended'
);

-- Dispatch Status
CREATE TYPE dispatch_status AS ENUM (
    'pending',
    'sent',
    'bounced',
    'opened'
);

-- Unlock Status
CREATE TYPE unlock_status AS ENUM (
    'payment_pending',
    'unlocked',
    'expired',
    'refunded'
);

-- Payment Status
CREATE TYPE payment_status AS ENUM (
    'initiated',
    'processing',
    'completed',
    'failed',
    'refunded',
    'disputed'
);

-- Subscription Type
CREATE TYPE subscription_type AS ENUM (
    'search_tier_1',
    'search_tier_2',
    'provider_profile',
    'advertisement'
);

-- Subscription Status
CREATE TYPE subscription_status AS ENUM (
    'active',
    'past_due',
    'cancelled',
    'paused',
    'trialing'
);

-- Payment Purpose
CREATE TYPE payment_purpose AS ENUM (
    'search_subscription',
    'nda_fee',
    'rfq_unlock',
    'provider_profile_subscription',
    'advertisement_subscription'
);

-- Ad Status
CREATE TYPE ad_status AS ENUM (
    'empty',
    'reserved_checkout_pending',
    'active',
    'paused',
    'cancelled',
    'expired'
);

-- Webhook Processing Status
CREATE TYPE webhook_processing_status AS ENUM (
    'received',
    'verified',
    'processing',
    'completed',
    'failed',
    'retrying'
);

-- Tier Evaluation Status
CREATE TYPE tier_evaluation_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'cancelled'
);

-- =============================================================================
-- SECTION 2: CORE AUTHENTICATION TABLES (Section 6)
-- =============================================================================

-- Users Table (Section 6.1)
-- Unified user table with multiple role support
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    roles TEXT[] NOT NULL DEFAULT '{}', -- customer, provider, advertiser, admin

    -- Admin permission flags (Section 7)
    is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
    can_review_claims BOOLEAN NOT NULL DEFAULT FALSE,
    can_moderate_providers BOOLEAN NOT NULL DEFAULT FALSE,
    can_moderate_ads BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_refunds BOOLEAN NOT NULL DEFAULT FALSE,
    can_override_rfq_status BOOLEAN NOT NULL DEFAULT FALSE,
    can_review_tier_requests BOOLEAN NOT NULL DEFAULT FALSE,

    -- Account security (Section 6.5)
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMP,

    -- Search quota tracking (Section 9)
    monthly_search_count INTEGER NOT NULL DEFAULT 0,
    search_count_reset_at TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,

    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

COMMENT ON TABLE users IS 'Unified user accounts with multi-role support';
COMMENT ON COLUMN users.roles IS 'Array of roles: customer, provider, advertiser, admin';

-- Refresh Tokens Table (Section 6.3)
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    replaced_by_token_id UUID REFERENCES refresh_tokens(id),
    created_ip INET,
    user_agent TEXT,
    last_used_at TIMESTAMP,

    CONSTRAINT valid_expiry CHECK (expires_at > issued_at)
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at) WHERE revoked_at IS NULL;

-- Password Reset Tokens Table (Section 6.4)
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_ip INET,

    CONSTRAINT valid_expiry CHECK (expires_at > created_at)
);

CREATE INDEX idx_password_reset_tokens_hash ON password_reset_tokens(token_hash);
CREATE INDEX idx_password_reset_tokens_user ON password_reset_tokens(user_id);

-- =============================================================================
-- SECTION 3: PROVIDER DIRECTORY (Section 8)
-- =============================================================================

-- Providers Table (Migrated from SQLite companies table) (Section 8.1)
-- Note: Preserves all 53 columns from source companies table
CREATE TABLE providers (
    -- Primary Key (mapped from companies.id)
    id INTEGER PRIMARY KEY, -- Preserving SQLite INTEGER PK

    -- Basic Info (from companies table)
    name TEXT NOT NULL,
    firm_name TEXT NOT NULL,
    website TEXT,
    phone TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,

    -- Google Places Data
    rating DECIMAL(3,2),
    review_count INTEGER,
    place_id TEXT,
    search_query TEXT,
    search_city TEXT,

    -- Classification Flags (from companies)
    is_engineering_service INTEGER NOT NULL DEFAULT 0, -- SQLite BOOLEAN
    is_mechanical_focus INTEGER NOT NULL DEFAULT 0,
    classification_confidence TEXT,
    classification_reasoning TEXT,

    -- Specialties (from companies)
    primary_specialty TEXT,
    secondary_specialties TEXT[], -- Normalized from JSON array

    -- Crawl Status (from companies)
    homepage_crawl_status TEXT,
    homepage_file TEXT,
    homepage_content_size INTEGER,
    deep_crawl_status TEXT,
    deep_crawl_page_count INTEGER,
    deep_crawl_content_size INTEGER,

    -- AI-Enriched Content (from companies)
    business_description TEXT,
    capabilities TEXT[], -- Normalized from JSON array
    specialties TEXT[], -- Normalized from JSON array
    software_tools TEXT[], -- Normalized from JSON array
    notable_clients TEXT,
    email_addresses TEXT[], -- Normalized from JSON array
    certifications TEXT[], -- Normalized from JSON array
    equipment TEXT[], -- Normalized from JSON array

    -- Business Evaluation (from companies)
    business_evaluation_tier TEXT CHECK (business_evaluation_tier IN ('A', 'B', 'C', 'D', 'E')),
    business_evaluation_years_in_business INTEGER,
    business_evaluation_employee_count TEXT,

    -- Proven Experience (from companies)
    proven_experience_project_count INTEGER,
    proven_experience_case_studies TEXT[], -- Normalized from JSON array
    proven_experience_industries_served TEXT[], -- Normalized from JSON array
    proven_experience_years_in_business INTEGER,
    proven_experience_notable_projects TEXT[], -- Normalized from JSON array

    -- Online Presence (from companies)
    online_presence_youtube_channel TEXT,
    online_presence_linkedin_url TEXT,
    online_presence_yelp_url TEXT,
    online_presence_review_count INTEGER,
    online_presence_average_rating DECIMAL(3,2),
    online_presence_reputation_summary TEXT,

    -- Team & Projects (from companies)
    team_members JSONB, -- Complex nested structure
    team_summary TEXT,
    projects JSONB, -- Complex nested structure

    -- New MVP Fields
    claim_status claim_status,
    claimed_by_user_id UUID REFERENCES users(id),
    claimed_at TIMESTAMP,

    -- Embedding Fields (Section 11.2)
    embedding vector(1536),
    embedding_model TEXT,
    embedding_generated_at TIMESTAMP,
    embedding_version TEXT,

    -- Timestamps (from companies)
    created_at TIMESTAMP,
    updated_at TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_rating CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5))
);

-- Indexes for providers
CREATE INDEX idx_providers_name ON providers(firm_name);
CREATE INDEX idx_providers_city ON providers(city);
CREATE INDEX idx_providers_state ON providers(state);
CREATE INDEX idx_providers_tier ON providers(business_evaluation_tier);
CREATE INDEX idx_providers_is_engineering ON providers(is_engineering_service);
CREATE INDEX idx_providers_is_mechanical ON providers(is_mechanical_focus);
CREATE INDEX idx_providers_specialty ON providers(primary_specialty);
CREATE INDEX idx_providers_claimed ON providers(claimed_by_user_id) WHERE claimed_by_user_id IS NOT NULL;
CREATE INDEX idx_providers_embedding ON providers USING ivfflat (embedding vector_cosine_ops);

COMMENT ON TABLE providers IS 'Provider directory migrated from SQLite companies table (6,766 records)';

-- Provider Memberships Table (Section 8.2)
CREATE TABLE provider_memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    membership_role membership_role NOT NULL,
    status membership_status NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(provider_id, user_id)
);

CREATE INDEX idx_provider_memberships_provider ON provider_memberships(provider_id);
CREATE INDEX idx_provider_memberships_user ON provider_memberships(user_id);
CREATE INDEX idx_provider_memberships_role ON provider_memberships(membership_role);

-- Provider Claim Requests Table (Section 8.3)
CREATE TABLE provider_claim_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    claimant_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status claim_status NOT NULL DEFAULT 'pending',
    proof_type TEXT,
    proof_payload JSONB,
    submitted_notes TEXT,
    admin_review_notes TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_provider_claim_requests_provider ON provider_claim_requests(provider_id);
CREATE INDEX idx_provider_claim_requests_claimant ON provider_claim_requests(claimant_user_id);
CREATE INDEX idx_provider_claim_requests_status ON provider_claim_requests(status) WHERE status = 'pending';

-- =============================================================================
-- SECTION 4: SEARCH & DISCOVERY (Section 10-11)
-- =============================================================================

-- IP Usage Tracking (Section 9.1)
CREATE TABLE ip_usage_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ip_address INET NOT NULL,
    usage_month TEXT NOT NULL, -- Format: YYYY-MM
    search_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ip_address, usage_month)
);

CREATE INDEX idx_ip_usage_tracking_ip ON ip_usage_tracking(ip_address);
CREATE INDEX idx_ip_usage_tracking_month ON ip_usage_tracking(usage_month);

-- Search Requests Table (Section 10.3)
CREATE TABLE search_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    ip_address INET,
    raw_query_text TEXT NOT NULL,
    extracted_document_text TEXT,
    normalized_query_text TEXT,
    llm_structured_output JSONB,
    embedding_model TEXT,
    embedding_version TEXT,
    llm_model TEXT,
    search_status TEXT,
    fallback_reason TEXT,
    results_count INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_search_requests_user ON search_requests(user_id);
CREATE INDEX idx_search_requests_ip ON search_requests(ip_address);
CREATE INDEX idx_search_requests_created ON search_requests(created_at);

-- =============================================================================
-- SECTION 5: RFQ DATA MODEL (Section 15)
-- =============================================================================

-- RFQs Table (Section 15.1)
CREATE TABLE rfqs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_user_id UUID REFERENCES users(id),
    customer_email TEXT NOT NULL,
    business_name TEXT,
    contact_name TEXT,
    project_description TEXT NOT NULL,
    urgency TEXT CHECK (urgency IN ('High', 'Intermediate', 'Low')),
    tollgate_phases TEXT[], -- TG0, TG1, TG3, TG4, TG6, All, Don't Know
    nda_required BOOLEAN NOT NULL DEFAULT FALSE,
    rfq_status rfq_status NOT NULL DEFAULT 'draft',
    quote_count INTEGER NOT NULL DEFAULT 0,
    is_closed BOOLEAN NOT NULL DEFAULT FALSE,
    selected_provider_id INTEGER REFERENCES providers(id),

    -- Document tracking
    has_documents BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    closed_at TIMESTAMP,

    CONSTRAINT valid_email CHECK (customer_email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

CREATE INDEX idx_rfqs_customer ON rfqs(customer_user_id);
CREATE INDEX idx_rfqs_status ON rfqs(rfq_status);
CREATE INDEX idx_rfqs_created ON rfqs(created_at);
CREATE INDEX idx_rfqs_selected ON rfqs(selected_provider_id);

-- RFQ Files Table (Section 15.2)
CREATE TABLE rfq_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    s3_key TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    extracted_text TEXT,
    uploaded_by_user_id UUID REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rfq_files_rfq ON rfq_files(rfq_id);
CREATE INDEX idx_rfq_files_s3 ON rfq_files(s3_key);

-- RFQ Matches Table (Section 15.3)
-- Stores search ranking snapshot at RFQ creation
CREATE TABLE rfq_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    rank_position INTEGER NOT NULL,
    composite_score INTEGER NOT NULL, -- 0-100
    specialty_score INTEGER NOT NULL, -- 0-25
    capabilities_score INTEGER NOT NULL, -- 0-50
    tier_score INTEGER NOT NULL, -- 0-25
    scoring_inputs JSONB NOT NULL, -- Detailed scoring data
    is_dispatched BOOLEAN NOT NULL DEFAULT FALSE,
    dispatched_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(rfq_id, provider_id)
);

CREATE INDEX idx_rfq_matches_rfq ON rfq_matches(rfq_id);
CREATE INDEX idx_rfq_matches_provider ON rfq_matches(provider_id);
CREATE INDEX idx_rfq_matches_rank ON rfq_matches(rfq_id, rank_position);
CREATE INDEX idx_rfq_matches_dispatched ON rfq_matches(rfq_id, is_dispatched);

-- RFQ Dispatch Batches Table (Section 15.4)
CREATE TABLE rfq_dispatch_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    batch_number INTEGER NOT NULL,
    scheduled_for TIMESTAMP NOT NULL,
    dispatched_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(rfq_id, batch_number)
);

CREATE INDEX idx_rfq_dispatch_batches_rfq ON rfq_dispatch_batches(rfq_id);
CREATE INDEX idx_rfq_dispatch_batches_scheduled ON rfq_dispatch_batches(scheduled_for) WHERE dispatched_at IS NULL;

-- RFQ Provider Dispatches Table (Section 15.5)
CREATE TABLE rfq_provider_dispatches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    batch_id UUID REFERENCES rfq_dispatch_batches(id),
    dispatch_status dispatch_status NOT NULL DEFAULT 'pending',
    teaser_email_sent_at TIMESTAMP,
    email_target TEXT,
    email_opened_at TIMESTAMP,
    teaser_link_clicked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(rfq_id, provider_id)
);

CREATE INDEX idx_rfq_provider_dispatches_rfq ON rfq_provider_dispatches(rfq_id);
CREATE INDEX idx_rfq_provider_dispatches_provider ON rfq_provider_dispatches(provider_id);
CREATE INDEX idx_rfq_provider_dispatches_status ON rfq_provider_dispatches(dispatch_status);

-- RFQ Unlocks Table (Section 15.6)
CREATE TABLE rfq_unlocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    unlocked_by_user_id UUID NOT NULL REFERENCES users(id),
    payment_attempt_id UUID, -- References payment_attempts
    unlock_status unlock_status NOT NULL DEFAULT 'payment_pending',
    unlocked_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(rfq_id, provider_id, unlocked_by_user_id)
);

CREATE INDEX idx_rfq_unlocks_rfq ON rfq_unlocks(rfq_id);
CREATE INDEX idx_rfq_unlocks_provider ON rfq_unlocks(provider_id);
CREATE INDEX idx_rfq_unlocks_user ON rfq_unlocks(unlocked_by_user_id);
CREATE INDEX idx_rfq_unlocks_status ON rfq_unlocks(unlock_status);

-- Quotes Table (Section 15.7)
CREATE TABLE quotes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    submitter_user_id UUID NOT NULL REFERENCES users(id),
    quote_status quote_status NOT NULL DEFAULT 'draft',
    rough_price_min DECIMAL(12,2),
    rough_price_max DECIMAL(12,2),
    currency TEXT NOT NULL DEFAULT 'USD',
    turnaround_estimate_text TEXT,
    assumptions_text TEXT,
    scope_notes TEXT,
    submitted_at TIMESTAMP,
    customer_viewed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_price_range CHECK (rough_price_max IS NULL OR rough_price_min IS NULL OR rough_price_max >= rough_price_min)
);

CREATE INDEX idx_quotes_rfq ON quotes(rfq_id);
CREATE INDEX idx_quotes_provider ON quotes(provider_id);
CREATE INDEX idx_quotes_submitter ON quotes(submitter_user_id);
CREATE INDEX idx_quotes_status ON quotes(quote_status);

-- Quote Files Table (Section 15.8)
CREATE TABLE quote_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quote_id UUID NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    s3_key TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quote_files_quote ON quote_files(quote_id);

-- =============================================================================
-- SECTION 6: NDA MANAGEMENT (Section 17)
-- =============================================================================

CREATE TABLE rfq_ndas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rfq_id UUID NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    provider_id INTEGER REFERENCES providers(id), -- NULL for customer-side NDA
    customer_user_id UUID REFERENCES users(id),
    nda_status nda_status NOT NULL DEFAULT 'not_required',
    signrequest_document_id TEXT,
    signrequest_template_id TEXT,
    signed_pdf_s3_key TEXT,
    audit_trail_s3_key TEXT,
    customer_signed_at TIMESTAMP,
    provider_signed_at TIMESTAMP,
    fully_signed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rfq_ndas_rfq ON rfq_ndas(rfq_id);
CREATE INDEX idx_rfq_ndas_provider ON rfq_ndas(provider_id);
CREATE INDEX idx_rfq_ndas_status ON rfq_ndas(nda_status);
CREATE INDEX idx_rfq_ndas_signrequest ON rfq_ndas(signrequest_document_id);

-- =============================================================================
-- SECTION 7: PAYMENT ARCHITECTURE (Section 25)
-- =============================================================================

-- Payment Attempts Table (Section 25.1)
CREATE TABLE payment_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_name TEXT NOT NULL, -- stripe, paypal, braintree
    external_payment_id TEXT,
    external_checkout_id TEXT,
    purpose payment_purpose NOT NULL,
    related_entity_type TEXT, -- rfq, subscription, etc.
    related_entity_id UUID,
    amount DECIMAL(10,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    payment_status payment_status NOT NULL DEFAULT 'initiated',
    idempotency_key TEXT UNIQUE,
    initiated_by_user_id UUID REFERENCES users(id),
    initiated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP,
    failed_at TIMESTAMP,
    failure_reason TEXT,
    metadata JSONB,

    CONSTRAINT positive_amount CHECK (amount > 0)
);

CREATE INDEX idx_payment_attempts_user ON payment_attempts(initiated_by_user_id);
CREATE INDEX idx_payment_attempts_status ON payment_attempts(payment_status);
CREATE INDEX idx_payment_attempts_provider ON payment_attempts(provider_name, external_payment_id);
CREATE INDEX idx_payment_attempts_entity ON payment_attempts(related_entity_type, related_entity_id);
CREATE INDEX idx_payment_attempts_idempotency ON payment_attempts(idempotency_key);

-- Subscriptions Table (Section 25.1)
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    provider_id INTEGER REFERENCES providers(id),
    advertisement_id UUID, -- References advertisements
    provider_name TEXT NOT NULL, -- stripe, paypal
    external_subscription_id TEXT,
    subscription_type subscription_type NOT NULL,
    subscription_status subscription_status NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_provider ON subscriptions(provider_id);
CREATE INDEX idx_subscriptions_external ON subscriptions(provider_name, external_subscription_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(subscription_status);
CREATE INDEX idx_subscriptions_period_end ON subscriptions(current_period_end);

-- Webhook Events Table (Section 25.1)
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_name TEXT NOT NULL, -- stripe, paypal, signrequest
    external_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
    processing_status webhook_processing_status NOT NULL DEFAULT 'received',
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,

    UNIQUE(provider_name, external_event_id)
);

CREATE INDEX idx_webhook_events_provider ON webhook_events(provider_name);
CREATE INDEX idx_webhook_events_type ON webhook_events(event_type);
CREATE INDEX idx_webhook_events_status ON webhook_events(processing_status);
CREATE INDEX idx_webhook_events_received ON webhook_events(received_at);

-- =============================================================================
-- SECTION 8: ADVERTISING ENGINE (Section 27)
-- =============================================================================

-- Ad Slots Table (Section 27.3)
CREATE TABLE ad_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    page_type TEXT NOT NULL, -- software-providers, featured-firms
    slot_name TEXT NOT NULL,
    slot_position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(page_type, slot_position)
);

CREATE INDEX idx_ad_slots_page ON ad_slots(page_type);
CREATE INDEX idx_ad_slots_status ON ad_slots(status);

-- Advertisements Table (Section 27.4)
CREATE TABLE advertisements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ad_slot_id UUID REFERENCES ad_slots(id),
    advertiser_user_id UUID NOT NULL REFERENCES users(id),
    provider_id INTEGER REFERENCES providers(id),
    stripe_subscription_id TEXT,
    title TEXT NOT NULL,
    promotional_text TEXT,
    outbound_url TEXT,
    image_s3_key TEXT,
    optional_price_text TEXT,
    ad_status ad_status NOT NULL DEFAULT 'empty',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_advertisements_slot ON advertisements(ad_slot_id);
CREATE INDEX idx_advertisements_advertiser ON advertisements(advertiser_user_id);
CREATE INDEX idx_advertisements_status ON advertisements(ad_status);
CREATE INDEX idx_advertisements_subscription ON advertisements(stripe_subscription_id);

-- =============================================================================
-- SECTION 9: TIER EVALUATION (Section 24)
-- =============================================================================

CREATE TABLE tier_evaluation_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    requested_by_user_id UUID NOT NULL REFERENCES users(id),
    current_tier TEXT,
    requested_reason TEXT,
    supporting_payload JSONB,
    status tier_evaluation_status NOT NULL DEFAULT 'pending',
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    new_tier TEXT, -- If approved
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tier_eval_provider ON tier_evaluation_requests(provider_id);
CREATE INDEX idx_tier_eval_requester ON tier_evaluation_requests(requested_by_user_id);
CREATE INDEX idx_tier_eval_status ON tier_evaluation_requests(status) WHERE status = 'pending';

-- =============================================================================
-- SECTION 10: AUDIT LOGGING (Section 28.2)
-- =============================================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_user_id UUID REFERENCES users(id),
    entity_type TEXT NOT NULL, -- rfq, provider, user, payment, etc.
    entity_id TEXT NOT NULL, -- UUID or string ID
    action TEXT NOT NULL, -- created, updated, deleted, status_changed, etc.
    before_state JSONB,
    after_state JSONB,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);

-- =============================================================================
-- SECTION 11: INITIAL DATA SEEDING
-- =============================================================================

-- Seed ad slots for MVP (Section 27.3)
INSERT INTO ad_slots (page_type, slot_name, slot_position, status) VALUES
    ('software-providers', 'Slot 1', 1, 'available'),
    ('software-providers', 'Slot 2', 2, 'available'),
    ('software-providers', 'Slot 3', 3, 'available'),
    ('software-providers', 'Slot 4', 4, 'available'),
    ('featured-firms', 'Slot 1', 1, 'available'),
    ('featured-firms', 'Slot 2', 2, 'available'),
    ('featured-firms', 'Slot 3', 3, 'available'),
    ('featured-firms', 'Slot 4', 4, 'available');

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
