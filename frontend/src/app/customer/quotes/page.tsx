'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { MessageSquare, Users, Activity, Clock, ChevronRight, FileText } from 'lucide-react';
import NdaBadge from '@/components/ui/NdaBadge';

const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') + '/api/v1';

function getAuthHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

interface RFQ {
  id: string;
  project_description: string;
  rfq_status: string;
  urgency: string | null;
  nda_required: boolean;
  nda_status?: string;
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

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-700',
    submitted: 'bg-blue-100 text-blue-700',
    open_for_dispatch: 'bg-yellow-100 text-yellow-700',
    dispatching: 'bg-orange-100 text-orange-700',
    open_for_unlock: 'bg-purple-100 text-purple-700',
    quote_limit_reached: 'bg-green-100 text-green-700',
    customer_selected_provider: 'bg-teal-100 text-teal-700',
    closed_no_selection: 'bg-red-100 text-red-700',
    cancelled: 'bg-gray-200 text-gray-500',
    awaiting_nda_payment: 'bg-pink-100 text-pink-700',
    awaiting_customer_signature: 'bg-indigo-100 text-indigo-700',
  };
  return map[status] ?? 'bg-gray-100 text-gray-700';
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Not yet submitted';
  try {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Unknown date';
  }
}

export default function CustomerQuotesPage() {
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchRFQs() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${apiBase}/customer/my-rfqs`, {
          credentials: 'include',
          headers: getAuthHeaders(),
        });
        if (!res.ok) {
          if (res.status === 401) {
            setError('Please log in to view your RFQs and quotes.');
            return;
          }
          throw new Error(`Server returned ${res.status}`);
        }
        const data = await res.json();
        const list: RFQ[] = Array.isArray(data) ? data : (data.rfqs ?? data.items ?? []);
        setRfqs(list);
      } catch (err: unknown) {
        console.error('Failed to fetch RFQs:', err);
        setError('Failed to load your RFQs. Please try again later.');
      } finally {
        setLoading(false);
      }
    }
    fetchRFQs();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="text-2xl font-bold text-blue-700 tracking-tight">
            ProMechDirectory
          </Link>
          <nav className="flex gap-6 text-sm text-gray-600">
            <Link href="/customer/dashboard" className="hover:text-blue-700">Dashboard</Link>
            <Link href="/customer/quotes" className="font-semibold text-blue-700">My Quotes</Link>
            <Link href="/search" className="hover:text-blue-700">Search</Link>
          </nav>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">My RFQs &amp; Quotes</h1>
        <p className="text-gray-500 mb-8">
          View all your submitted RFQs and the quotes received from engineering firms.
        </p>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
            <span className="ml-4 text-gray-500">Loading your RFQs&hellip;</span>
          </div>
        )}

        {!loading && error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
            <p className="text-red-600 font-medium">{error}</p>
            {error.includes('log in') && (
              <Link
                href="/auth/login"
                className="mt-4 inline-block bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
              >Log In</Link>
            )}
          </div>
        )}

        {!loading && !error && rfqs.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-xl p-12 text-center shadow-sm">
            <FileText className="mx-auto h-12 w-12 text-gray-300 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700 mb-2">No RFQs yet</h2>
            <p className="text-gray-400 mb-6">
              You haven&apos;t submitted any RFQs. Start by searching for engineering firms.
            </p>
            <Link
              href="/search"
              className="inline-block bg-blue-600 text-white px-8 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
            >
              Find Engineering Firms
            </Link>
          </div>
        )}

        {!loading && !error && rfqs.length > 0 && (
          <div className="space-y-4">
            {rfqs.map((rfq) => (
              <Link key={rfq.id} href={`/customer/rfq/${rfq.id}`} className="block">
                <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group">
                  {/* Top row */}
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2 flex-wrap">
                        <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${statusBadgeClass(rfq.rfq_status)}`}>
                          {formatStatus(rfq.rfq_status)}
                        </span>
                        {rfq.urgency && (
                          <span className="text-xs text-gray-400 border border-gray-200 px-2 py-0.5 rounded-full">
                            {rfq.urgency} urgency
                          </span>
                        )}
                        <NdaBadge ndaRequired={rfq.nda_required} ndaStatus={rfq.nda_status} />
                      </div>
                      <p className="text-gray-800 font-medium mb-1 group-hover:text-blue-700 transition-colors">
                        {rfq.project_description
                          ? rfq.project_description.slice(0, 140) + (rfq.project_description.length > 140 ? '...' : '')
                          : '(No description)'}
                      </p>
                      <p className="text-xs text-gray-400 flex items-center gap-1.5">
                        <Clock className="h-3 w-3" />
                        {formatDate(rfq.submitted_at ?? rfq.created_at)}
                        {rfq.business_name && (
                          <>
                            <span className="text-gray-300">&middot;</span>
                            <span>{rfq.business_name}</span>
                          </>
                        )}
                      </p>
                    </div>
                    <ChevronRight className="h-5 w-5 text-gray-300 group-hover:text-blue-600 transition-colors flex-shrink-0 mt-1" />
                  </div>

                  {/* Stats grid */}
                  <div className="grid grid-cols-3 gap-3">
                    {/* Quotes received */}
                    <div className="bg-green-50 border border-green-100 rounded-lg p-3 text-center">
                      <div className="flex items-center justify-center gap-1.5 mb-1">
                        <MessageSquare className="h-4 w-4 text-green-600" />
                        <span className="text-xs font-medium text-green-700">Quotes Received</span>
                      </div>
                      <p className="text-2xl font-bold text-green-700">{rfq.quote_count}</p>
                      <p className="text-xs text-green-600">of 5 max</p>
                    </div>

                    {/* Firms contacted */}
                    <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-center">
                      <div className="flex items-center justify-center gap-1.5 mb-1">
                        <Users className="h-4 w-4 text-blue-600" />
                        <span className="text-xs font-medium text-blue-700">Firms Contacted</span>
                      </div>
                      <p className="text-2xl font-bold text-blue-700">{rfq.dispatched_count}</p>
                      <p className="text-xs text-blue-600">
                        {rfq.total_matched > 0 ? `of ${rfq.total_matched} matched` : 'providers'}
                      </p>
                    </div>

                    {/* Pipeline remaining */}
                    <div className={`border rounded-lg p-3 text-center ${
                      rfq.is_closed || rfq.quote_count >= 5
                        ? 'bg-gray-50 border-gray-100'
                        : rfq.remaining_count > 0
                        ? 'bg-orange-50 border-orange-100'
                        : 'bg-gray-50 border-gray-100'
                    }`}>
                      <div className="flex items-center justify-center gap-1.5 mb-1">
                        <Activity className={
                          rfq.is_closed || rfq.quote_count >= 5
                            ? 'h-4 w-4 text-gray-400'
                            : rfq.remaining_count > 0
                            ? 'h-4 w-4 text-orange-600'
                            : 'h-4 w-4 text-gray-400'
                        } />
                        <span className={
                          rfq.is_closed || rfq.quote_count >= 5
                            ? 'text-xs font-medium text-gray-500'
                            : rfq.remaining_count > 0
                            ? 'text-xs font-medium text-orange-700'
                            : 'text-xs font-medium text-gray-500'
                        }>Pipeline Remaining</span>
                      </div>
                      <p className={
                        rfq.is_closed || rfq.quote_count >= 5
                          ? 'text-2xl font-bold text-gray-400'
                          : rfq.remaining_count > 0
                          ? 'text-2xl font-bold text-orange-700'
                          : 'text-2xl font-bold text-gray-400'
                      }>
                        {rfq.is_closed || rfq.quote_count >= 5 ? '—' : rfq.remaining_count}
                      </p>
                      <p className="text-xs text-gray-500">
                        {rfq.is_closed || rfq.quote_count >= 5 ? 'Closed' : 'firms in queue'}
                      </p>
                    </div>
                  </div>{/* end stats grid */}
                </div>{/* end card */}
              </Link>
            ))}{/* end map */}
          </div>
        )}
      </main>
    </div>
  );
}

