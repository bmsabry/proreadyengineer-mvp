'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import {
  Receipt, CheckCircle, AlertCircle, RefreshCw, XCircle, LifeBuoy, ArrowLeft, Clock,
} from 'lucide-react';
import Link from 'next/link';

const SUPPORT_EMAIL = 'info@promechdirectory.com';

type Txn = {
  id: string;
  date: string | null;
  purpose: string;
  label: string;
  amount_cents: number;
  amount_display: string;
  currency: string;
  status: string;
  category: 'membership' | 'one_time' | 'other';
  action: 'refund' | 'cancel_membership' | 'contact_support' | 'none';
  within_window: boolean | null;
  refund_window_days: number | null;
  cancel_key: string | null;
  note: string | null;
};

function fmtDate(iso: string | null) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return '—';
  }
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-700',
    refunded: 'bg-slate-200 text-slate-600',
    disputed: 'bg-red-100 text-red-700',
  };
  const label = status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${map[status] || 'bg-slate-100 text-slate-600'}`}>
      {label}
    </span>
  );
}

export default function ProviderTransactionsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [txns, setTxns] = useState<Txn[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Confirmation modal state
  const [pending, setPending] = useState<Txn | null>(null);
  const [working, setWorking] = useState(false);
  const [resultMsg, setResultMsg] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api.billing
      .getMyTransactions()
      .then((res: any) => setTxns(res.data.transactions || []))
      .catch(() => setError('We could not load your transactions. Please try again.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!authLoading && user) load();
  }, [authLoading, user, load]);

  const runCancel = async (txn: Txn) => {
    if (!txn.cancel_key) return;
    setWorking(true);
    setResultMsg(null);
    try {
      const res: any = await api.billing.cancelSubscription(txn.cancel_key);
      const d = res.data || {};
      setResultMsg(d.message || (d.refunded ? 'Your payment was refunded.' : 'Your membership was updated.'));
      load();
    } catch (e: any) {
      setResultMsg(e?.response?.data?.detail || 'Something went wrong. Please contact support.');
    } finally {
      setWorking(false);
    }
  };

  const supportHref = (txn: Txn) =>
    `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Refund request — transaction ' + txn.id)}` +
    `&body=${encodeURIComponent(
      `Hello,\n\nI'd like to request a refund for the following transaction:\n\n` +
        `Transaction ID: ${txn.id}\nItem: ${txn.label}\nAmount: ${txn.amount_display}\nDate: ${fmtDate(txn.date)}\n\nReason: \n\nThank you.`,
    )}`;

  const ActionCell = ({ txn }: { txn: Txn }) => {
    if (txn.action === 'refund') {
      return (
        <button
          onClick={() => { setResultMsg(null); setPending(txn); }}
          className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refund
        </button>
      );
    }
    if (txn.action === 'cancel_membership') {
      return (
        <button
          onClick={() => { setResultMsg(null); setPending(txn); }}
          className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500 text-white hover:bg-amber-600 transition"
        >
          <XCircle className="h-3.5 w-3.5" /> Cancel membership
        </button>
      );
    }
    if (txn.action === 'contact_support') {
      return (
        <a
          href={supportHref(txn)}
          className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition"
        >
          <LifeBuoy className="h-3.5 w-3.5" /> Contact support for refund
        </a>
      );
    }
    return <span className="text-xs text-slate-500">{txn.note || '—'}</span>;
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        <RefreshCw className="h-5 w-5 animate-spin mr-2" /> Loading your transactions…
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/provider/dashboard" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4">
        <ArrowLeft className="h-4 w-4" /> Back to dashboard
      </Link>

      <div className="flex items-center gap-2 mb-1">
        <Receipt className="h-5 w-5 text-blue-600" />
        <h1 className="text-2xl font-bold text-slate-800">Transactions</h1>
      </div>
      <p className="text-sm text-slate-500 mb-6">
        Every payment on your account. Membership fees can be refunded within the refund window
        (5 days monthly, 14 days yearly); after that you can cancel and keep access until the period ends.
        One-time fees such as NDA and RFQ-unlock charges are non-refundable — contact support if you have a concern.
      </p>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mb-4">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {resultMsg && (
        <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 mb-4">
          <CheckCircle className="h-4 w-4" /> {resultMsg}
        </div>
      )}

      {txns.length === 0 ? (
        <div className="text-center py-16 text-slate-500">
          <Receipt className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">You don&apos;t have any transactions yet.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-left">
            <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">Date</th>
                <th className="px-4 py-3 font-semibold">Description</th>
                <th className="px-4 py-3 font-semibold">Amount</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {txns.map((txn) => (
                <tr key={txn.id} className="text-sm">
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{fmtDate(txn.date)}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{txn.label}</div>
                    {txn.category === 'membership' && txn.within_window === true && txn.action === 'refund' && (
                      <div className="flex items-center gap-1 text-xs text-emerald-600 mt-0.5">
                        <Clock className="h-3 w-3" /> Within {txn.refund_window_days}-day refund window
                      </div>
                    )}
                    {txn.category === 'membership' && txn.within_window === false && (
                      <div className="text-xs text-slate-500 mt-0.5">Refund window passed</div>
                    )}
                    {txn.category === 'one_time' && (
                      <div className="text-xs text-slate-500 mt-0.5">Non-refundable fee</div>
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-800 whitespace-nowrap">{txn.amount_display}</td>
                  <td className="px-4 py-3"><StatusBadge status={txn.status} /></td>
                  <td className="px-4 py-3 text-right"><ActionCell txn={txn} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Confirmation modal */}
      {pending && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4" onClick={() => !working && setPending(null)}>
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
            {pending.action === 'refund' ? (
              <>
                <h3 className="text-lg font-bold text-slate-800 mb-2">Refund this membership?</h3>
                <p className="text-sm text-slate-600 mb-4">
                  You&apos;re within the {pending.refund_window_days}-day refund window. We&apos;ll refund
                  {' '}<span className="font-semibold">{pending.amount_display}</span> to your original payment method and
                  cancel the membership immediately. Access ends now.
                </p>
              </>
            ) : (
              <>
                <h3 className="text-lg font-bold text-slate-800 mb-2">Cancel this membership?</h3>
                <p className="text-sm text-slate-600 mb-4">
                  The {pending.refund_window_days}-day refund window has passed, so this charge is non-refundable.
                  Your membership won&apos;t renew, and you keep full access until the end of your current paid period.
                </p>
              </>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setPending(null)}
                disabled={working}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 disabled:opacity-50"
              >
                Never mind
              </button>
              <button
                onClick={async () => { const t = pending; setPending(null); await runCancel(t); }}
                disabled={working}
                className={`px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-50 ${
                  pending.action === 'refund' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-amber-500 hover:bg-amber-600'
                }`}
              >
                {working ? 'Working…' : pending.action === 'refund' ? 'Yes, refund me' : 'Yes, cancel'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
