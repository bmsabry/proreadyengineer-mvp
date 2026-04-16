'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQ } from '@/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow,
} from '@/components/ui/table';
import { formatDate, getRFQStatusBadgeColor } from '@/lib/utils';
import { AlertTriangle, Eye, RefreshCw, Wrench, XCircle } from 'lucide-react';

export default function AdminRFQsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [terminating, setTerminating] = useState<string | null>(null);
  const [terminateMessage, setTerminateMessage] = useState<{ id: string; text: string; ok: boolean } | null>(null);
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState<{ message: string; repaired_count: number; details: any[] } | null>(null);

  const fetchRFQs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.admin.listRFQs({ page: 1, page_size: 100 });
      setRfqs(response.data.items ?? []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to fetch RFQs.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading) fetchRFQs();
  }, [authLoading, fetchRFQs]);

  const handleTerminate = async (rfqId: string) => {
    if (!confirm('Terminate dispatch for this RFQ? No more provider emails will be sent.')) return;
    setTerminating(rfqId);
    setTerminateMessage(null);
    try {
      await api.admin.terminateRFQDispatch(rfqId);
      setTerminateMessage({ id: rfqId, text: 'Dispatch terminated successfully.', ok: true });
      await fetchRFQs();
    } catch (err: any) {
      setTerminateMessage({
        id: rfqId,
        text: err?.response?.data?.detail || 'Failed to terminate dispatch.',
        ok: false,
      });
    } finally {
      setTerminating(null);
    }
  };

  const handleRepairQuoteCounts = async () => {
    if (!confirm('Recalculate all RFQ quote_count values from actual quote records? This fixes any double-counting.')) return;
    setRepairing(true);
    setRepairResult(null);
    try {
      const response = await api.admin.repairQuoteCounts();
      setRepairResult(response.data);
      await fetchRFQs();
    } catch (err: any) {
      setRepairResult({ message: err?.response?.data?.detail || 'Repair failed.', repaired_count: -1, details: [] });
    } finally {
      setRepairing(false);
    }
  };

  const getUrgencyColor = (urgency: string) => {
    switch (urgency?.toLowerCase()) {
      case 'high': return 'bg-red-100 text-red-800 border-red-200';
      case 'intermediate': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low': return 'bg-green-100 text-green-800 border-green-200';
      default: return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">RFQ Management</h1>
          <p className="text-sm text-gray-500 mt-1">
            Track, manage, and terminate active RFQ dispatch flows
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchRFQs}
          disabled={isLoading}
          className="flex items-center gap-2"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
        <Button
          onClick={handleRepairQuoteCounts}
          disabled={repairing}
          variant="outline"
          size="sm"
          className="flex items-center gap-2 text-orange-600 border-orange-300 hover:bg-orange-50"
        >
          <Wrench className="h-4 w-4" />
          {repairing ? 'Repairing...' : 'Repair Quote Counts'}
        </Button>
      </div>
      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Repair feedback */}
      {repairResult && (
        <div className={`flex items-center gap-3 p-3 rounded-lg border text-sm ${
          repairResult.repaired_count >= 0
            ? 'bg-green-50 border-green-200 text-green-800'
            : 'bg-red-50 border-red-200 text-red-800'
        }`}>
          <span>{repairResult.message}</span>
          {repairResult.repaired_count > 0 && (
            <span className="font-medium">({repairResult.repaired_count} RFQs updated)</span>
          )}
          <button onClick={() => setRepairResult(null)} className="ml-auto text-gray-400 hover:text-gray-600">x</button>
        </div>
      )}
      {/* Terminate feedback */}
      {terminateMessage && (
        <div className={`flex items-center gap-3 p-4 rounded-lg border ${
          terminateMessage.ok
            ? 'bg-green-50 border-green-200 text-green-700'
            : 'bg-red-50 border-red-200 text-red-700'
        }`}>
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span>{terminateMessage.text}</span>
          <button
            className="ml-auto text-xs underline"
            onClick={() => setTerminateMessage(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Table Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            All RFQs
            {!isLoading && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({rfqs.length} total)
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-40">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
            </div>
          ) : rfqs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
              <XCircle className="h-10 w-10" />
              <p className="text-sm font-medium text-center">
                No RFQs found. RFQs appear here after customers submit quote requests.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Description</TableHead>
                    <TableHead>Customer Email</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Urgency</TableHead>
                    <TableHead className="text-center">Quotes</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rfqs.map((rfq) => (
                    <TableRow key={rfq.id}>
                      <TableCell className="max-w-xs">
                        <p className="truncate text-sm font-medium text-gray-900">
                          {rfq.project_description || '(no description)'}
                        </p>
                        {rfq.business_name && (
                          <p className="text-xs text-gray-500 truncate">{rfq.business_name}</p>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-gray-700">
                        {rfq.customer_email || '—'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          className={`text-xs whitespace-nowrap ${getRFQStatusBadgeColor(rfq.rfq_status)}`}
                        >
                          {rfq.rfq_status?.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`text-xs ${getUrgencyColor(rfq.urgency)}`}
                        >
                          {rfq.urgency || '—'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 text-blue-800 text-sm font-semibold">
                          {rfq.quote_count ?? 0}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-gray-600 whitespace-nowrap">
                        {rfq.created_at ? formatDate(rfq.created_at) : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            asChild
                            variant="outline"
                            size="sm"
                            className="flex items-center gap-1"
                          >
                            <Link href={`/admin/rfqs/${rfq.id}`}>
                              <Eye className="h-3.5 w-3.5" />
                              Dispatch Tracking
                            </Link>
                          </Button>
                          {!rfq.is_closed && (
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => handleTerminate(rfq.id)}
                              disabled={terminating === rfq.id}
                              className="flex items-center gap-1"
                            >
                              {terminating === rfq.id ? (
                                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <XCircle className="h-3.5 w-3.5" />
                              )}
                              Terminate
                            </Button>
                          )}
                          {rfq.is_closed && (
                            <Badge variant="outline" className="text-xs text-gray-500">
                              Closed
                            </Badge>
                          )}
                        </div>
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
