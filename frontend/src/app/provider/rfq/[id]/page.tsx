'use client';

import { useEffect, useState, useCallback, useRef, Suspense } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Loader2, AlertCircle, CheckCircle, Download, FileText, Clock,
  Lock, LockOpen, Building2, ShieldAlert, ArrowLeft, CalendarDays, Layers,
  CreditCard, Send, Upload, X, Sparkles, Trophy, Ban,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import api from '@/lib/api';
import { Quote } from '@/types';
import { useRequireAuth } from '@/hooks/useAuth';

interface UnlockStatus {
  unlocked: boolean;
  has_membership?: boolean;
  has_dispatch?: boolean;
  urgency?: string;
  tollgate_phases?: string[];
  nda_required?: boolean;
  provider_nda_signed?: boolean;
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


const CLOSED_STATUSES = [
  'customer_selected_provider',
  'closed_no_selection',
  'quote_limit_reached',
  'cancelled',
  'closed',
];

function SubmittedQuoteCard({ quote }: { quote: Quote }) {
  const isAccepted = quote.quote_status === 'accepted';
  const isNotSelected = quote.quote_status === 'not_selected';
  const isWithdrawn = quote.quote_status === 'withdrawn';

  const statusLabels: Record<string, string> = {
    draft: 'Draft',
    submitted: 'Submitted - Awaiting Customer Review',
    withdrawn: 'Withdrawn',
    customer_viewed: 'Viewed by Customer',
    shortlisted: 'Shortlisted by Customer',
    accepted: 'Accepted - You Won!',
    not_selected: 'Not Selected',
    expired: 'Expired',
  };

  const statusLabel = statusLabels[quote.quote_status] || quote.quote_status;

  return (
    <div className="space-y-4">
      {isAccepted && (
        <Card className="border-yellow-300 bg-yellow-50">
          <CardContent className="pt-5">
            <div className="flex items-center gap-3 mb-3">
              <Trophy className="h-8 w-8 text-yellow-600" />
              <div>
                <h3 className="font-bold text-yellow-900 text-lg">Your Quote Was Accepted!</h3>
                <p className="text-yellow-700 text-sm">The customer has selected your firm. Direct contact details are below.</p>
              </div>
            </div>
            {(quote.customer_contact_name || quote.customer_email || quote.customer_company) && (
              <div className="mt-3 rounded-md border border-yellow-200 bg-white p-3 space-y-1">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Customer Contact</p>
                {quote.customer_contact_name && <p className="text-sm font-medium text-gray-900">{quote.customer_contact_name}</p>}
                {quote.customer_company && <p className="text-sm text-gray-600">{quote.customer_company}</p>}
                {quote.customer_email && (
                  <a href={`mailto:${quote.customer_email}`} className="text-sm text-blue-600 hover:underline block">{quote.customer_email}</a>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card className={isAccepted ? 'border-green-300' : isNotSelected ? 'border-gray-300' : 'border-blue-200'}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <CheckCircle className="h-5 w-5 text-green-500" />
              Your Submitted Quote
            </CardTitle>
            <Badge
              variant={isAccepted ? 'default' : isNotSelected ? 'secondary' : 'outline'}
              className={isAccepted ? 'bg-green-100 text-green-800' : isWithdrawn ? 'bg-red-100 text-red-700' : ''}>
              {statusLabel}
            </Badge>
          </div>
          {quote.submitted_at && (
            <CardDescription>Submitted {fmtDate(quote.submitted_at)}</CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {(quote.rough_price_min != null || quote.rough_price_max != null) && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Estimate Range</p>
              <p className="text-sm text-gray-800">
                {quote.rough_price_min != null ? `$${quote.rough_price_min.toLocaleString()}` : 'N/A'}
                {' — '}
                {quote.rough_price_max != null ? `$${quote.rough_price_max.toLocaleString()}` : 'N/A'}
                {quote.currency ? ` ${quote.currency}` : ' USD'}
              </p>
            </div>
          )}
          {quote.turnaround_estimate_text && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Turnaround</p>
              <p className="text-sm text-gray-800">{quote.turnaround_estimate_text}</p>
            </div>
          )}
          {quote.assumptions_text && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Technical Assumptions</p>
              <p className="text-sm text-gray-800 whitespace-pre-wrap">{quote.assumptions_text}</p>
            </div>
          )}
          {quote.scope_notes && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Scope Notes</p>
              <p className="text-sm text-gray-800 whitespace-pre-wrap">{quote.scope_notes}</p>
            </div>
          )}
          {quote.document_filename && (
            <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-500" />
              <span className="text-sm text-gray-700">{quote.document_filename}</span>
              <Badge className="ml-auto text-xs bg-blue-50 text-blue-700">Attached</Badge>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


function QuoteForm({ rfqId, onSuccess }: { rfqId: string; onSuccess: () => void }) {
  const [min, setMin] = useState('');
  const [max, setMax] = useState('');
  const [turnaround, setTurnaround] = useState('');
  const [assumptions, setAssumptions] = useState('');
  const [scopeNotes, setScopeNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Document upload state
  const [useDocument, setUseDocument] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractedDocKey, setExtractedDocKey] = useState<string | null>(null);
  const [extractedDocFilename, setExtractedDocFilename] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
    if (!allowed.includes(file.type)) {
      toast.error('Only PDF, DOCX, or TXT files are supported.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error('File must be under 10MB.');
      return;
    }
    setSelectedFile(file);
    setExtracting(true);
    toast.info('Extracting quote fields from document...');
    try {
      const result = await api.quotes.extractQuoteDocument(rfqId, file);
      // Pre-fill form fields with extracted data
      if (result.rough_price_min != null) setMin(String(result.rough_price_min));
      if (result.rough_price_max != null) setMax(String(result.rough_price_max));
      if (result.turnaround_estimate_text) setTurnaround(result.turnaround_estimate_text);
      if (result.assumptions_text) setAssumptions(result.assumptions_text);
      if (result.scope_notes) setScopeNotes(result.scope_notes);
      setExtractedDocKey(result.s3_key);
      setExtractedDocFilename(result.original_filename);
      toast.success('Fields pre-filled from your document. Please review before submitting.');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      toast.error(e?.response?.data?.detail || 'Failed to extract fields from document. Please fill in manually.');
      setSelectedFile(null);
    } finally {
      setExtracting(false);
    }
  };

  const handleClearDocument = () => {
    setSelectedFile(null);
    setExtractedDocKey(null);
    setExtractedDocFilename(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

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
        document_s3_key: extractedDocKey || undefined,
        document_filename: extractedDocFilename || undefined,
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

      {/* Document upload toggle */}
      <div className="rounded-md border border-gray-200 p-4 bg-gray-50">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Upload className="h-4 w-4 text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Upload a quote document instead of typing</span>
          </div>
          <button
            type="button"
            onClick={() => { setUseDocument(!useDocument); if (useDocument) handleClearDocument(); }}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              useDocument ? 'bg-blue-600' : 'bg-gray-300'
            }`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              useDocument ? 'translate-x-4' : 'translate-x-0.5'
            }`} />
          </button>
        </div>
        <p className="text-xs text-gray-500">Upload a PDF, DOCX, or TXT file. AI will extract fields and pre-fill the form for your review.</p>

        {useDocument && (
          <div className="mt-3">
            {!selectedFile ? (
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={handleFileSelect}
                  className="hidden"
                  id="quote-doc-upload"
                />
                <label
                  htmlFor="quote-doc-upload"
                  className="flex items-center justify-center gap-2 w-full py-3 border-2 border-dashed border-blue-300 rounded-md cursor-pointer hover:bg-blue-50 transition-colors"
                >
                  {extracting ? (
                    <><Loader2 className="h-4 w-4 animate-spin text-blue-500" /><span className="text-sm text-blue-600">Analyzing document...</span></>
                  ) : (
                    <><Upload className="h-4 w-4 text-blue-500" /><span className="text-sm text-blue-600">Click to select file (PDF, DOCX, TXT)</span></>
                  )}
                </label>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-md border border-green-200 bg-green-50 px-3 py-2">
                <div className="flex items-center gap-2">
                  {extracting ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                  ) : (
                    <><Sparkles className="h-4 w-4 text-green-500" /></>
                  )}
                  <span className="text-sm text-gray-700 truncate max-w-[200px]">{selectedFile.name}</span>
                  {!extracting && extractedDocKey && (
                    <Badge className="bg-green-100 text-green-700 text-xs">Fields extracted</Badge>
                  )}
                </div>
                <button type="button" onClick={handleClearDocument} className="text-gray-400 hover:text-gray-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            {extractedDocKey && (
              <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                <CheckCircle className="h-3 w-3" />
                Document saved. It will be shared with the customer only if your quote is accepted.
              </p>
            )}
          </div>
        )}
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
      <Button onClick={handleSubmit} disabled={submitting || extracting} size="lg" className="w-full bg-green-600 hover:bg-green-700 text-white">
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
  const [existingQuote, setExistingQuote] = useState<Quote | null>(null);
  const [quotesLoading, setQuotesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ndaSigningUrl, setNdaSigningUrl] = useState<string | null>(null);
  const [ndaSigning, setNdaSigning] = useState(false);
  const [ndaPolling, setNdaPolling] = useState(false);

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

  const loadExistingQuote = useCallback(async () => {
    setQuotesLoading(true);
    try {
      const res = await api.quotes.getMyQuotes();
      const myQuotes: Quote[] = Array.isArray(res.data) ? res.data : [];
      const match = myQuotes.find((q) => q.rfq_id === rfqId);
      if (match) setExistingQuote(match);
    } catch {
      // silently ignore
    } finally {
      setQuotesLoading(false);
    }
  }, [rfqId]);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  useEffect(() => {
    const result = searchParams.get('payment');
    if (result === 'success') {
      toast.info('Verifying payment...');
      api.providerRFQ.verifyPayment(rfqId)
        .then((res) => {
          const data = res.data as { unlocked?: boolean; reason?: string };
          if (data?.unlocked) {
            toast.success('Payment confirmed! Project files are now unlocked.');
            loadStatus();
          } else {
            toast.error(data?.reason || 'Payment verification pending. Please refresh in a moment.');
            loadStatus();
          }
        })
        .catch((err: unknown) => {
          const e = err as { response?: { status?: number; data?: { reason?: string; detail?: string } }; message?: string };
          const serverMsg = e?.response?.data?.reason || e?.response?.data?.detail || e?.message || 'Unknown error';
          const statusCode = e?.response?.status || 'network';
          toast.error(`Payment verification failed (${statusCode}): ${serverMsg}`);
          loadStatus();
        });
    }
    if (result === 'cancelled') toast.info('Payment cancelled. You can unlock anytime.');
  }, [searchParams, rfqId, loadStatus]);

  useEffect(() => {
    if (status?.unlocked) {
      if (status.nda_required && !status.provider_nda_signed) {
        // Need provider NDA before showing files
        startProviderNdaSigning();
      } else {
        loadFiles();
        loadExistingQuote();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.unlocked, status?.provider_nda_signed]);

  const startProviderNdaSigning = async () => {
    if (ndaSigning) return;
    setNdaSigning(true);
    try {
      const res = await api.providerRFQ.initiateProviderNda(rfqId);
      const data = res.data as { signing_url?: string; message?: string };
      if (data?.signing_url) {
        setNdaSigningUrl(data.signing_url);
      } else if (data?.message) {
        // NDA already signed or not required
        toast.success('NDA confirmed. Loading project files...');
        await loadStatus();
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || 'Failed to initiate NDA signing. Please refresh.');
    } finally {
      setNdaSigning(false);
    }
  };

  const pollProviderNdaStatus = async () => {
    if (ndaPolling) return;
    setNdaPolling(true);
    let attempts = 0;
    const maxAttempts = 40; // 2 minutes at 3s intervals
    const interval = setInterval(async () => {
      attempts++;
      try {
        await loadStatus();
        if (status?.provider_nda_signed) {
          clearInterval(interval);
          setNdaPolling(false);
          setNdaSigningUrl(null);
          toast.success('NDA signed! Loading project files...');
          loadFiles();
          loadExistingQuote();
        }
      } catch { /* ignore poll errors */ }
      if (attempts >= maxAttempts) {
        clearInterval(interval);
        setNdaPolling(false);
      }
    }, 3000);
  };

  const handleUnlock = async () => {
    setCheckingOut(true);
    try {
      const res = await api.providerRFQ.unlockCheckout(rfqId);
      const data = res.data as { already_paid?: boolean; checkout_url?: string; url?: string };
      if (data?.already_paid) {
        toast.info('Payment already on file. Verifying access...');
        try {
          const vRes = await api.providerRFQ.verifyPayment(rfqId);
          const vData = vRes.data as { unlocked?: boolean };
          if (vData?.unlocked) {
            toast.success('Access granted! Loading project files...');
            loadStatus();
          } else {
            toast.info('Payment confirmed. Refreshing status...');
            loadStatus();
          }
        } catch {
          loadStatus();
        }
        setCheckingOut(false);
        return;
      }
      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
      } else if (data?.url) {
        window.location.href = data.url;
      } else {
        toast.error('Payment session created but no redirect URL received. Please contact support.');
      }
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (!err.response) {
        toast.error('Cannot connect to server. Please refresh and try again.');
      } else {
        const detail = err.response?.data?.detail;
        toast.error(detail || `Server error (${err.response?.status}). Please try again.`);
      }
    } finally { setCheckingOut(false); }
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <Loader2 className="h-10 w-10 animate-spin text-blue-600 mx-auto mb-3"/>
        <p className="text-gray-500">Loading project details...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardContent className="pt-6 text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-3"/>
          <p className="text-gray-700 mb-4">{error}</p>
          <Button variant="outline" onClick={() => router.push('/provider/dashboard')}>
            <ArrowLeft className="h-4 w-4 mr-2"/>Back to Dashboard
          </Button>
        </CardContent>
      </Card>
    </div>
  );

  if (!status) return null;

  const isClosed = CLOSED_STATUSES.includes(status.rfq_status || '');

  if (status.has_membership && status.has_dispatch === false) return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="max-w-md w-full">
        <CardContent className="pt-6 text-center">
          <AlertCircle className="h-12 w-12 text-amber-500 mx-auto mb-3"/>
          <p className="text-gray-700 mb-4">This project is not in your invitation list.</p>
          <Button variant="outline" onClick={() => router.push('/provider/dashboard')}>
            <ArrowLeft className="h-4 w-4 mr-2"/>Back to Dashboard
          </Button>
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="sm" onClick={() => router.push('/provider/dashboard')} className="text-gray-500 hover:text-gray-700">
            <ArrowLeft className="h-4 w-4 mr-1"/>Dashboard
          </Button>
          <div className="h-4 w-px bg-gray-300" />
          <h1 className="text-xl font-semibold text-gray-900">Project Invitation</h1>
          {status.unlocked
            ? <Badge className="bg-green-100 text-green-800 border-green-200 ml-auto"><LockOpen className="h-3 w-3 mr-1" />Unlocked</Badge>
            : <Badge variant="outline" className="text-gray-500 ml-auto"><Lock className="h-3 w-3 mr-1" />Locked</Badge>
          }
        </div>

        <div className="space-y-6">
          <TeaserInfoPanel status={status} />

          {!status.unlocked && (
            <LockedCard status={status} onUnlock={handleUnlock} checkingOut={checkingOut} />
          )}

          {status.unlocked && status.nda_required && !status.provider_nda_signed && (
            <Card className="border-amber-200 bg-amber-50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-amber-800">
                  <ShieldAlert className="h-5 w-5"/>Non-Disclosure Agreement Required
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!ndaSigningUrl ? (
                  <div className="text-center py-6">
                    <ShieldAlert className="h-12 w-12 text-amber-500 mx-auto mb-4"/>
                    <h3 className="text-lg font-semibold text-amber-800 mb-2">Sign the NDA to Access Project Files</h3>
                    <p className="text-amber-700 mb-4">This project requires a Non-Disclosure Agreement. Please sign to view full details and submit a quote.</p>
                    <Button
                      onClick={startProviderNdaSigning}
                      disabled={ndaSigning}
                      className="bg-amber-600 hover:bg-amber-700 text-white"
                    >
                      {ndaSigning ? 'Preparing NDA...' : 'Sign NDA Now'}
                    </Button>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-amber-700 mb-3">Complete signing below, then your access to project files will be granted automatically.</p>
                    <iframe
                      src={ndaSigningUrl}
                      className="w-full border border-amber-300 rounded-lg"
                      style={{height: '600px'}}
                      title="Sign NDA"
                      onLoad={() => pollProviderNdaStatus()}
                    />
                    <div className="mt-3 flex justify-center">
                      <Button variant="outline" onClick={pollProviderNdaStatus} disabled={ndaPolling}>
                        {ndaPolling ? 'Checking signature status...' : 'I have signed - Check Status'}
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {status.unlocked && (!status.nda_required || status.provider_nda_signed) && (
            <>
              {status.project_description && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-blue-600"/>Full Project Description
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{status.project_description}</p>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Download className="h-5 w-5 text-blue-600"/>Project Files
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <FilesSection files={files} loading={filesLoading} />
                </CardContent>
              </Card>

              {quotesLoading ? (
                <Card>
                  <CardContent className="pt-6 text-center">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-500 mx-auto mb-2" />
                    <p className="text-sm text-gray-500">Loading quote status...</p>
                  </CardContent>
                </Card>
              ) : existingQuote ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <CheckCircle className="h-5 w-5 text-green-600" />Your Quote
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <SubmittedQuoteCard quote={existingQuote} />
                  </CardContent>
                </Card>
              ) : isClosed ? (
                <Card className="border-gray-200 bg-gray-50">
                  <CardContent className="pt-6 text-center">
                    <Ban className="h-12 w-12 text-gray-400 mx-auto mb-3" />
                    <h3 className="font-semibold text-gray-700 text-lg mb-2">Project No Longer Accepting Quotes</h3>
                    <p className="text-gray-500 text-sm">This project has been closed. No further quotes are being accepted.</p>
                  </CardContent>
                </Card>
              ) : !quoteSubmitted ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Send className="h-5 w-5 text-green-600"/>Submit Your Quote
                    </CardTitle>
                    <CardDescription>Only the first 5 quotes are shown to the customer. Submit early.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <QuoteForm rfqId={rfqId} onSuccess={() => setQuoteSubmitted(true)} />
                  </CardContent>
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
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600"/>
      </div>
    }>
      <ProviderRFQPageInner />
    </Suspense>
  );
}
