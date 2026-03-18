'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  Loader2, AlertCircle, Lock, CreditCard, CheckCircle, FileText, Clock, Tag,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface RFQTeaser {
  id: string;
  urgency?: string;
  tollgate_phases?: string[];
  rfq_status?: string;
  nda_required?: boolean;
}

interface UnlockStatus {
  unlocked: boolean;
  unlock_status?: string;
  rfq_status?: string;
  nda_status?: string;
  signing_url?: string;
}

export default function RFQUnlockPage() {
  const { isLoading: authLoading } = useRequireAuth(['provider']);
  const params = useParams();
  const rfqId = params.id as string;

  const [teaser, setTeaser] = useState<RFQTeaser | null>(null);
  const [unlockStatus, setUnlockStatus] = useState<UnlockStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [teaserRes, statusRes] = await Promise.all([
        api.providerRFQ.getTeaser(rfqId),
        api.providerRFQ.getUnlockStatus(rfqId),
      ]);
      setTeaser(teaserRes.data as unknown as RFQTeaser);
      setUnlockStatus(statusRes.data as unknown as UnlockStatus);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Failed to load RFQ details.');
    } finally {
      setLoading(false);
    }
  }, [rfqId]);

  useEffect(() => {
    if (!authLoading) fetchData();
  }, [authLoading, fetchData]);

  const handleUnlock = async () => {
    setError('');
    setPaying(true);
    try {
      const res = await api.providerRFQ.unlockCheckout(rfqId);
      const data = res.data as unknown as {
        checkout_url?: string;
        client_secret?: string;
        approval_url?: string;
      };
      const url = data.checkout_url || data.approval_url;
      if (url && url.startsWith('http')) {
        window.location.href = url;
      } else {
        setError('Payment URL not received. Please try again.');
        setPaying(false);
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e?.response?.data?.detail || 'Payment initiation failed. Please try again.');
      setPaying(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error && !teaser) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
            <CardTitle>Unable to Load RFQ</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Button onClick={fetchData} variant="outline">Try Again</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isClosed = ['closed_no_selection', 'cancelled', 'quote_limit_reached', 'customer_selected_provider']
    .includes(teaser?.rfq_status ?? '');

  if (isClosed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto mb-2" />
            <CardTitle>RFQ No Longer Available</CardTitle>
            <CardDescription>
              This RFQ has been closed. It may have reached its quote limit or the customer has already selected a provider.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Link href="/provider/dashboard"><Button variant="outline">Back to Dashboard</Button></Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (unlockStatus?.unlocked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
            <CardTitle>Already Unlocked</CardTitle>
            <CardDescription>You have already paid to access this RFQ.</CardDescription>
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
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="mb-6 flex items-center gap-2">
          <Lock className="h-5 w-5 text-blue-600" />
          <h1 className="text-2xl font-bold">Unlock RFQ Details</h1>
        </div>

        {teaser && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4" /> RFQ Overview
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {teaser.urgency && (
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-gray-400" />
                  <span className="text-sm text-gray-600">Urgency:</span>
                  <Badge variant={
                    teaser.urgency === 'High' ? 'destructive' :
                    teaser.urgency === 'Intermediate' ? 'default' : 'secondary'
                  }>{teaser.urgency}</Badge>
                </div>
              )}
              {teaser.tollgate_phases && teaser.tollgate_phases.length > 0 && (
                <div className="flex items-start gap-2">
                  <Tag className="h-4 w-4 text-gray-400 mt-0.5" />
                  <span className="text-sm text-gray-600 flex-shrink-0">Phases:</span>
                  <div className="flex flex-wrap gap-1">
                    {teaser.tollgate_phases.map((phase) => (
                      <Badge key={phase} variant="outline" className="text-xs">{phase}</Badge>
                    ))}
                  </div>
                </div>
              )}
              {teaser.nda_required && (
                <div className="flex items-center gap-2 text-sm text-orange-700 bg-orange-50 px-3 py-2 rounded-md">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  This project requires NDA signing before accessing full details.
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5" /> Pay to Unlock &mdash; $10
            </CardTitle>
            <CardDescription>
              Pay a one-time $10 fee to access the full RFQ details and submit a quote.
              Only the first five quotes are shown to the customer.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-md">
                <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}
            <Button className="w-full" onClick={handleUnlock} disabled={paying}>
              {paying
                ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Redirecting to payment...</>
                : <><CreditCard className="mr-2 h-4 w-4" />Pay $10 to Unlock</>}
            </Button>
            <p className="text-xs text-gray-500 text-center">
              Quotes are rough, non-binding, order-of-magnitude estimates.
              Refined estimates follow direct engagement.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
