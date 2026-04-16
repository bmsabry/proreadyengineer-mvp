'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface WebhookEvent {
  id: string;
  provider_name: string;
  event_type: string;
  processing_status: string;
  received_at: string;
  processed_at?: string;
  error_message?: string;
}

interface PaginatedWebhooks {
  items: WebhookEvent[];
  total: number;
  page: number;
  page_size: number;
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, { label: string; className: string }> = {
    processed: { label: 'Processed', className: 'bg-green-100 text-green-800 border-green-200' },
    failed: { label: 'Failed', className: 'bg-red-100 text-red-800 border-red-200' },
    pending: { label: 'Pending', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
    processing: { label: 'Processing', className: 'bg-blue-100 text-blue-800 border-blue-200' },
  };
  const v = variants[status.toLowerCase()] || { label: status, className: 'bg-gray-100 text-gray-800' };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${v.className}`}>
      {v.label}
    </span>
  );
}

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

function truncateId(id: string): string {
  return id.length > 12 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
}

export default function AdminWebhooksPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);

  const [events, setEvents] = useState<WebhookEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [replaying, setReplaying] = useState<string | null>(null);
  const [replaySuccess, setReplaySuccess] = useState<string | null>(null);

  const fetchWebhooks = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params: Record<string, string | number> = { page: 1, page_size: 50 };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (providerFilter !== 'all') params.provider = providerFilter;

      const res = await api.admin.listWebhooks(params as { page?: number; page_size?: number; provider?: string });
      const data = res.data as unknown as PaginatedWebhooks | WebhookEvent[];

      if (Array.isArray(data)) {
        setEvents(data);
        setTotal(data.length);
      } else {
        setEvents(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Failed to load webhook events.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, providerFilter]);

  useEffect(() => {
    if (!authLoading) fetchWebhooks();
  }, [authLoading, fetchWebhooks]);

  const handleReplay = async (eventId: string) => {
    setReplaying(eventId);
    setReplaySuccess(null);
    try {
      await api.admin.replayWebhook(eventId);
      setReplaySuccess(eventId);
      setTimeout(() => setReplaySuccess(null), 3000);
      fetchWebhooks();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || `Failed to replay event ${truncateId(eventId)}.`);
    } finally {
      setReplaying(null);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  const statusCounts = events.reduce((acc, e) => {
    const s = e.processing_status.toLowerCase();
    // Map backend enum values to display categories
    if (s === 'completed') {
      acc.processed = (acc.processed || 0) + 1;
    } else if (s === 'failed') {
      acc.failed = (acc.failed || 0) + 1;
    } else {
      // received, verified, processing, retrying → all count as pending
      acc.pending = (acc.pending || 0) + 1;
    }
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Webhook Events</h1>
            <p className="text-gray-500 text-sm mt-1">Monitor and replay inbound webhook events</p>
          </div>
          <Button onClick={fetchWebhooks} variant="outline" disabled={loading}>
            {loading
              ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Loading...</>
              : <><RefreshCw className="mr-2 h-4 w-4" />Refresh</>}
          </Button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold">{total}</p>
              <p className="text-sm text-gray-500">Total Events</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-green-600">{statusCounts.processed || 0}</p>
              <p className="text-sm text-gray-500">Processed</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-yellow-600">{statusCounts.pending || 0}</p>
              <p className="text-sm text-gray-500">Pending</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-red-600">{statusCounts.failed || 0}</p>
              <p className="text-sm text-gray-500">Failed</p>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Filters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-700">Status:</span>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="processed">Processed</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-700">Provider:</span>
                <Select value={providerFilter} onValueChange={setProviderFilter}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="stripe">Stripe</SelectItem>
                    <SelectItem value="paypal">PayPal</SelectItem>
                    <SelectItem value="signrequest">SignRequest</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-md">
            <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Replay success */}
        {replaySuccess && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm text-green-700">Event replayed successfully.</p>
          </div>
        )}

        {/* Table */}
        <Card>
          <CardContent className="p-0">
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              </div>
            ) : events.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-gray-500">No webhook events found.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50 text-left">
                      <th className="px-4 py-3 font-medium text-gray-700">ID</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Provider</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Event Type</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Status</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Received At</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Processed At</th>
                      <th className="px-4 py-3 font-medium text-gray-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {events.map((event) => (
                      <tr key={event.id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3 font-mono text-xs text-gray-500">
                          {truncateId(event.id)}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className="capitalize text-xs">
                            {event.provider_name}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">{event.event_type}</td>
                        <td className="px-4 py-3">
                          <StatusBadge status={event.processing_status} />
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-600">{formatDate(event.received_at)}</td>
                        <td className="px-4 py-3 text-xs text-gray-600">{formatDate(event.processed_at)}</td>
                        <td className="px-4 py-3">
                          {event.processing_status.toLowerCase() === 'failed' && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleReplay(event.id)}
                              disabled={replaying === event.id}
                              className="text-xs"
                            >
                              {replaying === event.id
                                ? <><Loader2 className="mr-1 h-3 w-3 animate-spin" />Replaying</>
                                : <><Play className="mr-1 h-3 w-3" />Replay</>}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

      </div>
    </div>
  );
}
