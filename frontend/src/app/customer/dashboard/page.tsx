'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import {
  AlertCircle, RefreshCw, Plus, Activity, FileText,
  CheckCircle, XCircle, MessageSquare, Clock, Calendar,
  TrendingUp, Shield, ArrowRight, CreditCard, Zap, LifeBuoy
} from 'lucide-react';
import {
  CustomerRFQ, ACTIVE_STATUSES, RfqCard, SkeletonCard,
  formatDate
} from '../_shared/RfqListPage';

// ─── Types ────────────────────────────────────────────────────────────────────

interface SubStatus {
  has_active: boolean;
  subscription_type: string | null;
  current_period_end: string | null;
  cancel_at: string | null;
}

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color: string;
}

interface MiniBarProps {
  value: number;
  max: number;
  color: string;
}

interface SubscriptionCardProps {
  subStatus: SubStatus | null;
  isLoading: boolean;
}

interface AnalyticsPanelProps {
  rfqs: CustomerRFQ[];
  user: { created_at?: string; email: string } | null;
  subStatus: SubStatus | null;
}

interface ContactFormState {
  category: string;
  subject: string;
  message: string;
}

// ─── Small UI helpers ─────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div className={`rounded-xl border p-4 ${color}`}>
      <p className="text-xs font-medium text-slate-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function MiniBar({ value, max, color }: MiniBarProps) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="w-full bg-slate-100 rounded-full h-1.5 mt-1">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// ─── Subscription Card ────────────────────────────────────────────────────────

function SubscriptionCard({ subStatus, isLoading }: SubscriptionCardProps) {
  const isActive = subStatus?.has_active === true;
  const tier = subStatus?.subscription_type;
  const displayTier = 'Search Plan';

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 mt-4">
      <div className="flex items-center gap-2 mb-4">
        <CreditCard className="h-5 w-5 text-[#0F2B54]" />
        <h2 className="text-base font-bold text-slate-900">Subscription</h2>
      </div>
      {isLoading ? (
        <div className="animate-pulse">
          <div className="h-4 bg-slate-200 rounded w-1/2 mb-3" />
          <div className="h-10 bg-slate-100 rounded-xl" />
        </div>
      ) : !isActive ? (
        <>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Current Plan</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">Free</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">5 searches / month included.</p>
          <Link href="/billing">
            <button className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl font-semibold text-sm transition-all duration-150 shadow-sm hover:shadow-md">
              <Zap className="h-4 w-4" /> Upgrade — $20/month
            </button>
          </Link>
          <p className="text-xs text-slate-400 text-center mt-2">100 searches/month</p>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Current Plan</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">{displayTier}</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">100 searches / month — $20/month.</p>
          <Link href="/billing">
            <button className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 border border-[#0F2B54] text-[#0F2B54] hover:bg-[#0F2B54] hover:text-white rounded-xl font-semibold text-sm transition-all duration-150">
              <CreditCard className="h-4 w-4" /> Active — Manage Subscription
            </button>
          </Link>
        </>
      )}
    </div>
  );
}

// ─── Analytics Panel ──────────────────────────────────────────────────────────

function AnalyticsPanel({ rfqs, user, subStatus }: AnalyticsPanelProps) {
  const total = rfqs.length;
  const active = rfqs.filter(r => ACTIVE_STATUSES.includes(r.rfq_status)).length;
  const cancelled = rfqs.filter(r => r.rfq_status === 'cancelled').length;
  const accepted = rfqs.filter(r => r.rfq_status === 'customer_selected_provider').length;
  const quoted = rfqs.filter(r => r.quote_count > 0).length;
  const totalQuotes = rfqs.reduce((s, r) => s + (r.quote_count || 0), 0);
  const avgQuotes = total > 0 ? (totalQuotes / total).toFixed(1) : '0';
  const ndaSigned = rfqs.filter(r => r.nda_required && r.rfq_status === 'customer_selected_provider').length;
  const ndaAwaiting = rfqs.filter(r => r.nda_awaiting_customer_signature && !r.is_closed && r.rfq_status !== 'cancelled').length;

  const quotedWithDate = rfqs.filter(r => r.quote_count > 0 && r.submitted_at);
  const avgDays = quotedWithDate.length > 0
    ? Math.round(quotedWithDate.reduce((s, r) => {
        const ms = Date.now() - new Date(r.submitted_at!).getTime();
        return s + ms / (1000 * 60 * 60 * 24);
      }, 0) / quotedWithDate.length)
    : null;

  const tier = subStatus?.has_active
    ? 'Search Plan'
    : 'Free';
  const createdAt = user?.created_at;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 h-fit">
      <div className="flex items-center gap-2 mb-5">
        <TrendingUp className="h-5 w-5 text-[#0F2B54]" />
        <h2 className="text-base font-bold text-slate-900">Activity Summary</h2>
      </div>

      {ndaAwaiting > 0 && (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-bold text-amber-900">
              Action required: {ndaAwaiting} NDA{ndaAwaiting > 1 ? 's' : ''} awaiting your signature
            </p>
            <p className="text-xs text-amber-800 mt-0.5">
              A provider signed to access your RFQ &mdash; check your email to countersign so they can proceed.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-5">
        <StatCard label="Total RFQs" value={total} color="bg-slate-50 border-slate-200" />
        <StatCard label="Active" value={active} color="bg-blue-50 border-blue-200" />
        <StatCard label="Total Quotes" value={totalQuotes} color="bg-emerald-50 border-emerald-200" />
        <StatCard label="Avg Quotes/RFQ" value={avgQuotes} color="bg-violet-50 border-violet-200" />
      </div>

      <div className="space-y-2.5 mb-5">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Breakdown</p>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <MessageSquare className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Quoted RFQs</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{quoted}</span>
          </div>
          <MiniBar value={quoted} max={total} color="bg-emerald-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <CheckCircle className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Accepted</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{accepted}</span>
          </div>
          <MiniBar value={accepted} max={total} color="bg-teal-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <XCircle className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">Cancelled</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{cancelled}</span>
          </div>
          <MiniBar value={cancelled} max={total} color="bg-slate-400" />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Shield className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-xs text-slate-600">NDAs Signed</span>
            </div>
            <span className="text-xs font-bold text-slate-900">{ndaSigned}</span>
          </div>
          <MiniBar value={ndaSigned} max={total} color="bg-violet-400" />
        </div>
      </div>

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
            <FileText className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-xs text-slate-500">Plan</span>
          </div>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
            tier === 'Free' ? 'bg-slate-100 text-slate-600' : 'bg-blue-100 text-blue-700'
          }`}>{tier}</span>
        </div>
        {avgDays !== null && (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              <span className="text-xs text-slate-500">Avg days to quote</span>
            </div>
            <span className="text-xs font-medium text-slate-700">{avgDays}d</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Inner dashboard (uses useSearchParams — must be wrapped in Suspense) ─────

function CustomerDashboardInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, isLoading: authLoading } = useRequireAuth(['customer', 'admin']);

  const [rfqs, setRfqs] = useState<CustomerRFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Subscription status — fetched live from API (User model has no subscription_tier field)
  const [subStatus, setSubStatus] = useState<SubStatus | null>(null);
  const [subLoading, setSubLoading] = useState(true);

  // Payment success banner
  const [paymentBanner, setPaymentBanner] = useState<string | null>(null);

  // Contact support modal
  const [showContactModal, setShowContactModal] = useState(false);
  const [contactForm, setContactForm] = useState<ContactFormState>({ category: 'general', subject: '', message: '' });
  const [contactSubmitting, setContactSubmitting] = useState(false);
  const [contactSuccess, setContactSuccess] = useState(false);

  // ── Fetch live subscription status ──────────────────────────────────────────
  const fetchSubStatus = useCallback(async () => {
    try {
      const { apiClient } = await import('@/lib/api');
      const resp = await apiClient.get('/billing/subscription-status');
      setSubStatus(resp.data as SubStatus);
    } catch {
      setSubStatus({ has_active: false, subscription_type: null, current_period_end: null, cancel_at: null });
    } finally {
      setSubLoading(false);
    }
  }, []);

  // ── Handle Stripe redirect with ?payment=success&session_id=xxx ─────────────
  useEffect(() => {
    const payment = searchParams.get('payment');
    const sessionId = searchParams.get('session_id');
    const purpose = searchParams.get('purpose') || 'search_subscription';
    if (payment !== 'success') return;

    // Always clean the URL immediately
    router.replace('/customer/dashboard');

    if (sessionId) {
      // Verified fulfillment path — call backend to confirm + fulfill
      (async () => {
        try {
          const { apiClient } = await import('@/lib/api');
          await apiClient.post('/billing/verify-subscription', { session_id: sessionId, purpose });
          setPaymentBanner('🎉 Your subscription is now active!');
          await fetchSubStatus();
        } catch {
          // Webhook may have already fulfilled — just refresh status
          setPaymentBanner('✅ Payment received! Your subscription will activate shortly.');
          await fetchSubStatus();
        }
      })();
    } else {
      // Legacy flow without session_id
      setPaymentBanner('✅ Payment received! Your subscription will activate shortly.');
      fetchSubStatus();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchSubStatus();
  }, [fetchSubStatus]);

  // ── Load RFQs ────────────────────────────────────────────────────────────────
  const load = useCallback(async (silent = false) => {
    if (!user) return;
    if (!silent) setIsLoading(true);
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
      all.sort((a, b) => {
        const da = new Date(a.submitted_at || a.created_at || 0).getTime();
        const db2 = new Date(b.submitted_at || b.created_at || 0).getTime();
        return db2 - da;
      });
      setRfqs(all);
    } catch (e) {
      console.error(e);
      setLoadError('Network error — please refresh.');
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  // Live updates: load on mount, poll every 20s, and refresh when the user
  // returns to the tab so the Activity Summary notes (NDA awaiting signature,
  // active/accepted/cancelled) reflect current state without a manual reload.
  useEffect(() => {
    if (!user) return;
    load();
    const id = setInterval(() => load(true), 20000);
    const onFocus = () => load(true);
    const onVisible = () => { if (document.visibilityState === 'visible') load(true); };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(id);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [user, load]);

  const handleCancelled = (rfqId: string) => {
    setRfqs(prev => prev.map(r =>
      r.id === rfqId ? { ...r, rfq_status: 'cancelled', is_closed: true } : r
    ));
  };

  const activeRfqs = rfqs.filter(r => ACTIVE_STATUSES.includes(r.rfq_status)).slice(0, 3);

  const handleContactSubmit = async () => {
    setContactSubmitting(true);
    try {
      const { apiClient } = await import('@/lib/api');
      await apiClient.post('/support/contact-authenticated', contactForm);
      setContactSuccess(true);
      setTimeout(() => {
        setShowContactModal(false);
        setContactSuccess(false);
        setContactForm({ category: 'general', subject: '', message: '' });
      }, 2500);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = e?.response?.data?.detail || e?.message || String(err);
      alert('Failed to submit (' + detail + '). Please email info@mail.promechdirectory.com directly.');
    } finally {
      setContactSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

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
              <p className="text-sm font-medium text-slate-500 mb-1">Customer Portal</p>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">Dashboard</h1>
              <p className="mt-1 text-sm text-slate-600">Your engineering RFQ activity at a glance</p>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => setShowContactModal(true)} className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-50 hover:border-slate-300 transition-colors">
                <LifeBuoy className="h-4 w-4" /> Contact Support
              </button>
              <Link href="/">
                <button className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl font-semibold text-sm transition-all duration-150 shadow-sm hover:shadow-md">
                  <Plus className="h-4 w-4" /> New RFQ
                </button>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {loadError && (
          <div className="mb-6 flex items-start gap-3 px-4 py-3.5 bg-rose-50 border border-rose-200 rounded-xl">
            <AlertCircle className="h-4 w-4 text-rose-600 mt-0.5 shrink-0" />
            <p className="flex-1 text-sm font-medium text-rose-700">{loadError}</p>
            <button onClick={() => { setLoadError(null); load(); }}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-600 hover:text-rose-800 shrink-0">
              <RefreshCw className="h-3 w-3" /> Retry
            </button>
          </div>
        )}

        {isLoading ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-1/2 mb-4" />
                <div className="grid grid-cols-2 gap-3">
                  {[1,2,3,4].map(i => <div key={i} className="h-16 bg-slate-100 rounded-xl" />)}
                </div>
              </div>
            </div>
            <div className="lg:col-span-2 space-y-4">
              <SkeletonCard /><SkeletonCard /><SkeletonCard />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* LEFT: Analytics + Subscription */}
            <div className="lg:col-span-1">
              <AnalyticsPanel rfqs={rfqs} user={user as { created_at?: string; email: string } | null} subStatus={subStatus} />
              <SubscriptionCard subStatus={subStatus} isLoading={subLoading} />
            </div>

            {/* RIGHT: Last 3 active RFQs */}
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-[#0F2B54]" />
                  <h2 className="text-base font-bold text-slate-900">Active RFQs</h2>
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                    {rfqs.filter(r => ACTIVE_STATUSES.includes(r.rfq_status)).length} total
                  </span>
                </div>
                <Link href="/customer/active-rfqs" className="inline-flex items-center gap-1 text-xs text-[#0F2B54] hover:underline font-medium">
                  See all <ArrowRight className="h-3 w-3" />
                </Link>
              </div>

              {activeRfqs.length === 0 ? (
                <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center">
                  <Activity className="h-10 w-10 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-500 text-sm font-medium">No active RFQs at the moment</p>
                  <p className="text-slate-400 text-xs mt-1">Submit a new RFQ to get started</p>
                  <Link href="/">
                    <button className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-medium hover:bg-[#1a3a6b] transition-colors">
                      <Plus className="h-3.5 w-3.5" /> New RFQ
                    </button>
                  </Link>
                </div>
              ) : (
                <div className="space-y-4">
                  {activeRfqs.map(rfq => (
                    <RfqCard key={rfq.id} rfq={rfq} showCancel onCancelled={handleCancelled} />
                  ))}
                  {rfqs.filter(r => ACTIVE_STATUSES.includes(r.rfq_status)).length > 3 && (
                    <Link href="/customer/active-rfqs">
                      <div className="flex items-center justify-center gap-2 py-3 border-2 border-dashed border-slate-200 rounded-xl text-sm text-slate-500 hover:border-[#0F2B54] hover:text-[#0F2B54] transition-colors cursor-pointer">
                        <ArrowRight className="h-4 w-4" />
                        View all active RFQs
                      </div>
                    </Link>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Contact Support Modal */}
      {showContactModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
            <div className="flex items-center justify-between p-6 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <LifeBuoy className="h-5 w-5 text-[#0F2B54]" />
                <h2 className="text-lg font-bold text-slate-900">Contact Support</h2>
              </div>
              <button onClick={() => setShowContactModal(false)} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
            </div>
            {contactSuccess ? (
              <div className="p-8 text-center">
                <CheckCircle className="h-12 w-12 text-emerald-500 mx-auto mb-3" />
                <p className="text-lg font-semibold text-slate-800">Message Sent!</p>
                <p className="text-sm text-slate-500 mt-1">We will get back to you within 24 hours.</p>
              </div>
            ) : (
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Issue Category</label>
                  <select
                    value={contactForm.category}
                    onChange={e => setContactForm(f => ({ ...f, category: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20"
                  >
                    <option value="payment">Payment or billing issue</option>
                    <option value="bug">Website problem or error</option>
                    <option value="add_firm">Add or claim my firm</option>
                    <option value="rfq_nda">RFQ or NDA question</option>
                    <option value="general">General information</option>
                    <option value="collaboration">Collaboration or partnership</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Subject</label>
                  <input
                    type="text"
                    value={contactForm.subject}
                    onChange={e => setContactForm(f => ({ ...f, subject: e.target.value }))}
                    placeholder="Brief summary of your issue"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1.5">Description</label>
                  <textarea
                    value={contactForm.message}
                    onChange={e => setContactForm(f => ({ ...f, message: e.target.value }))}
                    rows={4}
                    placeholder="Please describe your issue in detail..."
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20 resize-none"
                  />
                </div>
                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => setShowContactModal(false)}
                    className="flex-1 px-4 py-2 border border-slate-200 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleContactSubmit}
                    disabled={contactSubmitting || !contactForm.subject || !contactForm.message}
                    className="flex-1 px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-semibold hover:bg-[#1a3a6b] transition-colors disabled:opacity-60"
                  >
                    {contactSubmitting ? 'Sending...' : 'Send Message'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Outer page — Suspense boundary required for useSearchParams in Next.js 15 ─

export default function CustomerDashboard() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <CustomerDashboardInner />
    </Suspense>
  );
}
