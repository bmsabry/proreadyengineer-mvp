'use client';

import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api';

export default function BillingPage() {
  const { isLoading: authLoading } = useRequireAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const run = async () => {
    setError('');
    setLoading(true);
    try {
      // Step 1: Check if user has an existing subscription
      const portalRes = await apiClient.get('/billing/portal');
      const portalData = portalRes.data;

      // Step 2a: User HAS a subscription — open Stripe billing portal
      if (portalData?.url) {
        window.location.href = portalData.url;
        return;
      }

      // Step 2b: User has NO subscription — create a Stripe checkout session
      if (portalData?.no_subscription) {
        const origin = window.location.origin;
        const checkoutRes = await apiClient.post('/stripe/create-search-subscription', {
          subscription_type: 'search_tier1',
          origin,
        });
        const checkoutData = checkoutRes.data;
        const checkoutUrl = checkoutData?.checkout_url || checkoutData?.url;
        if (checkoutUrl) {
          window.location.href = checkoutUrl;
          return;
        }
        throw new Error('No checkout URL returned from Stripe');
      }

      throw new Error('Unexpected response from billing service');

    } catch (err: unknown) {
      const e = err as Error;
      setError(e.message || 'Failed to open billing portal');
      setLoading(false);
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
        <p className="text-gray-600 text-sm">Redirecting to billing...</p>
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
