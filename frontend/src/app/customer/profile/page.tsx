'use client';

import { useState, useEffect } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import {
  User, Mail, Building2, Calendar, Shield, Star,
  CheckCircle, AlertCircle, CreditCard, Zap, Lock, Clock
} from 'lucide-react';
import Link from 'next/link';

interface SubscriptionInfo {
  has_active: boolean;
  subscription_type: string | null;
  current_period_end: string | null;
  cancel_at: string | null;
  nda_credits_total?: number;
  nda_credits_used?: number;
  nda_credits_remaining?: number;
}

export default function CustomerProfilePage() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [loadingSub, setLoadingSub] = useState(true);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [reactivateLoading, setReactivateLoading] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  useEffect(() => {
    if (!authLoading && user) {
      setLoadingSub(true);
      api.billing
        .getSubscriptionStatus()
        .then((res: any) => setSubscription(res.data))
        .catch(() => setSubscription({ has_active: false, subscription_type: null, current_period_end: null, cancel_at: null }))
        .finally(() => setLoadingSub(false));
    }
  }, [authLoading, user]);

  const handleCancelSubscription = async () => {
    setCancelLoading(true);
    setShowCancelConfirm(false);
    try {
      const res = await api.billing.cancelSubscription('customer_monthly');
      const data = res.data as any;
      if (data.immediate) {
        alert(data.message || 'Subscription cancelled.');
        window.location.reload();
      } else {
        setSubscription((prev) => (prev ? { ...prev, cancel_at: data.cancel_at } : prev));
        alert(data.message || "Your subscription won't renew; you keep access until the period ends.");
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to cancel subscription. Please try again.');
    } finally {
      setCancelLoading(false);
    }
  };

  const handleReactivateSubscription = async () => {
    setReactivateLoading(true);
    try {
      await api.billing.reactivateSubscription('customer_monthly');
      setSubscription((prev) => (prev ? { ...prev, cancel_at: null } : prev));
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to reactivate subscription. Please try again.');
    } finally {
      setReactivateLoading(false);
    }
  };

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#0F2B54]" />
      </div>
    );
  }

  const createdAt = user.created_at ? new Date(user.created_at) : null;
  const formattedDate = createdAt
    ? createdAt.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
    : '\u2014';

  const displayName =
    (user as any).full_name ||
    [(user as any).first_name, (user as any).last_name].filter(Boolean).join(' ') ||
    user.email.split('@')[0];

  const businessName = (user as any).business_name || null;
  const entityType = (user as any).entity_type || null;
  const state = (user as any).state || null;
  const emailVerified = (user as any).email_verified !== false;
  const lastLogin = (user as any).last_login_at ? new Date((user as any).last_login_at) : null;
  const monthlySearchCount = (user as any).monthly_search_count ?? 0;

  const isSubscribed = subscription?.has_active;
  const searchLimit = isSubscribed ? 100 : 5;
  const searchesRemaining = Math.max(0, searchLimit - monthlySearchCount);
  const searchPercent = Math.min(100, (monthlySearchCount / searchLimit) * 100);
  const ndaCreditsTotal = subscription?.nda_credits_total ?? 0;
  const ndaCreditsUsed = subscription?.nda_credits_used ?? 0;
  const ndaCreditsRemaining = subscription?.nda_credits_remaining ?? 0;
  const ndaPercent = ndaCreditsTotal > 0 ? Math.min(100, (ndaCreditsUsed / ndaCreditsTotal) * 100) : 0;

  const cancelAtDate = subscription?.cancel_at
    ? new Date(subscription.cancel_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : null;

  const renewsDate = subscription?.current_period_end
    ? new Date(subscription.current_period_end).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : null;

  const cancelConfirmMessage = cancelAtDate
    ? 'Are you sure? You will keep access until ' + cancelAtDate + '.'
    : 'Are you sure? If you are within the refund window (5 days for monthly, 14 days for annual) you will be refunded and access ends now; otherwise you keep access until the end of your current billing period and it will not renew.';

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Confirm Cancel Dialog */}
      {showCancelConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-slate-800 mb-2">Cancel Subscription?</h3>
            <p className="text-sm text-slate-600 mb-5">{cancelConfirmMessage}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowCancelConfirm(false)}
                className="flex-1 px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors"
              >
                Keep Subscription
              </button>
              <button
                onClick={handleCancelSubscription}
                disabled={cancelLoading}
                className="flex-1 px-4 py-2 bg-rose-600 text-white rounded-lg text-sm font-semibold hover:bg-rose-700 transition-colors disabled:opacity-60"
              >
                {cancelLoading ? 'Cancelling...' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ background: 'linear-gradient(135deg, #0F2B54 0%, #1a3a6b 100%)' }} className="px-8 py-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center text-white text-2xl font-bold">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">{displayName}</h1>
              <p className="text-blue-200 text-sm mt-0.5">{user.email}</p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                  isSubscribed ? 'bg-emerald-500/20 text-emerald-200' : 'bg-white/10 text-white/70'
                }`}>
                  {isSubscribed ? <Star className="h-3 w-3" /> : <User className="h-3 w-3" />}
                  {isSubscribed ? 'Search Subscriber' : 'Free Account'}
                </span>
                {emailVerified ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-200">
                    <CheckCircle className="h-3 w-3" /> Verified
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/20 text-amber-200">
                    <AlertCircle className="h-3 w-3" /> Unverified
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-8 py-8 space-y-6">

        {/* Account Information */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
            <User className="h-5 w-5 text-[#0F2B54]" />
            <h2 className="font-semibold text-slate-800">Account Information</h2>
          </div>
          <div className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Full Name</label>
              <p className="mt-1 text-slate-800 font-medium">{displayName}</p>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Email Address</label>
              <div className="mt-1 flex items-center gap-2">
                <p className="text-slate-800 font-medium">{user.email}</p>
                {emailVerified
                  ? <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                  : <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                }
              </div>
            </div>
            {businessName && (
              <div>
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Business / Entity Name</label>
                <p className="mt-1 text-slate-800 font-medium">{businessName}</p>
              </div>
            )}
            {entityType && (
              <div>
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Entity Type</label>
                <p className="mt-1 text-slate-800 font-medium capitalize">{entityType}</p>
              </div>
            )}
            {state && (
              <div>
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">State</label>
                <p className="mt-1 text-slate-800 font-medium">{state}</p>
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Account Created</label>
              <div className="mt-1 flex items-center gap-1.5 text-slate-800 font-medium">
                <Calendar className="h-4 w-4 text-slate-400" />
                {formattedDate}
              </div>
            </div>
            {lastLogin && (
              <div>
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Last Login</label>
                <div className="mt-1 flex items-center gap-1.5 text-slate-800 font-medium">
                  <Clock className="h-4 w-4 text-slate-400" />
                  {lastLogin.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Account Roles</label>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {user.roles.map((role) => (
                  <span key={role} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full capitalize">{role}</span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
            <Zap className="h-5 w-5 text-[#0F2B54]" />
            <h2 className="font-semibold text-slate-800">Account Tier &amp; Search Quota</h2>
          </div>
          <div className="px-6 py-5">
            {loadingSub ? (
              <div className="animate-pulse h-20 bg-slate-100 rounded-lg" />
            ) : isSubscribed ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Star className="h-5 w-5 text-emerald-500" />
                      <span className="font-semibold text-slate-800 text-lg">Search Subscriber</span>
                    </div>
                    <p className="text-slate-500 text-sm mt-0.5">100 searches / month &middot; $50/mo or $500/yr</p>
                    {cancelAtDate ? (
                      <p className="text-amber-600 text-xs mt-1 font-medium">Cancels on {cancelAtDate} &mdash; access continues until then</p>
                    ) : renewsDate ? (
                      <p className="text-slate-400 text-xs mt-1">Renews {renewsDate}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-col items-end gap-2 flex-shrink-0">
                    {cancelAtDate ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                        Cancels {cancelAtDate}
                      </span>
                    ) : null}
                    <div className="flex gap-2">
                      {cancelAtDate ? (
                        <button
                          onClick={handleReactivateSubscription}
                          disabled={reactivateLoading}
                          className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
                        >
                          {reactivateLoading ? 'Reactivating...' : 'Reactivate'}
                        </button>
                      ) : (
                        <button
                          onClick={() => setShowCancelConfirm(true)}
                          disabled={cancelLoading}
                          className="px-3 py-1.5 border border-rose-300 text-rose-600 rounded-lg text-xs font-semibold hover:bg-rose-50 transition-colors disabled:opacity-60"
                        >
                          {cancelLoading ? 'Cancelling...' : 'Cancel Subscription'}
                        </button>
                      )}
                      <Link
                        href="/billing"
                        className="px-3 py-1.5 border border-slate-300 text-slate-700 rounded-lg text-xs font-medium hover:bg-slate-50 transition-colors"
                      >
                        Manage
                      </Link>
                    </div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-slate-600">Searches used this month</span>
                    <span className="font-medium text-slate-800">{monthlySearchCount} / {searchLimit}</span>
                  </div>
                  <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full transition-all"
                      style={{ width: searchPercent + '%' }}
                    />
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{searchesRemaining} searches remaining this month</p>
                </div>
                {ndaCreditsTotal > 0 && (
                  <div className="border-t border-slate-100 pt-4">
                    <div className="flex justify-between text-sm mb-1.5">
                      <span className="text-slate-600">Free NDAs this month</span>
                      <span className="font-medium text-slate-800">{ndaCreditsUsed} / {ndaCreditsTotal}</span>
                    </div>
                    <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full transition-all"
                        style={{ width: ndaPercent + '%' }}
                      />
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{ndaCreditsRemaining} NDAs remaining &#xB7; $50 value included with your plan</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <User className="h-5 w-5 text-slate-400" />
                      <span className="font-semibold text-slate-800 text-lg">Free Account</span>
                    </div>
                    <p className="text-slate-500 text-sm mt-0.5">5 searches / month &middot; No charge</p>
                  </div>
                  <Link
                    href="/billing"
                    className="px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-semibold hover:bg-[#1a3a6b] transition-colors flex items-center gap-1.5"
                  >
                    <Zap className="h-4 w-4" /> Upgrade &mdash; $50/mo
                  </Link>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1.5">
                    <span className="text-slate-600">Searches used this month</span>
                    <span className="font-medium text-slate-800">{monthlySearchCount} / {searchLimit}</span>
                  </div>
                  <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500 rounded-full transition-all"
                      style={{ width: searchPercent + '%' }}
                    />
                  </div>
                  <p className="text-xs text-slate-400 mt-1">{searchesRemaining} searches remaining &middot; Upgrade for 100/month</p>
                </div>
                <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg">
                  <p className="text-sm text-blue-800 font-medium">&#x1F680; Upgrade to Search Plan &mdash; $50/mo or $500/yr</p>
                  <p className="text-xs text-blue-600 mt-0.5">Get 100 searches/month, priority RFQ matching, and full platform access.</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Security & Password */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
            <Shield className="h-5 w-5 text-[#0F2B54]" />
            <h2 className="font-semibold text-slate-800">Security</h2>
          </div>
          <div className="px-6 py-5 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-800">Password</p>
                <p className="text-xs text-slate-400 mt-0.5">Last changed: unknown</p>
              </div>
              <Link
                href="/forgot-password"
                className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors flex items-center gap-1.5"
              >
                <Lock className="h-4 w-4" /> Change Password
              </Link>
            </div>
            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <div>
                <p className="text-sm font-medium text-slate-800">Email Verification</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {emailVerified ? 'Your email address is verified.' : 'Please verify your email address.'}
                </p>
              </div>
              {emailVerified ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-sm font-medium">
                  <CheckCircle className="h-4 w-4" /> Verified
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 text-amber-700 rounded-lg text-sm font-medium">
                  <AlertCircle className="h-4 w-4" /> Unverified
                </span>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
        {/* Account Tier & Search Quota */}