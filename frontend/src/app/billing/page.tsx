'use client';

import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, ExternalLink, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import PaymentTrust from '@/components/PaymentTrust';
import { useRequireAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';

export default function BillingPage() {
  const { isLoading: authLoading } = useRequireAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'redirect' | 'choose'>('redirect');
  const [checkingOut, setCheckingOut] = useState<'month' | 'year' | null>(null);
  const [agreed, setAgreed] = useState(false);

  // Step 1: existing subscriber -> open portal; otherwise show the plan chooser.
  const run = async () => {
    setError('');
    setLoading(true);
    try {
      const portalRes = await apiClient.get('/billing/portal');
      const portalData = portalRes.data;
      if (portalData?.url) {
        window.location.href = portalData.url;
        return;
      }
      if (portalData?.no_subscription) {
        setMode('choose');
        setLoading(false);
        return;
      }
      throw new Error('Unexpected response from billing service');
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to open billing portal');
      setLoading(false);
    }
  };

  // Step 2: start a Stripe checkout for the chosen billing interval.
  const startCheckout = async (billing_interval: 'month' | 'year') => {
    if (checkingOut) return;
    setCheckingOut(billing_interval);
    setError('');
    try {
      const origin = window.location.origin;
      const checkoutRes = await apiClient.post('/stripe/create-search-subscription', {
        subscription_type: 'search_tier1',
        billing_interval,
        origin,
      });
      const checkoutData = checkoutRes.data;
      const checkoutUrl = checkoutData?.checkout_url || checkoutData?.url;
      if (checkoutUrl) {
        window.location.href = checkoutUrl;
        return;
      }
      throw new Error('No checkout URL returned from Stripe');
    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to start checkout');
      setCheckingOut(null);
    }
  };

  useEffect(() => {
    if (authLoading) return;
    run();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-50">
        <Loader2 className="h-10 w-10 animate-spin text-blue-600" />
        <p className="text-gray-600 text-sm">Loading billing...</p>
      </div>
    );
  }

  if (mode === 'choose') {
    const features = [
      '100 searches per month (vs. 10 on the free plan)',
      '5 free NDA-required RFQs each month (then $10 each)',
      'Priority RFQ matching and full platform access',
      'AI Help Assistant access',
    ];
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <div className="w-full max-w-3xl">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-bold text-slate-800">Choose your Search Plan</h1>
            <p className="text-slate-500 text-sm mt-1">Same features either way — save $100 with annual billing.</p>
          </div>
          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4" /> {error}
            </div>
          )}
          <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            <p className="mb-2"><strong>Refund policy:</strong> Annual plans are refundable within <strong>14 days</strong> of payment; after that there is no refund and your plan continues until the end of the paid year. Monthly plans are refundable within <strong>5 days</strong> of payment; after that there is no refund and your plan continues until the end of the paid month. One-time fees (RFQ unlocks, NDA fees, profile-edit unlock) are non-refundable. You can cancel anytime to stop renewal.</p>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5" />
              <span>I have read and agree to the <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">Terms of Service</a> and the refund policy above.</span>
            </label>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Monthly</CardTitle>
                <CardDescription><span className="text-2xl font-bold text-slate-800">$50</span> / month</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-1.5 text-sm text-slate-600">
                  {features.map((f) => (
                    <li key={f} className="flex gap-2"><Check className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />{f}</li>
                  ))}
                </ul>
                <Button className="w-full" disabled={!!checkingOut || !agreed} onClick={() => startCheckout('month')}>
                  {checkingOut === 'month' ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Redirecting...</> : 'Subscribe monthly — $50/mo'}
                </Button>
              </CardContent>
            </Card>
            <Card className="border-emerald-300 ring-1 ring-emerald-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">Annual <span className="text-xs font-semibold bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">Save $100</span></CardTitle>
                <CardDescription><span className="text-2xl font-bold text-slate-800">$500</span> / year <span className="text-slate-500">(~$41.67/mo)</span></CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ul className="space-y-1.5 text-sm text-slate-600">
                  {features.map((f) => (
                    <li key={f} className="flex gap-2"><Check className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />{f}</li>
                  ))}
                </ul>
                <Button className="w-full" disabled={!!checkingOut || !agreed} onClick={() => startCheckout('year')}>
                  {checkingOut === 'year' ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Redirecting...</> : 'Subscribe annually — $500/yr'}
                </Button>
              </CardContent>
            </Card>
          </div>
          <PaymentTrust refund="subscription" className="mt-5" />
          <div className="text-center mt-6">
            <Button variant="outline" onClick={() => window.history.back()}>Go Back</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
          <CardTitle>Billing Portal Unavailable</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button onClick={run} className="w-full">
            <ExternalLink className="mr-2 h-4 w-4" />Try Again
          </Button>
          <Button variant="outline" onClick={() => window.history.back()} className="w-full">
            Go Back
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
