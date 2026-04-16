'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { toast } from 'sonner';
import { Clock, AlertCircle, ArrowRight, X } from 'lucide-react';

function WithdrawDialog({ quoteId, onConfirm, onCancel, busy }: {
  quoteId: string; onConfirm: () => void; onCancel: () => void; busy: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900">Withdraw Quote?</h3>
          <button onClick={onCancel} disabled={busy} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
        </div>
        <p className="text-sm text-slate-600 mb-2">
          Are you sure? This will retract your quote only. The RFQ will remain open for other providers.
        </p>
        <p className="text-xs text-slate-400 mb-6">Quote ID: <span className="font-mono">{quoteId.slice(0,8)}&hellip;</span></p>
        <div className="flex gap-3">
          <Button variant="outline" size="sm" onClick={onCancel} disabled={busy} className="flex-1">Cancel</Button>
          <Button size="sm" onClick={onConfirm} disabled={busy}
            className="flex-1 bg-red-600 hover:bg-red-700 text-white">
            {busy ? 'Withdrawing…' : 'Yes, Withdraw'}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function PendingRFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [items, setItems] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [withdrawTarget, setWithdrawTarget] = useState<string | null>(null);
  const [isWithdrawing, setIsWithdrawing] = useState(false);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await api.quotes.getForProvider();
        const list: Quote[] = (res as any).data ?? res ?? [];
        // Pending RFQs = provider submitted a quote AND the RFQ is still OPEN
        // (customer has NOT yet selected a provider or closed the RFQ)
        const CLOSED_RFQ_STATUSES = [
          'customer_selected_provider', 'closed_no_selection', 'cancelled'
        ];
        const pending = (Array.isArray(list) ? list : [])
          .filter(q =>
            ['submitted', 'customer_viewed', 'shortlisted'].includes(q.quote_status) &&
            !(q as any).rfq_is_closed &&
            !CLOSED_RFQ_STATUSES.includes((q as any).rfq_status || '')
          )
          .sort((a, b) =>
            new Date(b.submitted_at ?? b.created_at).getTime() -
            new Date(a.submitted_at ?? a.created_at).getTime()
          );
        setItems(pending);
      } catch (e) { console.error(e); }
      finally { setIsLoading(false); }
    })();
  }, [user]);

  const handleWithdraw = async () => {
    if (!withdrawTarget) return;
    setIsWithdrawing(true);
    try {
      await api.quotes.withdraw(withdrawTarget);
      setItems(prev => prev.filter(q => q.id !== withdrawTarget));
      toast.success('Quote withdrawn successfully.');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to withdraw quote. Please try again.');
    } finally {
      setIsWithdrawing(false);
      setWithdrawTarget(null);
    }
  };

  if (authLoading || isLoading) {
    return <div className="min-h-[60vh] flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" /></div>;
  }

  const statusColor = (s: string) => ({
    shortlisted:     'bg-purple-100 text-purple-700',
    customer_viewed: 'bg-blue-100 text-blue-700',
    submitted:       'bg-amber-100 text-amber-700',
  } as Record<string,string>)[s] ?? 'bg-slate-100 text-slate-600';

  return (
    <>
      {withdrawTarget && (
        <WithdrawDialog
          quoteId={withdrawTarget}
          onConfirm={handleWithdraw}
          onCancel={() => setWithdrawTarget(null)}
          busy={isWithdrawing}
        />
      )}
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Clock className="h-6 w-6 text-amber-500" />
            Pending RFQs
          </h1>
          <p className="text-slate-500 text-sm mt-1 max-w-2xl">
            These are RFQs you quoted and the RFQ is still open. The customer has not yet made a selection.
            You may withdraw your quote if needed.
          </p>
        </div>

        {items.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center max-w-lg mx-auto">
            <AlertCircle className="h-10 w-10 mx-auto mb-3 text-slate-300" />
            <p className="text-base font-medium text-slate-500">No pending quotes</p>
            <p className="text-sm text-slate-400 mt-1">Submitted quotes awaiting a customer decision will appear here.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {items.map((q) => (
              <div key={q.id} className="bg-white rounded-xl border border-amber-200 p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-3 flex-wrap">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${statusColor(q.quote_status)}`}>
                    {q.quote_status.replace(/_/g, ' ')}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">{formatDate(q.submitted_at ?? q.created_at)}</span>
                </div>

                <p className="text-xs text-slate-500 mb-2">
                  RFQ: <span className="font-mono font-medium text-slate-700">{q.rfq_id.slice(0,8)}&hellip;</span>
                </p>

                {q.rough_price_min != null && q.rough_price_max != null && (
                  <div className="bg-slate-50 rounded-lg px-3 py-2 mb-2">
                    <p className="text-sm font-bold text-slate-900">
                      ${Number(q.rough_price_min).toLocaleString()} &ndash; ${Number(q.rough_price_max).toLocaleString()}
                      {q.currency ? ` ${q.currency}` : ''}
                    </p>
                    {q.turnaround_estimate_text && (
                      <p className="text-xs text-slate-500">Turnaround: {q.turnaround_estimate_text}</p>
                    )}
                  </div>
                )}

                {q.scope_notes && (
                  <p className="text-xs text-slate-500 mb-3 line-clamp-2">{q.scope_notes}</p>
                )}

                <div className="flex gap-2 mt-3">
                  <Button size="sm" variant="outline"
                    onClick={() => router.push(`/provider/rfq/${q.rfq_id}`)}
                    className="flex-1 text-xs flex items-center justify-center gap-1">
                    View <ArrowRight size={12} />
                  </Button>
                  <Button size="sm"
                    onClick={() => setWithdrawTarget(q.id)}
                    className="flex-1 text-xs bg-red-600 hover:bg-red-700 text-white">
                    Withdraw Quote
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
