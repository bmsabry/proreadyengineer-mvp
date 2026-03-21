'use client';

import { useEffect, useState, useCallback, Suspense } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Loader2, AlertCircle, CheckCircle, Download, FileText, Clock,
  Lock, LockOpen, Building2, ShieldAlert, ArrowLeft, CalendarDays, Layers, CreditCard, Send,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useRequireAuth } from '@/hooks/useAuth';

interface UnlockStatus {
  unlocked: boolean;
  has_membership?: boolean;
  has_dispatch?: boolean;
  urgency?: string;
  tollgate_phases?: string[];
  nda_required?: boolean;
  business_name?: string;
  project_description_preview?: string;
  project_description?: string;
  rfq_status?: string;
  submitted_at?: string;
}

interface RFQFile {
  id: string;
  original_filename: string;
  presigned_url?: string;
  file_size_bytes?: number;
}

const urgencyVariant = (u?: string): 'destructive' | 'default' | 'secondary' => {
  if (!u) return 'secondary';
  const l = u.toLowerCase();
  if (l === 'high') return 'destructive';
  if (l === 'intermediate') return 'default';
  return 'secondary';
};

const fmtDate = (iso?: string) =>
  iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Unknown';

const fmtBytes = (n?: number) => {
  if (!n) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
};

function TeaserInfoPanel({ status }: { status: UnlockStatus }) {
  return (
    <Card className="border-blue-200 bg-blue-50">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2 mb-2">
          <Building2 className="h-5 w-5 text-blue-600" />
          <CardTitle className="text-lg text-blue-900">{status.business_name || 'Engineering Project Request'}</CardTitle>
        </div>
        <div className="flex flex-wrap gap-2">
          {status.urgency && <Badge variant={urgencyVariant(status.urgency)}><Clock className="h-3 w-3 mr-1"/>{status.urgency} Priority</Badge>}
          {status.nda_required && <Badge variant="outline" className="border-amber-400 text-amber-700 bg-amber-50"><ShieldAlert className="h-3 w-3 mr-1"/>NDA Required</Badge>}
          {status.rfq_status && <Badge variant="outline" className="capitalize text-gray-600">{status.rfq_status.replace(/_/g, ' ')}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.submitted_at && <div className="flex items-center gap-2 text-sm text-gray-600"><CalendarDays className="h-4 w-4"/><span>Submitted {fmtDate(status.submitted_at)}</span></div>}
        {status.tollgate_phases && status.tollgate_phases.length > 0 && (
          <div className="flex items-start gap-2 text-sm text-gray-700">
            <Layers className="h-4 w-4 mt-0.5 flex-shrink-0 text-blue-500" />
            <div><span className="font-medium">Tollgate Phases: </span>{status.tollgate_phases.join(', ')}</div>
          </div>
        )}
        {status.project_description_preview && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-1 flex items-center gap-1"><FileText className="h-4 w-4"/>Project Summary</p>
            <p className="text-sm text-gray-600 bg-white rounded p-3 border border-blue-100 leading-relaxed">{status.project_description_preview}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function LockedCard({ status, onUnlock, checkingOut }: { status: UnlockStatus; onUnlock: () => void; checkingOut: boolean }) {
  return (
    <Card className="border-gray-200">
      <CardHeader className="text-center pb-2">
        <div className="flex justify-center mb-3"><div className="rounded-full bg-gray-100 p-4"><Lock className="h-8 w-8 text-gray-500"/></div></div>
        <CardTitle>Full Project Details Locked</CardTitle>
        <CardDescription className="text-base">Unlock this project to access complete documents and submit a quote.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-gray-600 mb-4">
          {['Complete project description and requirements','All uploaded project documents and drawings','Quote submission form','Customer direct contact (after quote acceptance)'].map((item) => (
            <li key={item} className="flex items-center gap-2"><CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0"/>{item}</li>
          ))}
        </ul>
        {status.nda_required && (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 mb-4 text-sm text-amber-800 flex items-start gap-2">
            <ShieldAlert className="h-4 w-4 mt-0.5 flex-shrink-0"/>
            <span><strong>NDA Required:</strong> After unlocking you will be asked to sign a Non-Disclosure Agreement before accessing project files.</span>
          </div>
        )}
      </CardContent>
      <CardFooter className="flex flex-col gap-3">
        <Button onClick={onUnlock} disabled={checkingOut} size="lg" className="w-full bg-blue-600 hover:bg-blue-700 text-white">
          {checkingOut ? <><Loader2 className="h-4 w-4 mr-2 animate-spin"/>Processing...</> : <><CreditCard className="h-4 w-4 mr-2"/>Unlock for $10 - One-time fee</>}
        </Button>
        <p className="text-xs text-gray-500 text-center">Secure payment via Stripe. Only the first 5 quotes are shown to the customer.</p>
      </CardFooter>
    </Card>
  );
}

function FilesSection({ files, loading }: { files: RFQFile[]; loading: boolean }) {
  if (loading) return <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin"/>Loading files...</div>;
  if (!files.length) return <p className="text-sm text-gray-500 italic">No files attached to this project.</p>;
  return (
    <ul className="space-y-2">
      {files.map((f) => (
        <li key={f.id} className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2">
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <FileText className="h-4 w-4 text-blue-500"/>
            <span>{f.original_filename}</span>
            {f.file_size_bytes && <span className="text-gray-400 text-xs">({fmtBytes(f.file_size_bytes)})</span>}
          </div>
          {f.presigned_url && (
            <a href={f.presigned_url} target="_blank" rel="noreferrer">
              <Button variant="ghost" size="sm"><Download className="h-4 w-4 mr-1"/>Download</Button>
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

function QuoteForm({ rfqId, onSuccess }: { rfqId: string; onSuccess: () => void }) {
  const [min, setMin] = useState('');
  const [max, setMax] = useState('');
  const [turnaround, setTurnaround] = useState('');
  const [assumptions, setAssumptions] = useState('');
  const [scopeNotes, setScopeNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const handleSubmit = async () => {
    if (!assumptions.trim()) { toast.error('Please list your technical assumptions.'); return; }
    if (!turnaround.trim()) { toast.error('Please provide a turnaround estimate.'); return; }
    setSubmitting(true);
    try {
      await api.providerRFQ.submitQuote(rfqId, {
        rough_price_min: min ? parseFloat(min) : undefined,
        rough_price_max: max ? parseFloat(max) : undefined,
        turnaround_estimate_text: turnaround,
        assumptions_text: assumptions,
        scope_notes: scopeNotes || undefined,
      });
      toast.success('Quote submitted successfully!');
      onSuccess();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to submit quote.');
    } finally { setSubmitting(false); }
  };
  return (
    <div className="space-y-4">
      <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-800">
        <strong>Note:</strong> Quotes are rough, non-binding estimates. A refined final estimate follows direct engagement.
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="qmin">Min Estimate (USD)</Label>
          <Input id="qmin" type="number" placeholder="e.g. 5000" value={min} onChange={(e) => setMin(e.target.value)}/>
        </div>
        <div>
          <Label htmlFor="qmax">Max Estimate (USD)</Label>
          <Input id="qmax" type="number" placeholder="e.g. 15000" value={max} onChange={(e) => setMax(e.target.value)}/>
        </div>
      </div>
      <div>
        <Label htmlFor="turn">Turnaround Estimate *</Label>
        <Input id="turn" placeholder="e.g. 4-6 weeks" value={turnaround} onChange={(e) => setTurnaround(e.target.value)}/>
      </div>
      <div>
        <Label htmlFor="assump">Technical Assumptions <span className="text-red-500">*</span></Label>
        <Textarea id="assump" placeholder="List all technical assumptions, constraints, and scope boundaries..." rows={5} value={assumptions} onChange={(e) => setAssumptions(e.target.value)}/>
        <p className="text-xs text-gray-500 mt-1">Be specific. Customers compare quotes based on these.</p>
      </div>
      <div>
        <Label htmlFor="scope">Additional Scope Notes</Label>
        <Textarea id="scope" placeholder="Optional: scope clarifications or exclusions..." rows={3} value={scopeNotes} onChange={(e) => setScopeNotes(e.target.value)}/>
      </div>
      <Button onClick={handleSubmit} disabled={submitting} size="lg" className="w-full bg-green-600 hover:bg-green-700 text-white">
        {submitting ? <><Loader2 className="h-4 w-4 mr-2 animate-spin"/>Submitting...</> : <><Send className="h-4 w-4 mr-2"/>Submit Quote</>}
      </Button>
    </div>
  );
}

function ProviderRFQPageInner() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rfqId = params.id as string;
  useRequireAuth(['provider', 'admin']);

  const [status, setStatus] = useState<UnlockStatus | null>(null);
  const [files, setFiles] = useState<RFQFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filesLoading, setFilesLoading] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [quoteSubmitted, setQuoteSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const result = searchParams.get('payment');
    if (result === 'success') toast.success('Payment confirmed! Project files are now unlocked.');
    if (result === 'cancelled') toast.info('Payment cancelled. You can unlock anytime.');
  }, [searchParams]);

  const loadStatus = useCallback(async () => {
    try {
      const res = await api.providerRFQ.getUnlockStatus(rfqId);
      setStatus(res.data);
    } catch (e: unknown) {
      const code = (e as { response?: { status?: number } })?.response?.status;
      if (code === 404) setError('This RFQ was not found or is no longer available.');
      else if (code === 403) setError('You do not have provider access to this project.');
      else setError('Failed to load project details. Please refresh or try again.');
    } finally { setLoading(false); }
  }, [rfqId]);

  const loadFiles = useCallback(async () => {
    setFilesLoading(true);
    try {
      const res = await api.providerRFQ.getFiles(rfqId);
      const data = res.data;
      setFiles(Array.isArray(data) ? data : []);
    } catch {
      // files may be temporarily unavailable
    } finally { setFilesLoading(false); }
  }, [rfqId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => { if (status?.unlocked) loadFiles(); }, [status?.unlocked, loadFiles]);

  const handleUnlock = async () => {
    setCheckingOut(true);
    try {
      const res = await api.providerRFQ.unlockCheckout(rfqId);
      const url = res.data?.checkout_url || res.data?.url;
      if (url) { window.location.href = url; }
      else toast.error('Could not initiate payment. Please try again.');
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || 'Failed to start checkout. Please try again.');
    } finally { setCheckingOut(false); }
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center"><Loader2 className="h-10 w-10 animate-spin text-blue-600 mx-auto mb-3"/><p className="text-gray-500">Loading project details...</p></div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardContent className="pt-6 text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-3"/>
          <p className="text-gray-700 mb-4">{error}</p>
          <Button variant="outline" onClick={() => router.push('/provider/dashboard')}><ArrowLeft className="h-4 w-4 mr-2"/>Back to Dashboard</Button>
        </CardContent>
      </Card>
    </div>
  );

  if (!status) return null;

  // No dispatch record - provider stumbled on this URL
  if (status.has_membership && status.has_dispatch === false) return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardContent className="pt-6 text-center">
          <AlertCircle className="h-12 w-12 text-amber-500 mx-auto mb-3"/>
          <p className="text-gray-700 mb-4">This project is not in your invitation list.</p>
          <Button variant="outline" onClick={() => router.push('/provider/dashboard')}><ArrowLeft className="h-4 w-4 mr-2"/>Back to Dashboard</Button>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="sm" onClick={() => router.push('/provider/dashboard')} className="text-gray-500 hover:text-gray-700"><ArrowLeft className="h-4 w-4 mr-1"/>Dashboard</Button>
          <div className="h-4 w-px bg-gray-300" />
          <h1 className="text-xl font-semibold text-gray-900">Project Invitation</h1>
          {status.unlocked
            ? <Badge className="bg-green-100 text-green-800 border-green-200 ml-auto"><LockOpen className="h-3 w-3 mr-1" />Unlocked</Badge>
            : <Badge variant="outline" className="text-gray-500 ml-auto"><Lock className="h-3 w-3 mr-1" />Locked</Badge>
          }
        </div>

        <div className="space-y-6">
          {/* Always show teaser info */}
          <TeaserInfoPanel status={status} />

          {/* Lock / Unlock section */}
          {!status.unlocked && (
            <LockedCard status={status} onUnlock={handleUnlock} checkingOut={checkingOut} />
          )}

          {/* Unlocked: full description + files + quote form */}
          {status.unlocked && (
            <>
              {status.project_description && (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2"><FileText className="h-5 w-5 text-blue-600"/>Full Project Description</CardTitle></CardHeader>
                  <CardContent><p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{status.project_description}</p></CardContent>
                </Card>
              )}

              <Card>
                <CardHeader><CardTitle className="flex items-center gap-2"><Download className="h-5 w-5 text-blue-600"/>Project Files</CardTitle></CardHeader>
                <CardContent><FilesSection files={files} loading={filesLoading} /></CardContent>
              </Card>

              {!quoteSubmitted ? (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2"><Send className="h-5 w-5 text-green-600"/>Submit Your Quote</CardTitle><CardDescription>Only the first 5 quotes are shown to the customer. Submit early.</CardDescription></CardHeader>
                  <CardContent><QuoteForm rfqId={rfqId} onSuccess={() => setQuoteSubmitted(true)} /></CardContent>
                </Card>
              ) : (
                <Card className="border-green-200 bg-green-50">
                  <CardContent className="pt-6 text-center">
                    <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3"/>
                    <h3 className="font-semibold text-green-900 text-lg mb-2">Quote Submitted!</h3>
                    <p className="text-green-700 text-sm">Your quote has been sent to the customer. You will be notified if you are selected.</p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProviderRFQPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-600"/></div>}>
      <ProviderRFQPageInner />
    </Suspense>
  );
}
