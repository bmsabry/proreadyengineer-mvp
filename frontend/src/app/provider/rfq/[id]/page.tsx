'use client';

import { useEffect, useState, useCallback, useRef, Suspense } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import {
  Loader2, AlertCircle, CheckCircle, Download, FileText, Clock,
  Lock, LockOpen, Building2, ShieldAlert, ArrowLeft, CalendarDays, Layers,
  CreditCard, Send, Upload, X, Sparkles, Trophy, Ban, RefreshCw, Mail, Star, Phone,
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
import NdaBadge from '@/components/ui/NdaBadge';

interface UnlockStatus {
  unlocked: boolean;
  has_membership?: boolean;
  has_dispatch?: boolean;
  urgency?: string;
  tollgate_phases?: string[];
  nda_required?: boolean;
  nda_status?: string;
  provider_nda_signed?: boolean;
  provider_has_signed?: boolean;
  quote_accepted?: boolean;
  business_name?: string;
  project_description_preview?: string;
  project_description?: string;
  rfq_status?: string;
  submitted_at?: string;
  is_annual_subscriber?: boolean;
  customer_contact?: { name?: string | null; company?: string | null; email?: string | null; phone?: string | null; state?: string | null } | null;
  contact_locked_reason?: string | null;
}

interface RFQFile {
  id: string;
  original_filename: string;
  presigned_url?: string;
  file_size_bytes?: number;
  inline_text?: string;
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
          <NdaBadge ndaRequired={status.nda_required} ndaStatus={status.nda_status} variant="full" />
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
        <Button onClick={onUnlock} disabled={checkingOut} size="lg" className="w-full bg-primary hover:bg-primary/90 text-white">
          {checkingOut
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin"/>Processing...</>
            : status.is_annual_subscriber
              ? <><CheckCircle className="h-4 w-4 mr-2"/>Unlock — free with your membership</>
              : <><CreditCard className="h-4 w-4 mr-2"/>Unlock for $50 - One-time fee</>}
        </Button>
        <p className="text-xs text-gray-500 text-center">
          {status.is_annual_subscriber
            ? 'Included in your Annual Professional membership — no per-RFQ fee. Only the first 5 quotes are shown to the customer.'
            : 'Secure payment via Stripe. Only the first 5 quotes are shown to the customer.'}
        </p>
      </CardFooter>
    </Card>
  );
}

function FilesSection({ files, loading, rfqId }: { files: RFQFile[]; loading: boolean; rfqId: string }) {
  if (loading) return <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin"/>Loading files...</div>;
  if (!files.length) return <p className="text-sm text-gray-500 italic">No files attached to this project.</p>;
  return (
    <ul className="space-y-2">
      {files.map((f) => (
        <li key={f.id} className="flex items-center justify-between rounded border border-gray-200 bg-gray-50 px-3 py-2">
          <div className="flex items-center gap-2 text-sm text-gray-700">
            <FileText className="h-4 w-4 text-blue-500"/>
            <span>{f.original_filename}</span>
            {f.file_size_bytes && <span className="text-gray-600 text-xs">({fmtBytes(f.file_size_bytes)})</span>}
          </div>
          {f.presigned_url ? (
            <a href={f.presigned_url} target="_blank" rel="noreferrer">
              <Button variant="ghost" size="sm"><Download className="h-4 w-4 mr-1"/>Download</Button>
            </a>
          ) : f.inline_text ? (
            <Button variant="ghost" size="sm" onClick={() => {
              const blob = new Blob([f.inline_text!], { type: 'text/plain' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = f.original_filename || 'project_document.txt';
              a.click();
              URL.revokeObjectURL(url);
            }}><Download className="h-4 w-4 mr-1"/>Download</Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={async () => {
              try {
                const token = localStorage.getItem('access_token');
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/provider/rfqs/${rfqId}/files/${f.id}/download`, {
                  headers: { Authorization: `Bearer ${token}` }
                });
                if (!res.ok) { alert('Download failed: ' + (await res.json()).detail); return; }
                const data = await res.json();
                if (data.download_url) {
                  window.open(data.download_url, '_blank');
                } else if (data.inline_text) {
                  const blob = new Blob([data.inline_text], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = data.filename || f.original_filename || 'document.txt';
                  a.click();
                  URL.revokeObjectURL(url);
                }
              } catch (e) { alert('Download error'); }
            }}><Download className="h-4 w-4 mr-1"/>Download</Button>
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
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = async (file: File) => {
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
      if (result.rough_price_min != null) setMin(String(result.rough_price_min));
      if (result.rough_price_max != null) setMax(String(result.rough_price_max));
      if (result.turnaround_estimate_text) setTurnaround(result.turnaround_estimate_text);
      if (result.assumptions_text) setAssumptions(result.assumptions_text);
      if (result.scope_notes) setScopeNotes(result.scope_notes);
      setExtractedDocKey(result.s3_key);
      setExtractedDocFilename(result.original_filename);
      toast.success('Fields pre-filled from your document. Please review before submitting.');
    } catch (err: unknown) {
      const rawDetailEx = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      let extractErrMsg = 'Failed to extract fields from document. Please fill in manually.';
      if (typeof rawDetailEx === 'string') {
        extractErrMsg = rawDetailEx;
      } else if (Array.isArray(rawDetailEx)) {
        extractErrMsg = (rawDetailEx as Array<{ msg?: string }>).map(d => d.msg || 'Error').join('; ');
      }
      toast.error(extractErrMsg);
      setSelectedFile(null);
    } finally {
      setExtracting(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await processFile(file);
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    // Auto-enable document upload mode on drop
    setUseDocument(true);
    await processFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleClearDocument = () => {
    setSelectedFile(null);
    setExtractedDocKey(null);
    setExtractedDocFilename(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async () => {
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
      const rawDetail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      let errMsg = 'Failed to submit quote.';
      if (typeof rawDetail === 'string') {
        errMsg = rawDetail;
      } else if (Array.isArray(rawDetail)) {
        errMsg = (rawDetail as Array<{ msg?: string; loc?: unknown[] }>)
          .map(d => {
            const field = Array.isArray(d.loc) ? d.loc.filter(l => l !== 'body').join('.') : '';
            return field ? `${field}: ${d.msg || 'invalid'}` : (d.msg || 'Validation error');
          })
          .join('; ');
      }
      toast.error(errMsg);
    } finally { setSubmitting(false); }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-sm text-blue-800">
        <strong>Note:</strong> Quotes are rough, non-binding estimates. A refined final estimate follows direct engagement.
      </div>

      {/* Document upload toggle */}
      <div
        className={`rounded-md border-2 p-4 transition-colors ${
          isDragging
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 bg-gray-50'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
      >
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

        {/* Always-visible drag zone — activates upload mode automatically on drop */}
        {!selectedFile && !useDocument && (
          <div
            className={`mt-3 flex items-center justify-center gap-2 w-full py-3 border-2 border-dashed rounded-md transition-colors ${
              isDragging ? 'border-blue-400 bg-blue-100' : 'border-gray-300'
            }`}
          >
            <Upload className="h-4 w-4 text-gray-600" />
            <span className="text-xs text-gray-600">or drag &amp; drop a file here</span>
          </div>
        )}

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
                  className={`flex items-center justify-center gap-2 w-full py-4 border-2 border-dashed rounded-md cursor-pointer transition-colors ${
                    isDragging
                      ? 'border-blue-400 bg-blue-100'
                      : 'border-blue-300 hover:bg-blue-50'
                  }`}
                >
                  {extracting ? (
                    <><Loader2 className="h-4 w-4 animate-spin text-blue-500" /><span className="text-sm text-blue-600">Analyzing document...</span></>
                  ) : (
                    <div className="flex flex-col items-center gap-1">
                      <Upload className="h-5 w-5 text-blue-500" />
                      <span className="text-sm text-blue-600 font-medium">Drag &amp; drop or click to select</span>
                      <span className="text-xs text-gray-600">PDF, DOCX, or TXT · max 10MB</span>
                    </div>
                  )}
                </label>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-md border border-green-200 bg-green-50 px-3 py-2">
                <div className="flex items-center gap-2">
                  {extracting ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                  ) : (
                    <Sparkles className="h-4 w-4 text-green-500" />
                  )}
                  <span className="text-sm text-gray-700 truncate max-w-[200px]">{selectedFile.name}</span>
                  {!extracting && extractedDocKey && (
                    <Badge className="bg-green-100 text-green-700 text-xs">Fields extracted</Badge>
                  )}
                </div>
                <button type="button" onClick={handleClearDocument} className="text-gray-600 hover:text-gray-600">
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
  const [signingNda, setSigningNda] = useState(false);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [quoteSubmitted, setQuoteSubmitted] = useState(false);
  const [existingQuote, setExistingQuote] = useState<Quote | null>(null);
  const [quotesLoading, setQuotesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ndaPolling, setNdaPolling] = useState(false);
  const [ndaEmailPending, setNdaEmailPending] = useState(false);
  const [showClosedWarning, setShowClosedWarning] = useState(false);

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
      const data = res.data as { files?: Array<{ file_id?: string; id?: string; filename?: string; original_filename?: string; download_url?: string; presigned_url?: string; file_size_bytes?: number; inline_text?: string }> } | Array<{ file_id?: string; id?: string; filename?: string; original_filename?: string; download_url?: string; presigned_url?: string; file_size_bytes?: number; inline_text?: string }>;
      // Backend returns { files: [...] } wrapper object, or may return array directly
      const rawFiles = Array.isArray(data) ? data : ((data as { files?: unknown[] })?.files || []);
      setFiles((rawFiles as Array<{ file_id?: string; id?: string; filename?: string; original_filename?: string; download_url?: string; presigned_url?: string; file_size_bytes?: number; inline_text?: string }>).map((f) => ({
        id: f.file_id || f.id || '',
        original_filename: f.filename || f.original_filename || 'document',
        presigned_url: f.download_url || f.presigned_url,
        file_size_bytes: f.file_size_bytes,
        inline_text: f.inline_text,
      })));
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
      // Always load existing quote status
      loadExistingQuote();
      // Load files if: no NDA required, OR (NDA required AND quote accepted AND NDA signed)
      const canAccessFiles = !status.nda_required || status.provider_nda_signed;
      if (canAccessFiles) {
        loadFiles();
      }
      // Poll for NDA signing only when the RFQ is still OPEN, NDA is required, and not yet
      // signed. A closed/cancelled RFQ has no signing action, so don't prompt or poll.
      const _rfqClosed = CLOSED_STATUSES.includes(status.rfq_status || '');
      if (status.nda_required && !status.provider_nda_signed && !_rfqClosed) {
        startNdaPoll();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.unlocked, status?.provider_nda_signed, status?.quote_accepted]);

  const startNdaPoll = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await api.providerRFQ.getUnlockStatus(rfqId);
        const s = res.data as UnlockStatus;
        setStatus(s);
        if (s?.provider_nda_signed) {
          clearInterval(interval);
          setNdaEmailPending(false);
          loadFiles();
          loadExistingQuote();
        }
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(interval);
  }, [rfqId, loadFiles, loadExistingQuote]);

  const handleProceedAnyway = async () => {
    setShowClosedWarning(false);
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
        } catch { loadStatus(); }
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

  const handleUnlock = () => {
    if (CLOSED_STATUSES.includes(status?.rfq_status || '')) {
      setShowClosedWarning(true);
      return;
    }
    handleProceedAnyway();
  };

  const handleSignNda = async () => {
    if (signingNda) return;  // ignore double-clicks while in flight
    setSigningNda(true);
    try {
      const res = await api.providerRFQ.initiateProviderNda(rfqId);
      const data = res.data as { signing_url?: string; message?: string };
      if (data?.signing_url) {
        window.location.href = data.signing_url;
        return;
      }
      toast.info(data?.message || 'NDA created \u2014 check your email to sign. The customer will be notified to countersign.');
      setNdaEmailPending(true);
      startNdaPoll();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      toast.error(err.response?.data?.detail || err.message || 'Could not start NDA signing.');
    } finally {
      setSigningNda(false);
    }
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
      {showClosedWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-2xl shadow-xl border border-amber-200 max-w-md w-full mx-4 p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                <AlertCircle className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-900 mb-1">RFQ Is Closed</h3>
                <p className="text-sm text-slate-600 leading-relaxed">
                  This RFQ is closed and no longer accepting bids. You can still pay $50 to view
                  the project details for reference, but you will not be able to submit a quote.
                </p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowClosedWarning(false)}
                className="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleProceedAnyway}
                disabled={checkingOut}
                className="px-4 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-xl transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {checkingOut && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Pay to View Anyway
              </button>
            </div>
          </div>
        </div>
      )}
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

          {status.unlocked && (
            <>
              {/* Always show full project description after payment */}
              {status.project_description && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-blue-600" />Full Project Description
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">{status.project_description}</p>
                  </CardContent>
                </Card>
              )}

              {/* ANNUAL PERK: direct customer contact for active provider_annual subscribers. */}
              {status.is_annual_subscriber && status.customer_contact && (
                <Card className="border-emerald-200 bg-emerald-50">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-emerald-900">
                      <Star className="h-5 w-5 text-emerald-600" />Customer Contact
                      <span className="ml-1 text-xs font-medium text-emerald-700 bg-emerald-100 rounded-full px-2 py-0.5">Annual member</span>
                    </CardTitle>
                    <CardDescription className="text-emerald-800">
                      Reach out directly to discuss this project.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid sm:grid-cols-2 gap-3 text-sm">
                      {status.customer_contact.name && (
                        <div><p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Contact</p><p className="text-gray-900">{status.customer_contact.name}</p></div>
                      )}
                      {status.customer_contact.company && (
                        <div className="flex flex-col"><p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Company</p><p className="text-gray-900 inline-flex items-center gap-1"><Building2 className="h-3.5 w-3.5 text-emerald-600" />{status.customer_contact.company}</p></div>
                      )}
                      {status.customer_contact.email && (
                        <div><p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Email</p><a href={`mailto:${status.customer_contact.email}`} className="text-emerald-700 inline-flex items-center gap-1 hover:underline"><Mail className="h-3.5 w-3.5" />{status.customer_contact.email}</a></div>
                      )}
                      {status.customer_contact.phone && (
                        <div><p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Phone</p><a href={`tel:${status.customer_contact.phone}`} className="text-emerald-700 inline-flex items-center gap-1 hover:underline"><Phone className="h-3.5 w-3.5" />{status.customer_contact.phone}</a></div>
                      )}
                      {status.customer_contact.state && (
                        <div><p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">Location</p><p className="text-gray-900">{status.customer_contact.state}</p></div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* ANNUAL PERK gated behind NDA: tell them to sign first. */}
              {status.is_annual_subscriber && status.contact_locked_reason === 'nda_required' && (
                <Card className="border-emerald-200 bg-emerald-50/60">
                  <CardContent className="pt-5">
                    <div className="flex items-start gap-3">
                      <Star className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <h3 className="font-semibold text-emerald-900 mb-1">Customer contact unlocks after the NDA</h3>
                        <p className="text-sm text-emerald-800">As an Annual member you get the customer&apos;s direct contact details &mdash; this RFQ requires a mutual NDA, so sign it above and the contact will appear here once both parties have signed.</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* NDA required + not yet fully signed + RFQ still open: provider must sign to view */}
              {status.nda_required && !status.provider_nda_signed && !isClosed && (
                <Card className="border-amber-200 bg-amber-50">
                  <CardContent className="pt-6">
                    <div className="flex items-start gap-3">
                      <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                      <div>
                        {status.provider_has_signed ? (
                          <>
                            <h3 className="font-semibold text-amber-900 mb-1">You&apos;ve signed &mdash; waiting for the customer to countersign</h3>
                            <p className="text-sm text-amber-800 mb-3">
                              Your signature is recorded. The customer has been notified to countersign the NDA. Once both parties have signed, this page unlocks the full RFQ and files automatically and you can submit a quote.
                            </p>
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={checkingStatus}
                              className="border-amber-400 text-amber-800 hover:bg-amber-100"
                              onClick={async () => { if (checkingStatus) return; setCheckingStatus(true); try { await loadStatus(); } finally { setCheckingStatus(false); } }}
                            >
                              {checkingStatus
                                ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Checking&hellip;</>
                                : <><RefreshCw className="h-3 w-3 mr-1" />Check Status</>}
                            </Button>
                          </>
                        ) : (
                          <>
                            <h3 className="font-semibold text-amber-900 mb-1">Sign the NDA to view this project</h3>
                            <p className="text-sm text-amber-800 mb-3">
                              This RFQ requires a mutual Non-Disclosure Agreement. Sign it to unlock the full project description and files. The customer will be notified to countersign; once both parties sign, you get full access and can submit a quote.
                            </p>
                            <p className="text-xs text-amber-700 mb-3">After both signatures, this page refreshes automatically to show the full RFQ and files.</p>
                          {ndaEmailPending && (
                            <div className="mb-3 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-3">
                              <ShieldAlert className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
                              <div className="text-xs text-blue-800">
                                <p className="font-semibold text-blue-900">Check your email to sign the NDA</p>
                                <p className="mt-0.5">We&apos;ve emailed you a secure signing link from SignWell. Open it and sign to continue &mdash; the customer is then notified to countersign. This page unlocks automatically once both parties sign.</p>
                                <p className="mt-1 text-blue-600">Didn&apos;t get it? Use <span className="font-semibold">Resend signing email</span>. Already signed? Click <span className="font-semibold">Check Status</span>.</p>
                              </div>
                            </div>
                          )}
                            {signingNda && (
                              <div className="mb-2 flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-100/70 px-3 py-2 text-xs text-amber-900">
                                <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
                                <span>Setting up your NDA with SignWell&hellip; this can take a few seconds. Please don&apos;t close or click again.</span>
                              </div>
                            )}
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                disabled={signingNda || checkingStatus}
                                className={ndaEmailPending ? "bg-amber-300 text-white hover:bg-amber-400" : "bg-amber-600 text-white hover:bg-amber-700"}
                                onClick={handleSignNda}
                              >
                                {signingNda
                                  ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Working&hellip;</>
                                  : <><ShieldAlert className="h-3 w-3 mr-1" />{ndaEmailPending ? 'Resend signing email' : 'Sign NDA'}</>}
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={signingNda || checkingStatus}
                                className="border-amber-400 text-amber-800 hover:bg-amber-100"
                                onClick={async () => { if (checkingStatus) return; setCheckingStatus(true); try { await loadStatus(); } finally { setCheckingStatus(false); } }}
                              >
                                {checkingStatus
                                  ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Checking&hellip;</>
                                  : <><RefreshCw className="h-3 w-3 mr-1" />Check Status</>}
                              </Button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Files section: show when no NDA required OR (quote accepted AND NDA signed) */}
              {(!status.nda_required || status.provider_nda_signed) && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Download className="h-5 w-5 text-blue-600" />Project Files
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <FilesSection files={files} loading={filesLoading} rfqId={rfqId} />
                  </CardContent>
                </Card>
              )}

              {/* NDA required but quote NOT yet accepted: show documents notice */}
              {status.nda_required && !status.quote_accepted && (
                <Card className="border-blue-100 bg-blue-50">
                  <CardContent className="pt-5">
                    <div className="flex items-start gap-3">
                      <ShieldAlert className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <h3 className="font-semibold text-blue-900 mb-1">Project Documents</h3>
                        <p className="text-sm text-blue-700">
                          This project requires an NDA. Uploaded documents will be available to you after the customer accepts your quote and both parties sign the Non-Disclosure Agreement.
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Quote section: always visible after unlock */}
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
                    <Ban className="h-12 w-12 text-gray-600 mx-auto mb-3" />
                    <h3 className="font-semibold text-gray-700 text-lg mb-2">Project No Longer Accepting Quotes</h3>
                    <p className="text-gray-500 text-sm">This project has been closed. No further quotes are being accepted.</p>
                  </CardContent>
                </Card>
              ) : !quoteSubmitted ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Send className="h-5 w-5 text-green-600" />Submit Your Quote
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
                    <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3" />
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
