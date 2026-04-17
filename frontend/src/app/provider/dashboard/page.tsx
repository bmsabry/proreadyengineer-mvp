'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api, apiClient } from '@/lib/api';
import { RFQTeaser, Quote } from '@/types';
import { formatDate } from '@/lib/utils';
import {
  TrendingUp, FileText, CheckCircle, Clock, XCircle,
  FileSignature, Calendar, ArrowRight, Inbox,
  CreditCard, Bell, Phone, Crown, Megaphone,
  Loader2, AlertCircle, X,
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

// --- Advertisement status card (replaces static Advertise CTA) -------------

interface ProviderAd {
  id: string;
  title: string;
  page_type?: string | null;
  ad_status: string;
  admin_review_notes?: string | null;
  reviewed_at?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
}

function AdvertisementStatusCard() {
  const [ads, setAds] = useState<ProviderAd[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  const fetchAds = async () => {
    try {
      const resp = await apiClient.get('/me/promotions');
      const list = Array.isArray(resp.data) ? resp.data : [];
      setAds(list);
      setFetchError(null);
      // eslint-disable-next-line no-console
      console.log('[AdStatusCard] /advertiser/ads/me returned', list.length, 'ad(s)', list.map((a: any) => ({ id: a.id, ad_status: a.ad_status, title: a.title })));
    } catch (err: any) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.message || 'unknown error';
      setFetchError(`HTTP ${status ?? '?'}: ${detail}`);
      // eslint-disable-next-line no-console
      console.error('[AdStatusCard] fetch failed', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAds();
    const id = setInterval(fetchAds, 15000);
    return () => clearInterval(id);
  }, []);

  // Pick the most-recently-updated ad in a non-terminal state, or the latest
  // ad overall if none are active.
  const relevantStatuses = new Set([
    'processing', 'pending_review', 'reserved_checkout_pending',
    'active', 'rejected',
  ]);
  const relevantAds = ads.filter((a) => relevantStatuses.has(a.ad_status));
  const ordered = [...(relevantAds.length > 0 ? relevantAds : ads)].sort((a, b) => {
    const ta = new Date(a.reviewed_at || a.updated_at || a.created_at || 0).getTime();
    const tb = new Date(b.reviewed_at || b.updated_at || b.created_at || 0).getTime();
    return tb - ta;
  });
  const ad = ordered[0];

  const dismissStalledAd = async (adId: string) => {
    try {
      await apiClient.post(`/me/promotions/${adId}/cancel`);
      // Optimistic: remove locally so card flips to 'no ads' state.
      setAds((prev) => prev.filter((x) => x.id !== adId));
      setModalOpen(false);
    } catch (err: any) {
      // eslint-disable-next-line no-console
      console.error('[AdStatusCard] dismiss failed', err);
    }
  };

  const startCheckout = async (adId: string) => {
    setCheckoutLoading(true);
    setCheckoutError(null);
    try {
      const resp = await apiClient.post(`/me/promotions/${adId}/checkout-session`);
      const data = resp.data;
      if (data.already_paid) {
        window.location.reload();
        return;
      }
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      throw new Error('Checkout URL was not returned by the server.');
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Unable to start checkout.';
      setCheckoutError(msg);
      setCheckoutLoading(false);
    }
  };

  // ── Loading shimmer ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 flex items-center gap-3">
        <Loader2 className="h-4 w-4 text-slate-400 animate-spin shrink-0" />
        <p className="text-xs text-slate-500">Loading ad status…</p>
      </div>
    );
  }

  // ── Error state — show explicit diagnostic so we never silently
  //    fall back to a static CTA when the endpoint is failing.
  if (fetchError) {
    return (
      <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 flex items-start gap-2">
        <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-red-700">Could not load ad status</p>
          <p className="text-[10px] text-red-600 truncate">{fetchError}</p>
          <button type="button" onClick={() => { setLoading(true); fetchAds(); }} className="text-[10px] text-red-700 font-semibold underline mt-1">Retry</button>
        </div>
      </div>
    );
  }

  // ── No ads at all — show a clearly-NEW CTA (different text from the old
  //    static one so we can tell at a glance whether the new code shipped).
  if (!ad) {
    return (
      <Link href="/provider/advertise">
        <div className="mt-3 rounded-xl border border-violet-200 bg-gradient-to-r from-violet-50 to-blue-50 p-3 flex items-center gap-3 hover:shadow-sm hover:border-violet-300 transition-all cursor-pointer group">
          <div className="w-8 h-8 rounded-lg bg-violet-100 flex items-center justify-center shrink-0">
            <Megaphone className="h-4 w-4 text-violet-600" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-slate-900 group-hover:text-violet-700 transition-colors">Start an ad ($50/mo)</p>
            <p className="text-[10px] text-slate-500">No ads yet — click to create one</p>
          </div>
          <ArrowRight className="h-3.5 w-3.5 text-violet-400 group-hover:text-violet-600 transition-colors shrink-0" />
        </div>
      </Link>
    );
  }

  // Status-driven card presentation.
  const status = ad.ad_status;
  // A 'processing' ad that is more than 3 minutes old is considered
  // stalled (LLM generation probably died). Show a clear dead-end UI
  // with a Dismiss button so the provider isn't stuck.
  const STALL_THRESHOLD_MS = 3 * 60 * 1000;
  const createdTs = new Date(ad.created_at || ad.updated_at || 0).getTime();
  const ageMs = Date.now() - createdTs;
  const isStalled = status === 'processing' && createdTs > 0 && ageMs > STALL_THRESHOLD_MS;
  const isProcessing = status === 'processing' && !isStalled;
  const isPending = status === 'pending_review';
  const isCheckoutPending = status === 'reserved_checkout_pending';
  const isActive = status === 'active';
  const isRejected = status === 'rejected';

  const cardClass = isStalled
    ? 'border-red-200 bg-red-50 hover:border-red-300'
    : isCheckoutPending
    ? 'border-amber-300 bg-gradient-to-r from-amber-50 to-orange-50 hover:border-amber-400 ring-1 ring-amber-200'
    : isActive
      ? 'border-emerald-200 bg-gradient-to-r from-emerald-50 to-teal-50 hover:border-emerald-300'
      : isRejected
        ? 'border-red-200 bg-gradient-to-r from-red-50 to-orange-50 hover:border-red-300'
        : isPending
          ? 'border-amber-200 bg-gradient-to-r from-amber-50 to-yellow-50 hover:border-amber-300'
          : 'border-violet-200 bg-gradient-to-r from-violet-50 to-blue-50 hover:border-violet-300';

  const iconBg = isStalled
    ? 'bg-red-100'
    : isCheckoutPending
    ? 'bg-amber-100'
    : isActive
      ? 'bg-emerald-100'
      : isRejected
        ? 'bg-red-100'
        : isPending
          ? 'bg-amber-100'
          : 'bg-violet-100';

  const Icon = isStalled
    ? AlertCircle
    : isCheckoutPending
    ? CreditCard
    : isActive
      ? CheckCircle
      : isRejected
        ? XCircle
        : isPending
          ? Clock
          : isProcessing
            ? Loader2
            : Megaphone;

  const iconColor = isStalled
    ? 'text-red-600'
    : isCheckoutPending
    ? 'text-amber-600'
    : isActive
      ? 'text-emerald-600'
      : isRejected
        ? 'text-red-600'
        : isPending
          ? 'text-amber-600'
          : 'text-violet-600';

  const title = isStalled
    ? 'Ad generation stalled'
    : isCheckoutPending
    ? 'Approved - Pay to Publish'
    : isActive
      ? 'Your ad is live'
      : isRejected
        ? 'Ad not approved'
        : isPending
          ? 'Pending admin review'
          : isProcessing
            ? 'Generating your ad...'
            : 'Advertise with Us';

  const subtitle = isStalled
    ? 'Dismiss and submit a new ad'
    : isCheckoutPending
    ? 'Click to complete the $50/month subscription'
    : isActive
      ? `${ad.title} - visible on the directory`
      : isRejected
        ? 'Click to view admin feedback'
        : isPending
          ? 'Usually reviewed within 1 business day'
          : isProcessing
            ? 'This usually takes 1-2 minutes'
            : 'Promote your services - $50/month';

  return (
    <>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className={`mt-3 w-full text-left rounded-xl border p-3 flex items-center gap-3 hover:shadow-sm transition-all cursor-pointer ${cardClass}`}
      >
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${iconBg}`}>
          <Icon className={`h-4 w-4 ${iconColor} ${isProcessing ? 'animate-spin' : ''}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-bold text-slate-900 truncate">{title}</p>
          <p className="text-[10px] text-slate-500 truncate">{subtitle}</p>
        </div>
        <ArrowRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />
      </button>

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="absolute top-3 right-3 text-slate-400 hover:text-slate-700"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="flex items-center gap-3 mb-4">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${iconBg}`}>
                <Icon className={`h-5 w-5 ${iconColor} ${isProcessing ? 'animate-spin' : ''}`} />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">{title}</h3>
                <p className="text-xs text-slate-500 truncate">{ad.title}</p>
              </div>
            </div>

            {isProcessing && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                <p className="font-semibold mb-1">What happens next:</p>
                <ol className="list-decimal list-inside space-y-1 text-blue-700 text-xs">
                  <li>Our AI reads all pages of your website.</li>
                  <li>Your ad card is professionally generated.</li>
                  <li>An admin reviews and approves the ad.</li>
                  <li>You complete the $50/month subscription.</li>
                  <li>Your ad goes live on the directory.</li>
                </ol>
              </div>
            )}

            {isPending && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                <p className="font-semibold mb-1">Queued for admin review</p>
                <p className="text-amber-700 text-xs">An admin will review the generated ad copy and approve or reject within 1 business day. We will email you as soon as there is a decision.</p>
              </div>
            )}

            {isStalled && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-800 text-sm font-semibold mb-1">This ad’s generation appears to have stalled.</p>
                <p className="text-red-700 text-xs mb-3">It has been processing for more than 3 minutes. You can dismiss it and submit a new one.</p>
                <button
                  type="button"
                  onClick={() => dismissStalledAd(ad.id)}
                  className="w-full bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-red-700 transition-colors"
                >Dismiss this ad</button>
              </div>
            )}

            {isCheckoutPending && (
              <div className="space-y-3">
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                  <p className="font-semibold mb-1">Approved - one last step</p>
                  <p className="text-amber-700 text-xs">Your ad has been approved by our review team. Complete the $50/month subscription to publish it to the public directory. The ad will go live within seconds of a successful payment.</p>
                </div>
                {checkoutError && (
                  <p className="text-red-700 text-xs">{checkoutError}</p>
                )}
                <button
                  type="button"
                  disabled={checkoutLoading}
                  onClick={() => startCheckout(ad.id)}
                  className="w-full py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
                >
                  {checkoutLoading ? 'Redirecting to Stripe...' : 'Pay & Publish ($50/month)'}
                </button>
              </div>
            )}

            {isActive && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-sm text-emerald-800">
                <p className="font-semibold mb-1">Live on the directory</p>
                <p className="text-emerald-700 text-xs">Your ad is visible to visitors. An email confirmation was sent to your inbox.</p>
                <Link href={ad.page_type === 'software-providers' ? '/software-providers' : '/featured-firms'}>
                  <span className="inline-flex items-center gap-1 mt-2 text-emerald-700 underline text-xs">
                    View the public directory <ArrowRight className="h-3 w-3" />
                  </span>
                </Link>
              </div>
            )}

            {isRejected && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
                <p className="font-semibold mb-1">Admin feedback</p>
                <p className="text-red-700 text-xs whitespace-pre-wrap">
                  {ad.admin_review_notes || 'An admin reviewed the ad and decided not to publish it. A detailed email was sent explaining why and what to adjust before resubmitting.'}
                </p>
                <Link href="/provider/advertise">
                  <span className="inline-flex items-center gap-1 mt-2 text-red-700 underline text-xs">
                    Submit an updated ad <ArrowRight className="h-3 w-3" />
                  </span>
                </Link>
              </div>
            )}

            <div className="mt-4 pt-4 border-t border-slate-100 flex justify-between gap-2">
              <Link
                href="/provider/advertise"
                className="text-xs text-slate-500 hover:text-slate-800 underline"
              >
                Open ad management
              </Link>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

interface UserSubscription {
  id: string;
  type: string;
  label: string;
  status: string;
  current_period_end: string | null;
  current_period_start: string | null;
  cancel_at: string | null;
  billing_interval: 'month' | 'year' | 'one_time';
  amount_display: string | null;
  has_stripe_subscription: boolean;
  advertisement_id: string | null;
  warning?: string;
}

function ProviderAnalyticsPanel({
  teasers, quotes, hasMembership, user, contactedRfqIds, providerSubStatus, userSubs,
}: {
  teasers: RFQTeaser[];
  quotes: Quote[];
  hasMembership: boolean;
  user: any;
  contactedRfqIds: string[];
  providerSubStatus?: { has_active: boolean; subscription_type: string | null; current_period_end: string | null; cancel_at: string | null } | null;
  userSubs: UserSubscription[];
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
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <CreditCard className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs text-slate-500">Subscriptions</span>
          </div>
          {userSubs.length === 0 ? (
            <Link href="/provider/upgrade">
              <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors cursor-pointer">
                Inactive — Upgrade
              </span>
            </Link>
          ) : (
            <ul className="space-y-2">
              {userSubs.map((sub) => {
                const isAnnual = sub.type === 'provider_annual';
                const isAdSub = sub.type === 'advertisement';
                const isAdLegacy = sub.type === 'advertisement_legacy';
                const pillClasses = isAnnual
                  ? 'bg-blue-100 text-blue-700 border-blue-200'
                  : (isAdSub || isAdLegacy)
                  ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                  : 'bg-slate-100 text-slate-700 border-slate-200';
                const amount = sub.amount_display
                  || (sub.billing_interval === 'month' ? 'Monthly' : sub.billing_interval === 'year' ? 'Yearly' : 'One-time');
                const periodLabel = sub.billing_interval === 'one_time'
                  ? 'Does NOT auto-renew'
                  : sub.current_period_end
                  ? `Renews ${new Date(sub.current_period_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
                  : null;
                return (
                  <li key={sub.id} className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full border ${pillClasses}`}>
                        {isAnnual && <Crown className="h-3 w-3" />}
                        {sub.label}
                      </span>
                      <div className="mt-0.5 flex flex-wrap gap-x-2">
                        <span className="text-[10px] text-slate-500 font-medium">{amount}</span>
                        {periodLabel && (
                          <span className={`text-[10px] ${sub.billing_interval === 'one_time' ? 'text-amber-600 font-semibold' : 'text-slate-400'}`}>
                            {periodLabel}
                          </span>
                        )}
                        {sub.cancel_at && (
                          <span className="text-[10px] text-amber-600">
                            Cancels {new Date(sub.cancel_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                          </span>
                        )}
                      </div>
                      {sub.warning && (
                        <p className="mt-1 text-[10px] text-amber-700 leading-snug">{sub.warning}</p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
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
        {/* Status-aware Advertise card */}
        <AdvertisementStatusCard />
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
  const [userSubs, setUserSubs] = useState<UserSubscription[]>([]);
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
        const [tr, qr, sr, usr] = await Promise.all([
          api.providerRFQ.getTeasers(),
          api.quotes.getForProvider(),
          api.billing.getProviderSubscriptionStatus().catch(() => null),
          api.billing.getUserSubscriptions().catch(() => null),
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
        const usd = (usr as any)?.data ?? usr;
        if (usd && Array.isArray(usd.subscriptions)) {
          setUserSubs(usd.subscriptions);
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
          try {
            const _resp_us = await apiClient.get('/billing/user-subscriptions');
            const usd = _resp_us.data;
            if (usd && Array.isArray(usd.subscriptions)) {
              setUserSubs(usd.subscriptions);
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
              userSubs={userSubs}
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
