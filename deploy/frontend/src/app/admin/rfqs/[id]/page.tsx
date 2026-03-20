'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { AdminRFQDispatchTracking, AdminDispatchProvider } from '@/types';

export default function AdminRFQDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user, loading: authLoading } = useRequireAuth(['admin']);
  const rfqId = params.id as string;

  const [data, setData] = useState<AdminRFQDispatchTracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [terminating, setTerminating] = useState(false);
  const [terminateSuccess, setTerminateSuccess] = useState(false);

  const fetchTracking = useCallback(async () => {
    if (!rfqId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.admin.getRFQDispatchTracking(rfqId);
      setData(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load RFQ tracking data');
    } finally {
      setLoading(false);
    }
  }, [rfqId]);

  useEffect(() => {
    if (!authLoading && user) {
      fetchTracking();
    }
  }, [authLoading, user, fetchTracking]);

  const handleTerminate = async () => {
    if (!rfqId) return;
    if (!confirm('Are you sure you want to terminate dispatch for this RFQ? This will stop all future provider emails.')) return;
    setTerminating(true);
    try {
      await api.admin.terminateRFQDispatch(rfqId);
      setTerminateSuccess(true);
      await fetchTracking();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to terminate dispatch');
    } finally {
      setTerminating(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'quoted': return 'bg-green-100 text-green-800 border border-green-200';
      case 'sent': return 'bg-blue-100 text-blue-800 border border-blue-200';
      case 'failed': return 'bg-red-100 text-red-800 border border-red-200';
      case 'pending': return 'bg-gray-100 text-gray-600 border border-gray-200';
      case 'opened': return 'bg-purple-100 text-purple-800 border border-purple-200';
      default: return 'bg-gray-100 text-gray-600 border border-gray-200';
    }
  };

  const getRFQStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'open_for_dispatch':
      case 'dispatching':
      case 'open_for_unlock': return 'bg-blue-100 text-blue-800';
      case 'quote_limit_reached':
      case 'customer_selected_provider': return 'bg-green-100 text-green-800';
      case 'cancelled':
      case 'closed_no_selection': return 'bg-red-100 text-red-800';
      case 'submitted': return 'bg-yellow-100 text-yellow-800';
      case 'awaiting_nda_payment':
      case 'awaiting_customer_signature': return 'bg-orange-100 text-orange-800';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
  };

  const getTierColor = (tier: string | null) => {
    switch (tier) {
      case 'A': return 'bg-emerald-100 text-emerald-800 font-bold';
      case 'B': return 'bg-blue-100 text-blue-800 font-bold';
      case 'C': return 'bg-yellow-100 text-yellow-800 font-bold';
      case 'D': return 'bg-orange-100 text-orange-800 font-bold';
      case 'E': return 'bg-red-100 text-red-800 font-bold';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">Checking authentication...</div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => router.push('/admin')} className="text-gray-500 hover:text-gray-700 transition-colors">
                &#8592; Back to Admin
              </button>
              <span className="text-gray-300">|</span>
              <h1 className="text-xl font-semibold text-gray-900">RFQ Dispatch Tracking</h1>
              {data && (
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${getRFQStatusColor(data.rfq_status)}`}>
                  {data.rfq_status.replace(/_/g, ' ').toUpperCase()}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={fetchTracking} disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
                &#8635; {loading ? 'Refreshing...' : 'Refresh'}
              </button>
              {data && !data.is_closed && (
                <button onClick={handleTerminate} disabled={terminating}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50">
                  &#9632; {terminating ? 'Terminating...' : 'Terminate Dispatch'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {terminateSuccess && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-md text-green-800 text-sm">
            &#10003; RFQ dispatch has been terminated. No further provider emails will be sent.
          </div>
        )}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-800 text-sm">
            &#9888; {error}
          </div>
        )}
        {loading && !data && (
          <div className="flex items-center justify-center py-20">
            <div className="text-gray-500">Loading dispatch tracking data...</div>
          </div>
        )}
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="bg-white rounded-lg border border-gray-200 p-4 md:col-span-2">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">RFQ Details</h2>
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">RFQ ID:</span>
                    <span className="text-sm font-mono text-gray-700 break-all">{data.rfq_id}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">Customer Email:</span>
                    <span className="text-sm text-gray-900">{data.customer_email}</span>
                  </div>
                  {data.business_name && (
                    <div className="flex items-start gap-2">
                      <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">Business:</span>
                      <span className="text-sm text-gray-900">{data.business_name}</span>
                    </div>
                  )}
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">Description:</span>
                    <span className="text-sm text-gray-700 line-clamp-3">{data.project_description}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">Urgency:</span>
                    <span className="text-sm text-gray-900">{data.urgency || '—'}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">NDA Required:</span>
                    <span className={`text-sm font-medium ${data.nda_required ? 'text-orange-600' : 'text-gray-600'}`}>
                      {data.nda_required ? 'Yes' : 'No'}
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-xs text-gray-500 w-28 shrink-0 pt-0.5">Submitted:</span>
                    <span className="text-sm text-gray-700">{formatDate(data.submitted_at)}</span>
                  </div>
                </div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Stats</h2>
                <div className="space-y-4">
                  <div className="text-center p-3 bg-gray-50 rounded-lg">
                    <div className="text-3xl font-bold text-gray-900">{data.total_matches}</div>
                    <div className="text-xs text-gray-500 mt-1">Total Matches</div>
                  </div>
                  <div className="text-center p-3 bg-blue-50 rounded-lg">
                    <div className="text-3xl font-bold text-blue-700">{data.total_contacted}</div>
                    <div className="text-xs text-gray-500 mt-1">Providers Contacted</div>
                  </div>
                  <div className="text-center p-3 bg-green-50 rounded-lg">
                    <div className="text-3xl font-bold text-green-700">{data.total_quoted}</div>
                    <div className="text-xs text-gray-500 mt-1">Quotes Received</div>
                  </div>
                  <div className="text-center p-3 bg-purple-50 rounded-lg">
                    <div className="text-3xl font-bold text-purple-700">{data.quote_count}/5</div>
                    <div className="text-xs text-gray-500 mt-1">Quote Limit</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-700">Provider Dispatch Details</h2>
                <span className="text-xs text-gray-500">{data.providers.length} providers</span>
              </div>
              {data.providers.length === 0 ? (
                <div className="p-8 text-center text-gray-500 text-sm">No providers dispatched yet.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rank</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Provider</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Tier</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Score</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Batch</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email Status</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Unlocked</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quoted</th>
                        <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Dispatched At</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {data.providers.map((p: AdminDispatchProvider, idx: number) => (
                        <tr key={p.provider_id} className={idx % 2 === 0 ? '' : 'bg-gray-50'}>
                          <td className="px-4 py-3 text-gray-500 font-mono">{p.rank_position}</td>
                          <td className="px-4 py-3">
                            <div className="font-medium text-gray-900">{p.provider_name}</div>
                            {p.primary_specialty && (
                              <div className="text-xs text-gray-500">{p.primary_specialty}</div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {p.tier ? (
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${getTierColor(p.tier)}`}>
                                Tier {p.tier}
                              </span>
                            ) : (
                              <span className="text-gray-400 text-xs">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-700 font-mono">
                            {p.composite_score !== null ? p.composite_score.toFixed(1) : '—'}
                          </td>
                          <td className="px-4 py-3 text-gray-600">
                            {p.batch_number !== null ? `Batch ${p.batch_number}` : '—'}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(p.dispatch_status)}`}>
                              {p.dispatch_status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.has_unlocked ? (
                              <span className="text-green-600 text-base">&#10003;</span>
                            ) : (
                              <span className="text-gray-300 text-base">&#10007;</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-center">
                            {p.has_quoted ? (
                              <span className="text-green-600 text-base">&#10003;</span>
                            ) : (
                              <span className="text-gray-300 text-base">&#10007;</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                            {formatDate(p.teaser_email_sent_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
