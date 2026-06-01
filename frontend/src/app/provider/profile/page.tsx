'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import {
  User, Calendar, Clock, CheckCircle, AlertCircle,
  Star, Zap, Crown, Building2, Lock
} from 'lucide-react';
import Link from 'next/link';

interface ProviderSubscription {
  has_active: boolean;
  subscription_type: string | null;
  current_period_end: string | null;
  cancel_at: string | null;
}

interface ProfileFormData {
  name: string;
  website: string;
  phone: string;
  address: string;
  city: string;
  state: string;
  postal_code: string;
  primary_specialty: string;
  business_description: string;
  capabilities: string;
  specialties: string;
  secondary_specialties: string;
  software_tools: string;
  notable_clients: string;
  email_addresses: string;
  certifications: string;
  notable_projects: string;
}

function splitCsv(val: string): string[] {
  return val.split(',').map(function(s) { return s.trim(); }).filter(function(s) { return s.length > 0; });
}

function joinArr(arr: string[] | null | undefined): string {
  if (!arr || !Array.isArray(arr)) return '';
  return arr.join(', ');
}

export default function ProviderProfilePage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [provider, setProvider] = useState(null as Provider | null);
  const [isLoading, setIsLoading] = useState(true);
  const [isInviteFlow, setIsInviteFlow] = useState(false);
  const [linkFailed, setLinkFailed] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const router = useRouter();
  const [fullEditStatus, setFullEditStatus] = useState(null as { paid: boolean; provider_id: string | null } | null);
  const [providerSub, setProviderSub] = useState(null as ProviderSubscription | null);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [reactivateLoading, setReactivateLoading] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  const [formData, setFormData] = useState({
    name: '',
    website: '',
    phone: '',
    address: '',
    city: '',
    state: '',
    postal_code: '',
    primary_specialty: '',
    business_description: '',
    capabilities: '',
    specialties: '',
    secondary_specialties: '',
    software_tools: '',
    notable_clients: '',
    email_addresses: '',
    certifications: '',
    notable_projects: '',
  } as ProfileFormData);

  useEffect(function() {
    if (!user) return;
    var didMount = true;

    function applyProfileData(data: any) {
      setProvider(data);
      setFormData({
        name: data.name || '',
        website: data.website || '',
        phone: data.phone || '',
        address: data.address || '',
        city: data.city || '',
        state: data.state || '',
        postal_code: data.postal_code || '',
        primary_specialty: data.primary_specialty || '',
        business_description: data.business_description || '',
        capabilities: joinArr(data.capabilities),
        specialties: joinArr(data.specialties),
        secondary_specialties: joinArr(data.secondary_specialties),
        software_tools: joinArr(data.software_tools),
        notable_clients: data.notable_clients || '',
        email_addresses: joinArr(data.email_addresses),
        certifications: joinArr(data.certifications),
        notable_projects: joinArr(data.proven_experience_notable_projects),
      });
    }

    async function fetchProvider(retryCount = 0) {
      const pendingToken = typeof window !== 'undefined'
        ? localStorage.getItem('pendingInviteToken')
        : null;
      if (pendingToken) {
        setIsInviteFlow(true);
        try { await api.auth.redeemInvite(pendingToken); }
        catch (redeemErr) {
          console.warn('[Profile] Invite redemption failed:', redeemErr);
          // If invite redemption itself failed, don't keep retrying
          if (didMount) {
            setIsInviteFlow(false);
            setLinkFailed(true);
            setIsLoading(false);
          }
          return;
        }
      }
      try {
        const response = await api.providers.getProfile();
        if (response.data && didMount) {
          applyProfileData(response.data);
          setIsInviteFlow(false);
          if (pendingToken) {
            localStorage.removeItem('pendingInviteToken');
            localStorage.removeItem('pendingInviteRfqId');
          }
        }
      } catch (err) {
        console.warn('[Profile] No provider profile found');
        // If invite flow, retry up to 2 times with a delay (backend may still be linking)
        if (pendingToken && retryCount < 2 && didMount) {
          setTimeout(function() { fetchProvider(retryCount + 1); }, 2000);
          return;
        }
        // After retries exhausted or no invite flow, show failure state
        if (didMount) {
          setIsInviteFlow(false);
          if (pendingToken) setLinkFailed(true);
        }
      } finally {
        // Only clear loading when we're not going to retry
        if (didMount && !(pendingToken && retryCount < 2)) setIsLoading(false);
      }
    }

    fetchProvider();
    return function() { didMount = false; };
  }, [user]);

  useEffect(function() {
    if (authLoading) return;
    api.providers.getFullEditStatus()
      .then(function(res) { setFullEditStatus(res.data); })
      .catch(function() {});
    api.billing.getProviderSubscriptionStatus()
      .then(function(res) { setProviderSub(res.data); })
      .catch(function() {
        setProviderSub({ has_active: false, subscription_type: null, current_period_end: null, cancel_at: null });
      });
  }, [authLoading]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    try {
      const payload = {
        name: formData.name,
        website: formData.website,
        phone: formData.phone,
        address: formData.address,
        city: formData.city,
        state: formData.state,
        postal_code: formData.postal_code,
        primary_specialty: formData.primary_specialty,
        business_description: formData.business_description,
        capabilities: splitCsv(formData.capabilities),
        specialties: splitCsv(formData.specialties),
        secondary_specialties: splitCsv(formData.secondary_specialties),
        software_tools: splitCsv(formData.software_tools),
        notable_clients: formData.notable_clients,
        email_addresses: splitCsv(formData.email_addresses),
        certifications: splitCsv(formData.certifications),
        proven_experience_notable_projects: splitCsv(formData.notable_projects),
      };
      await api.providers.saveFullEdit(payload);
      toast.success('Profile updated successfully');
    } catch (error) {
      toast.error('Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  }

  async function handleProfileEditCheckout() {
    try {
      const res = await api.providers.startFullEditCheckout();
      if (res.data?.payment_intent_id) {
        toast.success('Checkout initiated. Complete payment to unlock profile editing.');
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Failed to initiate checkout');
    }
  }

  async function handleCancelSubscription() {
    setCancelLoading(true);
    setShowCancelConfirm(false);
    try {
      const res = await api.billing.cancelSubscription('provider_annual');
      const data = res.data as any;
      if (data.immediate) {
        toast.success(data.message || 'Subscription cancelled.');
        setTimeout(function() { window.location.reload(); }, 1200);
      } else {
        setProviderSub(function(prev) {
          return prev ? { ...prev, cancel_at: data.cancel_at } : prev;
        });
        toast.success(data.message || "Subscription won't renew; access continues to period end.");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to cancel subscription. Please try again.');
    } finally {
      setCancelLoading(false);
    }
  }

  async function handleReactivateSubscription() {
    setReactivateLoading(true);
    try {
      await api.billing.reactivateSubscription('provider_annual');
      setProviderSub(function(prev) { return prev ? { ...prev, cancel_at: null } : prev; });
      toast.success('Subscription reactivated successfully.');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to reactivate subscription. Please try again.');
    } finally {
      setReactivateLoading(false);
    }
  }

  if (authLoading || isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#0F2B54]" />
      </div>
    );
  }

  const displayName =
    (user as any)?.full_name ||
    [(user as any)?.first_name, (user as any)?.last_name].filter(Boolean).join(' ') ||
    user?.email?.split('@')[0] || 'Provider';
  const emailVerified = (user as any)?.email_verified !== false;
  const createdAt = user?.created_at ? new Date(user.created_at) : null;
  const lastLogin = (user as any)?.last_login_at ? new Date((user as any).last_login_at) : null;

  const isAnnualPro = !!(providerSub?.has_active && providerSub.subscription_type === 'provider_annual');
  const hasProfileEdit = !!(fullEditStatus?.paid || isAnnualPro);

  const cancelAtDate = providerSub?.cancel_at
    ? new Date(providerSub.cancel_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : null;

  const renewsDate = providerSub?.current_period_end
    ? new Date(providerSub.current_period_end).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : null;

  const cancelConfirmMsg = cancelAtDate
    ? 'Are you sure? You will keep Annual Professional access until ' + cancelAtDate + '.'
    : 'Are you sure? You will keep Annual Professional access until the end of your current billing period.';

  return (
    <div className="min-h-screen bg-slate-50">

      {showCancelConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-slate-800 mb-2">Cancel Annual Subscription?</h3>
            <p className="text-sm text-slate-600 mb-5">{cancelConfirmMsg}</p>
            <div className="flex gap-3">
              <button onClick={function() { setShowCancelConfirm(false); }}
                className="flex-1 px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors">
                Keep Subscription
              </button>
              <button onClick={handleCancelSubscription} disabled={cancelLoading}
                className="flex-1 px-4 py-2 bg-rose-600 text-white rounded-lg text-sm font-semibold hover:bg-rose-700 transition-colors disabled:opacity-60">
                {cancelLoading ? 'Cancelling...' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ background: 'linear-gradient(135deg, #0F2B54 0%, #1a3a6b 100%)' }} className="px-8 py-8">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center text-white text-2xl font-bold flex-shrink-0">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">{displayName}</h1>
              <p className="text-blue-200 text-sm mt-0.5">{user?.email}</p>
              <div className="flex flex-wrap items-center gap-2 mt-1.5">
                {isAnnualPro ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-200">
                    <Crown className="h-3 w-3" /> Annual Professional
                  </span>
                ) : fullEditStatus?.paid ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/20 text-blue-200">
                    <Star className="h-3 w-3" /> Profile Edit Unlocked
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-white/10 text-white/70">
                    <User className="h-3 w-3" /> Free Account
                  </span>
                )}
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

      <div className="max-w-3xl mx-auto px-8 py-8 space-y-6">
        {!provider ? (
          <Card>
            <CardContent className="py-8 text-center">
              <div className="max-w-sm mx-auto">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Building2 className="w-8 h-8 text-blue-600" />
                </div>
                {isInviteFlow ? (
                  <>
                    <h3 className="text-lg font-semibold mb-2">Linking Your Firm&hellip;</h3>
                    <p className="text-muted-foreground text-sm mb-6">
                      Your engineering firm is being linked to your account. This may take a moment.
                    </p>
                    <Button onClick={function() { window.location.reload(); }} variant="default">Refresh Page</Button>
                  </>
                ) : linkFailed ? (
                  <>
                    <h3 className="text-lg font-semibold mb-2">Firm Linking Failed</h3>
                    <p className="text-muted-foreground text-sm mb-6">
                      We couldn&apos;t link your firm automatically. You can search for your firm to claim it, or try refreshing.
                    </p>
                    <div className="flex flex-col gap-3">
                      <Button onClick={function() { router.push('/provider/claim'); }} variant="default">Search &amp; Claim Your Firm</Button>
                      <Button onClick={function() { window.location.reload(); }} variant="outline">Refresh Page</Button>
                    </div>
                  </>
                ) : (user?.roles || []).includes('provider') ? (
                  <>
                    <h3 className="text-lg font-semibold mb-2">No Firm Linked Yet</h3>
                    <p className="text-muted-foreground text-sm mb-6">
                      Your account is not yet linked to an engineering firm. Search for your firm to claim it, or add a new one.
                    </p>
                    <div className="flex flex-col gap-3">
                      <Button onClick={function() { router.push('/provider/claim'); }} variant="default">Search &amp; Claim Your Firm</Button>
                      <Button onClick={function() { router.push('/provider/add-firm'); }} variant="outline">Add New Firm</Button>
                    </div>
                  </>
                ) : (
                  <>
                    <h3 className="text-lg font-semibold mb-2">No Firm Linked Yet</h3>
                    <p className="text-muted-foreground text-sm mb-6">
                      Your account is not yet linked to an engineering firm. Search for your firm to claim it, or add a new one.
                    </p>
                    <div className="flex flex-col gap-3">
                      <Button onClick={function() { router.push('/provider/claim'); }} variant="default">Search &amp; Claim Your Firm</Button>
                      <Button onClick={function() { router.push('/provider/add-firm'); }} variant="outline">Add New Firm</Button>
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <>

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
                    <p className="text-slate-800 font-medium">{user?.email}</p>
                    {emailVerified
                      ? <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                      : <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
                    }
                  </div>
                </div>
                {createdAt && (
                  <div>
                    <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Account Created</label>
                    <div className="mt-1 flex items-center gap-1.5 text-slate-800 font-medium">
                      <Calendar className="h-4 w-4 text-slate-400" />
                      {createdAt.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
                    </div>
                  </div>
                )}
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
                    {(user?.roles || []).map(function(role) {
                      return <span key={role} className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs rounded-full capitalize">{role}</span>;
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Subscription and Tier */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
                <Crown className="h-5 w-5 text-[#0F2B54]" />
                <h2 className="font-semibold text-slate-800">Subscription and Tier</h2>
              </div>
              <div className="px-6 py-5 space-y-4">
                {isAnnualPro ? (
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <Crown className="h-5 w-5 text-emerald-500" />
                          <span className="font-semibold text-slate-800 text-lg">Annual Professional</span>
                        </div>
                        <p className="text-slate-500 text-sm mt-0.5">$1,000/year &mdash; all RFQs + unlimited profile edits</p>
                        {cancelAtDate ? (
                          <p className="text-amber-600 text-xs mt-1 font-medium">Cancels on {cancelAtDate} &mdash; access continues until then</p>
                        ) : renewsDate ? (
                          <p className="text-slate-400 text-xs mt-1">Renews {renewsDate}</p>
                        ) : null}
                      </div>
                      <div className="flex flex-col items-end gap-2 flex-shrink-0">
                        {cancelAtDate && (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700">
                            Cancels {cancelAtDate}
                          </span>
                        )}
                        <div className="flex gap-2">
                          {cancelAtDate ? (
                            <button onClick={handleReactivateSubscription} disabled={reactivateLoading}
                              className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60">
                              {reactivateLoading ? 'Reactivating...' : 'Reactivate'}
                            </button>
                          ) : (
                            <button onClick={function() { setShowCancelConfirm(true); }} disabled={cancelLoading}
                              className="px-3 py-1.5 border border-rose-300 text-rose-600 rounded-lg text-xs font-semibold hover:bg-rose-50 transition-colors disabled:opacity-60">
                              {cancelLoading ? 'Cancelling...' : 'Cancel Subscription'}
                            </button>
                          )}
                          <Link href="/provider/upgrade" className="px-3 py-1.5 border border-slate-300 text-slate-700 rounded-lg text-xs font-medium hover:bg-slate-50 transition-colors">Manage</Link>
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="p-3 bg-emerald-50 rounded-lg text-center">
                        <CheckCircle className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
                        <p className="text-xs font-medium text-emerald-800">All RFQs Included</p>
                        <p className="text-xs text-emerald-600">No unlock fees</p>
                      </div>
                      <div className="p-3 bg-emerald-50 rounded-lg text-center">
                        <CheckCircle className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
                        <p className="text-xs font-medium text-emerald-800">Unlimited Profile Edits</p>
                        <p className="text-xs text-emerald-600">All fields</p>
                      </div>
                      <div className="p-3 bg-emerald-50 rounded-lg text-center">
                        <CheckCircle className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
                        <p className="text-xs font-medium text-emerald-800">Request Rank Up</p>
                        <p className="text-xs text-emerald-600">Increase tier</p>
                      </div>
                    </div>
                  </div>
                ) : fullEditStatus?.paid ? (
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <Star className="h-5 w-5 text-blue-500" />
                          <span className="font-semibold text-slate-800 text-lg">Profile Edit Unlocked</span>
                        </div>
                        <p className="text-slate-500 text-sm mt-0.5">$500 one-time &mdash; unlimited profile edits forever</p>
                      </div>
                      <Link href="/provider/upgrade" className="px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-semibold hover:bg-[#1a3a6b] transition-colors">Upgrade to Annual</Link>
                    </div>
                    <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg">
                      <p className="text-sm font-medium text-blue-800">Upgrade to Annual Pro for $1,000/year</p>
                      <p className="text-xs text-blue-600 mt-0.5">Get automatic RFQ delivery with no $50 unlock fees. Pays for itself with just 20 RFQs.</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <User className="h-5 w-5 text-slate-400" />
                          <span className="font-semibold text-slate-800 text-lg">Free Account</span>
                        </div>
                        <p className="text-slate-500 text-sm mt-0.5">Pay $50 per RFQ unlock &mdash; no profile edits included</p>
                      </div>
                      <Link href="/provider/upgrade" className="px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-semibold hover:bg-[#1a3a6b] transition-colors flex items-center gap-1.5">
                        <Zap className="h-4 w-4" /> View Plans
                      </Link>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="p-4 border-2 border-[#0F2B54] rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <Crown className="h-5 w-5 text-[#0F2B54]" />
                          <span className="font-bold text-slate-800">Annual Professional</span>
                          <span className="ml-auto text-xs bg-[#0F2B54] text-white px-2 py-0.5 rounded-full">Best Value</span>
                        </div>
                        <p className="text-2xl font-bold text-[#0F2B54]">$1,000<span className="text-sm font-normal text-slate-500">/year</span></p>
                        <ul className="mt-2 space-y-1 text-xs text-slate-600">
                          <li className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> All RFQs auto-delivered</li>
                          <li className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> Unlimited profile edits</li>
                          <li className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> Request Rank Up</li>
                          <li className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> Pays off at just 20 RFQs</li>
                        </ul>
                        <Link href="/provider/upgrade" className="mt-3 block w-full text-center px-4 py-2 bg-[#0F2B54] text-white rounded-lg text-sm font-semibold hover:bg-[#1a3a6b] transition-colors">
                          Get Annual Pro
                        </Link>
                      </div>
                      <div className="p-4 border border-slate-200 rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <Star className="h-5 w-5 text-slate-400" />
                          <span className="font-bold text-slate-800">Profile Edit Only</span>
                        </div>
                        <p className="text-2xl font-bold text-slate-700">$500<span className="text-sm font-normal text-slate-500"> once</span></p>
                        <ul className="mt-2 space-y-1 text-xs text-slate-600">
                          <li className="flex items-center gap-1"><CheckCircle className="h-3 w-3 text-emerald-500" /> Unlimited profile edits</li>
                          <li className="flex items-center gap-1"><span className="h-3 w-3 flex-shrink-0">&#8212;</span> RFQs still $50/unlock</li>
                          <li className="flex items-center gap-1"><span className="h-3 w-3 flex-shrink-0">&#8212;</span> No rank-up requests</li>
                        </ul>
                        <button onClick={handleProfileEditCheckout}
                          className="mt-3 w-full px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors">
                          Unlock for $500
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Company Profile Form */}
            <form onSubmit={handleSubmit}>
              <div className="relative">

                {!hasProfileEdit && (
                  <div className="absolute inset-0 z-10 flex flex-col items-center justify-start pt-16 rounded-xl"
                    style={{ background: 'rgba(255,255,255,0.82)', backdropFilter: 'blur(3px)' }}>
                    <div className="bg-white border border-slate-200 shadow-xl rounded-2xl px-8 py-8 max-w-sm w-full mx-4 text-center">
                      <div className="w-14 h-14 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <Lock className="h-7 w-7 text-amber-600" />
                      </div>
                      <h3 className="text-lg font-bold text-slate-800 mb-2">Unlock Profile Editing</h3>
                      <p className="text-sm text-slate-500 mb-6">
                        Upgrade your account to edit your company profile, update capabilities, and improve your ranking with buyers.
                      </p>
                      <Link href="/provider/upgrade"
                        className="block w-full px-6 py-3 bg-[#0F2B54] text-white rounded-xl text-sm font-semibold hover:bg-[#1a3a6b] transition-colors">
                        View Upgrade Options
                      </Link>
                    </div>
                  </div>
                )}

                <div className="space-y-6">

                  <Card>
                    <CardHeader>
                      <CardTitle>Basic Information</CardTitle>
                      <CardDescription>Your company details</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="name">Company Name</Label>
                        <Input id="name" value={formData.name} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, name: e.target.value }; }); }} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="website">Website</Label>
                        <Input id="website" value={formData.website} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, website: e.target.value }; }); }} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="phone">Phone</Label>
                        <Input id="phone" value={formData.phone} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, phone: e.target.value }; }); }} />
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader><CardTitle>Location</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="address">Address</Label>
                        <Input id="address" value={formData.address} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, address: e.target.value }; }); }} />
                      </div>
                      <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                          <Label htmlFor="city">City</Label>
                          <Input id="city" value={formData.city} disabled={!hasProfileEdit}
                            onChange={function(e) { setFormData(function(prev) { return { ...prev, city: e.target.value }; }); }} />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="state">State</Label>
                          <Input id="state" value={formData.state} disabled={!hasProfileEdit}
                            onChange={function(e) { setFormData(function(prev) { return { ...prev, state: e.target.value }; }); }} />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="postal_code">Postal Code</Label>
                          <Input id="postal_code" value={formData.postal_code} disabled={!hasProfileEdit}
                            onChange={function(e) { setFormData(function(prev) { return { ...prev, postal_code: e.target.value }; }); }} />
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Business Description</CardTitle>
                      <CardDescription>Describe your engineering capabilities and specialties</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="primary_specialty">Primary Specialty</Label>
                        <Input id="primary_specialty" value={formData.primary_specialty} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, primary_specialty: e.target.value }; }); }} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="business_description">Business Description</Label>
                        <Textarea id="business_description" rows={5} value={formData.business_description} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, business_description: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Heavily weighs on the matching process, as evaluated by AI.</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="notable_projects" className="font-semibold">Notable Projects</Label>
                        <Textarea id="notable_projects" rows={4}
                          placeholder="e.g. Fatigue analysis for Boeing 737 landing gear, CFD simulation for SpaceX Starship heat shield, FEA for NASA composite pressure vessel"
                          value={formData.notable_projects} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, notable_projects: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of notable projects, each summarized in one sentence — this field has the greatest impact on RFQ match determination.</p>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Capabilities &amp; Specialties</CardTitle>
                      <CardDescription>Enter values separated by commas</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="capabilities">Capabilities</Label>
                        <Textarea id="capabilities" rows={3}
                          placeholder="e.g. FEA, CFD, Fatigue Analysis, Structural Design"
                          value={formData.capabilities} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, capabilities: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of technical capabilities</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="specialties">Specialties</Label>
                        <Textarea id="specialties" rows={3}
                          placeholder="e.g. Aerospace, Automotive, Medical Devices"
                          value={formData.specialties} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, specialties: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of industry specialties</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="secondary_specialties">Secondary Specialties</Label>
                        <Textarea id="secondary_specialties" rows={2}
                          placeholder="e.g. Thermal Analysis, Vibration Testing"
                          value={formData.secondary_specialties} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, secondary_specialties: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of secondary specialties</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="software_tools">Software Tools</Label>
                        <Textarea id="software_tools" rows={3}
                          placeholder="e.g. ANSYS, SolidWorks, MATLAB, Abaqus"
                          value={formData.software_tools} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, software_tools: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of engineering software tools</p>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Additional Information</CardTitle>
                      <CardDescription>Enter values separated by commas for list fields</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="notable_clients">Notable Clients</Label>
                        <Textarea id="notable_clients" rows={2}
                          placeholder="e.g. Boeing, Lockheed Martin, SpaceX"
                          value={formData.notable_clients} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, notable_clients: e.target.value }; }); }} />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email_addresses">Contact Email Addresses</Label>
                        <Textarea id="email_addresses" rows={2}
                          placeholder="e.g. info@example.com, sales@example.com"
                          value={formData.email_addresses} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, email_addresses: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Enter one email only for the firm.</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="certifications">Certifications</Label>
                        <Textarea id="certifications" rows={2}
                          placeholder="e.g. ISO 9001, AS9100, NADCAP"
                          value={formData.certifications} disabled={!hasProfileEdit}
                          onChange={function(e) { setFormData(function(prev) { return { ...prev, certifications: e.target.value }; }); }} />
                        <p className="text-xs text-slate-400">Comma-separated list of certifications and accreditations</p>
                      </div>
                    </CardContent>
                  </Card>

                  {hasProfileEdit && (
                    <Button type="submit" className="w-full" disabled={isSaving}>
                      {isSaving ? 'Saving...' : 'Save Changes'}
                    </Button>
                  )}

                  {!hasProfileEdit && (
                    <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center">
                      <p className="text-sm text-slate-500">
                        <Link href="/provider/upgrade" className="text-[#0F2B54] font-semibold hover:underline">Upgrade your plan</Link> to save profile changes.
                      </p>
                    </div>
                  )}

                </div>
              </div>
            </form>

          </>
        )}
      </div>
    </div>
  );
}
