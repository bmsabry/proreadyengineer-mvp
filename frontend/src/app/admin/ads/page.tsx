'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '../../../hooks/useAuth';
import { formatDate } from '../../../lib/utils';
import {
  Megaphone, CheckCircle, XCircle, Pause, Eye, BarChart3,
  Plus, Pencil, Trash2, Play, Loader2, ExternalLink,
  MousePointer, Search, Globe, FileText, Sparkles, AlertCircle, X,
} from 'lucide-react';

const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';

function getAuthHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

type TabKey = 'pending' | 'processing' | 'checkout_pending' | 'active' | 'all' | 'rejected' | 'paused';

interface Ad {
  id: string;
  title: string;
  promotional_text?: string | null;
  outbound_url?: string | null;
  page_type?: string | null;
  ad_status: string;
  provider_id?: number | null;
  advertiser_user_id?: string | null;
  llm_extracted_content?: Record<string, any> | null;
  source_website_url?: string | null;
  image_s3_key?: string | null;
  optional_price_text?: string | null;
  click_count?: number;
  impression_count?: number;
  admin_review_notes?: string | null;
  reviewed_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface ProviderOption {
  id: string;
  name: string;
  firm_name: string;
  website?: string | null;
}

interface Analytics {
  status_counts: Record<string, number>;
  total_clicks: number;
  total_impressions: number;
  ctr: number;
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  pending_review: 'bg-amber-100 text-amber-700',
  rejected: 'bg-red-100 text-red-700',
  paused: 'bg-slate-200 text-slate-600',
  cancelled: 'bg-slate-200 text-slate-600',
  expired: 'bg-slate-200 text-slate-600',
  empty: 'bg-slate-100 text-slate-500',
};

const STATUS_LABEL: Record<string, string> = {
  pending_review: 'Pending',
  reserved_checkout_pending: 'Checkout Pending',
};

export default function AdminAdsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);

  // --- State ---
  const [tab, setTab] = useState<TabKey>('pending');
  const [ads, setAds] = useState<Ad[]>([]);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  // Detail / review modal
  const [selectedAd, setSelectedAd] = useState<Ad | null>(null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewResult, setReviewResult] = useState<string | null>(null);

  // Edit modal
  const [editAd, setEditAd] = useState<Ad | null>(null);
  const [editForm, setEditForm] = useState<Record<string, any>>({});
  const [editLoading, setEditLoading] = useState(false);
  const [editResult, setEditResult] = useState<string | null>(null);

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    provider_id: '',
    page_type: 'software-providers',
    website_url: '',
    description_text: '',
    outbound_url: '',
  });
  const [providerSearch, setProviderSearch] = useState('');
  const [providerOptions, setProviderOptions] = useState<ProviderOption[]>([]);
  const [providerLoading, setProviderLoading] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<ProviderOption | null>(null);
  const [createLoading, setCreateLoading] = useState(false);
  const [createResult, setCreateResult] = useState<any>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  // Delete
  const [deleteTarget, setDeleteTarget] = useState<Ad | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Reject-and-notify (for pending ads): asks admin for a reason, backend
  // uses LLM3 to draft + send email to provider, and deletes the record.
  const [rejectTarget, setRejectTarget] = useState<Ad | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectLoading, setRejectLoading] = useState(false);
  const [rejectResult, setRejectResult] = useState<string | null>(null);

  // --- Fetchers ---
  const fetchAds = useCallback(async () => {
    setLoading(true);
    try {
      let url: string;
      if (tab === 'pending') {
        url = `${apiBase}/admin/ads/pending`;
      } else if (tab === 'processing') {
        url = `${apiBase}/admin/ads?status=processing`;
      } else if (tab === 'checkout_pending') {
        url = `${apiBase}/admin/ads?status=reserved_checkout_pending`;
      } else {
        const statusParam = tab === 'all' ? '' : `?status=${tab}`;
        url = `${apiBase}/admin/ads${statusParam}`;
      }
      const res = await fetch(url, { credentials: 'include', headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setAds(Array.isArray(data) ? data : (data.items ?? []));
      }
    } catch (err) {
      console.error('Failed to fetch ads:', err);
    } finally {
      setLoading(false);
    }
  }, [tab]);

  const fetchAnalytics = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/admin/ads/analytics`, {
        credentials: 'include', headers: getAuthHeaders(),
      });
      if (res.ok) setAnalytics(await res.json());
    } catch {}
  }, []);

  useEffect(() => { fetchAds(); fetchAnalytics(); }, [fetchAds, fetchAnalytics]);

  // Provider search for create modal
  const searchProviders = useCallback(async (q: string) => {
    if (q.length < 2) { setProviderOptions([]); return; }
    setProviderLoading(true);
    try {
      const res = await fetch(`${apiBase}/admin/providers?search=${encodeURIComponent(q)}&limit=10`, {
        credentials: 'include', headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setProviderOptions(data.providers ?? []);
      }
    } catch {} finally { setProviderLoading(false); }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchProviders(providerSearch), 300);
    return () => clearTimeout(timer);
  }, [providerSearch, searchProviders]);

  // --- Handlers ---
  const handleReview = async (ad: Ad, action: 'approve' | 'reject') => {
    setSelectedAd(ad);
    setReviewLoading(true);
    setReviewResult(null);
    try {
      const res = await fetch(`${apiBase}/admin/ads/${ad.id}/review`, {
        method: 'POST', credentials: 'include', headers: getAuthHeaders(),
        body: JSON.stringify({ action, notes: reviewNotes || null }),
      });
      if (res.ok) {
        const data = await res.json();
        setReviewResult(data.message);
        setTimeout(() => {
          setSelectedAd(null);
          setReviewNotes('');
          setReviewResult(null);
          if (action === 'approve') setTab('checkout_pending');
          fetchAds();
          fetchAnalytics();
        }, 1200);
      } else {
        const err = await res.json();
        setReviewResult(`Error: ${err.detail || 'Failed'}`);
      }
    } catch (err: any) {
      setReviewResult(`Error: ${err.message}`);
    } finally { setReviewLoading(false); }
  };

  const handlePause = async (adId: string) => {
    await fetch(`${apiBase}/admin/ads/${adId}/pause`, { method: 'POST', credentials: 'include', headers: getAuthHeaders() });
    fetchAds(); fetchAnalytics();
  };

  const handleReactivate = async (adId: string) => {
    await fetch(`${apiBase}/admin/ads/${adId}/reactivate`, { method: 'POST', credentials: 'include', headers: getAuthHeaders() });
    fetchAds(); fetchAnalytics();
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      await fetch(`${apiBase}/admin/ads/${deleteTarget.id}`, { method: 'DELETE', credentials: 'include', headers: getAuthHeaders() });
      setDeleteTarget(null);
      fetchAds(); fetchAnalytics();
    } catch {} finally { setDeleteLoading(false); }
  };

  const handleRejectAndNotify = async () => {
    if (!rejectTarget) return;
    if (!rejectReason.trim()) {
      setRejectResult('Please provide a reason — the provider will see this in their email.');
      return;
    }
    setRejectLoading(true);
    setRejectResult(null);
    try {
      const res = await fetch(`${apiBase}/admin/ads/${rejectTarget.id}/reject-and-notify`, {
        method: 'POST', credentials: 'include', headers: getAuthHeaders(),
        body: JSON.stringify({ reason: rejectReason }),
      });
      if (res.ok) {
        setRejectResult('Email drafted and sent. Ad removed.');
        setTimeout(() => {
          setRejectTarget(null);
          setRejectReason('');
          setRejectResult(null);
          setSelectedAd(null);
          fetchAds();
          fetchAnalytics();
        }, 1400);
      } else {
        const err = await res.json().catch(() => ({}));
        setRejectResult(`Error: ${err.detail || 'Rejection failed'}`);
      }
    } catch (e: any) {
      setRejectResult(`Error: ${e?.message || 'Network error'}`);
    } finally {
      setRejectLoading(false);
    }
  };

  const handleEditSave = async () => {
    if (!editAd) return;
    setEditLoading(true);
    setEditResult(null);
    try {
      const res = await fetch(`${apiBase}/admin/ads/${editAd.id}`, {
        method: 'PATCH', credentials: 'include', headers: getAuthHeaders(),
        body: JSON.stringify(editForm),
      });
      if (res.ok) {
        setEditResult('Saved');
        setTimeout(() => { setEditAd(null); setEditResult(null); fetchAds(); }, 800);
      } else {
        const err = await res.json();
        setEditResult(`Error: ${err.detail || 'Failed'}`);
      }
    } catch (err: any) { setEditResult(`Error: ${err.message}`); }
    finally { setEditLoading(false); }
  };

  const handleCreate = async () => {
    if (!selectedProvider) { setCreateError('Select a provider first.'); return; }
    setCreateLoading(true);
    setCreateError(null);
    setCreateResult(null);
    try {
      const res = await fetch(`${apiBase}/admin/ads/create`, {
        method: 'POST', credentials: 'include', headers: getAuthHeaders(),
        body: JSON.stringify({
          provider_id: parseInt(selectedProvider.id),
          page_type: createForm.page_type,
          website_url: createForm.website_url || selectedProvider.website || null,
          description_text: createForm.description_text || null,
          outbound_url: createForm.outbound_url || createForm.website_url || selectedProvider.website || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setCreateResult(data);
      } else {
        const err = await res.json();
        setCreateError(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
      }
    } catch (err: any) { setCreateError(err.message); }
    finally { setCreateLoading(false); }
  };

  const openEditModal = (ad: Ad) => {
    setEditAd(ad);
    setEditForm({
      title: ad.title,
      promotional_text: ad.promotional_text || '',
      outbound_url: ad.outbound_url || '',
      optional_price_text: ad.optional_price_text || '',
      page_type: ad.page_type || 'software-providers',
      admin_review_notes: ad.admin_review_notes || '',
    });
    setEditResult(null);
  };

  const resetCreateModal = () => {
    setShowCreate(false);
    setCreateForm({ provider_id: '', page_type: 'software-providers', website_url: '', description_text: '', outbound_url: '' });
    setProviderSearch('');
    setProviderOptions([]);
    setSelectedProvider(null);
    setCreateResult(null);
    setCreateError(null);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    );
  }

  const tabs: { key: TabKey; label: string; count?: number }[] = [
    { key: 'pending', label: 'Pending Review', count: analytics?.status_counts?.pending_review ?? 0 },
    { key: 'processing', label: 'Processing', count: analytics?.status_counts?.processing ?? 0 },
    { key: 'checkout_pending', label: 'Checkout Pending', count: analytics?.status_counts?.reserved_checkout_pending ?? 0 },
    { key: 'active', label: 'Active', count: analytics?.status_counts?.active ?? 0 },
    { key: 'paused', label: 'Paused', count: analytics?.status_counts?.paused ?? 0 },
    { key: 'rejected', label: 'Rejected', count: analytics?.status_counts?.rejected ?? 0 },
    { key: 'all', label: 'All' },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Megaphone className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold text-slate-900">Ad Management</h1>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Create Advertisement
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* Analytics Cards */}
        {analytics && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">Pending Review</p>
              <p className="text-2xl font-bold text-amber-600">{analytics.status_counts.pending_review ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">Active Ads</p>
              <p className="text-2xl font-bold text-emerald-600">{analytics.status_counts.active ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">Paused</p>
              <p className="text-2xl font-bold text-slate-500">{analytics.status_counts.paused ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-1.5 mb-1">
                <MousePointer className="h-3 w-3 text-slate-400" />
                <p className="text-xs text-slate-500">Total Clicks</p>
              </div>
              <p className="text-2xl font-bold text-blue-600">{analytics.total_clicks.toLocaleString()}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center gap-1.5 mb-1">
                <BarChart3 className="h-3 w-3 text-slate-400" />
                <p className="text-xs text-slate-500">CTR</p>
              </div>
              <p className="text-2xl font-bold text-violet-600">{analytics.ctr}%</p>
              <p className="text-[10px] text-slate-400">{analytics.total_impressions.toLocaleString()} impressions</p>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-white border border-slate-200 rounded-xl p-1 w-fit">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t.key ? 'bg-primary text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs ${tab === t.key ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-600'}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Ad List */}
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          {loading ? (
            <div className="p-12 text-center"><Loader2 className="h-6 w-6 animate-spin text-slate-400 mx-auto" /></div>
          ) : ads.length === 0 ? (
            <div className="p-12 text-center">
              <Megaphone className="h-8 w-8 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-500 mb-2">No ads found for this filter.</p>
              <button onClick={() => setShowCreate(true)} className="text-sm text-primary font-medium hover:underline">
                Create one now
              </button>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {ads.map(ad => {
                const content = ad.llm_extracted_content ?? {};
                const ctr = (ad.impression_count ?? 0) > 0
                  ? ((ad.click_count ?? 0) / (ad.impression_count ?? 1) * 100).toFixed(1)
                  : '0.0';
                return (
                  <div key={ad.id} className="p-5 hover:bg-slate-50/50 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        {/* Title row */}
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <h3 className="text-sm font-bold text-slate-900 truncate max-w-[300px]">{ad.title}</h3>
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${STATUS_COLORS[ad.ad_status] || 'bg-slate-100 text-slate-600'}`}>
                            {STATUS_LABEL[ad.ad_status] || ad.ad_status}
                          </span>
                          {ad.page_type && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                              {ad.page_type}
                            </span>
                          )}
                          {ad.provider_id && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">
                              Provider #{ad.provider_id}
                            </span>
                          )}
                        </div>

                        {/* Promo text preview */}
                        {ad.promotional_text && (
                          <p className="text-xs text-slate-500 line-clamp-1 mb-1">{ad.promotional_text}</p>
                        )}

                        {/* Meta row */}
                        <div className="flex items-center gap-4 text-[10px] text-slate-400 flex-wrap">
                          {ad.created_at && <span>Created {formatDate(ad.created_at)}</span>}
                          {ad.outbound_url && (
                            <a href={ad.outbound_url} target="_blank" rel="noopener" className="flex items-center gap-0.5 hover:text-slate-600">
                              <ExternalLink className="h-2.5 w-2.5" />
                              {(() => { try { return new URL(ad.outbound_url).hostname; } catch { return ad.outbound_url; } })()}
                            </a>
                          )}
                          <span className="flex items-center gap-0.5">
                            <MousePointer className="h-2.5 w-2.5" />
                            {ad.click_count ?? 0} clicks
                          </span>
                          <span>{ad.impression_count ?? 0} impr.</span>
                          <span>{ctr}% CTR</span>
                        </div>

                        {/* Specialties */}
                        {content.specialties?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {content.specialties.slice(0, 6).map((s: string, i: number) => (
                              <span key={i} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">{s}</span>
                            ))}
                            {content.specialties.length > 6 && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-400">+{content.specialties.length - 6}</span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button onClick={() => { setSelectedAd(ad); setReviewNotes(''); setReviewResult(null); }}
                          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50" title="View details">
                          <Eye className="h-4 w-4 text-slate-500" />
                        </button>
                        <button onClick={() => openEditModal(ad)}
                          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50" title="Edit">
                          <Pencil className="h-4 w-4 text-slate-500" />
                        </button>
                        {ad.ad_status === 'pending_review' && (
                          <button onClick={() => handleReview(ad, 'approve')}
                            className="p-2 rounded-lg bg-emerald-50 border border-emerald-200 hover:bg-emerald-100" title="Approve">
                            <CheckCircle className="h-4 w-4 text-emerald-600" />
                          </button>
                        )}
                        {ad.ad_status === 'active' && (
                          <button onClick={() => handlePause(ad.id)}
                            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50" title="Pause">
                            <Pause className="h-4 w-4 text-slate-500" />
                          </button>
                        )}
                        {['paused', 'rejected', 'cancelled'].includes(ad.ad_status) && (
                          <button onClick={() => handleReactivate(ad.id)}
                            className="p-2 rounded-lg bg-blue-50 border border-blue-200 hover:bg-blue-100" title="Reactivate">
                            <Play className="h-4 w-4 text-blue-600" />
                          </button>
                        )}
                        <button
                          onClick={() => {
                            if (ad.ad_status === 'pending_review') {
                              setRejectTarget(ad);
                              setRejectReason('');
                              setRejectResult(null);
                            } else {
                              setDeleteTarget(ad);
                            }
                          }}
                          className="p-2 rounded-lg border border-red-200 hover:bg-red-50"
                          title={ad.ad_status === 'pending_review' ? 'Reject & notify provider' : 'Delete'}>
                          <Trash2 className="h-4 w-4 text-red-400" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ===================== CREATE AD MODAL ===================== */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Create Advertisement</h2>
              <button onClick={resetCreateModal} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
            </div>

            {createResult ? (
              <div className="p-6 space-y-4">
                <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 p-3 rounded-xl">
                  <CheckCircle className="h-5 w-5" />
                  <p className="text-sm font-medium">{createResult.message}</p>
                </div>
                <div className="rounded-xl border p-4 bg-slate-50">
                  <p className="text-sm font-bold text-slate-900 mb-1">{createResult.title}</p>
                  {createResult.promotional_text && <p className="text-xs text-slate-600">{createResult.promotional_text}</p>}
                </div>
                <button
                  onClick={() => { resetCreateModal(); fetchAds(); fetchAnalytics(); }}
                  className="w-full py-2.5 rounded-xl bg-primary text-white text-sm font-medium hover:bg-primary/90"
                >
                  Done
                </button>
              </div>
            ) : (
              <div className="p-6 space-y-5">
                {/* Provider search */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                    <Search className="inline h-3.5 w-3.5 mr-1 text-slate-400" />
                    Select Provider
                  </label>
                  {selectedProvider ? (
                    <div className="flex items-center justify-between p-3 rounded-xl bg-blue-50 border border-blue-200">
                      <div>
                        <p className="text-sm font-bold text-slate-900">{selectedProvider.name}</p>
                        <p className="text-xs text-slate-500">{selectedProvider.firm_name} &middot; ID #{selectedProvider.id}</p>
                        {selectedProvider.website && <p className="text-xs text-blue-600">{selectedProvider.website}</p>}
                      </div>
                      <button onClick={() => { setSelectedProvider(null); setProviderSearch(''); }} className="text-xs text-blue-600 hover:underline">Change</button>
                    </div>
                  ) : (
                    <div className="relative">
                      <input
                        type="text"
                        value={providerSearch}
                        onChange={e => setProviderSearch(e.target.value)}
                        placeholder="Type firm name to search..."
                        className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
                      />
                      {providerLoading && <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-slate-400" />}
                      {providerOptions.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg z-10 max-h-48 overflow-y-auto">
                          {providerOptions.map(p => (
                            <button
                              key={p.id}
                              onClick={() => {
                                setSelectedProvider(p);
                                setProviderOptions([]);
                                if (p.website) setCreateForm(f => ({ ...f, website_url: p.website || '' }));
                              }}
                              className="w-full text-left px-4 py-2.5 hover:bg-slate-50 text-sm border-b border-slate-100 last:border-0"
                            >
                              <p className="font-medium text-slate-900">{p.name}</p>
                              <p className="text-xs text-slate-500">{p.firm_name} &middot; #{p.id}{p.website ? ` &middot; ${p.website}` : ''}</p>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Page type */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1.5">Ad Placement</label>
                  <div className="grid grid-cols-2 gap-3">
                    {(['software-providers', 'featured-firms'] as const).map(pt => (
                      <button key={pt} type="button"
                        onClick={() => setCreateForm(f => ({ ...f, page_type: pt }))}
                        className={`rounded-xl border-2 p-3 text-left transition-all ${createForm.page_type === pt ? 'border-violet-400 bg-violet-50' : 'border-slate-200 hover:border-slate-300'}`}>
                        <p className="text-sm font-bold text-slate-900">{pt === 'software-providers' ? 'Software Providers' : 'Featured Firms'}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Website URL */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1">
                    <Globe className="inline h-3.5 w-3.5 mr-1 text-slate-400" />
                    Website URL
                  </label>
                  <input type="url" value={createForm.website_url}
                    onChange={e => setCreateForm(f => ({ ...f, website_url: e.target.value }))}
                    placeholder="https://company.com"
                    className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
                  <p className="text-xs text-slate-400 mt-1">LLM will scrape this to generate ad content.</p>
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1">
                    <FileText className="inline h-3.5 w-3.5 mr-1 text-slate-400" />
                    Description / Brochure Text <span className="font-normal text-slate-400">(optional)</span>
                  </label>
                  <textarea value={createForm.description_text}
                    onChange={e => setCreateForm(f => ({ ...f, description_text: e.target.value }))}
                    rows={4} placeholder="Additional text to feed to the AI..."
                    className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
                </div>

                {/* Outbound URL */}
                <div>
                  <label className="block text-sm font-semibold text-slate-700 mb-1">Click-Through URL <span className="font-normal text-slate-400">(optional)</span></label>
                  <input type="url" value={createForm.outbound_url}
                    onChange={e => setCreateForm(f => ({ ...f, outbound_url: e.target.value }))}
                    placeholder="Defaults to website URL"
                    className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
                </div>

                {createError && (
                  <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200">
                    <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
                    <p className="text-sm text-red-700">{createError}</p>
                  </div>
                )}

                <button onClick={handleCreate} disabled={createLoading || !selectedProvider}
                  className="w-full py-3 rounded-xl bg-primary text-white text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 flex items-center justify-center gap-2">
                  {createLoading ? <><Loader2 className="h-4 w-4 animate-spin" />Generating with AI...</> : <><Sparkles className="h-4 w-4" />Create &amp; Auto-Approve</>}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ===================== VIEW DETAIL / REVIEW MODAL ===================== */}
      {selectedAd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Ad Details</h2>
              <button onClick={() => { setSelectedAd(null); setReviewResult(null); }} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
            </div>
            <div className="p-6 space-y-5">
              {/* Status + meta */}
              <div>
                <h3 className="text-base font-bold text-slate-900">{selectedAd.title}</h3>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_COLORS[selectedAd.ad_status] || 'bg-slate-100'}`}>
                    {STATUS_LABEL[selectedAd.ad_status] || selectedAd.ad_status}
                  </span>
                  {selectedAd.page_type && <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">{selectedAd.page_type}</span>}
                  {selectedAd.provider_id && <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">Provider #{selectedAd.provider_id}</span>}
                </div>
              </div>

              {/* Core fields */}
              {selectedAd.promotional_text && (
                <div><p className="text-xs font-semibold text-slate-500 mb-1">Promotional Text</p><p className="text-sm text-slate-700">{selectedAd.promotional_text}</p></div>
              )}
              {selectedAd.outbound_url && (
                <div><p className="text-xs font-semibold text-slate-500 mb-1">Outbound URL</p>
                  <a href={selectedAd.outbound_url} target="_blank" rel="noopener" className="text-sm text-blue-600 hover:underline flex items-center gap-1">
                    {selectedAd.outbound_url} <ExternalLink className="h-3 w-3" /></a></div>
              )}
              {selectedAd.source_website_url && (
                <div><p className="text-xs font-semibold text-slate-500 mb-1">Source Website</p><p className="text-sm text-slate-600">{selectedAd.source_website_url}</p></div>
              )}
              {selectedAd.optional_price_text && (
                <div><p className="text-xs font-semibold text-slate-500 mb-1">Price Text</p><p className="text-sm text-slate-700">{selectedAd.optional_price_text}</p></div>
              )}

              {/* Analytics */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-xl bg-slate-50 p-3 text-center">
                  <p className="text-lg font-bold text-blue-600">{selectedAd.click_count ?? 0}</p><p className="text-[10px] text-slate-500">Clicks</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 text-center">
                  <p className="text-lg font-bold text-slate-600">{selectedAd.impression_count ?? 0}</p><p className="text-[10px] text-slate-500">Impressions</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 text-center">
                  <p className="text-lg font-bold text-violet-600">
                    {(selectedAd.impression_count ?? 0) > 0 ? ((selectedAd.click_count ?? 0) / (selectedAd.impression_count ?? 1) * 100).toFixed(1) : '0.0'}%
                  </p><p className="text-[10px] text-slate-500">CTR</p>
                </div>
              </div>

              {/* Timestamps */}
              <div className="grid grid-cols-2 gap-3 text-xs text-slate-500">
                {selectedAd.created_at && <div><span className="font-semibold">Created:</span> {formatDate(selectedAd.created_at)}</div>}
                {selectedAd.started_at && <div><span className="font-semibold">Started:</span> {formatDate(selectedAd.started_at)}</div>}
                {selectedAd.reviewed_at && <div><span className="font-semibold">Reviewed:</span> {formatDate(selectedAd.reviewed_at)}</div>}
                {selectedAd.ended_at && <div><span className="font-semibold">Ended:</span> {formatDate(selectedAd.ended_at)}</div>}
              </div>

              {/* LLM Extracted Content */}
              {selectedAd.llm_extracted_content && Object.keys(selectedAd.llm_extracted_content).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-2">AI-Extracted Content</p>
                  <div className="rounded-xl border border-slate-200 p-4 bg-slate-50 space-y-3">
                    {selectedAd.llm_extracted_content.headline && (
                      <div><p className="text-xs text-slate-400">Headline</p><p className="text-sm font-bold text-slate-900">{selectedAd.llm_extracted_content.headline}</p></div>
                    )}
                    {selectedAd.llm_extracted_content.tagline && (
                      <div><p className="text-xs text-slate-400">Tagline</p><p className="text-sm text-violet-600">{selectedAd.llm_extracted_content.tagline}</p></div>
                    )}
                    {selectedAd.llm_extracted_content.value_proposition && (
                      <div><p className="text-xs text-slate-400">Value Proposition</p><p className="text-sm text-slate-700">{selectedAd.llm_extracted_content.value_proposition}</p></div>
                    )}
                    {selectedAd.llm_extracted_content.company_name && (
                      <div><p className="text-xs text-slate-400">Company Name</p><p className="text-sm text-slate-700">{selectedAd.llm_extracted_content.company_name}</p></div>
                    )}
                    {selectedAd.llm_extracted_content.specialties?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Specialties</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedAd.llm_extracted_content.specialties.map((s: string, i: number) => (
                            <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-violet-100 text-violet-700">{s}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.capabilities?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Capabilities</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedAd.llm_extracted_content.capabilities.map((c: string, i: number) => (
                            <span key={i} className="px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-600">{c}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.proof_points?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Proof Points</p>
                        <ul className="space-y-1">
                          {selectedAd.llm_extracted_content.proof_points.map((p: string, i: number) => (
                            <li key={i} className="flex items-start gap-1.5"><CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" /><span className="text-xs text-slate-600">{p}</span></li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.industry_keywords?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Search Keywords</p>
                        <div className="flex flex-wrap gap-1">
                          {selectedAd.llm_extracted_content.industry_keywords.map((k: string, i: number) => (
                            <span key={i} className="px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-600">{k}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.cta_label && (
                      <div><p className="text-xs text-slate-400">CTA Label</p><p className="text-sm text-slate-700">{selectedAd.llm_extracted_content.cta_label}</p></div>
                    )}
                    {selectedAd.llm_extracted_content.contact_info && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Contact Info</p>
                        <p className="text-xs text-slate-600">
                          {[selectedAd.llm_extracted_content.contact_info.phone, selectedAd.llm_extracted_content.contact_info.email, selectedAd.llm_extracted_content.contact_info.location].filter(Boolean).join(' | ')}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Review notes */}
              {selectedAd.admin_review_notes && (
                <div className="border-t border-slate-100 pt-3">
                  <p className="text-xs font-semibold text-slate-500 mb-1">Admin Notes</p>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{selectedAd.admin_review_notes}</p>
                </div>
              )}

              {/* Review actions for pending */}
              {selectedAd.ad_status === 'pending_review' && !reviewResult && (
                <div className="border-t border-slate-100 pt-4">
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5">Review Notes (optional)</label>
                  <textarea value={reviewNotes} onChange={e => setReviewNotes(e.target.value)} rows={2}
                    placeholder="Add notes..." className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
                  <div className="flex gap-3 mt-3">
                    <button onClick={() => handleReview(selectedAd, 'approve')} disabled={reviewLoading}
                      className="flex-1 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-60 flex items-center justify-center gap-2">
                      {reviewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />} Approve
                    </button>
                    <button
                      onClick={() => {
                        setRejectTarget(selectedAd);
                        setRejectReason(reviewNotes || '');
                        setRejectResult(null);
                      }}
                      disabled={reviewLoading}
                      className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60 flex items-center justify-center gap-2">
                      <XCircle className="h-4 w-4" /> Reject &amp; Notify
                    </button>
                  </div>
                </div>
              )}

              {reviewResult && (
                <div className={`p-3 rounded-xl text-sm font-medium ${reviewResult.startsWith('Error') ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
                  {reviewResult}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ===================== EDIT MODAL ===================== */}
      {editAd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900">Edit Ad</h2>
              <button onClick={() => { setEditAd(null); setEditResult(null); }} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Title</label>
                <input type="text" value={editForm.title || ''} onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Promotional Text</label>
                <textarea value={editForm.promotional_text || ''} onChange={e => setEditForm(f => ({ ...f, promotional_text: e.target.value }))} rows={3}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Outbound URL</label>
                <input type="url" value={editForm.outbound_url || ''} onChange={e => setEditForm(f => ({ ...f, outbound_url: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Price Text</label>
                <input type="text" value={editForm.optional_price_text || ''} onChange={e => setEditForm(f => ({ ...f, optional_price_text: e.target.value }))}
                  placeholder="e.g. $99/month" className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Page Type</label>
                <select value={editForm.page_type || ''} onChange={e => setEditForm(f => ({ ...f, page_type: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200">
                  <option value="software-providers">Software Providers</option>
                  <option value="featured-firms">Featured Firms</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Admin Notes</label>
                <textarea value={editForm.admin_review_notes || ''} onChange={e => setEditForm(f => ({ ...f, admin_review_notes: e.target.value }))} rows={2}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none" />
              </div>

              {editResult && (
                <div className={`p-3 rounded-xl text-sm font-medium ${editResult.startsWith('Error') ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'}`}>
                  {editResult}
                </div>
              )}

              <button onClick={handleEditSave} disabled={editLoading}
                className="w-full py-2.5 rounded-xl bg-primary text-white text-sm font-semibold hover:bg-primary/90 disabled:opacity-60 flex items-center justify-center gap-2">
                {editLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pencil className="h-4 w-4" />} Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===================== DELETE CONFIRMATION ===================== */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-sm w-full p-6">
            <h2 className="text-lg font-bold text-slate-900 mb-2">Delete Ad?</h2>
            <p className="text-sm text-slate-600 mb-1">This will permanently delete:</p>
            <p className="text-sm font-bold text-slate-900 mb-4">&ldquo;{deleteTarget.title}&rdquo;</p>
            <p className="text-xs text-red-500 mb-4">This action cannot be undone.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteTarget(null)}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleteLoading}
                className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60 flex items-center justify-center gap-2">
                {deleteLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ===================== REJECT & NOTIFY MODAL (pending ads) ===================== */}
      {rejectTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6">
            <h2 className="text-lg font-bold text-slate-900 mb-1">Reject &amp; Notify Provider</h2>
            <p className="text-sm text-slate-600 mb-1">This ad will be removed and an email (drafted by our AI from your reason) will be sent to the provider explaining the rejection and next steps.</p>
            <p className="text-sm font-semibold text-slate-900 mt-3 mb-1">&ldquo;{rejectTarget.title}&rdquo;</p>
            <label className="block text-xs font-semibold text-slate-500 mt-4 mb-1.5">
              Why is this ad being rejected? <span className="text-red-500">*</span>
            </label>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              rows={4}
              placeholder="e.g. The ad headline does not describe the firm's core services. Please resubmit with a headline that names the primary technical domains you cover."
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-200 resize-none"
            />
            <p className="text-xs text-slate-500 mt-1">The AI will rephrase this into a professional email — you can write it internally or bluntly.</p>
            {rejectResult && (
              <div className={`mt-3 p-3 rounded-xl text-sm font-medium ${rejectResult.startsWith('Error') ? 'bg-red-50 text-red-700' : rejectResult.startsWith('Please') ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
                {rejectResult}
              </div>
            )}
            <div className="flex gap-3 mt-5">
              <button
                onClick={() => { setRejectTarget(null); setRejectReason(''); setRejectResult(null); }}
                disabled={rejectLoading}
                className="flex-1 py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60">
                Cancel
              </button>
              <button
                onClick={handleRejectAndNotify}
                disabled={rejectLoading || !rejectReason.trim()}
                className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60 flex items-center justify-center gap-2">
                {rejectLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                Reject &amp; Send Email
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
