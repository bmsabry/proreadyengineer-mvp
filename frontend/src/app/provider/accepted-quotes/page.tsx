'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { Trophy, ArrowRight, Mail, Phone, Globe } from 'lucide-react';

export default function AcceptedQuotesPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await api.quotes.getForProvider();
        setQuotes((r.data || []).filter((q: Quote) => q.quote_status === 'accepted'));
      } catch(e) { console.error(e); } finally { setIsLoading(false); }
    };
    if (user) load();
  }, [user]);

  if (authLoading || isLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600"></div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-100 mb-4">
            <Trophy className="h-8 w-8 text-emerald-600" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900">🏆 Accepted Quotes</h1>
          <p className="text-slate-500 text-sm mt-1">Projects where your quote was selected</p>
        </div>
        {quotes.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
            <Trophy className="h-12 w-12 mx-auto mb-4 text-slate-300" />
            <h3 className="text-base font-semibold text-slate-700 mb-2">No accepted quotes yet</h3>
            <p className="text-sm text-slate-500 mb-6">Keep submitting quality quotes to win projects!</p>
            <Button onClick={() => router.push('/provider/rfqs')} className="bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl">Browse RFQs</Button>
          </div>
        ) : (
          <div className="space-y-6">
            {quotes.map(q => (
              <div key={q.id} className="rounded-xl border-2 border-emerald-400 bg-white shadow-sm p-6">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-semibold bg-emerald-100 text-emerald-700"><Trophy className="h-4 w-4" /> Accepted!</span>
                    <p className="text-base font-semibold text-slate-900 mt-2">RFQ #{String(q.rfq_id).slice(0,8)}&hellip;</p>
                    <p className="text-xs text-slate-400">{q.submitted_at ? formatDate(q.submitted_at) : 'Recently'}</p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => router.push('/provider/rfq/' + q.rfq_id)} className="gap-1 rounded-xl text-xs shrink-0">View Project <ArrowRight className="h-3 w-3" /></Button>
                </div>
                {q.rough_price_min != null && q.rough_price_max != null && (
                  <p className="text-sm font-semibold text-slate-700 mb-2">${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max).toLocaleString()}</p>
                )}
                {q.turnaround_estimate_text && <p className="text-xs text-slate-600 mb-1"><span className="font-medium">Turnaround:</span> {q.turnaround_estimate_text}</p>}
                {q.assumptions_text && <p className="text-xs text-slate-600 mb-3"><span className="font-medium">Assumptions:</span> {q.assumptions_text}</p>}
                <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                  <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-3 flex items-center gap-1"><Trophy className="h-3.5 w-3.5" /> Customer Contact</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {q.customer_contact_name && <p><span className="font-medium text-slate-600">Name: </span>{q.customer_contact_name}</p>}
                    {q.customer_company && <p><span className="font-medium text-slate-600">Company: </span>{q.customer_company}</p>}
                    {q.customer_email && <p className="flex items-center gap-1.5"><Mail className="h-3 w-3 text-slate-400" /><a href={`mailto:${q.customer_email}`} className="text-blue-600 hover:underline">{q.customer_email}</a></p>}
                    {(q as any).customer_phone && <p className="flex items-center gap-1.5"><Phone className="h-3 w-3 text-slate-400" />{(q as any).customer_phone}</p>}
                    {(q as any).customer_website && <p className="flex items-center gap-1.5"><Globe className="h-3 w-3 text-slate-400" /><a href={(q as any).customer_website} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">{(q as any).customer_website}</a></p>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
