'use client';

import { useEffect, useState, useRef, Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Loader2, CheckCircle, FileText, CreditCard, Shield } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useRequireAuth } from '@/hooks/useAuth';
import { api, apiClient } from '@/lib/api';
import { toast } from 'sonner';

function CustomerNdaSignContent() {
  const { isLoading: authLoading } = useRequireAuth();
  const params = useParams();
  const searchParams = useSearchParams();
  const rfqId = params.id as string;

  const [status, setStatus] = useState('loading');
  const [subStatus, setSubStatus] = useState<{ has_active: boolean; nda_credits_remaining: number } | null>(null);
  const [freeCreditApplied, setFreeCreditApplied] = useState(false);
  const [isPaying, setIsPaying] = useState(false);
  const submitCalledRef = useRef(false);
  const isPaidReturn = searchParams.get('paid') === 'true';
  const isCancelled = searchParams.get('cancelled') === 'true';

  // Step 1: Load NDA status
  useEffect(() => {
    if (authLoading) return;
    api.rfqs.ndaStatus(rfqId)
      .then((res) => {
        const data = res.data as { nda_status?: string; fully_signed_at?: string; nda_required?: boolean };
        if (!data.nda_required) {
          setStatus('not_required');
        } else if (data.nda_status === 'fully_signed' || data.fully_signed_at) {
          setStatus('fully_signed');
        } else {
          setStatus('nda_pending');
        }
      })
      .catch(() => setStatus('nda_pending'));
  }, [authLoading, rfqId]);

  // Step 2: Load subscription status to know if user has free NDA credits
  useEffect(() => {
    if (authLoading) return;
    apiClient.get('/billing/subscription-status')
      .then((res) => {
        const d = res.data as { has_active: boolean; nda_credits_remaining?: number };
        setSubStatus({ has_active: d.has_active, nda_credits_remaining: d.nda_credits_remaining ?? 0 });
      })
      .catch(() => setSubStatus({ has_active: false, nda_credits_remaining: 0 }));
  }, [authLoading]);

  // Step 3: After Stripe payment redirect (?paid=true), submit RFQ
  useEffect(() => {
    if (!isPaidReturn || authLoading || submitCalledRef.current) return;
    submitCalledRef.current = true;
    api.rfqs.submit(rfqId).catch(() => {});
  }, [isPaidReturn, authLoading, rfqId]);

  // Button handler - subscribed user gets free credit, others go to Stripe
  const handlePayNda = async () => {
    setIsPaying(true);
    try {
      const res = await api.rfqs.ndaCheckout(rfqId);
      const data = res.data as { free_credit?: boolean; checkout_url?: string; credits_remaining?: number };
      if (data.free_credit) {
        setFreeCreditApplied(true);
        api.rfqs.submit(rfqId).catch(() => {});
        setIsPaying(false);
        return;
      }
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast.error('Could not initiate payment. Please try again.');
        setIsPaying(false);
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const detail = axiosErr?.response?.data?.detail || 'Request failed. Please try again.';
      toast.error(detail);
      setIsPaying(false);
    }
  };

  // --- Loading state ---
  if (authLoading || status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  // --- Not required ---
  if (status === 'not_required') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              No NDA Required
            </CardTitle>
            <CardDescription>This RFQ does not require an NDA. Your request is being processed.</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/customer/dashboard">
              <Button className="w-full">Go to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- Already fully signed ---
  if (status === 'fully_signed') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              NDA Already Signed
            </CardTitle>
            <CardDescription>Your NDA has been fully executed. Providers can now access your RFQ.</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/customer/dashboard">
              <Button className="w-full">Go to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- Stripe paid return ---
  if (isPaidReturn) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              Payment Confirmed
            </CardTitle>
            <CardDescription>
              Your NDA fee has been received. Your RFQ is now active and providers are being matched.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/customer/dashboard">
              <Button className="w-full">Go to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- Free credit successfully applied ---
  if (freeCreditApplied) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              NDA Credit Applied
            </CardTitle>
            <CardDescription>
              No payment needed. Your subscription covers this NDA.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-800">
              Your RFQ has been submitted and providers are being matched. You will receive an email to sign the NDA after you select a provider from your quotes.
            </div>
            <Link href="/customer/dashboard">
              <Button className="w-full">Go to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // --- NDA pending: show appropriate action based on subscription ---
  const isSubscribed = subStatus !== null && subStatus.has_active && subStatus.nda_credits_remaining > 0;
  const creditsRemaining = subStatus?.nda_credits_remaining ?? 0;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
      <Card className="max-w-lg w-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-600" />
            NDA Required for This RFQ
          </CardTitle>
          <CardDescription>
            You requested an NDA for this project. Review the options below.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isSubscribed ? (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4 space-y-3">
              <div className="flex items-center gap-2 text-green-800 font-semibold">
                <Shield className="h-5 w-5" />
                Subscription Benefit — Free NDA
              </div>
              <p className="text-sm text-green-700">
                Your subscription includes 3 free NDAs per month (a $30 value).
                You have <strong>{creditsRemaining} credit{creditsRemaining !== 1 ? 's' : ''} remaining</strong> this month.
              </p>
              <p className="text-sm text-green-700">
                No payment required. You will receive an email to sign the NDA after you select a provider from your quotes.
              </p>
              <Button
                className="w-full bg-green-600 hover:bg-green-700"
                onClick={handlePayNda}
                disabled={isPaying}
              >
                {isPaying
                  ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Applying Credit...</span>
                  : 'Confirm — Use Free NDA Credit'}
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {isCancelled && (
                <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
                  Payment was cancelled. Click below to try again.
                </div>
              )}
              <div className="bg-gray-50 border rounded-lg p-4 space-y-2 text-sm text-gray-700">
                <div className="flex items-center gap-2 font-semibold text-gray-900">
                  <CreditCard className="h-4 w-4" />
                  NDA Document Handling Fee
                </div>
                <p>A one-time <strong>$10 fee</strong> covers NDA preparation, signing, and secure storage.</p>
                <p className="text-xs text-gray-500">
                  Tip: Subscribers get 3 free NDAs/month ($30 value).{' '}
                  <Link href="/billing" className="text-blue-600 underline">Upgrade your plan.</Link>
                </p>
              </div>
              <Button
                className="w-full"
                onClick={handlePayNda}
                disabled={isPaying}
              >
                {isPaying
                  ? <span className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Processing...</span>
                  : 'Pay $10 NDA Fee'}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function CustomerNdaSignPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    }>
      <CustomerNdaSignContent />
    </Suspense>
  );
}
