'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { toast } from 'sonner';
import {
  AlertCircle, MessageSquare, Users, Plus, RefreshCw, Inbox,
  Send, Clock, ChevronRight, XCircle, Loader2
} from 'lucide-react';

export interface CustomerRFQ {
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
  nda_awaiting_customer_signature?: boolean;
}

export const ACTIVE_STATUSES = ['submitted', 'open_for_dispatch', 'dispatching', 'open_for_unlock'];

export const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  submitted: 'bg-blue-50 text-blue-700 border-blue-200',
  open_for_dispatch: 'bg-amber-50 text-amber-700 border-amber-200',
  dispatching: 'bg-orange-50 text-orange-700 border-orange-200',
  open_for_unlock: 'bg-violet-50 text-violet-700 border-violet-200',
  quote_limit_reached: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  customer_selected_provider: 'bg-teal-50 text-teal-700 border-teal-200',
  closed_no_selection: 'bg-rose-50 text-rose-600 border-rose-200',
  cancelled: 'bg-slate-100 text-slate-500 border-slate-200',
  awaiting_nda_payment: 'bg-pink-50 text-pink-700 border-pink-200',
  awaiting_customer_signature: 'bg-indigo-50 text-indigo-700 border-indigo-200',
};

export function formatStatus(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatDate(d: string | null): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

export function SkeletonCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 animate-pulse">
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-200 rounded-lg w-3/4" />
          <div className="h-3 bg-slate-100 rounded-lg w-1/3" />
        </div>
        <div className="h-5 bg-slate-200 rounded-full w-28 ml-4 shrink-0" />
      </div>
      <div className="grid grid-cols-3 gap-3 mt-5">
        {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <div className="h-3 bg-slate-100 rounded w-32" />
        <div className="h-3 bg-slate-100 rounded w-16" />
      </div>
    </div>
  );
}

interface RfqCardProps {
  rfq: CustomerRFQ;
  showCancel?: boolean;
  onCancelled?: (rfqId: string) => void;
}

export function RfqCard({ rfq, showCancel = false, onCancelled }: RfqCardProps) {
  const [cancelling, setCancelling] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const statusClass = STATUS_COLORS[rfq.rfq_status] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  const dateLabel = rfq.submitted_at ? formatDate(rfq.submitted_at) : rfq.created_at ? formatDate(rfq.created_at) : '';
  const isActive = ACTIVE_STATUSES.includes(rfq.rfq_status);

  const handleCancel = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirmOpen) { setConfirmOpen(true); return; }
    setCancelling(true);
    try {
      await api.rfqs.cancel(rfq.id);
      toast.success('RFQ cancelled successfully');
      onCancelled?.(rfq.id);
    } catch {
      toast.error('Failed to cancel RFQ. Please try again.');
    } finally {
      setCancelling(false);
      setConfirmOpen(false);
    }
  };

  const handleCancelAbort = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setConfirmOpen(false);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 p-6 group">
      <div className="flex items-start justify-between gap-4 mb-5">
        <Link href={`/customer/rfq/${rfq.id}`} className="flex-1 min-w-0">
          <p className="text-base font-semibold text-slate-900 leading-snug line-clamp-2 group-hover:text-[#0F2B54] transition-colors duration-150 cursor-pointer">
            {rfq.project_description}
          </p>
          {rfq.business_name && (
            <p className="mt-1 text-sm text-slate-500">{rfq.business_name}</p>
          )}
        </Link>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border ${statusClass}`}>
            {formatStatus(rfq.rfq_status)}
          </span>
          {showCancel && isActive && (
            confirmOpen ? (
              <div className="flex items-center gap-1">
                <span className="text-xs text-slate-600 whitespace-nowrap">Confirm?</span>
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                >
                  {cancelling ? <Loader2 className="h-3 w-3 animate-spin" /> : <XCircle className="h-3 w-3" />}
                  Yes
                </button>
                <button
                  onClick={handleCancelAbort}
                  className="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                >
                  No
                </button>
              </div>
            ) : (
              <button
                onClick={handleCancel}
                className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 rounded-lg text-xs font-medium transition-colors"
              >
                <XCircle className="h-3 w-3" />
                Cancel RFQ
              </button>
            )
          )}
        </div>
      </div>

      <Link href={`/customer/rfq/${rfq.id}`}>
        <div className="grid grid-cols-3 gap-3 cursor-pointer">
          <div className="bg-emerald-50 border border-emerald-100 rounded-xl px-4 py-3">
            <div className="flex items-center gap-1.5 mb-1">
              <MessageSquare className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-xs font-medium text-emerald-700">Quotes</span>
            </div>
            <p className="text-xl font-bold text-emerald-800">{rfq.quote_count}</p>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Send className="h-3.5 w-3.5 text-blue-600" />
              <span className="text-xs font-medium text-blue-700">Dispatched</span>
            </div>
            <p className="text-xl font-bold text-blue-800">{rfq.dispatched_count}</p>
          </div>
          <div className="bg-amber-50 border border-amber-100 rounded-xl px-4 py-3">
            <div className="flex items-center gap-1.5 mb-1">
              <Users className="h-3.5 w-3.5 text-amber-700" />
              <span className="text-xs font-medium text-amber-700">Remaining</span>
            </div>
            <p className="text-xl font-bold text-amber-800">{rfq.remaining_count}</p>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {rfq.urgency && (
              <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                <Clock className="h-3 w-3" />{rfq.urgency}
              </span>
            )}
            {rfq.nda_required && (
              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-violet-50 text-violet-700 border border-violet-200">NDA</span>
            )}
            {dateLabel && <span className="text-xs text-slate-400">{dateLabel}</span>}
          </div>
          <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-[#0F2B54] group-hover:translate-x-0.5 transition-all duration-150" />
        </div>
      </Link>
    </div>
  );
}

interface RfqListPageProps {
  title: string;
  subtitle: string;
  filter: (rfq: CustomerRFQ) => boolean;
  emptyMessage: string;
  showCancel?: boolean;
  roles?: string[];
}

export function useRfqs() {
  const [rfqs, setRfqs] = useState<CustomerRFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { user } = useRequireAuth(['customer', 'admin']);

  const load = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;
      const res = await fetch(base + '/customer/my-rfqs', { credentials: 'include', headers });
      if (!res.ok) { setLoadError('Server returned ' + res.status); return; }
      const data = await res.json();
      const all: CustomerRFQ[] = Array.isArray(data) ? data : (data.items ?? []);
      // Sort newest first
      all.sort((a, b) => {
        const da = new Date(a.submitted_at || a.created_at || 0).getTime();
        const db = new Date(b.submitted_at || b.created_at || 0).getTime();
        return db - da;
      });
      setRfqs(all);
    } catch (e) {
      console.error(e);
      setLoadError('Network error — please refresh.');
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  return { rfqs, setRfqs, isLoading, loadError, setLoadError, reload: load };
}

export function RfqListPage({ title, subtitle, filter, emptyMessage, showCancel = false }: RfqListPageProps) {
  const { rfqs, setRfqs, isLoading, loadError, setLoadError, reload } = useRfqs();
  const filtered = rfqs.filter(filter);

  const handleCancelled = (rfqId: string) => {
    setRfqs(prev => prev.map(r =>
      r.id === rfqId ? { ...r, rfq_status: 'cancelled', is_closed: true } : r
    ));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500 mb-1">Customer Portal</p>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">{title}</h1>
              <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
            </div>
            <Link href="/">
              <button className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl font-semibold text-sm transition-all duration-150 shadow-sm hover:shadow-md">
                <Plus className="h-4 w-4" />
                New RFQ
              </button>
            </Link>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {loadError && (
          <div className="mb-6 flex items-start gap-3 px-4 py-3.5 bg-rose-50 border border-rose-200 rounded-xl">
            <AlertCircle className="h-4 w-4 text-rose-600 mt-0.5 shrink-0" />
            <p className="flex-1 text-sm font-medium text-rose-700">{loadError}</p>
            <button
              onClick={() => { setLoadError(null); reload(); }}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-600 hover:text-rose-800 transition-colors shrink-0"
            >
              <RefreshCw className="h-3 w-3" /> Retry
            </button>
          </div>
        )}

        {isLoading && (
          <div className="space-y-4">
            <SkeletonCard /><SkeletonCard /><SkeletonCard />
          </div>
        )}

        {!isLoading && !loadError && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-5">
              <Inbox className="h-8 w-8 text-slate-400" />
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-2">No RFQs here</h2>
            <p className="text-slate-500 text-sm max-w-xs mb-6">{emptyMessage}</p>
            <Link href="/">
              <button className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl font-semibold text-sm transition-all duration-150 shadow-sm">
                <Plus className="h-4 w-4" /> Submit an RFQ
              </button>
            </Link>
          </div>
        )}

        {!isLoading && filtered.length > 0 && (
          <div className="space-y-4">
            {filtered.map((rfq) => (
              <RfqCard
                key={rfq.id}
                rfq={rfq}
                showCancel={showCancel}
                onCancelled={handleCancelled}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
