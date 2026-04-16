'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { Loader2, CheckCircle, AlertCircle, RefreshCw, FileText, Mail } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface UnlockStatus {
  unlocked: boolean;
  nda_status?: string;
  signing_url?: string;
  provider_signed_at?: string;
  fully_signed_at?: string;
}

export default function ProviderNdaSignPage() {
  const { isLoading: authLoading } = useRequireAuth(['provider']);
  const params = useParams();
  const rfqId = params.id as string;

  const [status, setStatus] = useState<UnlockStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.providerRFQ.getUnlockStatus(rfqId);
      setStatus(res.data as unknown as UnlockStatus);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Failed to load NDA status.');
    } finally {
      setLoading(false);
    }
  }, [rfqId]);

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
            <CardTitle>Error Loading NDA Status</CardTitle>
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

  const isSigned =
    status?.provider_signed_at ||
    status?.fully_signed_at ||
    status?.nda_status === 'fully_signed' ||
    status?.nda_status === 'provider_signed';

  if (isSigned) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
            <CardTitle>NDA Signed!</CardTitle>
            <CardDescription>
              You have successfully signed the NDA. You can now access the full RFQ details.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Link href={`/provider/rfq/${rfqId}`}>
              <Button className="w-full">View Full RFQ Details</Button>
            </Link>
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
            <h1 className="text-2xl font-bold">Sign NDA to Access RFQ</h1>
          </div>
          <p className="text-gray-600">
            This RFQ requires a Non-Disclosure Agreement before you can view the full project details.
          </p>
        </div>

        {status?.signing_url ? (
          <div className="space-y-4">
            <Card>
              <CardContent className="p-0">
                <iframe
                  src={status.signing_url}
                  className="w-full h-[600px] rounded-lg border-0"
                  title="Provider NDA Signing"
                />
              </CardContent>
            </Card>
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">After signing, click refresh to update status.</p>
              <Button onClick={fetchStatus} variant="outline" size="sm">
                <RefreshCw className="mr-2 h-4 w-4" />Refresh Status
              </Button>
            </div>
          </div>
        ) : (
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <Mail className="h-8 w-8 text-blue-500" />
                <div>
                  <CardTitle>Check Your Email</CardTitle>
                  <CardDescription>
                    Please check your email for the NDA signing link from Signwell.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-gray-600">
                A signing request has been sent to your registered email address. Click the link in
                that email to sign the NDA securely via Signwell.
              </p>
              <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                <p className="text-sm text-blue-800">
                  <strong>Tip:</strong> Check your spam folder if you don&apos;t see the email within a few minutes.
                </p>
              </div>
              <Button onClick={fetchStatus} variant="outline" className="w-full">
                <RefreshCw className="mr-2 h-4 w-4" />I&apos;ve Signed — Check Status
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
