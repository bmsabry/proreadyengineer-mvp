'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { Trophy, FileText, ArrowRight } from 'lucide-react';

type FilterTab = 'all' | 'submitted' | 'accepted' | 'not_selected' | 'withdrawn';

function QStatusBadge({ status }: { status: string }) {
  const m: Record<string,string> = {
    submitted:'bg-blue-100 text-blue-700', accepted:'bg-emerald-100 text-emerald-700',
    not_selected:'bg-slate-100 text-slate-500', withdrawn:'bg-red-100 text-red-600',
    draft:'bg-amber-100 text-amber-700', shortlisted:'bg-purple-100 text-purple-700',
  };
  const c = m[status] || 'bg-slate-100 text-slate-600';
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${c}`}>{status.replace(/_/g,' ')}</span>;
}

const TABS: { key: FilterTab; label: string }[] = [
  { key:'all', label:'All' }, { key:'submitted', label:'Submitted' },
  { key:'accepted', label:'Accepted' }, { key:'not_selected', label:'Not Selected' },
  { key:'withdrawn', label:'Withdrawn' },
];

export default function MyQuotesPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<FilterTab>('all');

  useEffect(() => {
    const load = async () => {
      try { const r = await api.quotes.getForProvider(); setQuotes(r.data || []); }
      catch(e) { console.error(e); } finally { setIsLoading(false); }
    };
    if (user) load();
  }, [user]);

  const filtered = activeTab === 'all' ? quotes : quotes.filter(q => q.quote_status === activeTab);

  if (authLoading || isLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900">My Quotes</h1>
          <p className="text-slate-500 text-sm mt-1">All quotes you have submitted</p>
        </div>
        <div className="flex gap-1 mb-6 bg-white rounded-xl border border-slate-200 p-1 overflow-x-auto">
          {TABS.map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex-shrink-0 py-1.5 px-3 rounded-lg text-sm font-medium transition-colors ${activeTab === tab.key ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>
              {tab.label}
            </button>
          ))}
        </div>
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
            <FileText className="h-10 w-10 mx-auto mb-3 text-slate-300" />
            <p className="text-slate-500 mb-4">No quotes found. Browse RFQs to get started.</p>
            <Link href="/provider/rfqs"><Button className="bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl">Browse RFQs</Button></Link>
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map(q => (
              <div key={q.id} className={`rounded-xl border bg-white shadow-sm p-5 ${q.quote_status === 'accepted' ? 'border-emerald-300' : 'border-slate-200'}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <p className="text-sm font-semibold text-slate-900">RFQ #{String(q.rfq_id).slice(0,8)}&hellip;</p>
                      <QStatusBadge status={q.quote_status} />
                    </div>
                    <p className="text-xs text-slate-400">{q.submitted_at ? formatDate(q.submitted_at) : 'Draft'}</p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => router.push('/provider/rfq/' + q.rfq_id)} className="gap-1 text-slate-600 rounded-xl">View Project <ArrowRight className="h-3 w-3" /></Button>
                </div>
                {q.rough_price_min != null && q.rough_price_max != null && <p className="text-sm font-semibold text-slate-700 mb-2">${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max).toLocaleString()}</p>}
                {q.turnaround_estimate_text && <p className="text-xs text-slate-600 mb-1"><span className="font-medium">Turnaround:</span> {q.turnaround_estimate_text}</p>}
                {q.assumptions_text && <p className="text-xs text-slate-600 mb-1 line-clamp-2"><span className="font-medium">Assumptions:</span> {q.assumptions_text}</p>}
                {q.scope_notes && <p className="text-xs text-slate-600 line-clamp-2"><span className="font-medium">Scope:</span> {q.scope_notes}</p>}
                {q.quote_status === 'accepted' && (
                  <div className="mt-3 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
                    <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-2 flex items-center gap-1"><Trophy className="h-3 w-3" /> Customer Contact</p>
                    <div className="space-y-1 text-xs">
                      {q.customer_contact_name && <p><span className="font-medium text-slate-600">Name: </span>{q.customer_contact_name}</p>}
                      {q.customer_company && <p><span className="font-medium text-slate-600">Company: </span>{q.customer_company}</p>}
                      {q.customer_email && <p><span className="font-medium text-slate-600">Email: </span><a href={`mailto:${q.customer_email}`} className="text-blue-600 hover:underline">{q.customer_email}</a></p>}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
