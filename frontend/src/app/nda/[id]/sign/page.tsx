'use client';

import { useEffect, useState, useCallback, useRef, Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Loader2, CheckCircle, AlertCircle, RefreshCw, FileText, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

type PageState = 'loading' | 'payment_required' | 'initiating' | 'signing' | 'fully_signed' | 'cancelled' | 'error';

function CustomerNdaSignContent() {
  const { isLoading: authLoading } = useRequireAuth();
  const params = useParams();
  const searchParams = useSearchParams();
  const rfqId = params.id as string;

  const [pageState, setPageState] = useState<PageState>('loading');
  const [signingUrl, setSigningUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Feature 2 & 3: polling state
  const [isPolling, setIsPolling] = useState(false);
  const [pollingMessage, setPollingMessage] = useState('');
  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const pollingStartRef = useRef<number | null>(null);

  const isPaidReturn = searchParams.get('paid') === 'true';
  const isCancelledReturn = searchParams.get('cancelled') === 'true';

  // Feature 2: polling helper
  const startStatusPolling = useCallback(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    pollingRef.current = setInterval(async () => {
      // Stop after 2 minutes
      if (pollingStartRef.current && Date.now() - pollingStartRef.current > 120000) {
        clearInterval(pollingRef.current!);
        setIsPolling(false);
        setPollingMessage('Signature pending. Click Refresh to check again.');
        return;
      }

      try {
        const res = await api.rfqs.ndaStatus(rfqId);
        const data = res.data as { nda_status?: string; fully_signed_at?: string };
        if (data.nda_status === 'fully_signed' || data.fully_signed_at) {
          clearInterval(pollingRef.current!);
          setIsPolling(false);
          setPageState('fully_signed');
        }
      } catch (e) {
        // keep polling
      }
    }, 3000);
  }, [rfqId]);

  // Feature 1 & 2: handle iframe completion or manual refresh
  const handleSigningComplete = useCallback(async () => {
    if (isPolling) return; // prevent double-trigger
    setIsPolling(true);
    setPollingMessage('Confirming your signature...');

    // Step 1: Call confirm-signed (primary path, not relying on webhook alone)
    try {
      const confirmRes = await api.rfqs.ndaConfirmSigned(rfqId);
      const confirmData = confirmRes.data as { confirmed?: boolean };
      if (confirmData.confirmed) {
        setPageState('fully_signed');
        setIsPolling(false);
        return;
      }
    } catch (e) {
      // continue to polling fallback
    }

    // Step 2: Fall back to polling ndaStatus
    setPollingMessage('Checking signature status...');
    pollingStartRef.current = Date.now();
    startStatusPolling();
  }, [rfqId, isPolling, startStatusPolling]);

  // Cleanup: clear polling interval on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // Feature 1: listen for Signwell iframe postMessage completion events
  useEffect(() => {
    if (pageState !== 'signing') return;

    const handleIframeMessage = (event: MessageEvent) => {
      const data = event.data;
      if (!data) return;
      // Signwell completion signals
      const isCompletion =
        data.type === 'signwell:document_signed' ||
        data.type === 'signwell:completed' ||
        data.action === 'signed' ||
        data.action === 'completed' ||
        (typeof data === 'string' &&
          (data.includes('signed') || data.includes('completed')));
      if (isCompletion) {
        handleSigningComplete();
      }
    };

    window.addEventListener('message', handleIframeMessage);
    return () => window.removeEventListener('message', handleIframeMessage);
  }, [pageState, handleSigningComplete]);

  const handlePaidReturn = useCallback(async () => {
    setPageState('initiating');
    try {
      const initiateRes = await api.rfqs.ndaInitiate(rfqId);
      const initData = initiateRes.data as { signing_url?: string };
      if (initData.signing_url) {
        setSigningUrl(initData.signing_url);
        setPageState('signing');
        return;
      }
      const urlRes = await api.rfqs.ndaSigningUrl(rfqId);
      const urlData = urlRes.data as { signing_url?: string };
      if (urlData.signing_url) {
        setSigningUrl(urlData.signing_url);
        setPageState('signing');
      } else {
        setErrorMsg('NDA signing initiated but signing link not ready yet. Please refresh in a moment.');
        setPageState('error');
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setErrorMsg(e?.response?.data?.detail || 'Failed to initiate NDA signing. Your payment was received — please contact support.');
      setPageState('error');
    }
  }, [rfqId]);

  const checkNdaStatus = useCallback(async () => {
    setPageState('loading');
    try {
      const res = await api.rfqs.ndaStatus(rfqId);
      const data = res.data as { nda_status?: string; signing_url?: string; fully_signed_at?: string };
      if (data.nda_status === 'fully_signed' || data.fully_signed_at) {
        setPageState('fully_signed');
      } else if (data.signing_url) {
        setSigningUrl(data.signing_url);
        setPageState('signing');
      } else {
        setPageState('payment_required');
      }
    } catch {
      setPageState('payment_required');
    }
  }, [rfqId]);

  useEffect(() => {
    if (authLoading) return;
    if (isCancelledReturn) {
      setPageState('cancelled');
      return;
    }
    if (isPaidReturn) {
      handlePaidReturn();
      return;
    }
    checkNdaStatus();
  }, [authLoading, isPaidReturn, isCancelledReturn, handlePaidReturn, checkNdaStatus]);

  const initiatePayment = async () => {
    setErrorMsg('');
    try {
      const res = await api.rfqs.ndaCheckout(rfqId);
      const data = res.data as { checkout_url?: string };
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        setErrorMsg('No checkout URL returned. Please try again.');
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setErrorMsg(e?.response?.data?.detail || 'Failed to initiate payment. Please try again.');
    }
  };

  if (authLoading || pageState === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (pageState === 'initiating') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600 font-medium">Payment confirmed! Setting up your NDA...</p>
          <p className="text-sm text-gray-500 mt-2">This may take a few seconds.</p>
        </div>
      </div>
    );
  }

  if (pageState === 'fully_signed') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
            <CardTitle>NDA Fully Signed</CardTitle>
            <CardDescription>
              The NDA for this RFQ has been fully executed. Your project details are now protected
              and your RFQ will be dispatched to matched engineering providers.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center space-y-3">
            <p className="text-sm text-gray-600">
              You will receive notifications as quotes come in.
            </p>
            <Link href={`/customer/rfq/${rfqId}/tracking`}>
              <Button className="w-full">View RFQ Tracking</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (pageState === 'cancelled') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <XCircle className="h-12 w-12 text-yellow-500 mx-auto mb-2" />
            <CardTitle>Payment Cancelled</CardTitle>
            <CardDescription>
              Your NDA payment was cancelled. Your RFQ has been saved but cannot be dispatched
              until the NDA is signed.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center space-y-3">
            <Button onClick={initiatePayment} className="w-full">
              Try Payment Again ($5 NDA Fee)
            </Button>
            <Link href="/customer/dashboard">
              <Button variant="outline" className="w-full">Back to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (pageState === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
            <CardTitle>Error</CardTitle>
            <CardDescription>{errorMsg}</CardDescription>
          </CardHeader>
          <CardContent className="text-center space-y-3">
            <Button onClick={checkNdaStatus} variant="outline" className="w-full">
              <RefreshCw className="mr-2 h-4 w-4" /> Retry
            </Button>
            <Link href="/customer/dashboard">
              <Button variant="outline" className="w-full">Back to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (pageState === 'signing' && signingUrl) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <div className="max-w-4xl mx-auto w-full px-6 py-8">
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="h-5 w-5 text-blue-600" />
              <h1 className="text-2xl font-bold">Sign Your NDA</h1>
            </div>
            <p className="text-gray-600">
              Please sign the Non-Disclosure Agreement below. Once signed, your RFQ will be
              dispatched to matched engineering providers.
            </p>
          </div>
          <Card className="mb-4">
            <CardContent className="p-0">
              <iframe
                src={signingUrl}
                className="w-full h-[600px] rounded-lg border-0"
                title="NDA Signing"
              />
            </CardContent>
          </Card>
          {/* Feature 3: status bar below iframe */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isPolling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                  <span className="text-sm text-blue-600">{pollingMessage}</span>
                </>
              ) : (
                <span className="text-sm text-gray-500">
                  After signing, your RFQ will be dispatched automatically.
                </span>
              )}
            </div>
            <Button
              onClick={() => { handleSigningComplete(); }}
              variant="outline"
              size="sm"
              disabled={isPolling}
            >
              {isPolling ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Checking...</>
              ) : (
                <><RefreshCw className="mr-2 h-4 w-4" />I have signed - Check Status</>
              )}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // payment_required state (default fallback)
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <FileText className="h-12 w-12 text-blue-600 mx-auto mb-2" />
          <CardTitle>NDA Required</CardTitle>
          <CardDescription>
            This RFQ requires a Non-Disclosure Agreement. A one-time $5 document handling fee
            is required to initiate the NDA signing process.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center space-y-3">
          {errorMsg && (
            <p className="text-sm text-red-600 bg-red-50 rounded p-2">{errorMsg}</p>
          )}
          <Button onClick={initiatePayment} className="w-full">
            Pay $5 &amp; Sign NDA
          </Button>
          <Link href="/customer/dashboard">
            <Button variant="outline" className="w-full">Back to Dashboard</Button>
          </Link>
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
