'use client';

import { useEffect, useState, Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Loader2, CheckCircle, AlertCircle, FileText } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

function CustomerNdaSignContent() {
  const { isLoading: authLoading } = useRequireAuth();
  const params = useParams();
  const searchParams = useSearchParams();
  const rfqId = params.id as string;

  const [status, setStatus] = useState<'loading' | 'nda_pending' | 'fully_signed' | 'not_required'>('loading');
  const isPaidReturn = searchParams.get('paid') === 'true';

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

  if (authLoading || status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gray-50">
      <Card className="max-w-lg w-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-blue-600" />
            Non-Disclosure Agreement
          </CardTitle>
          <CardDescription>
            RFQ #{rfqId ? rfqId.toString().slice(0, 8) : ''}...
          </CardDescription>
        </CardHeader>
        <CardContent>
          {status === 'fully_signed' && (
            <div className="text-center">
              <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-green-900 mb-2">NDA Fully Signed</h3>
              <p className="text-sm text-gray-600 mb-4">
                Both parties have signed the NDA. Project files are now accessible.
              </p>
              <Link href={`/provider/rfq/${rfqId}`} className="text-blue-600 hover:underline text-sm">
                View Project &rarr;
              </Link>
            </div>
          )}

          {status === 'not_required' && (
            <div className="text-center">
              <CheckCircle className="h-12 w-12 text-blue-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No NDA Required</h3>
              <p className="text-sm text-gray-600 mb-4">This project does not require an NDA.</p>
              <Link href="/customer/dashboard" className="text-blue-600 hover:underline text-sm">
                &larr; Back to Dashboard
              </Link>
            </div>
          )}

          {status === 'nda_pending' && (
            <div>
              {isPaidReturn && (
                <div className="bg-green-50 border border-green-200 rounded-md p-4 mb-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <span className="font-medium text-green-900 text-sm">Payment Received</span>
                  </div>
                  <p className="text-sm text-green-800">
                    Your RFQ has been submitted and matched providers are being contacted.
                  </p>
                </div>
              )}
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-gray-900 mb-1">Awaiting NDA Signatures</h3>
                  <p className="text-sm text-gray-600 mb-3">
                    The Non-Disclosure Agreement signing process happens after a provider quote is
                    accepted. Both parties will receive an email from Signwell with signing
                    instructions at that time.
                  </p>
                  <p className="text-xs text-gray-500">
                    If you have already accepted a quote and received a signing email, please check
                    your inbox.
                  </p>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t">
                <Link href="/customer/dashboard" className="text-blue-600 hover:underline text-sm">
                  &larr; Back to Dashboard
                </Link>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function NdaSignPage() {
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
