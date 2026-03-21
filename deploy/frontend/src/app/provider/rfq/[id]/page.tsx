'use client';

import { useEffect, useState, useCallback , Suspense } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Loader2, AlertCircle, CheckCircle, Download, FileText, Clock, Tag,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface RFQFile {
  id: string;
  original_filename: string;
  mime_type?: string;
  file_size_bytes?: number;
  presigned_url?: string;
  download_url?: string;
}

interface UnlockStatus {
  unlocked: boolean;
  nda_status?: string;
  rfq_status?: string;
  files?: RFQFile[];
  project_description?: string;
  urgency?: string;
  tollgate_phases?: string[];
  nda_required?: boolean;
}

interface QuoteForm {
  rough_price_min: string;
  rough_price_max: string;
  turnaround_estimate_text: string;
  assumptions_text: string;
  scope_notes: string;
}

const emptyForm: QuoteForm = {
  rough_price_min: '',
  rough_price_max: '',
  turnaround_estimate_text: '',
  assumptions_text: '',
  scope_notes: '',
};

function formatBytes(bytes?: number): string {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function ProviderRFQDetailPageContent() {
  const { isLoading: authLoading } = useRequireAuth(['provider']);
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rfqId = params.id as string;

  const [rfqData, setRfqData] = useState<UnlockStatus | null>(null);
  const [files, setFiles] = useState<RFQFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState<QuoteForm>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [quoteSuccess, setQuoteSuccess] = useState(false);
  const [quoteError, setQuoteError] = useState('');
  const [subscriptionRequired, setSubscriptionRequired] = useState(false);
  // FIX 2: Track locked state inline instead of redirecting to /rfqs/{id}/unlock
  const [isLocked, setIsLocked] = useState(false);

  const fetchRFQ = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const statusRes = await api.providerRFQ.getUnlockStatus(rfqId);
      const status = statusRes.data as unknown as UnlockStatus;
      if (!status.unlocked) {
        if (
          status.nda_status &&
          status.nda_status !== 'not_required' &&
          status.nda_status !== 'fully_signed'
        ) {
          router.replace('/provider/nda/' + rfqId + '/sign');
          return;
        }
        // FIX 2: Show inline locked view instead of redirecting to /rfqs/{id}/unlock
        setIsLocked(true);
        return;
      }
      setRfqData(status);
      try {
        const filesRes = await api.providerRFQ.getFiles(rfqId);
        setSubscriptionRequired(false);
        setFiles((filesRes.data as unknown as RFQFile[]) || []);
      } catch (fileErr: unknown) {
        const fe = fileErr as { response?: { status?: number; data?: { detail?: string } } };
        const detail = fe?.response?.data?.detail || '';
        if (fe?.response?.status === 403 && detail.includes('SUBSCRIPTION_REQUIRED')) {
          setSubscriptionRequired(true);
          setFiles([]);
        } else {
          setFiles((status.files as RFQFile[]) || []);
        }
      }
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: string } } };
      if (e?.response?.status === 401 || e?.response?.status === 403) {
        // FIX 2: Show inline locked view instead of redirecting to /rfqs/{id}/unlock
        setIsLocked(true);
        return;
      }
      setError(e?.response?.data?.detail || 'Failed to load RFQ details.');
    } finally {
      setLoading(false);
    }
  }, [rfqId, router]);

  // Store invite token from URL on mount
  useEffect(() => {
    const invite = searchParams.get('invite');
    if (invite) {
      localStorage.setItem('pendingInviteToken', invite);
      localStorage.setItem('pendingInviteRfqId', searchParams.get('rfq_id') || rfqId);
    }
  }, [rfqId, searchParams]);

    useEffect(() => {
    if (!authLoading) fetchRFQ();
  }, [authLoading, fetchRFQ]);

  const handleDownload = (file: RFQFile) => {
    const url = file.presigned_url || file.download_url;
    if (url) window.open(url, '_blank');
  };

  const handleSubmitQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    setQuoteError('');
    setSubmitting(true);
    try {
      await api.providerRFQ.submitQuote(rfqId, {
        rough_price_min: form.rough_price_min ? Number(form.rough_price_min) : undefined,
        rough_price_max: form.rough_price_max ? Number(form.rough_price_max) : undefined,
        turnaround_estimate_text: form.turnaround_estimate_text || undefined,
        assumptions_text: form.assumptions_text || undefined,
        scope_notes: form.scope_notes || undefined,
      });
      setQuoteSuccess(true);
      setForm(emptyForm);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setQuoteError(e?.response?.data?.detail || 'Failed to submit quote.');
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  // FIX 2: Show contextual locked view instead of immediate redirect to bare payment form.
  // Brand-new users arriving from email invites had no context for the $10 payment.
  if (isLocked) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <div className="flex justify-center mb-4">
              <div className="h-16 w-16 rounded-full bg-amber-100 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
            </div>
            <CardTitle className="text-xl">Unlock RFQ to View Details</CardTitle>
            <CardDescription className="mt-2 text-base">
              You have been invited to bid on an engineering project.
              Pay a one-time $10 fee to access the full project description,
              uploaded files, and submit your rough quote.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800 space-y-2">
              <p className="font-semibold">What you get after unlocking:</p>
              <ul className="list-disc list-inside space-y-1">
                <li>Full project description and scope</li>
                <li>All uploaded project files and drawings</li>
                <li>Ability to submit a rough quote to the customer</li>
              </ul>
            </div>
            <p className="text-xs text-gray-500 text-center">
              Only the first 5 quotes per RFQ are accepted &mdash; unlock now to secure your spot.
            </p>
            <Button
              className="w-full bg-amber-600 hover:bg-amber-700 text-white"
              onClick={() => router.push(`/rfqs/${rfqId}/unlock`)}
            >
              Unlock This RFQ &mdash; $10
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => router.push("/provider/dashboard")}
            >
              Back to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
        <Card className="w-full max-w-lg">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
            <CardTitle>Error Loading RFQ</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Button onClick={fetchRFQ} variant="outline">Try Again</Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-6 py-10 space-y-6">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-blue-600" />
          <h1 className="text-2xl font-bold">RFQ Details</h1>
          <Badge variant="outline" className="ml-auto">Unlocked</Badge>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Project Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {rfqData?.project_description && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">Project Description</p>
                <p className="text-sm text-gray-600 whitespace-pre-wrap">
                  {rfqData.project_description}
                </p>
              </div>
            )}
            {rfqData?.urgency && (
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className="text-sm text-gray-600">Urgency:</span>
                <Badge
                  variant={
                    rfqData.urgency === 'High'
                      ? 'destructive'
                      : rfqData.urgency === 'Intermediate'
                      ? 'default'
                      : 'secondary'
                  }
                >
                  {rfqData.urgency}
                </Badge>
              </div>
            )}
            {rfqData?.tollgate_phases && rfqData.tollgate_phases.length > 0 && (
              <div className="flex items-start gap-2">
                <Tag className="h-4 w-4 text-gray-400 mt-0.5" />
                <span className="text-sm text-gray-600 flex-shrink-0">Phases:</span>
                <div className="flex flex-wrap gap-1">
                  {rfqData.tollgate_phases.map((phase) => (
                    <Badge key={phase} variant="outline" className="text-xs">
                      {phase}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {rfqData?.nda_required && (
              <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 px-3 py-2 rounded-md">
                <CheckCircle className="h-4 w-4 flex-shrink-0" />
                NDA has been signed for this project.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Project Files</CardTitle>
            <CardDescription>
              Download the project documents to review before quoting.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {subscriptionRequired ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-center space-y-3">
                <div className="flex justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <p className="font-semibold text-amber-800">Subscription Required to Access Documents</p>
                <p className="text-sm text-amber-700">
                  Project files and documentation are available to providers with an active subscription ($10/month).
                  Your subscription also allows you to edit your profile and request tier upgrades.
                </p>
                <a
                  href="/provider/dashboard"
                  className="inline-block mt-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700"
                >
                  Subscribe Now — $10/month
                </a>
              </div>
            ) : files.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No files uploaded for this RFQ.
              </p>
            ) : (
              <ul className="space-y-2">
                {files.map((file) => (
                  <li
                    key={file.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-md border"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 text-blue-500 flex-shrink-0" />
                      <span className="text-sm font-medium truncate">
                        {file.original_filename}
                      </span>
                      {file.file_size_bytes && (
                        <span className="text-xs text-gray-400 flex-shrink-0">
                          {formatBytes(file.file_size_bytes)}
                        </span>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDownload(file)}
                      className="flex-shrink-0 ml-2"
                    >
                      <Download className="h-3 w-3 mr-1" />
                      Download
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Submit Your Quote</CardTitle>
            <CardDescription>
              Provide a rough, non-binding estimate. Be clear about assumptions and scope.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {quoteSuccess ? (
              <div className="flex items-center gap-2 text-green-700 bg-green-50 px-4 py-3 rounded-md">
                <CheckCircle className="h-5 w-5 flex-shrink-0" />
                <div>
                  <p className="font-medium">Quote submitted successfully!</p>
                  <p className="text-sm mt-0.5">
                    The customer will be notified and can view your submission.
                  </p>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmitQuote} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label htmlFor="price_min">Rough Price Min ($)</Label>
                    <Input
                      id="price_min"
                      type="number"
                      placeholder="e.g. 5000"
                      value={form.rough_price_min}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, rough_price_min: e.target.value }))
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="price_max">Rough Price Max ($)</Label>
                    <Input
                      id="price_max"
                      type="number"
                      placeholder="e.g. 15000"
                      value={form.rough_price_max}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, rough_price_max: e.target.value }))
                      }
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="turnaround">Turnaround Estimate</Label>
                  <Input
                    id="turnaround"
                    placeholder="e.g. 3-4 weeks"
                    value={form.turnaround_estimate_text}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, turnaround_estimate_text: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="assumptions">Assumptions</Label>
                  <Textarea
                    id="assumptions"
                    placeholder="List any assumptions made in your estimate..."
                    rows={3}
                    value={form.assumptions_text}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, assumptions_text: e.target.value }))
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="scope">Scope Notes</Label>
                  <Textarea
                    id="scope"
                    placeholder="Describe what is included and excluded from your estimate..."
                    rows={3}
                    value={form.scope_notes}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, scope_notes: e.target.value }))
                    }
                  />
                </div>
                {quoteError && (
                  <div className="flex items-center gap-2 text-red-600 bg-red-50 px-3 py-2 rounded-md text-sm">
                    <AlertCircle className="h-4 w-4 flex-shrink-0" />
                    {quoteError}
                  </div>
                )}
                <p className="text-xs text-gray-500">
                  Note: This is a rough, non-binding, order-of-magnitude estimate only.
                  A refined final estimate will follow direct engagement.
                </p>
                <Button type="submit" disabled={submitting} className="w-full">
                  {submitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    'Submit Quote'
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function ProviderRFQDetailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>}>
      <ProviderRFQDetailPageContent />
    </Suspense>
  );
}
