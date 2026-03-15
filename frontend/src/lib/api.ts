import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import {
  User, RegisterRequest, LoginRequest, AuthResponse, PasswordResetRequest, PasswordResetConfirm,
  Provider, ProviderClaimRequest, ProviderMembership, TierEvaluationRequest,
  SearchQueryRequest, SearchQueryResponse,
  RFQ, RFQFile, RFQDispatch, RFQUnlock, RFQMatch, RFQNDA, RFQTeaser, CreateRFQRequest,
  Quote, QuoteFile, CreateQuoteRequest,
  PaymentAttempt, Subscription,
  Advertisement, AdSlot,
  AuditLog, PaginatedResponse
} from '@/types';

// API Configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Token storage helpers (localStorage for cross-domain auth)
const TOKEN_KEY = 'access_token';

export const getStoredToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
};

export const setStoredToken = (token: string): void => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
};

export const clearStoredToken = (): void => {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
};

// Create Axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_URL + '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor - send stored token as Authorization Bearer header
apiClient.interceptors.request.use(
  (config) => {
    const token = getStoredToken();
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle 401 with token refresh
let isRefreshing = false;
// Flag to prevent auto-refresh during intentional logout
export let isLoggingOut = false;
export const setLoggingOut = (val: boolean) => { isLoggingOut = val; };
let refreshQueue: Array<(token?: string) => void> = [];

const processRefreshQueue = (error?: Error) => {
  refreshQueue.forEach(callback => callback());
  refreshQueue = [];
};

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError & { config?: any }) => {
    const originalRequest = error.config;

    // Don't retry refresh endpoint itself (prevents infinite loop)
    if (originalRequest?.url?.includes('auth/refresh') || 
        originalRequest?.url?.includes('auth/login') ||
        originalRequest?.url?.includes('auth/register')) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isLoggingOut) {
      if (isRefreshing) {
        // Queue this request until refresh completes
        return new Promise((resolve, reject) => {
          refreshQueue.push(() => {
            resolve(apiClient(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        await auth.refresh();
        processRefreshQueue();
        return apiClient(originalRequest);
      } catch (refreshError) {
        processRefreshQueue(refreshError as Error);
        // Only redirect if not already on auth pages
        if (typeof window !== 'undefined' && 
            !window.location.pathname.includes('/login') &&
            !window.location.pathname.includes('/register')) {
          // Don't redirect, just return error - let AuthContext handle it
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// Auth API - stores/clears token on auth events
const auth = {
  register: async (data: RegisterRequest) => {
    const response = await apiClient.post<AuthResponse>('/auth/register', data);
    if ((response.data as any)?.access_token) setStoredToken((response.data as any).access_token);
    return response;
  },

  login: async (data: LoginRequest) => {
    const response = await apiClient.post<AuthResponse>('/auth/login', data);
    if ((response.data as any)?.access_token) setStoredToken((response.data as any).access_token);
    return response;
  },

  refresh: async () => {
    const response = await apiClient.post('/auth/refresh');
    if (response.data?.access_token) setStoredToken(response.data.access_token);
    return response;
  },

  logout: async () => {
    clearStoredToken();
    return apiClient.post('/auth/logout');
  },

  logoutAll: async () => {
    clearStoredToken();
    return apiClient.post('/auth/logout-all');
  },

  forgotPassword: (data: PasswordResetRequest) =>
    apiClient.post('/auth/password/forgot', data),

  resetPassword: (data: PasswordResetConfirm) =>
    apiClient.post('/auth/password/reset', data),

  me: () =>
    apiClient.get<User>('/auth/me'),
};

// Public Search API
const search = {
  query: (data: SearchQueryRequest) => 
    apiClient.post<SearchQueryResponse>('/search/query', data),
  
  uploadInitiate: () => 
    apiClient.post<{ presigned_url: string; s3_key: string }>('/search/upload/initiate'),
  
  uploadComplete: (s3Key: string) => 
    apiClient.post('/search/upload/complete', { s3_key: s3Key }),
  
  getProviderPublic: (providerId: string) => 
    apiClient.get<Provider>(`/providers/${providerId}/public`),
  
  claimSearch: (query: string) => 
    apiClient.post<Provider[]>('/providers/claim-search', { query }),
  
  debug: () =>
    apiClient.get('/search/debug'),
};

// Providers
const providers = {
  // Public
  getPublic: (id: string) =>
    apiClient.get<Provider>(`/providers/${id}/public`),

  claimSearch: (data: { query: string }) =>
    apiClient.post<Provider[]>('/providers/claim-search', data),

  // Provider profile
  getProfile: () =>
    apiClient.get<Provider>('/provider/profile'),

  updateProfile: (data: Partial<Provider>) =>
    apiClient.patch<Provider>('/provider/profile', data),

  requestRankUp: (data: { requested_reason: string; supporting_payload?: Record<string, unknown> }) =>
    apiClient.post('/provider/profile/request-rank-up', data),

  getMemberships: () =>
    apiClient.get<ProviderMembership[]>('/provider/memberships'),
};

// Provider Claims API
const providerClaims = {
  create: (data: { provider_id: string; proof_type?: string; proof_payload?: Record<string, unknown>; submitted_notes?: string }) => 
    apiClient.post<ProviderClaimRequest>('/provider-claims', data),
  
  listMyClaims: () => 
    apiClient.get<ProviderClaimRequest[]>('/provider-claims/me'),
  
  // Admin endpoints
  listAll: () => 
    apiClient.get<ProviderClaimRequest[]>('/admin/provider-claims'),
  
  approve: (id: string) => 
    apiClient.post<ProviderClaimRequest>(`/admin/provider-claims/${id}/approve`),
  
  reject: (id: string, data: { reason?: string }) => 
    apiClient.post<ProviderClaimRequest>(`/admin/provider-claims/${id}/reject`, data),
};

// RFQs API
const rfqs = {
  create: (data: CreateRFQRequest) => 
    apiClient.post<RFQ>('/rfqs', data),
  
  get: (id: string) => 
    apiClient.get<RFQ>(`/rfqs/${id}`),
  
  fileInitiate: (rfqId: string, filename: string, mimeType: string, size: number) => 
    apiClient.post<RFQFile>(`/rfqs/${rfqId}/files/initiate`, { filename, mime_type: mimeType, file_size_bytes: size }),
  
  fileComplete: (rfqId: string, s3Key: string) => 
    apiClient.post(`/rfqs/${rfqId}/files/complete`, { s3_key: s3Key }),
  
  ndaCheckout: (rfqId: string) => 
    apiClient.post<{ checkout_url: string; payment_attempt_id: string }>(`/rfqs/${rfqId}/nda/checkout`),
  
  getStatus: (rfqId: string) => 
    apiClient.get<{ rfq_status: string; quote_count: number }>(`/rfqs/${rfqId}/status`),
  
  submit: (rfqId: string) => 
    apiClient.post<RFQ>(`/rfqs/${rfqId}/submit`),
};

// Provider RFQ access
const providerRFQ = {
  getTeasers: () =>
    apiClient.get<RFQTeaser[]>('/provider/rfqs/teasers'),

  getTeaser: (rfqId: string) =>
    apiClient.get<RFQTeaser>(`/provider/rfqs/${rfqId}/teaser`),

  unlockCheckout: (rfqId: string) =>
    apiClient.post<{ client_secret: string }>(`/provider/rfqs/${rfqId}/unlock/checkout`),

  getUnlockStatus: (rfqId: string) =>
    apiClient.get<{ unlocked: boolean }>(`/provider/rfqs/${rfqId}/unlock/status`),

  getFiles: (rfqId: string) =>
    apiClient.get<RFQFile[]>(`/provider/rfqs/${rfqId}/files`),

  submitQuote: (rfqId: string, data: {
    rough_price_min?: number;
    rough_price_max?: number;
    currency?: string;
    turnaround_estimate_text?: string;
    assumptions_text?: string;
    scope_notes?: string;
  }) =>
    apiClient.post<Quote>(`/provider/rfqs/${rfqId}/quote`, data),
};


// Provider RFQ Access API
const providerRfqAccess = {
  getTeasers: () => 
    apiClient.get<RFQ[]>('/provider/rfqs/teasers'),
  
  getTeaser: (rfqId: string) => 
    apiClient.get<RFQ>(`/provider/rfqs/${rfqId}/teaser`),
  
  unlockCheckout: (rfqId: string) => 
    apiClient.post<{ checkout_url: string; payment_attempt_id: string }>(`/provider/rfqs/${rfqId}/unlock/checkout`),
  
  getUnlockStatus: (rfqId: string) => 
    apiClient.get<RFQUnlock>(`/provider/rfqs/${rfqId}/unlock/status`),
  
  getFiles: (rfqId: string) => 
    apiClient.get<RFQFile[]>(`/provider/rfqs/${rfqId}/files`),
  
  submitQuote: (rfqId: string, data: CreateQuoteRequest) => 
    apiClient.post<Quote>(`/provider/rfqs/${rfqId}/quote`, data),
};

// Quotes API
const quotes = {
  // Customer endpoints
  getCustomerQuotes: (rfqId: string) => 
    apiClient.get<Quote[]>(`/customer/rfqs/${rfqId}/quotes`),

  getForCustomer: (rfqId: string) =>
    apiClient.get<Quote[]>(`/customer/rfqs/${rfqId}/quotes`),
  
  accept: (quoteId: string) => 
    apiClient.post<Quote>(`/customer/quotes/${quoteId}/accept`),
  
  // Provider endpoints
  withdraw: (quoteId: string) => 
    apiClient.post<Quote>(`/provider/quotes/${quoteId}/withdraw`),
  
  getMyQuotes: () => 
    apiClient.get<Quote[]>('/provider/quotes/me'),

  getForProvider: () =>
    apiClient.get<Quote[]>('/provider/quotes/me'),
};

// Provider Profile API
const providerProfile = {
  get: () => 
    apiClient.get<Provider>('/provider/profile'),
  
  create: (data: Partial<Provider>) => 
    apiClient.post<Provider>('/provider/profile', data),
  
  update: (data: Partial<Provider>) => 
    apiClient.patch<Provider>('/provider/profile', data),
  
  requestRankUp: (data: { reason: string; supporting_payload?: Record<string, unknown> }) => 
    apiClient.post<TierEvaluationRequest>('/provider/profile/request-rank-up', data),
  
  getMemberships: () => 
    apiClient.get<ProviderMembership[]>('/provider/memberships'),
};

// Ads API
const ads = {
  // Public endpoints
  getSoftwareProviders: () => 
    apiClient.get<Advertisement[]>('/ads/software-providers'),
  
  getFeaturedFirms: () => 
    apiClient.get<Advertisement[]>('/ads/featured-firms'),
  
  // Advertiser endpoints
  checkout: (data: { ad_slot_id: string }) => 
    apiClient.post<{ checkout_url: string }>('/ads/checkout', data),
  
  getMyAds: () => 
    apiClient.get<Advertisement[]>('/advertiser/ads/me'),
  
  uploadAssetInitiate: (adId: string) => 
    apiClient.post<{ presigned_url: string; s3_key: string }>(`/advertiser/ads/${adId}/asset/initiate`),
  
  uploadAssetComplete: (adId: string, s3Key: string) => 
    apiClient.post(`/advertiser/ads/${adId}/asset/complete`, { s3_key: s3Key }),
  
  updateAd: (adId: string, data: Partial<Advertisement>) => 
    apiClient.patch<Advertisement>(`/advertiser/ads/${adId}`, data),
};

// Billing API
const billing = {
  getPortal: () => 
    apiClient.get<{ portal_url: string }>('/billing/portal'),
};

// Admin API
const admin = {
  // RFQs
  getStats: () =>
    apiClient.get<any>('/admin/stats'),
  // backward compat alias
  getStatus: () =>
    apiClient.get<any>('/admin/stats'),
  listRFQs: (params?: { page?: number; page_size?: number; status?: string }) => 
    apiClient.get<PaginatedResponse<RFQ>>('/admin/rfqs', { params }),
  
  getRFQ: (id: string) => 
    apiClient.get<RFQ>(`/admin/rfqs/${id}`),
  
  overrideRFQStatus: (id: string, status: string) => 
    apiClient.post<RFQ>(`/admin/rfqs/${id}/override-status`, { status }),
  
  // Payments
  listPayments: (params?: { page?: number; page_size?: number; status?: string }) => 
    apiClient.get<PaginatedResponse<PaymentAttempt>>('/admin/payments', { params }),
  
  // Webhooks
  listWebhooks: (params?: { page?: number; page_size?: number; provider?: string }) => 
    apiClient.get<PaginatedResponse<{ id: string; provider_name: string; event_type: string; processing_status: string; received_at: string }>>('/admin/webhooks', { params }),
  
  replayWebhook: (id: string) => 
    apiClient.post(`/admin/webhooks/${id}/replay`),
  
  // Tier Requests
  listTierRequests: (params?: { page?: number; page_size?: number; status?: string }) => 
    apiClient.get<PaginatedResponse<TierEvaluationRequest>>('/admin/tier-requests', { params }),
  
  approveTierRequest: (id: string) => 
    apiClient.post<TierEvaluationRequest>(`/admin/tier-requests/${id}/approve`),
  
  rejectTierRequest: (id: string, data?: { reason?: string }) => 
    apiClient.post<TierEvaluationRequest>(`/admin/tier-requests/${id}/reject`, data),
  
  // Ads
  listAds: (params?: { page?: number; page_size?: number; status?: string }) => 
    apiClient.get<PaginatedResponse<Advertisement>>('/admin/ads', { params }),
  
  pauseAd: (id: string) => 
    apiClient.post<Advertisement>(`/admin/ads/${id}/pause`),
  
  // Users
  listUsers: (queryString?: string) =>
    apiClient.get<any>(`/admin/users${queryString ? '?' + queryString : ''}`),

  suspendUser: (id: string) =>
    apiClient.post<any>(`/admin/users/${id}/suspend`),
  getConfig: () =>
    apiClient.get<any>('/admin/config'),
  saveConfig: (data: Record<string, string>) =>
    apiClient.post<any>('/admin/config', data),

  resetUserSearchQuota: (userId: string) =>
    apiClient.post<any>(`/admin/users/${userId}/reset-search-quota`),

  // Debug / Testing
  testEmail: (toEmail: string) =>
    apiClient.post<any>('/admin/debug/test-email', { to_email: toEmail }),
  checkResendDomains: () =>
    apiClient.get<any>('/admin/debug/resend-domains'),
  testNda: (customerName: string, customerEmail: string, providerName: string, providerEmail: string) =>
    apiClient.post<any>('/admin/debug/test-nda', {
      customer_name: customerName,
      customer_email: customerEmail,
      provider_name: providerName,
      provider_email: providerEmail,
    }),
  testNdaStatus: (documentId: string) =>
    apiClient.get<any>(`/admin/debug/test-nda/${documentId}/status`),
  testNdaVoid: (documentId: string) =>
    apiClient.post<any>(`/admin/debug/test-nda/${documentId}/void`),
  testSignwellConnection: () =>
    apiClient.get<any>('/admin/debug/test-signwell'),
};

// Webhooks (server-side only, usually)
const webhooks = {
  stripe: (payload: unknown, signature: string) => 
    apiClient.post('/webhooks/stripe', payload, { headers: { 'Stripe-Signature': signature } }),
  
  paypal: (payload: unknown) => 
    apiClient.post('/webhooks/paypal', payload),
  
  signrequest: (payload: unknown) => 
    apiClient.post('/webhooks/signrequest', payload),
};

// Export all API modules
export const api = {
  auth,
  search,
  providers,
  providerClaims,
  rfqs,
  providerRFQ,
  providerRfqAccess,
  quotes,
  providerProfile,
  ads,
  billing,
  admin,
  webhooks,
};

export default api;

// ── Customer RFQ API helpers ─────────────────────────────────────────────────
import type { CustomerRFQSummary, RFQTrackingData } from '@/types';

export const customerRfqApi = {
  getMyRfqs: async (): Promise<CustomerRFQSummary[]> => {
    const res = await fetch(`${API_URL}/rfqs/customer/my-rfqs`, {
      method: 'GET', credentials: 'include',
      headers: { 'Content-Type': 'application/json',  },
    });
    if (!res.ok) throw new Error(`getMyRfqs failed: ${res.status}`);
    return res.json();
  },
  getRfqTracking: async (rfqId: string): Promise<RFQTrackingData> => {
    const res = await fetch(`${API_URL}/rfqs/customer/rfqs/${rfqId}/tracking`, {
      method: 'GET', credentials: 'include',
      headers: { 'Content-Type': 'application/json',  },
    });
    if (!res.ok) throw new Error(`getRfqTracking failed: ${res.status}`);
    return res.json();
  },
};
