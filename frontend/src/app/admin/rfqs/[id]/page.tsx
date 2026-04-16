'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { AdminRFQDispatchTracking, AdminDispatchProvider } from '@/types';
import { CheckCircle2, XCircle, Clock, ArrowLeft, Trophy } from 'lucide-react';

export default function AdminRFQDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user, isLoading: authLoading } = useRequireAuth(['admin']);
  const rfqId = params.id as string;

  const [data, setData] = useState<AdminRFQDispatchTracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [terminating, setTerminating] = useState(false);
  const [forceClosing, setForceClosing] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchTracking = useCallback(async () => {
    if (!rfqId) return;
    setError(null);
    try {
      const res = await api.admin.getRFQDispatchTracking(rfqId);
      setData(res.data);
      setLastUpdated(new Date());
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

  // Auto-refresh every 10 seconds while RFQ is not closed
  useEffect(() => {
    if (!data || data.is_closed) return;
    const interval = setInterval(fetchTracking, 10000);
    return () => clearInterval(interval);
  }, [data, fetchTracking]);

  const handleTerminate = async () => {
    if (!confirm('Stop dispatch for this RFQ? No further provider emails will be sent.')) return;
    setTerminating(true);
    setActionMessage(null);
    try {
      await api.admin.terminateRFQDispatch(rfqId);
      setActionMessage({ text: 'Dispatch terminated. No further emails will be sent.', ok: true });
      await fetchTracking();
    } catch (err: any) {
      setActionMessage({ text: err?.response?.data?.detail || 'Failed to terminate dispatch.', ok: false });
    } finally {
      setTerminating(false);
    }
  };

  const handleForceClose = async () => {
    if (!confirm('Force close this RFQ? This will stop all activity and mark it as cancelled.')) return;
    setForceClosing(true);
    setActionMessage(null);
    try {
      await api.admin.overrideRFQStatus(rfqId, 'cancelled');
      setActionMessage({ text: 'RFQ force closed successfully.', ok: true });
      await fetchTracking();
    } catch (err: any) {
      setActionMessage({ text: err?.response?.data?.detail || 'Failed to force close RFQ.', ok: false });
    } finally {
      setForceClosing(false);
    }
  };

  const getDispatchStatusColor = (status: string) => {
    switch (status) {
      case 'sent': return 'bg-green-100 text-green-800 border-green-200';
      case 'pending': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'failed': return 'bg-red-100 text-red-800 border-red-200';
      case 'skipped': return 'bg-gray-100 text-gray-600 border-gray-200';
      default: return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  const getDispatchStatusIcon = (status: string) => {
    switch (status) {
      case 'sent': return <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />;
      case 'pending': return <Clock className="h-3.5 w-3.5 text-yellow-600" />;
      case 'failed': return <XCircle className="h-3.5 w-3.5 text-red-600" />;
      default: return <Clock className="h-3.5 w-3.5 text-gray-400" />;
    }
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

  const getRFQStatusColor = (status: string) => {
    switch (status) {
      case 'open_for_dispatch':
      case 'dispatching':
      case 'open_for_unlock': return 'bg-blue-100 text-blue-800';
      case 'quote_limit_reached':
      case 'customer_selected_provider': return 'bg-green-100 text-green-800';
      case 'cancelled':
      case 'closed_no_selection': return 'bg-red-100 text-red-800';
      case 'submitted': return 'bg-yellow-100 text-yellow-800';
      default: return 'bg-gray-100 text-gray-600';
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return '--';
    return new Date(iso).toLocaleString();
  };

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  const providers: AdminDispatchProvider[] = data?.providers ?? [];
  return (
    <div className="p-6 space-y-6">
      {/* Back + Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <button
            onClick={() => router.push('/admin/rfqs')}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 mb-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to RFQs
          </button>
          <h1 className="text-2xl font-bold text-gray-900">RFQ Dispatch Tracking</h1>
          {data && (
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${getRFQStatusColor(data.rfq_status)}`}>
                {data.rfq_status.replace(/_/g, ' ').toUpperCase()}
              </span>
              {lastUpdated && (
                <span className="text-xs text-gray-400">Updated {lastUpdated.toLocaleTimeString()}</span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchTracking}
            disabled={loading}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            Refresh
          </button>
          {data && !data.is_closed && (
            <>
              <button
                onClick={handleTerminate}
                disabled={terminating}
                className="px-3 py-1.5 text-sm bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50"
              >
                {terminating ? 'Stopping...' : 'Stop Dispatch'}
              </button>
              <button
                onClick={async () => {
                  setTerminating(true);
                  try {
                    await api.admin.forceDispatchRFQ(rfqId);
                    alert('Next batch dispatched successfully!');
                    fetchTracking();
                  } catch (e: any) {
                    alert('Error: ' + (e.response?.data?.detail || e.message));
                  } finally {
                    setTerminating(false);
                  }
                }}
                disabled={terminating}
                className="px-3 py-1.5 text-sm border border-blue-500 text-blue-700 rounded-md hover:bg-blue-50 disabled:opacity-50"
              >
                Force Next Batch
              </button>
              <button
                onClick={handleForceClose}
                disabled={forceClosing}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
              >
                {forceClosing ? 'Closing...' : 'Force Close RFQ'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Action messages */}
      {actionMessage && (
        <div className={`p-3 rounded-md text-sm ${actionMessage.ok ? 'bg-green-50 border border-green-200 text-green-800' : 'bg-red-50 border border-red-200 text-red-800'}`}>
          {actionMessage.text}
        </div>
      )}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-800 text-sm">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* RFQ Details Card */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">RFQ Details</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
              <div className="flex gap-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">RFQ ID:</span>
                <span className="text-sm font-mono text-gray-700 break-all">{data.rfq_id}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">Customer Email:</span>
                <span className="text-sm text-gray-900">{data.customer_email}</span>
              </div>
              {data.business_name && (
                <div className="flex gap-2">
                  <span className="text-xs text-gray-500 w-32 shrink-0">Business:</span>
                  <span className="text-sm text-gray-900">{data.business_name}</span>
                </div>
              )}
              <div className="flex gap-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">Urgency:</span>
                <span className="text-sm text-gray-900">{data.urgency || '--'}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">NDA Required:</span>
                <span className={`text-sm font-medium ${data.nda_required ? 'text-orange-600' : 'text-gray-600'}`}>
                  {data.nda_required ? 'Yes' : 'No'}
                </span>
              </div>
              <div className="flex gap-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">Submitted:</span>
                <span className="text-sm text-gray-700">{formatDate(data.submitted_at)}</span>
              </div>
              <div className="flex gap-2 md:col-span-2">
                <span className="text-xs text-gray-500 w-32 shrink-0">Description:</span>
                <span className="text-sm text-gray-700">{data.project_description}</span>
              </div>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Matches', value: data.total_matches, color: 'text-gray-900' },
              { label: 'Dispatched', value: data.total_contacted, color: 'text-blue-700' },
              { label: 'Quotes Received', value: data.total_quoted, color: 'text-green-700' },
              { label: 'Quote Limit', value: `${data.quote_count}/5`, color: 'text-purple-700' },
            ].map(stat => (
              <div key={stat.label} className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className={`text-3xl font-bold ${stat.color}`}>{stat.value}</div>
                <div className="text-xs text-gray-500 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>

          {/* Providers Table */}
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">Provider Dispatch Details</h2>
              <span className="text-xs text-gray-500">
                {providers.length} provider{providers.length !== 1 ? 's' : ''} matched
              </span>
            </div>
            {providers.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                No providers matched for this RFQ.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-2 text-left w-12">#</th>
                      <th className="px-4 py-2 text-left">Provider</th>
                      <th className="px-4 py-2 text-center w-14">Tier</th>
                      <th className="px-4 py-2 text-right w-16">Score</th>
                      <th className="px-4 py-2 text-left">Email</th>
                      <th className="px-4 py-2 text-center w-24">Status</th>
                      <th className="px-4 py-2 text-center w-16">Quoted</th>
                      <th className="px-4 py-2 text-center w-20">Accepted</th>
                      <th className="px-4 py-2 text-left w-44">Emailed At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {providers.map((p) => (
                      <tr key={p.provider_id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3 text-gray-400 text-xs font-mono">{p.rank_position}</td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{p.provider_name || 'Unknown Provider'}</div>
                          {(p.city || p.state) && (
                            <div className="text-xs text-gray-400 mt-0.5">
                              {[p.city, p.state].filter(Boolean).join(', ')}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {p.tier ? (
                            <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs ${getTierColor(p.tier)}`}>
                              {p.tier}
                            </span>
                          ) : (
                            <span className="text-gray-300 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right font-mono text-xs text-gray-700">
                          {p.composite_score != null ? p.composite_score.toFixed(1) : '--'}
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-600 max-w-[180px] truncate">{p.email_target || p.provider_email || '--'}</td>
                        <td className="px-4 py-3 text-center">
                          {p.dispatch_status ? (
                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${getDispatchStatusColor(p.dispatch_status)}`}>
                              {getDispatchStatusIcon(p.dispatch_status)}
                              {p.dispatch_status}
                            </span>
                          ) : (
                            <span className="text-gray-300 text-xs">not sent</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {p.submitted_quote ? (
                            <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                          ) : (
                            <span className="text-gray-200 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {p.is_accepted ? (
                            <Trophy className="h-4 w-4 text-yellow-500 mx-auto" />
                          ) : (
                            <span className="text-gray-200 text-xs">--</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-500">{formatDate(p.teaser_email_sent_at)}</td>
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
  );
}
