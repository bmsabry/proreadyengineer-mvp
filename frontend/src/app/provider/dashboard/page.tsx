'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser, Quote } from '@/types';
import { formatDate } from '@/lib/utils';
import {
  TrendingUp, FileText, CheckCircle, Clock, XCircle,
  FileSignature, Calendar, ArrowRight, Inbox,
  CreditCard, Bell, Phone, Crown,
} from 'lucide-react';

// ─── Shared UI helpers ────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }: {
  label: string; value: string | number; sub?: string; color: string;
}) {
  return (
    <div className={`rounded-xl border p-4 ${color}`}>
      <p className="text-xs font-medium text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="w-full bg-slate-100 rounded-full h-1.5 mt-1">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function UrgencyBadge({ urgency }: { urgency?: string }) {
  const m: Record<string, string> = {
    High: 'bg-red-100 text-red-700 border-red-200',
    Intermediate: 'bg-amber-100 text-amber-700 border-amber-200',
    Low: 'bg-green-100 text-green-700 border-green-200',
  };
  const cls = m[urgency ?? ''] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>
      {urgency ?? 'N/A'}
    </span>
  );
}

// ─── Analytics Panel ─────────────────────────────────────────────────────────

function ProviderAnalyticsPanel({
  teasers, quotes, hasMembership, user, contactedRfqIds, providerSubStatus,
}: {
  teasers: RFQTeaser[];
  quotes: Quote[];
  hasMembership: boolean;
  user: any;
  contactedRfqIds: string[];
  providerSubStatus?: { has_active: boolean; subscription_type: string | null; current_period_end: string | null; cancel_at: string | null } | null;
}) {
  const CLOSED_STATUSES = ['customer_selected_provider', 'closed_no_selection', 'cancelled'];

  const totalReceived = teasers.length;
  const activeRFQs = teasers.filter(t =>
    t.status !== 'quoted' && (t as any).rfq_status === 'open_for_unlock'
  ).length;
  const submitted = quotes.filter(q => q.quote_status !== 'draft').length;
  const accepted = quotes.filter(q => q.quote_status === 'accepted').length;
  const pending = quotes.filter(q =>
    ['submitted', 'customer_viewed', 'shortlisted'].includes(q.quote_status) &&
    !(q as any).rfq_is_closed &&
    !CLOSED_STATUSES.includes((q as any).rfq_status || '')
  ).length;
  const notSelected = quotes.filter(q => ['not_selected', 'expired'].includes(q.quote_status)).length;
  const ndasSigned = teasers.filter(t =>
    t.nda_required && (t.status === 'unlocked' || t.status === 'quoted')
  ).length;
  const winRate = submitted > 0 ? Math.round((accepted / submitted) * 100) : 0;
  const createdAt = user?.created_at;

  const ndaTasks = teasers.filter(t =>
    t.nda_required && t.nda_status === 'provider_signature_pending'
  );
  const rfqTasks = teasers
    .filter(t => t.status !== 'quoted' && (t as any).rfq_status === 'open_for_unlock')
    .slice(0, 3);
  const acceptedTasks = quotes.filter(q =>
    q.quote_status === 'accepted' && !contactedRfqIds.includes(q.rfq_id)
  );
  const taskCount = ndaTasks.length + rfqTasks.length + (acceptedTasks.length > 0 ? 1 : 0);
  const hasTasks = taskCount > 0;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 h-fit">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-[#0F2B54]" />
          <h2 className="text-base font-bold text-slate-900">Activity Summary</h2>
        </div>
        {hasTasks && (
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">
            {taskCount} task{taskCount > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Action Required */}
      {hasTasks && (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-3 space-y-1.5">
          <div className="flex items-center gap-1.5 mb-2">
            <Bell className="h-3.5 w-3.5 text-amber-600" />
            <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider">Action Required</p>
          </div>

          {ndaTasks.map(t => (
            <Link
              key={t.rfq_id}
              href={`/provider/rfq/${t.rfq_id}`}
              className="flex items-center justify-between group py-0.5"
            >
              <div className="flex items-center gap-1.5">
                <FileSignature className="h-3.5 w-3.5 text-violet-500 shrink-0" />
                <span className="text-xs text-slate-700 group-hover:text-[#0F2B54]">NDA awaiting your signature</span>
              </div>
              <ArrowRight className="h-3 w-3 text-slate-400 group-hover:text-[#0F2B54]" />
            </Link>
          ))}

          {rfqTasks.map(t => (
            <Link
              key={t.rfq_id}
              href={`/provider/rfq/${t.rfq_id}`}
              className="flex items-center justify-between group py-0.5"
            >
              <div className="flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                <span className="text-xs text-slate-700 group-hover:text-[#0F2B54]">
                  RFQ awaiting your quote
                  {t.urgency === 'High' && (
                    <span className="ml-1 text-red-500 font-medium">&middot; High priority</span>
                  )}
                </span>
              </div>
              <ArrowRight className="h-3 w-3 text-slate-400 group-hover:text-[#0F2B54]" />
            </Link>
          ))}

          {acceptedTasks.length > 0 && (
            <Link
              href="/provider/accepted-rfqs"
              className="flex items-center justify-between group py-0.5"
            >
              <div className="flex items-center gap-1.5">
                <Phone className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                <span className="text-xs text-slate-700 group-hover:text-[#0F2B54]">
                  Accepted RFQ &mdash; contact the customer
                  {acceptedTasks.length > 1 && (
                    <span className="ml-1 text-emerald-600 font-medium">({acceptedTasks.length})</span>
                  )}
                </span>
              </div>
              <ArrowRight className="h-3 w-3 text-slate-400 group-hover:text-[#0F2B54]" />
            </Link>
          )}
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 mb-5">
        <StatCard label="RFQs Received"    value={totalReceived} color="bg-slate-50 border-slate-200" />
        <StatCard label="Active RFQs"      value={activeRFQs}    color="bg-blue-50 border-blue-200" />
        <StatCard label="Quotes Submitted" value={submitted}     color="bg-violet-50 border-violet-200" />
        <StatCard
          label="Win Rate"
          value={`${winRate}%`}
          sub={`${accepted} accepted`}
          color="bg-emerald-50 border-emerald-200"
        />
      </div>

      {/* Breakdown */}
      <div className="space-y-2.5 mb-5">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Breakdown</p>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Pending Decisions</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{pending}</span>
          </div>
          <MiniBar value={pending} max={submitted} color="bg-amber-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <CheckCircle className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Accepted</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{accepted}</span>
          </div>
          <MiniBar value={accepted} max={submitted} color="bg-emerald-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <XCircle className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Not Selected</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{notSelected}</span>
          </div>
          <MiniBar value={notSelected} max={submitted} color="bg-slate-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <FileSignature className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">NDAs Signed</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{ndasSigned}</span>
          </div>
          <MiniBar value={ndasSigned} max={totalReceived} color="bg-violet-400" />
        </div>
      </div>

      {/* Account */}
      <div className="border-t border-slate-100 pt-4 space-y-2">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Account</p>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs text-slate-500">Member since</span>
          </div>
          <span className="text-xs font-medium text-slate-700">
            {createdAt ? formatDate(createdAt) : '—'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <CreditCard className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs text-slate-500">Subscription</span>
          </div>
          {providerSubStatus?.has_active && providerSubStatus.subscription_type === 'provider_annual' ? (
            <div className="flex flex-col items-end gap-0.5">
              <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 border border-blue-200">
                <Crown className="h-3 w-3" /> Annual Pro
              </span>
              {providerSubStatus.current_period_end && (
                <span className="text-[10px] text-slate-400">
                  Renews {new Date(providerSubStatus.current_period_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              )}
              {providerSubStatus.cancel_at && (
                <span className="text-[10px] text-amber-600">
                  Cancels {new Date(providerSubStatus.cancel_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              )}
            </div>
          ) : hasMembership ? (
            <Link href="/provider/profile">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 hover:bg-emerald-200 transition-colors cursor-pointer">Active</span>
            </Link>
          ) : (
            <Link href="/provider/upgrade">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors cursor-pointer">
                Inactive — Upgrade
              </span>
            </Link>
          )}
        </div>
      </div>
      {/* Quick Access */}
      <div className="mt-4 pt-4 border-t border-slate-100">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Quick Access</p>
        <div className="grid grid-cols-3 gap-2">
          <Link href="/provider/active-rfqs">
            <div className="rounded-lg border border-slate-200 p-2.5 text-center hover:bg-blue-50 hover:border-slate-300 transition-all cursor-pointer">
              <p className="text-lg font-bold text-blue-600">{activeRFQs}</p>
              <p className="text-xs text-slate-500 mt-0.5">Active</p>
            </div>
          </Link>
          <Link href="/provider/pending-rfqs">
            <div className="rounded-lg border border-slate-200 p-2.5 text-center hover:bg-amber-50 hover:border-slate-300 transition-all cursor-pointer">
              <p className="text-lg font-bold text-amber-600">{pending}</p>
              <p className="text-xs text-slate-500 mt-0.5">Pending</p>
            </div>
          </Link>
          <Link href="/provider/accepted-rfqs">
            <div className="rounded-lg border border-slate-200 p-2.5 text-center hover:bg-emerald-50 hover:border-slate-300 transition-all cursor-pointer">
              <p className="text-lg font-bold text-emerald-600">{accepted}</p>
              <p className="text-xs text-slate-500 mt-0.5">Accepted</p>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────────────────────────────

function ProviderDashboardInner() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const [teasers, setTeasers] = useState<RFQTeaser[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [hasMembership, setHasMembership] = useState(false);
  const [providerSubStatus, setProviderSubStatus] = useState<{
    has_active: boolean;
    subscription_type: string | null;
    current_period_end: string | null;
    cancel_at: string | null;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [contactedRfqIds, setContactedRfqIds] = useState<string[]>([]);
  const [paymentBanner, setPaymentBanner] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      const stored = localStorage.getItem('provider_contacted_rfqs');
      if (stored) setContactedRfqIds(JSON.parse(stored));
    } catch {}
  }, []);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const [tr, qr, sr] = await Promise.all([
          api.providerRFQ.getTeasers(),
          api.quotes.getForProvider(),
          api.billing.getProviderSubscriptionStatus().catch(() => null),
        ]);
        const td = (tr as any).data ?? tr;
        const tlist = td?.teasers ?? td ?? [];
        setHasMembership(td?.has_membership ?? (Array.isArray(tlist) && tlist.length > 0));
        setTeasers(Array.isArray(tlist) ? tlist : []);
        const qd = (qr as any).data ?? qr ?? [];
        setQuotes(Array.isArray(qd) ? qd : []);
        const sd = (sr as any)?.data ?? sr;
        if (sd && typeof sd === 'object' && 'has_active' in sd) {
          setProviderSubStatus(sd);
        }
      } catch (e) {
        console.error('Dashboard fetch error:', e);
      } finally {
        setIsLoading(false);
      }
    })();
  }, [user]);

  // ── Handle Stripe redirect with ?payment=success&session_id=xxx ─────────────
  useEffect(() => {
    const payment = searchParams.get('payment');
    const sessionId = searchParams.get('session_id');
    const purpose = searchParams.get('purpose') || 'provider_annual_subscription';
    if (payment !== 'success') return;

    router.replace('/provider/dashboard');

    if (sessionId) {
      (async () => {
        try {
          const { apiClient } = await import('@/lib/api');
          await apiClient.post('/billing/verify-subscription', { session_id: sessionId, purpose });
          setPaymentBanner('🎉 Annual Professional subscription activated!');
          // Refresh provider subscription status
          try {
            const _resp_sd = await apiClient.get('/billing/provider-subscription-status');
        const sd = _resp_sd.data;
            if (sd && typeof sd === 'object' && 'has_active' in (sd as object)) {
              setProviderSubStatus(sd as typeof providerSubStatus);
            }
          } catch {}
        } catch {
          setPaymentBanner('✅ Payment received! Your subscription will activate shortly.');
        }
      })();
    } else {
      setPaymentBanner('✅ Payment received! Your subscription will activate shortly.');
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const activeRFQCards = [...teasers]
    .filter(t => t.status !== 'quoted' && (t as any).rfq_status === 'open_for_unlock')
    .sort((a, b) => new Date((b as any).created_at ?? 0).getTime() - new Date((a as any).created_at ?? 0).getTime())
    .slice(0, 3);

  return (
    <div className="min-h-screen bg-slate-50">

      {/* Payment success banner */}
      {paymentBanner && (
        <div className="bg-emerald-50 border-b border-emerald-200 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-600 shrink-0" />
            <p className="text-sm font-medium text-emerald-800">{paymentBanner}</p>
          </div>
          <button onClick={() => setPaymentBanner(null)} className="text-emerald-600 hover:text-emerald-800 text-lg leading-none">&times;</button>
        </div>
      )}

      {/* Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500 mb-1">Provider Portal</p>
              <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
            </div>
            <Link
              href="/provider/profile"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#0a1f3e] transition-colors"
            >
              <span>Manage Profile</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Analytics Panel */}
          <div className="lg:col-span-1">
            <ProviderAnalyticsPanel
              teasers={teasers}
              quotes={quotes}
              hasMembership={hasMembership}
              user={user}
              contactedRfqIds={contactedRfqIds}
              providerSubStatus={providerSubStatus}
            />
          </div>
          {/* RFQ Cards */}
          <div className="lg:col-span-2">
            <div className="bg-white border border-slate-200 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2">
                  <Inbox className="h-5 w-5 text-[#0F2B54]" />
                  <h2 className="text-base font-bold text-slate-900">Recent Active RFQs</h2>
                </div>
                <Link
                  href="/provider/all-rfqs"
                  className="text-xs text-[#0F2B54] font-medium hover:underline flex items-center gap-1"
                >
                  View all <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {activeRFQCards.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3">
                    <Inbox className="h-6 w-6 text-slate-400" />
                  </div>
                  <p className="text-sm font-medium text-slate-700 mb-1">No active RFQs</p>
                  <p className="text-xs text-slate-500 max-w-xs">
                    When customers send RFQ invitations that match your profile, they will appear here.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {activeRFQCards.map(teaser => (
                    <div
                      key={teaser.rfq_id}
                      className="rounded-2xl border border-slate-200 p-4 hover:border-slate-300 hover:shadow-sm transition-all"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">
                            RFQ #{String(teaser.rfq_id).slice(0, 8).toUpperCase()}
                          </p>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {(teaser as any).created_at
                              ? new Date((teaser as any).created_at).toLocaleDateString()
                              : 'Recent'}
                          </p>
                        </div>
                        <UrgencyBadge urgency={teaser.urgency} />
                      </div>
                      {teaser.tollgate_phases && teaser.tollgate_phases.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-3">
                          {teaser.tollgate_phases.map((phase: string) => (
                            <span
                              key={phase}
                              className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600"
                            >
                              {phase}
                            </span>
                          ))}
                        </div>
                      )}
                      <Link
                        href={`/provider/rfq/${teaser.rfq_id}`}
                        className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#0F2B54] hover:text-[#0a1f3e] transition-colors"
                      >
                        View RFQ <ArrowRight className="h-3 w-3" />
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Outer page — Suspense boundary required for useSearchParams in Next.js 15 ─

export default function ProviderDashboard() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <ProviderDashboardInner />
    </Suspense>
  );
}
