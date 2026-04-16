'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '../../../hooks/useAuth';
import { formatDate } from '../../../lib/utils';
import {
  Megaphone, CheckCircle, XCircle, Pause, Eye, BarChart3,
  ArrowRight, Clock, Loader2, ExternalLink, MousePointer,
} from 'lucide-react';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'https://proreadyengineer-api.onrender.com/api/v1';

function getAuthHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

type TabKey = 'pending' | 'active' | 'all' | 'rejected';

interface Ad {
  id: string;
  title: string;
  promotional_text?: string | null;
  outbound_url?: string | null;
  page_type?: string | null;
  ad_status: string;
  llm_extracted_content?: Record<string, any> | null;
  source_website_url?: string | null;
  click_count?: number;
  impression_count?: number;
  admin_review_notes?: string | null;
  reviewed_at?: string | null;
  started_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface Analytics {
  status_counts: Record<string, number>;
  total_clicks: number;
  total_impressions: number;
  ctr: number;
}

export default function AdminAdsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [tab, setTab] = useState<TabKey>('pending');
  const [ads, setAds] = useState<Ad[]>([]);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [selectedAd, setSelectedAd] = useState<Ad | null>(null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewResult, setReviewResult] = useState<string | null>(null);

  const fetchAds = useCallback(async () => {
    setLoading(true);
    try {
      let url: string;
      if (tab === 'pending') {
        url = `${apiBase}/admin/ads/pending`;
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
        credentials: 'include',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setAnalytics(await res.json());
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchAds();
    fetchAnalytics();
  }, [fetchAds, fetchAnalytics]);

  const handleReview = async (action: 'approve' | 'reject') => {
    if (!selectedAd) return;
    setReviewLoading(true);
    setReviewResult(null);
    try {
      const res = await fetch(`${apiBase}/admin/ads/${selectedAd.id}/review`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders(),
        body: JSON.stringify({ action, notes: reviewNotes || null }),
      });
      if (res.ok) {
        const data = await res.json();
        setReviewResult(data.message);
        // Refresh
        setTimeout(() => {
          setSelectedAd(null);
          setReviewNotes('');
          setReviewResult(null);
          fetchAds();
          fetchAnalytics();
        }, 1500);
      } else {
        const err = await res.json();
        setReviewResult(`Error: ${err.detail || 'Failed'}`);
      }
    } catch (err: any) {
      setReviewResult(`Error: ${err.message}`);
    } finally {
      setReviewLoading(false);
    }
  };

  const handlePause = async (adId: string) => {
    try {
      await fetch(`${apiBase}/admin/ads/${adId}/pause`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders(),
      });
      fetchAds();
    } catch {}
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
    { key: 'active', label: 'Active', count: analytics?.status_counts?.active ?? 0 },
    { key: 'rejected', label: 'Rejected', count: analytics?.status_counts?.rejected ?? 0 },
    { key: 'all', label: 'All' },
  ];

  const statusColor = (s: string) => {
    switch (s) {
      case 'active': return 'bg-emerald-100 text-emerald-700';
      case 'pending_review': return 'bg-amber-100 text-amber-700';
      case 'rejected': return 'bg-red-100 text-red-700';
      case 'paused': return 'bg-slate-200 text-slate-600';
      default: return 'bg-slate-100 text-slate-600';
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <div className="flex items-center gap-3">
            <Megaphone className="h-6 w-6 text-[#0F2B54]" />
            <h1 className="text-xl font-bold text-slate-900">Ad Management</h1>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* Analytics Cards */}
        {analytics && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">Pending Review</p>
              <p className="text-2xl font-bold text-amber-600">{analytics.status_counts.pending_review ?? 0}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <p className="text-xs text-slate-500 mb-1">Active Ads</p>
              <p className="text-2xl font-bold text-emerald-600">{analytics.status_counts.active ?? 0}</p>
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
                tab === t.key
                  ? 'bg-[#0F2B54] text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className={`ml-1.5 px-1.5 py-0.5 rounded-full text-xs ${
                  tab === t.key ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-600'
                }`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Ad List */}
        <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400 mx-auto" />
            </div>
          ) : ads.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-sm text-slate-500">No ads found for this filter.</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {ads.map(ad => {
                const content = ad.llm_extracted_content ?? {};
                return (
                  <div key={ad.id} className="p-5 hover:bg-slate-50 transition-colors">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-sm font-bold text-slate-900 truncate">{ad.title}</h3>
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${statusColor(ad.ad_status)}`}>
                            {ad.ad_status === 'pending_review' ? 'Pending' : ad.ad_status}
                          </span>
                          {ad.page_type && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
                              {ad.page_type}
                            </span>
                          )}
                        </div>
                        {ad.promotional_text && (
                          <p className="text-xs text-slate-500 line-clamp-1 mb-1">{ad.promotional_text}</p>
                        )}
                        <div className="flex items-center gap-4 text-[10px] text-slate-400">
                          {ad.created_at && <span>Created {formatDate(ad.created_at)}</span>}
                          {ad.outbound_url && (
                            <a href={ad.outbound_url} target="_blank" rel="noopener" className="flex items-center gap-0.5 hover:text-slate-600">
                              <ExternalLink className="h-2.5 w-2.5" /> {new URL(ad.outbound_url).hostname}
                            </a>
                          )}
                          {(ad.click_count ?? 0) > 0 && (
                            <span>{ad.click_count} clicks</span>
                          )}
                          {(ad.impression_count ?? 0) > 0 && (
                            <span>{ad.impression_count} impressions</span>
                          )}
                        </div>
                        {/* Specialties preview */}
                        {content.specialties?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {content.specialties.slice(0, 5).map((s: string, i: number) => (
                              <span key={i} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">{s}</span>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => { setSelectedAd(ad); setReviewNotes(''); setReviewResult(null); }}
                          className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
                          title="View details"
                        >
                          <Eye className="h-4 w-4 text-slate-500" />
                        </button>
                        {ad.ad_status === 'pending_review' && (
                          <>
                            <button
                              onClick={() => { setSelectedAd(ad); setReviewNotes(''); setReviewResult(null); handleReview('approve'); }}
                              className="p-2 rounded-lg bg-emerald-50 border border-emerald-200 hover:bg-emerald-100 transition-colors"
                              title="Quick approve"
                            >
                              <CheckCircle className="h-4 w-4 text-emerald-600" />
                            </button>
                          </>
                        )}
                        {ad.ad_status === 'active' && (
                          <button
                            onClick={() => handlePause(ad.id)}
                            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors"
                            title="Pause ad"
                          >
                            <Pause className="h-4 w-4 text-slate-500" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Review Modal */}
      {selectedAd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-100">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-slate-900">Ad Review</h2>
                <button
                  onClick={() => { setSelectedAd(null); setReviewResult(null); }}
                  className="text-slate-400 hover:text-slate-600 text-xl"
                >
                  &times;
                </button>
              </div>
            </div>

            <div className="p-6 space-y-5">
              {/* Ad info */}
              <div>
                <h3 className="text-base font-bold text-slate-900">{selectedAd.title}</h3>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${statusColor(selectedAd.ad_status)}`}>
                    {selectedAd.ad_status}
                  </span>
                  {selectedAd.page_type && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">{selectedAd.page_type}</span>
                  )}
                </div>
              </div>

              {selectedAd.promotional_text && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Promotional Text</p>
                  <p className="text-sm text-slate-700">{selectedAd.promotional_text}</p>
                </div>
              )}

              {selectedAd.outbound_url && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Outbound URL</p>
                  <a href={selectedAd.outbound_url} target="_blank" rel="noopener" className="text-sm text-blue-600 hover:underline flex items-center gap-1">
                    {selectedAd.outbound_url} <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}

              {selectedAd.source_website_url && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-1">Source Website</p>
                  <p className="text-sm text-slate-600">{selectedAd.source_website_url}</p>
                </div>
              )}

              {/* LLM extracted content */}
              {selectedAd.llm_extracted_content && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 mb-2">AI-Extracted Content</p>
                  <div className="rounded-xl border border-slate-200 p-4 bg-slate-50 space-y-3">
                    {selectedAd.llm_extracted_content.headline && (
                      <div>
                        <p className="text-xs text-slate-400">Headline</p>
                        <p className="text-sm font-bold text-slate-900">{selectedAd.llm_extracted_content.headline}</p>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.tagline && (
                      <div>
                        <p className="text-xs text-slate-400">Tagline</p>
                        <p className="text-sm text-violet-600">{selectedAd.llm_extracted_content.tagline}</p>
                      </div>
                    )}
                    {selectedAd.llm_extracted_content.value_proposition && (
                      <div>
                        <p className="text-xs text-slate-400">Value Proposition</p>
                        <p className="text-sm text-slate-700">{selectedAd.llm_extracted_content.value_proposition}</p>
                      </div>
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
                    {selectedAd.llm_extracted_content.proof_points?.length > 0 && (
                      <div>
                        <p className="text-xs text-slate-400 mb-1">Proof Points</p>
                        <ul className="space-y-1">
                          {selectedAd.llm_extracted_content.proof_points.map((p: string, i: number) => (
                            <li key={i} className="flex items-start gap-1.5">
                              <CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
                              <span className="text-xs text-slate-600">{p}</span>
                            </li>
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
                  </div>
                </div>
              )}

              {/* Review actions */}
              {selectedAd.ad_status === 'pending_review' && !reviewResult && (
                <div className="border-t border-slate-100 pt-4">
                  <label className="block text-xs font-semibold text-slate-500 mb-1.5">Admin Notes (optional)</label>
                  <textarea
                    value={reviewNotes}
                    onChange={e => setReviewNotes(e.target.value)}
                    rows={2}
                    placeholder="Add notes about your decision..."
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 resize-none"
                  />
                  <div className="flex gap-3 mt-3">
                    <button
                      onClick={() => handleReview('approve')}
                      disabled={reviewLoading}
                      className="flex-1 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
                    >
                      {reviewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
                      Approve
                    </button>
                    <button
                      onClick={() => handleReview('reject')}
                      disabled={reviewLoading}
                      className="flex-1 py-2.5 rounded-xl bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-60 transition-colors flex items-center justify-center gap-2"
                    >
                      {reviewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                      Reject
                    </button>
                  </div>
                </div>
              )}

              {/* Review result */}
              {reviewResult && (
                <div className={`p-3 rounded-xl text-sm font-medium ${
                  reviewResult.startsWith('Error')
                    ? 'bg-red-50 text-red-700'
                    : 'bg-emerald-50 text-emerald-700'
                }`}>
                  {reviewResult}
                </div>
              )}

              {/* Existing review info */}
              {selectedAd.admin_review_notes && (
                <div className="border-t border-slate-100 pt-3">
                  <p className="text-xs font-semibold text-slate-500 mb-1">Previous Review Notes</p>
                  <p className="text-sm text-slate-600">{selectedAd.admin_review_notes}</p>
                  {selectedAd.reviewed_at && (
                    <p className="text-[10px] text-slate-400 mt-1">Reviewed {formatDate(selectedAd.reviewed_at)}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
