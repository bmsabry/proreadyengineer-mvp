// User Types
export interface User {
  id: string;
  email: string;
  roles: ('customer' | 'provider' | 'advertiser' | 'admin')[];
  is_super_admin?: boolean;
  can_review_claims?: boolean;
  can_moderate_providers?: boolean;
  can_moderate_ads?: boolean;
  can_manage_refunds?: boolean;
  can_override_rfq_status?: boolean;
  can_review_tier_requests?: boolean;
  created_at: string;
  updated_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  roles?: ('customer' | 'provider' | 'advertiser')[];
  full_name?: string;
  company_name?: string;
  phone?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface AuthResponse {
  user: User;
  access_token?: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
}

// Provider Types
export interface Provider {
  id: number;  // Provider IDs are integers from backend
  name: string;
  tier: 'A' | 'B' | 'C' | 'D' | 'E';
  website?: string;
  phone?: string;
  address?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  primary_specialty?: string;
  secondary_specialties?: string[];
  business_description?: string;
  capabilities?: string[];
  specialties?: string[];
  software_tools?: string[];
  notable_clients?: string; // TEXT column in DB, not array
  certifications?: string[];
  email_addresses?: string[];
  is_engineering_service?: boolean;
  is_mechanical_focus?: boolean;
  created_at: string;
  updated_at: string;
  embedding_generated_at?: string;
}

export interface ProviderMembership {
  id: string;
  provider_id: string;
  user_id: string;
  membership_role: 'owner' | 'editor' | 'billing_manager' | 'viewer';
  status: 'active' | 'inactive';
  created_at: string;
  created_by?: string;
}

export interface ProviderClaimRequest {
  id: string;
  provider_id: string;
  claimant_user_id: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled';
  proof_type?: string;
  proof_payload?: Record<string, unknown>;
  submitted_notes?: string;
  admin_review_notes?: string;
  reviewed_by?: string;
  reviewed_at?: string;
  created_at: string;
  updated_at: string;
  provider?: Provider;
}

export interface TierEvaluationRequest {
  id: string;
  provider_id: string;
  requested_by_user_id: string;
  current_tier: string;
  requested_reason?: string;
  supporting_payload?: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  reviewed_by?: string;
  reviewed_at?: string;
  review_notes?: string;
  created_at: string;
  updated_at: string;
}

// Search Types
export interface SearchRequest {
  id: string;
  user_id?: string;
  ip_address?: string;
  raw_query_text: string;
  extracted_document_text?: string;
  normalized_query_text?: string;
  llm_structured_output?: SearchLLMOutput;
  embedding_model?: string;
  llm_model?: string;
  search_status: string;
  fallback_reason?: string;
  created_at: string;
}

export interface SearchLLMOutput {
  requires_engineering: number;
  requires_mechanical: number;
  software_mentioned?: string[];
  inferred_specialty?: string;
}

export interface SearchResult {
  // Actual fields returned by backend /api/v1/search/query
  provider: Provider;
  score: number;              // Primary match score (0-100)
  explanation: string;        // Human-readable match explanation
  // Legacy / optional fields (kept for compatibility)
  rank_position?: number;
  composite_score?: number;
  specialty_score?: number;
  capabilities_score?: number;
  tier_score?: number;
  scoring_inputs?: Record<string, unknown>;
}


export interface PipelineInfo {
  pipeline_used: 'ai_vector' | 'keyword_fallback' | 'no_api_key' | 'error' | string;
  llm_called: boolean;
  llm_response_received: boolean;
  llm_model: string;
  embedding_called: boolean;
  embedding_dims: number;
  api_key_source: 'database' | 'env_var' | 'missing' | string;
  fallback_reason: string | null;
  inferred_specialty: string | null;
  inferred_keywords: string[];
}

export interface SearchResponseWithPipeline {
  results: SearchResult[];
  total_matches: number;
  search_quota_remaining: number;
  pipeline_info: PipelineInfo | null;
}

export interface SearchQueryRequest {
  query: string;
}

export interface SearchQueryResponse {
  // Matches backend SearchResponse schema
  results: SearchResult[];
  total_matches: number;
  search_quota_remaining: number;
  pipeline_info?: PipelineInfo | null;
  // Optional legacy fields
  search_id?: string;
  query?: string;
  fallback_reason?: string;
}

// RFQ Types
export type RFQStatus = 
  | 'draft' 
  | 'submitted' 
  | 'awaiting_nda_payment' 
  | 'awaiting_customer_signature'
  | 'open_for_dispatch'
  | 'dispatching'
  | 'open_for_unlock'
  | 'quote_limit_reached'
  | 'customer_selected_provider'
  | 'closed_no_selection'
  | 'cancelled';

export interface RFQ {
  id: string;
  customer_user_id?: string;
  customer_email: string;
  business_name?: string;
  contact_name?: string;
  project_description: string;
  urgency: 'High' | 'Intermediate' | 'Low';
  tollgate_phases?: string[];
  nda_required: boolean;
  rfq_status: RFQStatus;
  quote_count: number;
  is_closed: boolean;
  selected_provider_id?: string;
  created_at: string;
  updated_at: string;
  submitted_at?: string;
  closed_at?: string;
  matches?: RFQMatch[];
  files?: RFQFile[];
  nda?: RFQNDA;
}

export interface RFQMatch {
  id: string;
  rfq_id: string;
  provider_id: string;
  rank_position: number;
  composite_score: number;
  specialty_score: number;
  capabilities_score: number;
  tier_score: number;
  scoring_inputs?: Record<string, unknown>;
  created_at: string;
  provider?: Provider;
}

export interface RFQFile {
  id: string;
  rfq_id: string;
  s3_key: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  uploaded_by_user_id?: string;
  created_at: string;
  presigned_url?: string;
}

export interface RFQNDA {
  id: string;
  rfq_id: string;
  provider_id?: string;
  customer_user_id?: string;
  nda_status: 'not_required' | 'payment_pending' | 'customer_signature_pending' | 'provider_signature_pending' | 'fully_signed' | 'failed' | 'cancelled';
  signrequest_document_id?: string;
  signrequest_template_id?: string;
  signed_pdf_s3_key?: string;
  audit_trail_s3_key?: string;
  customer_signed_at?: string;
  provider_signed_at?: string;
  fully_signed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateRFQRequest {
  customer_email: string;
  business_name?: string;
  contact_name?: string;
  project_description: string;
  urgency: 'High' | 'Intermediate' | 'Low';
  tollgate_phases?: string[];
  nda_required: boolean;
}

export interface RFQDispatch {
  id: string;
  rfq_id: string;
  provider_id: string;
  dispatch_status: string;
  teaser_email_sent_at?: string;
  email_target?: string;
  created_at: string;
  updated_at: string;
  provider?: Provider;
}
// RFQ Teaser for providers
export interface RFQTeaser {
  rfq_id: string;
  status?: string;
  dispatch_status?: string;
  urgency?: string;
  tollgate_phases?: string[];
  nda_required?: boolean;
}



export interface RFQUnlock {
  id: string;
  rfq_id: string;
  provider_id: string;
  unlocked_by_user_id: string;
  payment_attempt_id?: string;
  unlock_status: 'pending' | 'active' | 'expired' | 'cancelled';
  unlocked_at?: string;
  expires_at?: string;
  created_at: string;
}

// Quote Types
export type QuoteStatus = 'draft' | 'submitted' | 'withdrawn' | 'customer_viewed' | 'shortlisted' | 'accepted' | 'not_selected' | 'expired';

export interface Quote {
  id: string;
  rfq_id: string;
  provider_id: string;
  submitter_user_id: string;
  quote_status: QuoteStatus;
  rough_price_min?: number;
  rough_price_max?: number;
  currency?: string;
  turnaround_estimate_text?: string;
  assumptions_text?: string;
  scope_notes?: string;
  submitted_at?: string;
  created_at: string;
  updated_at: string;
  provider?: Provider;
  files?: QuoteFile[];
}

export interface QuoteFile {
  id: string;
  quote_id: string;
  s3_key: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  created_at: string;
  presigned_url?: string;
}
export interface QuoteAcceptResponse {
  success: boolean;
  message: string;
  rfq_id: string;
  selected_quote_id: string;
  selected_provider_id: number;
  provider_contact_revealed: boolean;
  provider_name?: string;
  provider_email?: string;
  provider_phone?: string;
  provider_website?: string;
  provider_city?: string;
  provider_state?: string;
  provider_address?: string;
}



export interface CreateQuoteRequest {
  rough_price_min?: number;
  rough_price_max?: number;
  currency?: string;
  turnaround_estimate_text?: string;
  assumptions_text?: string;
  scope_notes?: string;
}

// Payment Types
export type PaymentPurpose = 'search_subscription' | 'nda_fee' | 'rfq_unlock' | 'provider_profile_subscription' | 'advertisement_subscription';
export type PaymentStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'refunded';

export interface PaymentAttempt {
  id: string;
  provider_name: string;
  external_payment_id?: string;
  external_checkout_id?: string;
  purpose: PaymentPurpose;
  related_entity_type?: string;
  related_entity_id?: string;
  amount: number;
  currency: string;
  payment_status: PaymentStatus;
  idempotency_key?: string;
  initiated_by_user_id?: string;
  initiated_at: string;
  confirmed_at?: string;
  failed_at?: string;
  metadata?: Record<string, unknown>;
}

export interface Subscription {
  id: string;
  user_id?: string;
  provider_id?: string;
  advertisement_id?: string;
  provider_name: string;
  external_subscription_id?: string;
  subscription_type: string;
  subscription_status: 'active' | 'cancelled' | 'past_due' | 'incomplete' | 'paused';
  current_period_start?: string;
  current_period_end?: string;
  cancel_at?: string;
  cancelled_at?: string;
  created_at: string;
  updated_at: string;
}

// Ad Types
export interface AdSlot {
  id: string;
  page_type: string;
  slot_name: string;
  slot_position: number;
  status: 'available' | 'reserved' | 'occupied';
  created_at: string;
  updated_at: string;
}

export interface Advertisement {
  id: string;
  ad_slot_id: string;
  advertiser_user_id: string;
  provider_id?: string;
  stripe_subscription_id?: string;
  title: string;
  promotional_text?: string;
  outbound_url?: string;
  image_s3_key?: string;
  optional_price_text?: string;
  ad_status: 'empty' | 'reserved_checkout_pending' | 'active' | 'paused' | 'cancelled' | 'expired';
  started_at?: string;
  ended_at?: string;
  created_at: string;
  updated_at: string;
  image_presigned_url?: string;
  ad_slot?: AdSlot;
}

// Audit Log Types
export interface AuditLog {
  id: string;
  actor_user_id?: string;
  entity_type: string;
  entity_id: string;
  action: string;
  before_state?: Record<string, unknown>;
  after_state?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// API Response Types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiError {
  detail: string;
  code?: string;
  field?: string;
}

// ── Customer RFQ listing & tracking ──────────────────────────────────────────
export interface CustomerRFQSummary { id: string; project_description: string; rfq_status: string; urgency: string; nda_required: boolean; quote_count: number; is_closed: boolean; created_at: string|null; submitted_at: string|null; }
export interface DispatchedProvider { provider_id: number; provider_name: string; city: string|null; state: string|null; tier: string|null; dispatch_status: string; teaser_email_sent_at: string|null; batch_id: string|null; }
export interface RFQDispatchBatchDetail { id: string; batch_number: number; status: string; scheduled_for: string|null; dispatched_at: string|null; providers_contacted: DispatchedProvider[]; }
export interface TrackingQuote { id: string; provider_id: number; quote_status: string; rough_price_min: number|null; rough_price_max: number|null; currency: string|null; turnaround_estimate_text: string|null; submitted_at: string|null; }
export interface RFQTrackingData { rfq: CustomerRFQSummary; total_matches: number; total_dispatched: number; quotes_received: number; batches: RFQDispatchBatchDetail[]; quotes: TrackingQuote[]; }

export interface AdminDispatchProvider {
  rank_position: number;
  provider_id: number;
  provider_name: string | null;
  city: string | null;
  state: string | null;
  tier: string | null;
  composite_score: number;
  provider_email: string | null;
  is_dispatched: boolean;
  dispatched_at: string | null;
  dispatch_status: string;
  email_target: string | null;
  teaser_email_sent_at: string | null;
  submitted_quote: boolean;
}

export interface AdminRFQDispatchTracking {
  rfq_id: string;
  rfq_status: string;
  customer_email: string;
  business_name: string | null;
  project_description: string;
  urgency: string | null;
  nda_required: boolean;
  quote_count: number;
  is_closed: boolean;
  submitted_at: string | null;
  total_matches: number;
  total_contacted: number;
  total_quoted: number;
  providers: AdminDispatchProvider[];
}
