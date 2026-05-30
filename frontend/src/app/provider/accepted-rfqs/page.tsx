'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Quote } from '@/types';
import { formatDate } from '@/lib/utils';
import {
  CheckCircle, ArrowRight, ChevronDown, Phone,
  MailCheck, XCircle, User,
} from 'lucide-react';

export default function AcceptedRFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [items, setItems]               = useState<Quote[]>([]);
  const [contactingId, setContactingId] = useState<string | null>(null);
  const [isLoading, setIsLoading]       = useState(true);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await api.quotes.getForProvider();
        const list: Quote[] = (res as any).data ?? res ?? [];
        const accepted = (Array.isArray(list) ? list : [])
          .filter(q => q.quote_status === 'accepted')
          .sort((a, b) =>
            new Date(b.updated_at ?? b.created_at).getTime() -
            new Date(a.updated_at ?? a.created_at).getTime()
          );
        setItems(accepted);
      } catch (e) { console.error(e); }
      finally { setIsLoading(false); }
    })();
  }, [user]);

  const handleContacted = async (quoteId: string) => {
    if (contactingId) return;                 // guard double-clicks
    setContactingId(quoteId);
    // Optimistically hide the card; persist on the server so it never comes back.
    setItems(prev => prev.map(q => q.id === quoteId ? { ...q, provider_contacted: true } : q));
    try {
      await api.quotes.markContacted(quoteId);
    } catch (e) {
      console.error(e);
      // Revert on failure so the user can retry.
      setItems(prev => prev.map(q => q.id === quoteId ? { ...q, provider_contacted: false } : q));
    } finally {
      setContactingId(null);
    }
  };

  if (authLoading || isLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const activeItems  = items.filter(q => !q.provider_contacted);
  const closedItems  = items.filter(q => q.provider_contacted);

  return (
    <div>
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <CheckCircle className="h-6 w-6 text-emerald-600" />
          Accepted RFQs
        </h1>
        <p className="text-slate-500 text-sm mt-1 max-w-2xl">
          The customer selected your quote. Contact them directly to begin engagement.
          Once contacted, mark the RFQ as done to keep your list clean.
        </p>
      </div>

      {/* Empty state */}
      {items.length === 0 && (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center max-w-lg mx-auto">
          <CheckCircle className="h-10 w-10 mx-auto mb-3 text-slate-300" />
          <p className="text-base font-medium text-slate-500">No accepted quotes yet</p>
          <p className="text-sm text-slate-400 mt-1">When a customer selects your quote, engagement details will appear here.</p>
        </div>
      )}

      {/* Active accepted RFQs */}
      {activeItems.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {activeItems.map((q) => (
            <div key={q.id} className="bg-white rounded-2xl border-2 border-emerald-300 p-5 shadow-sm">

              {/* Card header */}
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle className="h-5 w-5 text-emerald-600 shrink-0" />
                <span className="text-sm font-bold text-emerald-700">Quote Accepted</span>
                <span className="ml-auto text-xs text-slate-400 shrink-0">
                  {formatDate(q.updated_at ?? q.created_at)}
                </span>
              </div>

              <p className="text-xs text-slate-500 mb-3">
                RFQ: <span className="font-mono font-medium text-slate-700">{q.rfq_id.slice(0, 8)}&hellip;</span>
              </p>

              {/* Price range */}
              {q.rough_price_min != null && q.rough_price_max != null && (
                <div className="bg-emerald-50 rounded-lg p-3 mb-3">
                  <p className="text-xs text-emerald-600 font-medium mb-0.5">Your Quote</p>
                  <p className="text-lg font-bold text-slate-900">
                    ${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max).toLocaleString()}
                    {q.currency ? ` ${q.currency}` : ''}
                  </p>
                  {q.turnaround_estimate_text && (
                    <p className="text-xs text-slate-500 mt-1">Turnaround: {q.turnaround_estimate_text}</p>
                  )}
                </div>
              )}

              {/* Customer contact */}
              {(q.customer_contact_name || q.customer_email || q.customer_company) ? (
                <div className="border border-emerald-200 bg-emerald-50 rounded-lg p-3 mb-4 space-y-1">
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Customer Contact</p>
                  {q.customer_contact_name && (
                    <div className="flex items-center gap-1.5">
                      <User className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                      <p className="text-sm font-medium text-slate-900">{q.customer_contact_name}</p>
                    </div>
                  )}
                  {q.customer_company && (
                    <p className="text-sm text-slate-600 ml-5">{q.customer_company}</p>
                  )}
                  {q.customer_email && (
                    <a
                      href={`mailto:${q.customer_email}`}
                      className="flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
                    >
                      <Phone className="h-3.5 w-3.5 shrink-0" />
                      {q.customer_email}
                    </a>
                  )}
                </div>
              ) : (
                <div className="border border-slate-200 rounded-lg p-3 mb-4 text-center">
                  <p className="text-xs text-slate-400">Customer contact details will appear here once available.</p>
                </div>
              )}

              {q.scope_notes && (
                <p className="text-xs text-slate-500 mb-4 line-clamp-2">{q.scope_notes}</p>
              )}

              {/* Action buttons */}
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => router.push(`/provider/rfq/${q.rfq_id}`)}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 border border-slate-200 rounded-xl text-xs font-medium text-slate-600 hover:border-slate-300 hover:bg-slate-50 transition-all"
                >
                  View Project Details <ArrowRight className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleContacted(q.id)}
                  disabled={contactingId === q.id}
                  className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-xl text-xs font-semibold transition-all"
                >
                  <MailCheck className="h-3.5 w-3.5" /> {contactingId === q.id ? 'Saving…' : 'Customer Already Contacted'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Closed RFQs section */}
      {closedItems.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <XCircle className="h-4 w-4 text-slate-400" />
            <h2 className="text-sm font-semibold text-slate-500">Closed RFQs</h2>
            <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">{closedItems.length}</span>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 divide-y divide-slate-100">
            {closedItems.map((q) => (
              <div
                key={q.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors cursor-pointer"
                onClick={() => router.push(`/provider/rfq/${q.rfq_id}`)}
              >
                <MailCheck className="h-4 w-4 text-emerald-500 shrink-0" />
                <span className="text-xs font-mono text-slate-500">RFQ {q.rfq_id.slice(0, 8)}&hellip;</span>
                {q.rough_price_min != null && (
                  <span className="text-xs text-slate-600">
                    ${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max ?? q.rough_price_min).toLocaleString()}
                  </span>
                )}
                <span className="text-xs text-slate-400 ml-auto">{formatDate(q.updated_at ?? q.created_at)}</span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-300" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
