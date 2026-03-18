'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { Loader2, CheckCircle, AlertCircle, RefreshCw, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface NdaInfo {
  nda_status: string;
  signing_url?: string;
  fully_signed_at?: string;
}

export default function CustomerNdaSignPage() {
  const { isLoading: authLoading } = useRequireAuth();
  const params = useParams();
  const rfqId = params.id as string;

  const [nda, setNda] = useState<NdaInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      // Get RFQ to check NDA status
      const res = await api.rfqs.getStatus(rfqId);
      const data = res.data as unknown as NdaInfo;
      setNda(data);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Failed to load NDA status.');
    } finally {
      setLoading(false);
    }
  }, [rfqId]);

  const initiateSigningFlow = async () => {
    setError('');
    try {
      const res = await api.rfqs.ndaCheckout(rfqId);
      const data = res.data as unknown as { checkout_url?: string; signing_url?: string };
      const url = data.signing_url || data.checkout_url;
      if (url) {
        window.location.href = url;
      } else {
        setError('No signing URL returned. Please contact support.');
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Failed to initiate NDA signing.');
    }
  };

  useEffect(() => {
    if (!authLoading) fetchStatus();
  }, [authLoading, fetchStatus]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
            <CardTitle>Error Loading NDA</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Button onClick={fetchStatus} variant="outline">
              <RefreshCw className="mr-2 h-4 w-4" />Try Again
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (nda?.nda_status === 'fully_signed' || nda?.fully_signed_at) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
            <CardTitle>NDA Already Signed</CardTitle>
            <CardDescription>
              The NDA for this RFQ has been fully executed. Your RFQ will be dispatched to providers shortly.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-sm text-gray-600">
              Your RFQ will be dispatched to matched engineering firms. You will receive notifications as quotes come in.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="max-w-4xl mx-auto w-full px-6 py-8">
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-5 w-5 text-blue-600" />
            <h1 className="text-2xl font-bold">Sign NDA</h1>
          </div>
          <p className="text-gray-600">
            You are signing a Non-Disclosure Agreement for your RFQ request. This protects your project details.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 mb-4 bg-red-50 border border-red-200 rounded-md">
            <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {nda?.signing_url ? (
          <div className="space-y-4">
            <Card>
              <CardContent className="p-0">
                <iframe
                  src={nda.signing_url}
                  className="w-full h-[600px] rounded-lg border-0"
                  title="NDA Signing"
                />
              </CardContent>
            </Card>
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">After signing, click refresh to update status.</p>
              <Button onClick={fetchStatus} variant="outline" size="sm">
                <RefreshCw className="mr-2 h-4 w-4" />Refresh Status
              </Button>
            </div>
            {(nda?.nda_status === 'customer_signature_pending' || nda?.nda_status === 'fully_signed') && (
              <Card className="bg-green-50 border-green-200">
                <CardContent className="py-4">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-5 w-5 text-green-600" />
                    <p className="text-sm text-green-800 font-medium">
                      Your RFQ will be dispatched to providers shortly.
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>NDA Signature Required</CardTitle>
              <CardDescription>
                A $5 document handling fee is required to initiate the NDA process.
                Click below to proceed to payment and signing.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={initiateSigningFlow} className="w-full">
                Proceed to NDA Payment &amp; Signing
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
