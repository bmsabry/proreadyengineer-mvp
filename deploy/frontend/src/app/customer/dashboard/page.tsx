'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Search, FileText, MessageSquare, Users, Clock, ChevronRight, AlertCircle, Activity } from 'lucide-react';

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const h: Record<string, string> = {};
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

interface CustomerRFQ {
  id: string;
  project_description: string;
  rfq_status: string;
  urgency: string | null;
  nda_required: boolean;
  quote_count: number;
  is_closed: boolean;
  business_name: string | null;
  contact_name: string | null;
  created_at: string | null;
  submitted_at: string | null;
  total_matched: number;
  dispatched_count: number;
  remaining_count: number;
}

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700 border-gray-200',
  submitted: 'bg-blue-100 text-blue-700 border-blue-200',
  open_for_dispatch: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  dispatching: 'bg-orange-100 text-orange-700 border-orange-200',
  open_for_unlock: 'bg-purple-100 text-purple-700 border-purple-200',
  quote_limit_reached: 'bg-green-100 text-green-700 border-green-200',
  customer_selected_provider: 'bg-teal-100 text-teal-700 border-teal-200',
  closed_no_selection: 'bg-red-100 text-red-700 border-red-200',
  cancelled: 'bg-gray-200 text-gray-500 border-gray-300',
  awaiting_nda_payment: 'bg-pink-100 text-pink-700 border-pink-200',
  awaiting_customer_signature: 'bg-indigo-100 text-indigo-700 border-indigo-200',
};

function formatStatus(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(d: string | null): string {
  if (!d) return '';
  try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch { return ''; }
}
export default function CustomerDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const router = useRouter();
  const [rfqs, setRfqs] = useState<CustomerRFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    const load = async () => {
      try {
        const base = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';
        const res = await fetch(base + '/customer/my-rfqs', {
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        });
        if (!res.ok) { setLoadError('Server returned ' + res.status); return; }
        const data = await res.json();
        setRfqs(Array.isArray(data) ? data : (data.items ?? []));
      } catch (e) {
        console.error(e);
        setLoadError('Network error — please refresh.');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, [user]);

  if (authLoading || isLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-3" />
            <p className="text-muted-foreground">Loading your RFQs...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-5xl">
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Customer Dashboard</h1>
          <p className="text-muted-foreground mt-1">Manage your RFQs and track incoming quotes</p>
        </div>
        <Button onClick={() => router.push('/')} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700">
          <Search className="h-4 w-4" />
          New RFQ
        </Button>
      </div>

      {loadError && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
          <p className="text-sm text-red-700 flex-1">{loadError}</p>
          <button onClick={() => window.location.reload()} className="text-sm underline text-red-700">Retry</button>
        </div>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-xl">
            <FileText className="h-5 w-5 text-blue-600" />
            Your RFQs
          </CardTitle>
          <CardDescription>
            {rfqs.length > 0
              ? rfqs.length + ' request' + (rfqs.length !== 1 ? 's' : '') + ' — click any card to view details and quotes'
              : 'Track the status of your requests for quotes'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {rfqs.length === 0 ? (
            <div className="text-center py-14">
              <FileText className="mx-auto h-12 w-12 text-muted-foreground/40 mb-4" />
              <p className="text-lg font-medium text-muted-foreground mb-1">No RFQs yet</p>
              <p className="text-sm text-muted-foreground mb-5">Start by searching for engineering providers to submit your first request.</p>
              <Button onClick={() => router.push('/')} className="flex items-center gap-2 mx-auto bg-blue-600 hover:bg-blue-700">
                <Search className="h-4 w-4" />
                Search &amp; Create RFQ
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {rfqs.map((rfq) => (
                <Link key={rfq.id} href={'/customer/rfq/' + rfq.id} className="block">
                  <div className="border rounded-xl p-5 hover:border-blue-300 hover:bg-blue-50/30 hover:shadow-sm transition-all cursor-pointer group">
                    <div className="flex items-start justify-between gap-4 mb-4">
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-gray-900 group-hover:text-blue-700 transition-colors line-clamp-2 leading-snug">
                          {rfq.project_description}
                        </p>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                          {rfq.created_at && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Clock className="h-3 w-3" />{formatDate(rfq.created_at)}
                            </span>
                          )}
                          {rfq.urgency && (
                            <span className={'text-xs font-medium ' + (rfq.urgency === 'High' ? 'text-red-600' : rfq.urgency === 'Intermediate' ? 'text-yellow-600' : 'text-green-600')}>
                              {rfq.urgency} Urgency
                            </span>
                          )}
                          {rfq.nda_required && <span className="text-xs font-medium text-purple-600">NDA Required</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Badge className={'text-xs border ' + (STATUS_COLORS[rfq.rfq_status] ?? 'bg-gray-100 text-gray-700 border-gray-200')}>
                          {formatStatus(rfq.rfq_status)}
                        </Badge>
                        <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-blue-600 transition-colors" />
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <div className="bg-green-50 border border-green-100 rounded-lg p-3 text-center">
                        <div className="flex items-center justify-center gap-1 mb-1">
                          <MessageSquare className="h-3.5 w-3.5 text-green-600" />
                          <span className="text-xs font-medium text-green-700">Quotes Received</span>
                        </div>
                        <p className="text-2xl font-bold text-green-700">{rfq.quote_count}</p>
                        <p className="text-xs text-green-600">of 5 max</p>
                      </div>

                      <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-center">
                        <div className="flex items-center justify-center gap-1 mb-1">
                          <Users className="h-3.5 w-3.5 text-blue-600" />
                          <span className="text-xs font-medium text-blue-700">Firms Contacted</span>
                        </div>
                        <p className="text-2xl font-bold text-blue-700">{rfq.dispatched_count}</p>
                        <p className="text-xs text-blue-600">{rfq.total_matched > 0 ? 'of ' + rfq.total_matched + ' matched' : 'providers'}</p>
                      </div>

                      <div className={'border rounded-lg p-3 text-center ' + (rfq.is_closed || rfq.quote_count >= 5 ? 'bg-gray-50 border-gray-100' : rfq.remaining_count > 0 ? 'bg-orange-50 border-orange-100' : 'bg-gray-50 border-gray-100')}>
                        <div className="flex items-center justify-center gap-1 mb-1">
                          <Activity className={'h-3.5 w-3.5 ' + (rfq.is_closed || rfq.quote_count >= 5 ? 'text-gray-400' : rfq.remaining_count > 0 ? 'text-orange-600' : 'text-gray-400')} />
                          <span className={'text-xs font-medium ' + (rfq.is_closed || rfq.quote_count >= 5 ? 'text-gray-500' : rfq.remaining_count > 0 ? 'text-orange-700' : 'text-gray-500')}>Pipeline Left</span>
                        </div>
                        <p className={'text-2xl font-bold ' + (rfq.is_closed || rfq.quote_count >= 5 ? 'text-gray-400' : rfq.remaining_count > 0 ? 'text-orange-700' : 'text-gray-400')}>
                          {rfq.is_closed || rfq.quote_count >= 5 ? '—' : rfq.remaining_count}
                        </p>
                        <p className="text-xs text-gray-500">{rfq.is_closed || rfq.quote_count >= 5 ? 'Closed' : 'firms in queue'}</p>
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
