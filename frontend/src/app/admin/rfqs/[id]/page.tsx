'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { AdminRFQDispatchTracking, AdminDispatchProvider } from '@/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow,
} from '@/components/ui/table';
import { formatDate, getRFQStatusBadgeColor } from '@/lib/utils';
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Clock,
  RefreshCw, XCircle, Users, Mail, FileText, BarChart3,
} from 'lucide-react';

export default function AdminRFQDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isLoading: authLoading } = useRequireAuth(['admin']);
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
    try {
      const res = await api.admin.getRFQDispatchTracking(rfqId);
      setData(res.data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load RFQ tracking data.');
    } finally {
      setLoading(false);
    }
  }, [rfqId]);

  useEffect(() => {
    if (!authLoading && rfqId) fetchTracking();
  }, [authLoading, rfqId, fetchTracking]);

  const handleTerminate = async () => {
    if (!confirm('Stop all future dispatch for this RFQ? No more provider emails will be sent.')) return;
    setTerminating(true);
    setActionMessage(null);
    try {
      await api.admin.terminateRFQDispatch(rfqId);
      setActionMessage({ text: 'Dispatch terminated successfully.', ok: true });
      await fetchTracking();
    } catch (err: any) {
      setActionMessage({ text: err?.response?.data?.detail || 'Failed to terminate dispatch.', ok: false });
    } finally {
      setTerminating(false);
    }
  };

  const handleForceClose = async () => {
    if (!confirm('Force close this RFQ? This will stop all activity and mark it as closed.')) return;
    setForceClosing(true);
    setActionMessage(null);
    try {
      await api.admin.forceCloseRFQ(rfqId);
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

  const getUnlockStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800 border-green-200';
      case 'pending': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'failed': return 'bg-red-100 text-red-800 border-red-200';
      default: return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  const getQuoteStatusColor = (status: string) => {
    switch (status) {
      case 'submitted': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'accepted': return 'bg-green-100 text-green-800 border-green-200';
      case 'withdrawn': return 'bg-red-100 text-red-800 border-red-200';
      case 'draft': return 'bg-gray-100 text-gray-600 border-gray-200';
      default: return 'bg-gray-100 text-gray-600 border-gray-200';
    }
  };

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  const rfq = data?.rfq;
  const providers: AdminDispatchProvider[] = data?.providers ?? [];

  return (
    <div className="p-6 space-y-6">
      {/* Back + Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <Button variant="ghost" size="sm" onClick={() => router.push('/admin/rfqs')} className="flex items-center gap-2 -ml-2 mb-1 text-gray-500 hover:text-gray-700">
            <ArrowLeft className="h-4 w-4" />
            Back to RFQs
          </Button>
          <h1 className="text-2xl font-bold text-gray-900">RFQ Dispatch Tracking</h1>
          <p className="text-sm text-gray-500">Real-time view of dispatch batches, provider engagement, unlocks, and quotes</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {lastUpdated && <span className="text-xs text-gray-400">Updated {lastUpdated.toLocaleTimeString()}</span>}
          <Button variant="outline" size="sm" onClick={fetchTracking} className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          {rfq && !rfq.is_closed && (
            <>
              <Button variant="outline" size="sm" onClick={handleTerminate} disabled={terminating} className="flex items-center gap-2 border-orange-300 text-orange-700 hover:bg-orange-50">
                {terminating ? <RefreshCw className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                Stop Dispatch
              </Button>
              <Button variant="destructive" size="sm" onClick={handleForceClose} disabled={forceClosing} className="flex items-center gap-2">
                {forceClosing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                Force Close
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Action Message */}
      {actionMessage && (
        <div className={`flex items-center gap-3 p-4 rounded-lg border ${actionMessage.ok ? 'bg-green-50 border-green-200 text-green-700' : 'bg-red-50 border-red-200 text-red-700'}`}>
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{actionMessage.text}</span>
          <button className="ml-auto text-xs underline" onClick={() => setActionMessage(null)}>Dismiss</button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card><CardContent className="pt-5 pb-4"><div className="flex items-center gap-3"><div className="p-2 bg-blue-100 rounded-lg"><Users className="h-5 w-5 text-blue-600" /></div><div><p className="text-xs text-gray-500">Providers Dispatched</p><p className="text-2xl font-bold text-gray-900">{providers.length}</p></div></div></CardContent></Card>
        <Card><CardContent className="pt-5 pb-4"><div className="flex items-center gap-3"><div className="p-2 bg-green-100 rounded-lg"><Mail className="h-5 w-5 text-green-600" /></div><div><p className="text-xs text-gray-500">Emails Sent</p><p className="text-2xl font-bold text-gray-900">{providers.filter((p) => p.dispatch_status === 'sent').length}</p></div></div></CardContent></Card>
        <Card><CardContent className="pt-5 pb-4"><div className="flex items-center gap-3"><div className="p-2 bg-indigo-100 rounded-lg"><FileText className="h-5 w-5 text-indigo-600" /></div><div><p className="text-xs text-gray-500">Quotes Received</p><p className="text-2xl font-bold text-gray-900">{rfq?.quote_count ?? 0}</p></div></div></CardContent></Card>
        <Card><CardContent className="pt-5 pb-4"><div className="flex items-center gap-3"><div className="p-2 bg-purple-100 rounded-lg"><BarChart3 className="h-5 w-5 text-purple-600" /></div><div><p className="text-xs text-gray-500">Unlocks</p><p className="text-2xl font-bold text-gray-900">{providers.filter((p) => p.unlock_status === 'completed').length}</p></div></div></CardContent></Card>
      </div>

      {/* RFQ Details Card */}
      {rfq && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4" />
              RFQ Details
              <Badge className={`ml-2 text-xs ${getRFQStatusBadgeColor(rfq.rfq_status)}`}>{rfq.rfq_status?.replace(/_/g, ' ')}</Badge>
              {rfq.is_closed && <Badge variant="outline" className="text-xs text-gray-500">Closed</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-4 text-sm">
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Customer Email</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.customer_email || '—'}</dd></div>
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Business</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.business_name || '—'}</dd></div>
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Urgency</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.urgency || '—'}</dd></div>
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">NDA Required</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.nda_required ? 'Yes' : 'No'}</dd></div>
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Created</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.created_at ? formatDate(rfq.created_at) : '—'}</dd></div>
              <div><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Submitted</dt>
              <dd className='text-gray-900 mt-0.5'>{rfq.submitted_at ? formatDate(rfq.submitted_at) : '—'}</dd></div>
              <div className="md:col-span-3"><dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">Project Description</dt>
              <dd className='text-gray-900 mt-1 whitespace-pre-wrap line-clamp-4'>{rfq.project_description || '(none)'}</dd></div>
            </dl>
          </CardContent>
        </Card>
      )}

      {/* Dispatch Providers Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4" />
            Provider Dispatch Log
            {providers.length > 0 && (
              <span className="ml-1 text-sm font-normal text-gray-500">({providers.length} providers)</span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {providers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-gray-400 gap-2">
              <Users className="h-8 w-8" />
              <p className="text-sm">No providers dispatched yet.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Provider</TableHead>
                    <TableHead>Batch</TableHead>
                    <TableHead>Dispatch Status</TableHead>
                    <TableHead>Email Sent At</TableHead>
                    <TableHead>Unlock</TableHead>
                    <TableHead>Quote</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {providers.map((p) => (
                    <TableRow key={p.provider_id}>
                      <TableCell>
                        <div className="font-medium text-sm text-gray-900">
                          {p.provider_name || p.provider_id}
                        </div>
                        {p.email_target && (
                          <div className="text-xs text-gray-500 truncate max-w-xs">{p.email_target}</div>
                        )}
                      </TableCell>
                      <TableCell className='text-sm text-gray-600'>
                        {p.batch_number != null ? p.batch_number : '—'}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {getDispatchStatusIcon(p.dispatch_status)}
                          <Badge variant="outline" className={`text-xs ${getDispatchStatusColor(p.dispatch_status)}`}>
                            {p.dispatch_status || '—'}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 whitespace-nowrap">
                        {p.teaser_email_sent_at ? formatDate(p.teaser_email_sent_at) : '—'}
                      </TableCell>
                      <TableCell>
                        {p.unlock_status ? (
                          <Badge variant="outline" className={`text-xs ${getUnlockStatusColor(p.unlock_status)}`}>
                            {p.unlock_status}
                          </Badge>
                        ) : (
                          <span className='text-gray-400 text-xs'>—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {p.quote_status ? (
                          <Badge variant="outline" className={`text-xs ${getQuoteStatusColor(p.quote_status)}`}>
                            {p.quote_status}
                          </Badge>
                        ) : (
                          <span className='text-gray-400 text-xs'>—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
