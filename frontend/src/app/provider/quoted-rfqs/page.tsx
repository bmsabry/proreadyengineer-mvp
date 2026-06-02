'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { MessageSquare, AlertCircle, ArrowRight } from 'lucide-react';

export default function QuotedRFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [items, setItems] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await api.quotes.getForProvider();
        const list: Quote[] = (res as any).data ?? res ?? [];
        // Closed RFQs where quote was NOT accepted: not_selected, expired, or withdrawn
        const closed = (Array.isArray(list) ? list : [])
          // Quoted RFQs = provider submitted a quote, RFQ is now CLOSED, quote was NOT accepted
          // Shows all quotes on closed RFQs except accepted and withdrawn/draft
          .filter(q =>
            !['accepted', 'withdrawn', 'draft'].includes(q.quote_status) &&
            (q as any).rfq_is_closed === true
          )
          .sort((a, b) =>
            new Date(b.updated_at ?? b.created_at).getTime() -
            new Date(a.updated_at ?? a.created_at).getTime()
          );
        setItems(closed);
      } catch (e) { console.error(e); }
      finally { setIsLoading(false); }
    })();
  }, [user]);

  if (authLoading || isLoading) {
    return <div className="min-h-[60vh] flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" /></div>;
  }

  const statusColor = (s: string) => ({
    not_selected: 'bg-slate-100 text-slate-500',
    expired:      'bg-orange-100 text-orange-600',
    withdrawn:    'bg-red-100 text-red-600',
  } as Record<string,string>)[s] ?? 'bg-slate-100 text-slate-600';

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <MessageSquare className="h-6 w-6 text-slate-500" />
          Quoted RFQs
        </h1>
        <p className="text-slate-500 text-sm mt-1 max-w-2xl">
          These are RFQs you submitted a quote for that are now closed. Your quote was not selected on these engagements.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center max-w-lg mx-auto">
          <MessageSquare className="h-10 w-10 mx-auto mb-3 text-slate-500" />
          <p className="text-base font-medium text-slate-500">No closed quotes yet</p>
          <p className="text-sm text-slate-500 mt-1">Quotes on closed RFQs where you were not selected will appear here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((q) => (
            <div key={q.id} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm opacity-80">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${statusColor(q.quote_status)}`}>
                  {q.quote_status.replace(/_/g, ' ')}
                </span>
                <span className="ml-auto text-xs text-slate-500">
                  {formatDate(q.updated_at ?? q.created_at)}
                </span>
              </div>

              <p className="text-xs text-slate-500 mb-2">
                RFQ: <span className="font-mono font-medium text-slate-700">{q.rfq_id.slice(0,8)}&hellip;</span>
              </p>

              {q.rough_price_min != null && q.rough_price_max != null && (
                <div className="bg-slate-50 rounded-lg px-3 py-2 mb-2">
                  <p className="text-xs text-slate-500 mb-0.5">Your Quote</p>
                  <p className="text-sm font-semibold text-slate-700">
                    ${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max).toLocaleString()}
                    {q.currency ? ` ${q.currency}` : ''}
                  </p>
                </div>
              )}

              {q.submitted_at && (
                <p className="text-xs text-slate-500 mb-3">Submitted {formatDate(q.submitted_at)}</p>
              )}

              <Button size="sm" variant="outline"
                onClick={() => router.push(`/provider/rfq/${q.rfq_id}`)}
                className="w-full text-xs flex items-center justify-center gap-1">
                View RFQ <ArrowRight size={12} />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
