"use client";
export const dynamic = "force-dynamic";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { PipelineInfo } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertCircle, CheckCircle, Database, Search, RefreshCw, Activity, Zap, Mail, FileSignature } from "lucide-react";

interface DatabaseStatus {
  connection_ok: boolean;
  provider_count: number;
  providers_with_embeddings: number;
  embedding_coverage_pct: number;
  sample_provider: string | null;
  last_embedded_name: string | null;
  last_embedded_at: string | null;
  error?: string;
}

interface ApiConfigInfo {
  openai_configured: boolean;
  openai_base_url: string | null;
  embedding_model: string;
  llm_model: string;
  llm1_configured: boolean;
  llm1_base_url: string | null;
  llm1_model: string;
  llm3_configured: boolean;
  llm3_base_url: string | null;
  llm3_model: string | null;
}

interface DebugInfo {
  database: DatabaseStatus;
  api_config: ApiConfigInfo;
  last_error: {
    error: string | null;
    timestamp: string | null;
    query: string | null;
  } | null;
}

interface TestEmailResult {
  success: boolean;
  message_id: string | null;
  error: string | null;
  api_key_present: boolean;
  api_key_prefix: string;
  from_address: string;
  to_address: string;
  resend_status_code: number | null;
}

interface ResendDomainResult {
  success: boolean;
  domain_verified: boolean;
  configured_domain: string;
  from_address: string;
  error: string | null;
  tip: string | null;
  domains: Array<{ name: string; status: string }>;
}

interface TestNDAResult {
  success: boolean;
  document_id: string | null;
  error: string | null;
  customer_signing_url: string | null;
  provider_signing_url: string | null;
  signwell_status: string | null;
  created_at: string | null;
}

interface NDAStatusResult {
  success: boolean;
  error: string | null;
  document_id: string | null;
  document_status: string | null;
  customer_signed: boolean;
  customer_signed_at: string | null;
  provider_signed: boolean;
  provider_signed_at: string | null;
  fully_signed: boolean;
  s3_saved: boolean;
  s3_key_checked: string | null;
  s3_download_url: string | null;
}

interface NDAVoidResult {
  success: boolean;
  error: string | null;
  message: string | null;
  document_id: string | null;
}

interface StripeTestResult {
  status: 'success' | 'error' | 'not_configured';
  account_id?: string;
  account_name?: string;
  test_payment_intent_id?: string;
  mode?: 'test' | 'live';
  message?: string;
  error?: string;
}

interface RfqUnlockTestStep {
  step: string;
  status: string;
  message: string;
}

interface RfqUnlockTestResult {
  steps: RfqUnlockTestStep[];
  status: string;
  ready: boolean;
}

interface PaypalTestResult {
  success?: boolean;
  mode?: string;
  app_id?: string;
  token_type?: string;
  error?: string;
}

function StatusBadge({ ok, label }: { ok: boolean; label?: string }) {
  return ok ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 border border-green-300">
      {label ?? '✓ OK'}
    </span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 border border-red-300">
      {label ?? '✗ Error'}
    </span>
  );
}


function PipelineBadge({ pipeline }: { pipeline: string | undefined }) {
  if (!pipeline) return null;
  const colors: Record<string, string> = {
    ai_vector: "bg-green-100 text-green-800 border-green-300",
    keyword_fallback: "bg-yellow-100 text-yellow-800 border-yellow-300",
    no_api_key: "bg-red-100 text-red-800 border-red-300",
  };
  const cls = colors[pipeline] ?? "bg-gray-100 text-gray-800 border-gray-300";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>
      {pipeline}
    </span>
  );
}

function AIPipelineBanner({ pipeline }: { pipeline: PipelineInfo }) {
  const isAI = pipeline.pipeline_used === "ai_vector";
  const isKeyword = pipeline.pipeline_used === "keyword_fallback";
  const bannerClass = isAI
    ? "bg-green-50 border-green-200"
    : isKeyword
    ? "bg-yellow-50 border-yellow-200"
    : "bg-red-50 border-red-200";
  return (
    <div className={`border rounded-lg p-4 ${bannerClass} space-y-3`}>
      <div className="flex items-center gap-2">
        <Zap className="h-4 w-4" />
        <span className="font-semibold text-sm">Pipeline Result</span>
        <PipelineBadge pipeline={pipeline.pipeline_used} />
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
        <div><span className="font-medium">API Key Source:</span> {pipeline.api_key_source ?? "none"}</div>
        <div><span className="font-medium">LLM Called:</span> {pipeline.llm_called ? "Yes" : "No"}</div>
        <div><span className="font-medium">LLM Response:</span> {pipeline.llm_response_received ? "Yes" : "No"}</div>
        <div><span className="font-medium">LLM Model:</span> {pipeline.llm_model ?? "n/a"}</div>
        <div><span className="font-medium">Embedding Called:</span> {pipeline.embedding_called ? "Yes" : "No"}</div>
        <div><span className="font-medium">Embedding Dims:</span> {pipeline.embedding_dims ?? "n/a"}</div>
        <div><span className="font-medium">Inferred Specialty:</span> {pipeline.inferred_specialty ?? "n/a"}</div>
        <div><span className="font-medium">Keywords:</span> {(pipeline.inferred_keywords ?? []).join(", ") || "n/a"}</div>
      </div>
      {pipeline.fallback_reason && (
        <div className="text-xs text-yellow-700">
          <span className="font-medium">Fallback Reason:</span> {pipeline.fallback_reason}
        </div>
      )}


    </div>
  );
}

interface NDAVoidResult {
  success: boolean;
  error: string | null;
  message: string | null;
  document_id: string | null;
}


// ---- Cron Health section ---------------------------------------------------
// Surfaces /internal/cron/status so admins can see at a glance whether the
// Render Cron Job is firing (primary) or only the asyncio fallback is
// carrying. Most RFQ "second batch didn't send" reports trace back to the
// Render cron service never being provisioned — this card makes that visible.

interface CronStatus {
  last_run: string | null;
  minutes_ago: number | null;
  last_trigger_source: string | null;
  last_run_http_cron: string | null;
  last_run_http_cron_minutes_ago: number | null;
  last_run_asyncio_loop: string | null;
  last_run_asyncio_loop_minutes_ago: number | null;
  last_result: string | null;
  status: 'healthy' | 'degraded' | 'stale' | 'unknown';
}

function CronHealthSection() {
  const [cron, setCron] = useState<CronStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [firing, setFiring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.admin.cronStatus();
      setCron(r.data as CronStatus);
    } catch (e) {
      setError((e as Error).message || 'request failed');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  async function fireNow() {
    if (!confirm('Run the RFQ dispatch poll right now? Safe — the interval guard prevents duplicate batches.')) return;
    setFiring(true);
    try {
      await api.admin.cronManualFire();
      await load();
    } catch (e) {
      alert('Manual fire failed: ' + ((e as Error).message || ''));
    } finally {
      setFiring(false);
    }
  }

  const statusColor = cron?.status === 'healthy' ? 'emerald'
    : cron?.status === 'degraded' ? 'amber'
    : cron?.status === 'stale' ? 'red' : 'slate';

  function relTime(min: number | null) {
    if (min === null || min === undefined) return 'never';
    if (min < 1) return 'just now';
    if (min < 60) return `${min}m ago`;
    const h = Math.floor(min / 60);
    return `${h}h ${min % 60}m ago`;
  }

  let resultSummary: { dispatched: number; skipped: number; reasons: string[] } | null = null;
  if (cron?.last_result) {
    try {
      const r = JSON.parse(cron.last_result) as { dispatched?: Array<{ rfq_id: string; providers_emailed: number }>; skipped?: Array<{ rfq_id: string; reason: string }> };
      const dispatched = (r.dispatched || []).length;
      const skipped = (r.skipped || []).length;
      const reasons = Array.from(new Set((r.skipped || []).map(s => s.reason).slice(0, 5)));
      resultSummary = { dispatched, skipped, reasons };
    } catch { /* ignore */ }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          RFQ Dispatch Cron Health
          {cron && (
            <span className={`ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-${statusColor}-100 text-${statusColor}-800`}>
              {cron.status}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-slate-500">
            Render Cron Job (primary, every 15 min) and asyncio backup (every 5 min) both call
            <code className="mx-1">/internal/cron/dispatch-rfq-batches</code>. Card auto-refreshes every 30s.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
            <Button variant="outline" size="sm" onClick={fireNow} disabled={firing}>
              <Zap className={`h-3 w-3 mr-1 ${firing ? 'animate-pulse' : ''}`} /> Fire now
            </Button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-xs">Could not load: {error}</div>
        )}

        {cron && (
          <>
            {cron.status === 'stale' && (
              <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-800 text-xs">
                <strong>STALE.</strong> No dispatch poll in over 20 minutes. Even the asyncio backup loop has not run. The API service may be down or the backup loop crashed at boot — check Render service logs.
              </div>
            )}
            {cron.status === 'degraded' && (
              <div className="p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-900 text-xs">
                <strong>DEGRADED.</strong> The asyncio backup loop is firing but the Render Cron Job has not called the endpoint in over an hour. The Cron Job service is likely not provisioned. Open Render dashboard → Engineering_Services_Directory project → create <code>proreadyengineer-rfq-cron</code> via Blueprint sync of <code>render.yaml</code>, or create it manually with schedule <code>*/15 * * * *</code>.
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 rounded-md border border-slate-200 bg-slate-50">
                <div className="text-slate-500">Last run (any trigger)</div>
                <div className="font-semibold text-slate-900 mt-0.5">{relTime(cron.minutes_ago)}</div>
                <div className="text-slate-400 mt-0.5">{cron.last_trigger_source || '—'}</div>
              </div>
              <div className="p-3 rounded-md border border-slate-200 bg-slate-50">
                <div className="text-slate-500">Render Cron Job (primary)</div>
                <div className="font-semibold text-slate-900 mt-0.5">{relTime(cron.last_run_http_cron_minutes_ago)}</div>
                <div className="text-slate-400 mt-0.5">expected ≤ 15 min</div>
              </div>
              <div className="p-3 rounded-md border border-slate-200 bg-slate-50">
                <div className="text-slate-500">Asyncio backup</div>
                <div className="font-semibold text-slate-900 mt-0.5">{relTime(cron.last_run_asyncio_loop_minutes_ago)}</div>
                <div className="text-slate-400 mt-0.5">expected ≤ 5 min</div>
              </div>
            </div>

            {resultSummary && (
              <div className="p-3 rounded-md border border-slate-200 bg-white text-xs">
                <div className="font-medium text-slate-800 mb-1">Last poll outcome</div>
                <div className="text-slate-600">Dispatched: <strong className="text-slate-900">{resultSummary.dispatched}</strong> · Skipped: <strong className="text-slate-900">{resultSummary.skipped}</strong></div>
                {resultSummary.reasons.length > 0 && (
                  <div className="text-slate-500 mt-1">Skip reasons: {resultSummary.reasons.join(', ')}</div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ---- Email Failures section ------------------------------------------------
// Lists every broken email (sync send-error or async Resend bounce) with a
// "Mark resolved" button. Pulled live from /admin/email-failures.

interface EmailFailureRow {
  id: string;
  to_email: string;
  subject: string | null;
  source: string;
  error_code: number | null;
  error_message: string | null;
  resend_email_id: string | null;
  resolved: boolean;
  resolved_at: string | null;
  created_at: string | null;
}

function sourceLabel(src: string): string {
  switch (src) {
    case 'sync_api_error': return 'Send error (Resend API)';
    case 'sync_smtp_error': return 'Send error (SMTP)';
    case 'sync_no_provider': return 'No transport configured';
    case 'webhook_bounced': return 'Bounced (Resend webhook)';
    case 'webhook_complained': return 'Complaint (Resend webhook)';
    case 'webhook_delivery_delayed': return 'Delivery delayed (Resend)';
    case 'webhook_failed': return 'Failed (Resend webhook)';
    default: return src;
  }
}

function EmailFailuresSection() {
  const [rows, setRows] = useState<EmailFailureRow[]>([]);
  const [total, setTotal] = useState(0);
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Use api.admin (axios apiClient) so the 401 auto-refresh interceptor fires
  // when the access token expires. Raw fetch() bypasses it and surfaces 401.
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.admin.listEmailFailures(unresolvedOnly, 100, 0);
      setRows((r.data.items ?? []) as EmailFailureRow[]);
      setTotal(r.data.total ?? 0);
    } catch (e) {
      const msg = (e as { response?: { status?: number }; message?: string })?.response?.status
        ? `HTTP ${(e as { response: { status: number } }).response.status}`
        : ((e as Error).message || 'request failed');
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [unresolvedOnly]);

  useEffect(() => { load(); }, [load]);

  async function markResolved(id: string) {
    setBusyId(id);
    try {
      await api.admin.resolveEmailFailure(id);
      await load();
    } catch (e) {
      alert('Could not mark resolved: ' + ((e as Error).message || 'request failed'));
    } finally {
      setBusyId(null);
    }
  }

  async function dismiss(id: string) {
    if (!confirm('Permanently delete this failure record?')) return;
    setBusyId(id);
    try {
      await api.admin.deleteEmailFailure(id);
      await load();
    } catch (e) {
      alert('Could not delete: ' + ((e as Error).message || 'request failed'));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-5 w-5" />
          Broken / Bounced Emails
          {rows.filter(r => !r.resolved).length > 0 && (
            <span className="ml-2 inline-flex items-center justify-center min-w-[24px] h-6 px-2 rounded-full bg-red-600 text-white text-xs font-bold">
              {rows.filter(r => !r.resolved).length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <p className="text-sm text-muted-foreground">
            Every email that failed to deliver is listed here, with the time it was reported. Sync errors are captured at send time; bounces from Resend arrive via webhook (configure <code>/api/v1/webhooks/resend</code> in your Resend dashboard).
          </p>
          <div className="flex items-center gap-2">
            <label className="text-xs flex items-center gap-1">
              <input
                type="checkbox"
                checked={unresolvedOnly}
                onChange={(e) => setUnresolvedOnly(e.target.checked)}
              />
              Unresolved only
            </label>
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>

        {error && (
          <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
            Could not load: {error}
          </div>
        )}

        {!loading && rows.length === 0 && !error && (
          <div className="p-4 rounded-md bg-green-50 border border-green-200 text-sm text-green-800 flex items-center gap-2">
            <CheckCircle className="h-4 w-4" /> No broken emails — all good.
          </div>
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto -mx-2">
            <table className="w-full text-xs border-separate border-spacing-0">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="px-2 py-1 font-medium">Reported</th>
                  <th className="px-2 py-1 font-medium">Recipient</th>
                  <th className="px-2 py-1 font-medium">Subject</th>
                  <th className="px-2 py-1 font-medium">Source</th>
                  <th className="px-2 py-1 font-medium">Error</th>
                  <th className="px-2 py-1 font-medium">Status</th>
                  <th className="px-2 py-1 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100 align-top">
                    <td className="px-2 py-2 text-slate-600 whitespace-nowrap">
                      {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-2 py-2 font-mono break-all">{r.to_email}</td>
                    <td className="px-2 py-2 max-w-[260px] truncate" title={r.subject ?? ''}>
                      {r.subject || <span className="text-slate-400">(none)</span>}
                    </td>
                    <td className="px-2 py-2">{sourceLabel(r.source)}{r.error_code != null && <span className="text-slate-400"> ({r.error_code})</span>}</td>
                    <td className="px-2 py-2 text-slate-700 max-w-[300px] truncate" title={r.error_message ?? ''}>
                      {r.error_message || <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-2 py-2">
                      {r.resolved ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700">
                          <CheckCircle className="h-3 w-3" /> Resolved
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-700">
                          <AlertCircle className="h-3 w-3" /> Unresolved
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right whitespace-nowrap">
                      {!r.resolved && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="mr-1"
                          disabled={busyId === r.id}
                          onClick={() => markResolved(r.id)}
                        >
                          Mark resolved
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === r.id}
                        onClick={() => dismiss(r.id)}
                      >
                        Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-400 mt-2">
              Showing {rows.length} of {total}.{' '}
              Email-per-bounce alerts are sent to the admin address; configure <code>ADMIN_EMAIL</code> in Settings to change it.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface EmailAuthCheck { status: string; record?: string | null; detail: string; policy?: string | null; rua?: string | null; selector?: string }
interface EmailAuthResult { domain: string; send_domain?: string; from_address?: string; checks: { spf: EmailAuthCheck; dkim: EmailAuthCheck; dmarc: EmailAuthCheck }; summary: { overall: string; message: string } }

function statusPill(status: string) {
  const map: Record<string, string> = {
    pass: "bg-green-100 text-green-800 border-green-200",
    warn: "bg-amber-100 text-amber-800 border-amber-200",
    fail: "bg-red-100 text-red-800 border-red-200",
  };
  const label: Record<string, string> = { pass: "OK", warn: "Review", fail: "Action needed" };
  return <span className={`text-xs font-medium px-2 py-0.5 rounded border ${map[status] || "bg-slate-100 text-slate-700 border-slate-200"}`}>{label[status] || status}</span>;
}

function EmailAuthRow({ title, check }: { title: string; check: EmailAuthCheck }) {
  return (
    <div className="border rounded-md p-3 space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-medium text-sm">{title}</span>
        {statusPill(check.status)}
      </div>
      <p className="text-sm text-muted-foreground">{check.detail}</p>
      {check.record && <p className="text-xs font-mono text-slate-500 break-all">{check.record}</p>}
    </div>
  );
}

function EmailAuthSection() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<EmailAuthResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runCheck = async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.admin.emailAuth();
      setResult(r.data as EmailAuthResult);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e?.message ?? "Check failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-5 w-5" />
          Email Authentication
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-muted-foreground">
          Live SPF, DKIM, and DMARC posture for your sending domain. DMARC tells inbox providers what to do with mail that fails authentication (forged/spoofed mail): <code>none</code> = monitor only, <code>quarantine</code> = send to spam, <code>reject</code> = block. Aggregate reports are emailed to the <code>rua</code> address.
        </p>
        <Button onClick={runCheck} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Checking..." : "Check now"}
        </Button>
        {error && (
          <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-md">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />{error}
          </div>
        )}
        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              {statusPill(result.summary.overall)}
              <span>{result.summary.message}</span>
              <span className="text-muted-foreground">({result.domain}{result.send_domain && result.send_domain !== result.domain ? ` · sending via ${result.send_domain}` : ""})</span>
            </div>
            <EmailAuthRow title="SPF (authorised senders)" check={result.checks.spf} />
            <EmailAuthRow title="DKIM (resend selector)" check={result.checks.dkim} />
            <EmailAuthRow title={`DMARC${result.checks.dmarc.policy ? ` — policy: ${result.checks.dmarc.policy}` : ""}`} check={result.checks.dmarc} />
            {result.checks.dmarc.rua && (
              <p className="text-xs text-muted-foreground">DMARC reports are sent to <code>{result.checks.dmarc.rua.replace("mailto:", "")}</code>.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DebuggingPage() {
  const [testQuery, setTestQuery] = useState("gas turbine combustion analysis");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<{ pipeline: PipelineInfo | null; count: number } | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<DebugInfo | null>(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);

  // Email test state
  const [emailTo, setEmailTo] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);
  const [emailResult, setEmailResult] = useState<TestEmailResult | null>(null);

  const [domainCheckLoading, setDomainCheckLoading] = useState(false);
  const [domainCheckResult, setDomainCheckResult] = useState<ResendDomainResult | null>(null);
  const [ndaCustomerName, setNdaCustomerName] = useState('');
  const [ndaCustomerEmail, setNdaCustomerEmail] = useState('');
  const [ndaProviderName, setNdaProviderName] = useState('');
  const [ndaProviderEmail, setNdaProviderEmail] = useState('');
  const [signwellTestLoading, setSignwellTestLoading] = useState(false);
  const [signwellTestResult, setSignwellTestResult] = useState<any | null>(null);
  const [ndaLoading, setNdaLoading] = useState(false);
  const [ndaResult, setNdaResult] = useState<TestNDAResult | null>(null);
  const [ndaStatusLoading, setNdaStatusLoading] = useState(false);
  const [ndaStatusResult, setNdaStatusResult] = useState<NDAStatusResult | null>(null);
  const [ndaVoidLoading, setNdaVoidLoading] = useState(false);
  const [ndaVoidResult, setNdaVoidResult] = useState<NDAVoidResult | null>(null);
  // Stripe test state
  const [stripeLoading, setStripeLoading] = useState(false);
  const [stripeResult, setStripeResult] = useState<StripeTestResult | null>(null);
  const [rfqUnlockLoading, setRfqUnlockLoading] = useState(false);
  const [rfqUnlockResult, setRfqUnlockResult] = useState<RfqUnlockTestResult | null>(null);
  const [paypalLoading, setPaypalLoading] = useState(false);
  const [paypalResult, setPaypalResult] = useState<PaypalTestResult | null>(null);
  const [llmPrompt, setLlmPrompt] = useState('In one sentence, what is gas turbine combustion?');
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmResult, setLlmResult] = useState<any | null>(null);
  const [docLlmPrompt, setDocLlmPrompt] = useState('Summarise the following engineering document in two sentences.');
  const [docLlmLoading, setDocLlmLoading] = useState(false);
  const [docLlmResult, setDocLlmResult] = useState<any | null>(null);
  const [chatLlmPrompt, setChatLlmPrompt] = useState('Reply with a one-sentence friendly greeting for a help chatbot.');
  const [chatLlmLoading, setChatLlmLoading] = useState(false);
  const [chatLlmResult, setChatLlmResult] = useState<any | null>(null);



  const testSignwellConnection = async () => {
    setSignwellTestLoading(true);
    setSignwellTestResult(null);
    try {
      const r = await api.admin.testSignwellConnection();
      setSignwellTestResult(r.data);
    } catch (e: any) {
      setSignwellTestResult({ success: false, error: e.response?.data?.detail ?? e.message ?? 'Request failed' });
    } finally {
      setSignwellTestLoading(false);
    }
  };

  const sendTestNDA = async () => {
    if (!ndaCustomerName.trim() || !ndaCustomerEmail.trim() || !ndaProviderName.trim() || !ndaProviderEmail.trim()) return;
    setNdaLoading(true); setNdaResult(null); setNdaStatusResult(null); setNdaVoidResult(null);
    try {
      const r = await api.admin.testNda(ndaCustomerName.trim(), ndaCustomerEmail.trim(), ndaProviderName.trim(), ndaProviderEmail.trim());
      setNdaResult(r.data as TestNDAResult);
    } catch (err: unknown) {
      const e = err as { message?: string; response?: { data?: { detail?: string } } };
      setNdaResult({ success: false, document_id: null, error: e.response?.data?.detail ?? e.message ?? 'Request failed', customer_signing_url: null, provider_signing_url: null, signwell_status: null, created_at: null });
    } finally { setNdaLoading(false); }
  };

  const checkNDAStatus = async () => {
    const docId = ndaResult?.document_id;
    if (!docId) return;
    setNdaStatusLoading(true); setNdaStatusResult(null);
    try {
      const r = await api.admin.testNdaStatus(docId);
      setNdaStatusResult(r.data as NDAStatusResult);
    } catch (err: unknown) {
      const e = err as { message?: string };
      setNdaStatusResult({ success: false, error: e.message ?? 'Request failed', document_id: docId, document_status: null, customer_signed: false, customer_signed_at: null, provider_signed: false, provider_signed_at: null, fully_signed: false, s3_saved: false, s3_key_checked: null, s3_download_url: null });
    } finally { setNdaStatusLoading(false); }
  };

  const voidTestNDA = async () => {
    const docId = ndaResult?.document_id;
    if (!docId) return;
    if (!window.confirm('Void document ' + docId + '? This cannot be undone.')) return;
    setNdaVoidLoading(true); setNdaVoidResult(null);
    try {
      const r = await api.admin.testNdaVoid(docId);
      setNdaVoidResult(r.data as NDAVoidResult);
    } catch (err: unknown) {
      const e = err as { message?: string };
      setNdaVoidResult({ success: false, error: e.message ?? 'Request failed', message: null, document_id: docId });
    } finally { setNdaVoidLoading(false); }
  };

  const testLlm = async () => {
    setLlmLoading(true);
    setLlmResult(null);
    try {
      const r = await api.admin.testLlm(llmPrompt.trim() || 'In one sentence, what is gas turbine combustion?');
      setLlmResult(r.data);
    } catch (err: any) {
      setLlmResult({ success: false, error: err?.message || 'Unknown error' });
    } finally {
      setLlmLoading(false);
    }
  };

  const testDocLlm = async () => {
    setDocLlmLoading(true);
    setDocLlmResult(null);
    try {
      const r = await api.admin.testDocLlm(docLlmPrompt.trim() || 'Summarise the following engineering document in two sentences.');
      setDocLlmResult(r.data);
    } catch (err: any) {
      setDocLlmResult({ success: false, error: err?.message || 'Unknown error' });
    } finally {
      setDocLlmLoading(false);
    }
  };

  const testChatLlm = async () => {
    setChatLlmLoading(true);
    setChatLlmResult(null);
    try {
      const r = await api.admin.testChatLlm(chatLlmPrompt.trim() || 'Reply with a one-sentence friendly greeting for a help chatbot.');
      setChatLlmResult(r.data);
    } catch (err: any) {
      setChatLlmResult({ success: false, error: err?.message || 'Unknown error' });
    } finally {
      setChatLlmLoading(false);
    }
  };

  const testStripeConnection = async () => {
    setStripeLoading(true);
    setStripeResult(null);
    try {
      const r = await api.admin.testStripeConnection();
      setStripeResult(r.data as StripeTestResult);
    } catch (e: any) {
      setStripeResult({ status: 'error', error: e.response?.data?.detail ?? e.message ?? 'Request failed' });
    } finally {
      setStripeLoading(false);
    }
  };

  const testRfqUnlockConfig = async () => {
    setRfqUnlockLoading(true);
    setRfqUnlockResult(null);
    try {
      const r = await api.admin.testRfqUnlockConfig();
      setRfqUnlockResult(r.data as RfqUnlockTestResult);
    } catch (e: any) {
      setRfqUnlockResult({
        steps: [],
        status: 'error',
        ready: false,
      });
    } finally {
      setRfqUnlockLoading(false);
    }
  };

  const testPaypalConnection = async () => {
    setPaypalLoading(true);
    setPaypalResult(null);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const r = await api.admin.testPaypalConnection();
      setPaypalResult(r.data as PaypalTestResult);
    } catch (e: unknown) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const err = e as any;
      setPaypalResult({ success: false, error: err?.response?.data?.detail ?? err?.message ?? 'Request failed' });
    } finally {
      setPaypalLoading(false);
    }
  };

  const checkResendDomain = async () => {
    setDomainCheckLoading(true);
    setDomainCheckResult(null);
    try {
      const response = await api.admin.checkResendDomains();
      setDomainCheckResult(response.data as ResendDomainResult);
    } catch (err: unknown) {
      const e = err as { message?: string };
      setDomainCheckResult({
        success: false,
        error: e.message ?? 'Request failed',
        domains: [],
        configured_domain: '',
        from_address: '',
        domain_verified: false,
        tip: null,
      });
    } finally {
      setDomainCheckLoading(false);
    }
  };

  const sendTestEmail = async () => {
    if (!emailTo.trim()) return;
    setEmailLoading(true);
    setEmailResult(null);
    try {
      const response = await api.admin.testEmail(emailTo.trim());
      const data: TestEmailResult = response.data;
      setEmailResult(data);
    } catch (err: unknown) {
      const e = err as { message?: string; response?: { data?: { detail?: string } } };
      setEmailResult({
        success: false,
        message_id: null,
        error: e.response?.data?.detail ?? e.message ?? "Request failed",
        api_key_present: false,
        api_key_prefix: "",
        from_address: "",
        to_address: emailTo,
        resend_status_code: null,
      });
    } finally {
      setEmailLoading(false);
    }
  };

  const loadDebugInfo = useCallback(async () => {
    setDebugLoading(true);
    setDebugError(null);
    try {
      const response = await api.search.debug();
      const raw = (response.data ?? {}) as Record<string, unknown>;
      const db = (raw.database ?? {}) as Record<string, unknown>;
      const apiCfg = (raw.api_config ?? {}) as Record<string, unknown>;
      const normalized: DebugInfo = {
        database: {
          connection_ok: Boolean(db.connection_ok),
          provider_count: Number(db.provider_count ?? 0),
          providers_with_embeddings: Number(db.providers_with_embeddings ?? 0),
          embedding_coverage_pct: Number(db.embedding_coverage_pct ?? 0),
          sample_provider: db.sample_provider != null ? String(db.sample_provider) : null,
          last_embedded_name: db.last_embedded_name != null ? String(db.last_embedded_name) : null,
          last_embedded_at: db.last_embedded_at != null ? String(db.last_embedded_at) : null,
          error: db.error != null ? String(db.error) : undefined,
        },
        api_config: {
          openai_configured: Boolean(apiCfg.openai_configured),
          openai_base_url: apiCfg.openai_base_url != null ? String(apiCfg.openai_base_url) : null,
          embedding_model: String(apiCfg.embedding_model ?? ""),
          llm_model: String(apiCfg.llm_model ?? ""),
          llm1_configured: Boolean(apiCfg.llm1_configured),
          llm1_base_url: apiCfg.llm1_base_url != null ? String(apiCfg.llm1_base_url) : null,
          llm1_model: String(apiCfg.llm1_model ?? ""),
          llm3_configured: Boolean(apiCfg.llm3_configured),
          llm3_base_url: apiCfg.llm3_base_url != null ? String(apiCfg.llm3_base_url) : null,
          llm3_model: apiCfg.llm3_model != null ? String(apiCfg.llm3_model) : null,
        },
        last_error: (raw as any).last_error && (raw as any).last_error.error != null ? (raw as any).last_error : null,
      };
      setDebugInfo(normalized);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setDebugError(e.response?.data?.detail ?? e.message ?? "Failed to load debug info");
    } finally {
      setDebugLoading(false);
    }
  }, []);

  useEffect(() => { loadDebugInfo(); }, [loadDebugInfo]);

  const runTestSearch = async () => {
    if (!testQuery.trim()) return;
    setSearchLoading(true);
    setSearchResult(null);
    setSearchError(null);
    try {
      const response = await api.search.query({ query: testQuery });
      const data = (response.data as unknown as Record<string, unknown>) ?? {};
      const results = (data.results ?? []) as unknown[];
      const pipeline = (data.pipeline_info ?? null) as PipelineInfo | null;
      setSearchResult({ pipeline, count: results.length });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setSearchError(e.response?.data?.detail ?? e.message ?? "Search failed");
    } finally {
      setSearchLoading(false);
    }
  };
  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6" />
            System Debugging
          </h1>
          <p className="text-muted-foreground text-sm mt-1">Live pipeline testing and system diagnostics</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadDebugInfo} disabled={debugLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${debugLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <CronHealthSection />

      <EmailFailuresSection />

      <EmailAuthSection />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Live Search Pipeline Test
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              value={testQuery}
              onChange={(e) => setTestQuery(e.target.value)}
              placeholder="Enter test search query..."
              className="flex-1"
              onKeyDown={(e) => { if (e.key === "Enter") runTestSearch(); }}
            />
            <Button onClick={runTestSearch} disabled={searchLoading}>
              <Search className="h-4 w-4 mr-2" />
              {searchLoading ? "Running..." : "Run Test Search"}
            </Button>
          </div>
          {searchError && (
            <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-md text-sm">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              {searchError}
            </div>
          )}
          {searchResult && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span>Search completed: <strong>{searchResult.count}</strong> result{searchResult.count !== 1 ? "s" : ""} returned</span>
              </div>
              {searchResult.pipeline ? (
                <AIPipelineBanner pipeline={searchResult.pipeline} />
              ) : (
                <p className="text-sm text-muted-foreground">No pipeline info returned.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Database className="h-5 w-5" />
          System Debug Info
        </h2>
        {debugError && (
          <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-md text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            {debugError}
          </div>
        )}
        {debugLoading && !debugInfo && (
          <p className="text-sm text-muted-foreground">Loading debug info...</p>
        )}
        {debugInfo && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Database className="h-4 w-4" />
                  Database Status
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Connection</span>
                  <StatusBadge ok={debugInfo.database.connection_ok} />
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Provider Count</span>
                  <span className="font-medium">{debugInfo.database.provider_count.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">With Embeddings</span>
                  <span className="font-medium">{debugInfo.database.providers_with_embeddings.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Coverage</span>
                  <span className="font-medium">{debugInfo.database.embedding_coverage_pct.toFixed(1)}%</span>
                </div>
                {debugInfo.database.last_embedded_name && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last Embedded</span>
                    <span className="font-medium text-xs text-right max-w-44 truncate">{debugInfo.database.last_embedded_name}</span>
                  </div>
                )}
                {debugInfo.database.last_embedded_at && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Embedded At</span>
                    <span className="font-medium text-xs">{new Date(debugInfo.database.last_embedded_at).toLocaleString()}</span>
                  </div>
                )}
                {debugInfo.database.sample_provider && (
                  <div className="pt-2 border-t">
                    <p className="text-xs text-muted-foreground mb-1">Sample Provider</p>
                    <p className="text-xs font-mono bg-muted p-1 rounded truncate">{debugInfo.database.sample_provider}</p>
                  </div>
                )}
                {debugInfo.database.error && (
                  <div className="pt-2 border-t">
                    <p className="text-xs text-red-600 font-mono">{debugInfo.database.error}</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <Zap className="h-4 w-4" />
                  API Configuration
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">LLM 1 — Embeddings</p>
                  <div className="space-y-1 pl-2">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground">Configured</span>
                      <StatusBadge ok={debugInfo.api_config.llm1_configured} />
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Base URL</span>
                      <span className="font-medium text-xs truncate max-w-40">{debugInfo.api_config.llm1_base_url ?? "default"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Model</span>
                      <span className="font-medium text-xs">{debugInfo.api_config.llm1_model || "—"}</span>
                    </div>
                  </div>
                </div>
                <div className="border-t pt-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">LLM 2 — Firm Ranking</p>
                  <div className="space-y-1 pl-2">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground">Configured</span>
                      <StatusBadge ok={debugInfo.api_config.openai_configured} />
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Base URL</span>
                      <span className="font-medium text-xs truncate max-w-40">{debugInfo.api_config.openai_base_url ?? "default"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Model</span>
                      <span className="font-medium text-xs">{debugInfo.api_config.llm_model || "—"}</span>
                    </div>
                  </div>
                </div>
                <div className="border-t pt-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">LLM 3 — Document Collapse</p>
                  <div className="space-y-1 pl-2">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground">Configured</span>
                      <StatusBadge ok={debugInfo.api_config.llm3_configured} />
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Base URL</span>
                      <span className="font-medium text-xs truncate max-w-40">{debugInfo.api_config.llm3_base_url ?? "default"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Model</span>
                      <span className="font-medium text-xs">{debugInfo.api_config.llm3_model || "—"}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {debugInfo.last_error && (
              <Card className="md:col-span-2 border-red-200">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base text-red-700 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    Last Search Error
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-xs bg-red-50 p-3 rounded space-y-1">
                    {debugInfo.last_error.error && (
                      <p><span className="font-semibold text-red-900">Error:</span> <span className="text-red-800">{debugInfo.last_error.error}</span></p>
                    )}
                    {debugInfo.last_error.query && (
                      <p><span className="font-semibold text-red-900">Query:</span> <span className="text-red-700">{debugInfo.last_error.query}</span></p>
                    )}
                    {debugInfo.last_error.timestamp && (
                      <p><span className="font-semibold text-red-900">Time:</span> <span className="text-red-700">{debugInfo.last_error.timestamp}</span></p>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>

      {/* ---- Email Integration (Resend) ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5" />
            📧 Email Integration (Resend)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between items-center text-sm">
            <span className="text-muted-foreground">API Key</span>
            {emailResult ? (
              emailResult.api_key_present ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 border border-green-300">
                  <CheckCircle className="h-3 w-3" /> Configured
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 border border-red-300">
                  <AlertCircle className="h-3 w-3" /> Not Set
                </span>
              )
            ) : (
              <span className="text-xs text-muted-foreground italic">Send a test to check</span>
            )}
          </div>
          {emailResult?.api_key_prefix && (
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Key Prefix</span>
              <span className="font-mono text-xs bg-muted px-2 py-0.5 rounded">{emailResult.api_key_prefix}...</span>
            </div>
          )}
          <div className="flex gap-2">
            <Input
              type="email"
              value={emailTo}
              onChange={(e) => setEmailTo(e.target.value)}
              placeholder="Send test to email address"
              className="flex-1"
              onKeyDown={(e) => { if (e.key === "Enter") sendTestEmail(); }}
            />
            <Button onClick={sendTestEmail} disabled={emailLoading || !emailTo.trim()}>
              <Mail className="h-4 w-4 mr-2" />
              {emailLoading ? "Sending..." : "Send Test Email"}
            </Button>
          </div>
          {emailResult?.success && (
            <div className="bg-green-50 border border-green-200 rounded-md p-3 space-y-1 text-sm">
              <div className="flex items-center gap-2 text-green-700 font-medium">
                <CheckCircle className="h-4 w-4" />
                ✅ Email sent successfully
              </div>
              {emailResult.message_id && (
                <div className="text-xs text-green-600">Message ID: {emailResult.message_id}</div>
              )}
              <div className="text-xs text-green-600">From: {emailResult.from_address}</div>
              <div className="text-xs text-green-600">To: {emailResult.to_address}</div>
            </div>
          )}
          {emailResult && !emailResult.success && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3 space-y-1 text-sm">
              <div className="flex items-center gap-2 text-red-700 font-medium">
                <AlertCircle className="h-4 w-4" />
                ❌ Failed: {emailResult.error}
              </div>
              {emailResult.resend_status_code && (
                <div className="text-xs text-red-500">HTTP Status: {emailResult.resend_status_code}</div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Resend Domain Verification Check ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>🔍</span> Resend Domain Verification
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-gray-600">
            Check which domains are verified under the currently configured Resend API key.
            If your domain is missing, add it at{' '}
            <a href="https://resend.com/domains" target="_blank" rel="noreferrer" className="text-blue-600 underline">resend.com/domains</a>.
          </p>
          <Button onClick={checkResendDomain} disabled={domainCheckLoading} size="sm">
            {domainCheckLoading ? 'Checking...' : '🔍 Check Domain Verification'}
          </Button>
          {domainCheckResult && (
            <div className={`rounded-md border p-3 text-sm ${domainCheckResult.domain_verified ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'}`}>
              <div className="font-semibold mb-2">
                {domainCheckResult.domain_verified
                  ? <span>&#x2705; Domain <strong>{domainCheckResult.configured_domain}</strong> is VERIFIED in Resend</span>
                  : <span>&#x274c; Domain <strong>{domainCheckResult.configured_domain}</strong> is NOT verified in this Resend account</span>
                }
              </div>
              {domainCheckResult.error && (
                <div className="text-red-700 mb-2">Error: {domainCheckResult.error}</div>
              )}
              {domainCheckResult.tip && (
                <div className="text-orange-700 mb-2 p-2 bg-orange-50 rounded border border-orange-200">
                  💡 {domainCheckResult.tip}
                </div>
              )}
              {domainCheckResult.domains.length > 0 ? (
                <div>
                  <div className="font-medium mb-1">Domains in this Resend account:</div>
                  <ul className="space-y-1">
                    {domainCheckResult.domains.map((d) => (
                      <li key={d.name} className="flex items-center gap-2">
                        <span className={d.status === 'verified' ? 'text-green-600' : 'text-red-600'}>
                          {d.status === 'verified' ? '✅' : '⚠️'}
                        </span>
                        <span className="font-mono text-xs">{d.name}</span>
                        <span className="text-xs text-gray-500">({d.status})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : domainCheckResult.success ? (
                <div className="text-gray-600">
                  No domains found. Go to{' '}
                  <a href="https://resend.com/domains" target="_blank" rel="noreferrer" className="text-blue-600 underline">resend.com/domains</a>{' '}
                  and add <strong>{domainCheckResult.configured_domain}</strong>.
                </div>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Signwell Connection Test ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>🔑</span> Signwell API Connection Test
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600">
            Verifies your Signwell API key is valid by listing available templates.
            Use this to diagnose 401 errors before running the full NDA test.
          </p>
          <Button onClick={testSignwellConnection} disabled={signwellTestLoading}>
            {signwellTestLoading ? 'Testing...' : '🔌 Test Signwell Connection'}
          </Button>
          {signwellTestResult && (
            <div className={`p-4 rounded border ${
              signwellTestResult.success
                ? 'bg-green-50 border-green-200'
                : 'bg-red-50 border-red-200'
            }`}>
              {signwellTestResult.success ? (
                <div className="space-y-1 text-sm text-green-800">
                  <div className="font-semibold">✅ {signwellTestResult.message}</div>
                  <div>Key preview: <code className="bg-green-100 px-1 rounded">{signwellTestResult.key_preview}</code> (length: {signwellTestResult.key_length})</div>
                  <div>Templates found: <strong>{signwellTestResult.templates_found}</strong></div>
                  {signwellTestResult.templates?.length > 0 && (
                    <ul className="list-disc ml-5">
                      {signwellTestResult.templates.map(function(t: { id: string; name: string }) {
                        return <li key={t.id}><strong>{t.name}</strong> &mdash; <code className="bg-green-100 px-1 rounded">{t.id}</code></li>;
                      })}
                    </ul>
                  )}
                </div>
              ) : (
                <div className="space-y-1 text-sm text-red-800">
                  <div className="font-semibold">❌ {signwellTestResult.error}</div>
                  {signwellTestResult.key_preview && (
                    <div>Key being used: <code className="bg-red-100 px-1 rounded">{signwellTestResult.key_preview}</code> (length: {signwellTestResult.key_length})</div>
                  )}
                  {signwellTestResult.hint && (
                    <div className="text-yellow-700">💡 {signwellTestResult.hint}</div>
                  )}
                  {signwellTestResult.raw_response && (
                    <div className="text-xs text-gray-500 mt-1">API response: {signwellTestResult.raw_response}</div>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Signwell NDA End-to-End Test ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSignature className="h-5 w-5" />
            Signwell NDA End-to-End Test
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Creates a real Signwell NDA using the configured template and sends signing invitations
            to both parties. Verify the full document-signing flow end-to-end.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Customer Name</label>
              <Input value={ndaCustomerName} onChange={(e) => setNdaCustomerName(e.target.value)} placeholder="e.g. Alice Johnson" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Customer Email</label>
              <Input type="email" value={ndaCustomerEmail} onChange={(e) => setNdaCustomerEmail(e.target.value)} placeholder="e.g. alice@example.com" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Provider Name</label>
              <Input value={ndaProviderName} onChange={(e) => setNdaProviderName(e.target.value)} placeholder="e.g. Acme Engineering LLC" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Provider Email</label>
              <Input type="email" value={ndaProviderEmail} onChange={(e) => setNdaProviderEmail(e.target.value)} placeholder="e.g. contracts@acme.com" />
            </div>
          </div>

          <Button
            onClick={sendTestNDA}
            disabled={ndaLoading || !ndaCustomerName.trim() || !ndaCustomerEmail.trim() || !ndaProviderName.trim() || !ndaProviderEmail.trim()}
          >
            <FileSignature className="h-4 w-4 mr-2" />
            {ndaLoading ? 'Creating NDA...' : 'Create & Send Test NDA'}
          </Button>

          {/* Creation result */}
          {ndaResult && ndaResult.success && (
            <div className="bg-green-50 border border-green-200 rounded-md p-4 space-y-3">
              <div className="flex items-center gap-2 text-green-700 font-semibold">
                <CheckCircle className="h-4 w-4" />
                NDA document created successfully!
              </div>
              <div className="text-xs space-y-1">
                <div><span className="font-medium">Document ID:</span>{' '}
                  <span className="font-mono bg-white border border-green-200 px-2 py-0.5 rounded">{ndaResult.document_id}</span>
                </div>
                <div><span className="font-medium">Signwell Status:</span> {ndaResult.signwell_status}</div>
                <div><span className="font-medium">Created:</span> {ndaResult.created_at}</div>
              </div>
              {ndaResult.customer_signing_url && (
                <div className="text-xs">
                  <span className="font-medium">Customer signing link:</span>{' '}
                  <a href={ndaResult.customer_signing_url} target="_blank" rel="noreferrer"
                     className="text-blue-600 underline break-all">{ndaResult.customer_signing_url}</a>
                </div>
              )}
              {ndaResult.provider_signing_url && (
                <div className="text-xs">
                  <span className="font-medium">Provider signing link:</span>{' '}
                  <a href={ndaResult.provider_signing_url} target="_blank" rel="noreferrer"
                     className="text-blue-600 underline break-all">{ndaResult.provider_signing_url}</a>
                </div>
              )}
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={checkNDAStatus} disabled={ndaStatusLoading}>
                  <RefreshCw className={`h-3 w-3 mr-1 ${ndaStatusLoading ? 'animate-spin' : ''}`} />
                  {ndaStatusLoading ? 'Checking...' : 'Check Status'}
                </Button>
                <Button size="sm" variant="outline"
                  className="border-red-300 text-red-700 hover:bg-red-50"
                  onClick={voidTestNDA} disabled={ndaVoidLoading}>
                  {ndaVoidLoading ? 'Voiding...' : 'Void / Cancel'}
                </Button>
              </div>
            </div>
          )}

          {ndaResult && !ndaResult.success && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm">
              <div className="flex items-center gap-2 text-red-700 font-medium">
                <AlertCircle className="h-4 w-4" />
                Failed: {ndaResult.error}
              </div>
            </div>
          )}

          {/* Status result */}
          {ndaStatusResult && (
            <div className={`border rounded-md p-4 space-y-2 text-sm ${
              ndaStatusResult.fully_signed ? 'bg-green-50 border-green-200' : 'bg-blue-50 border-blue-200'
            }`}>
              <div className="font-semibold">
                {ndaStatusResult.fully_signed ? 'Fully Signed' : 'Awaiting Signatures'}
              </div>
              {ndaStatusResult.error && (
                <div className="text-red-700">Error: {ndaStatusResult.error}</div>
              )}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <div><span className="font-medium">Signwell Status:</span> {ndaStatusResult.document_status ?? 'n/a'}</div>
                <div><span className="font-medium">Fully Signed:</span> {ndaStatusResult.fully_signed ? 'Yes' : 'No'}</div>
                <div className={ndaStatusResult.customer_signed ? 'text-green-700' : 'text-amber-700'}>
                  <span className="font-medium">Customer:</span>{' '}
                  {ndaStatusResult.customer_signed ? 'Signed' : 'Pending'}
                  {ndaStatusResult.customer_signed_at ? ` (${new Date(ndaStatusResult.customer_signed_at).toLocaleString()})` : ''}
                </div>
                <div className={ndaStatusResult.provider_signed ? 'text-green-700' : 'text-amber-700'}>
                  <span className="font-medium">Provider:</span>{' '}
                  {ndaStatusResult.provider_signed ? 'Signed' : 'Pending'}
                  {ndaStatusResult.provider_signed_at ? ` (${new Date(ndaStatusResult.provider_signed_at).toLocaleString()})` : ''}
                </div>
                <div><span className="font-medium">S3 PDF Saved:</span> {ndaStatusResult.s3_saved ? 'Yes' : 'No'}</div>
                {ndaStatusResult.s3_key_checked && (
                  <div className="col-span-2 font-mono text-xs text-muted-foreground">{ndaStatusResult.s3_key_checked}</div>
                )}
              </div>
              {ndaStatusResult.s3_download_url && (
                <a href={ndaStatusResult.s3_download_url} target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-1 text-xs text-blue-600 underline">
                  Download Signed PDF
                </a>
              )}
            </div>
          )}

          {/* Void result */}
          {ndaVoidResult && (
            <div className={`border rounded-md p-3 text-sm ${
              ndaVoidResult.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
            }`}>
              {ndaVoidResult.success ? (
                <div className="flex items-center gap-2 text-green-700">
                  <CheckCircle className="h-4 w-4" />
                  {ndaVoidResult.message}
                </div>
              ) : (
                <div className="flex items-center gap-2 text-red-700">
                  <AlertCircle className="h-4 w-4" />
                  Void failed: {ndaVoidResult.error}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Stripe Payment Integration ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>&#x1F4B3;</span> Stripe Payment Integration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600">
            Verifies your Stripe API key is valid by retrieving account info and creating
            (then immediately cancelling) a $1.00 test PaymentIntent.
          </p>
          <Button onClick={testStripeConnection} disabled={stripeLoading}>
            {stripeLoading ? 'Testing...' : '🔌 Test Stripe Connection'}
          </Button>
          {stripeResult && stripeResult.status === 'success' && (
            <div className="bg-green-50 border border-green-200 rounded-md p-4 space-y-2 text-sm">
              <div className="flex items-center gap-2 text-green-700 font-semibold">
                <CheckCircle className="h-4 w-4" />
                &#x2705; Connected successfully
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-green-800">
                <div><span className="font-medium">Account Name:</span> {stripeResult.account_name}</div>
                <div>
                  <span className="font-medium">Account ID:</span>{' '}
                  <code className="bg-green-100 px-1 rounded">{stripeResult.account_id}</code>
                </div>
                <div>
                  <span className="font-medium">Mode:</span>{' '}
                  <span className={`font-semibold ${
                    stripeResult.mode === 'live' ? 'text-orange-700' : 'text-green-700'
                  }`}>
                    {stripeResult.mode === 'live' ? '⚠️ LIVE' : '🧪 Test'}
                  </span>
                </div>
                <div>
                  <span className="font-medium">Test PaymentIntent:</span>{' '}
                  <code className="bg-green-100 px-1 rounded text-xs">{stripeResult.test_payment_intent_id}</code>
                </div>
              </div>
            </div>
          )}
          {stripeResult && stripeResult.status === 'not_configured' && (
            <div className="bg-yellow-50 border border-yellow-300 rounded-md p-3 text-sm">
              <div className="flex items-center gap-2 text-yellow-800 font-medium">
                <AlertCircle className="h-4 w-4" />
                &#x26A0;&#xFE0F; Not Configured
              </div>
              <div className="text-xs text-yellow-700 mt-1">{stripeResult.message}</div>
              <div className="text-xs text-yellow-600 mt-1">
                Go to Admin &gt; Settings and add your Stripe Secret Key.
              </div>
            </div>
          )}
          {stripeResult && stripeResult.status === 'error' && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm">
              <div className="flex items-center gap-2 text-red-700 font-medium">
                <AlertCircle className="h-4 w-4" />
                ❌ Error: {stripeResult.error}
              </div>
            </div>
          )}
        </CardContent>
      </Card>


      {/* ---- RFQ Unlock Checkout Config ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>&#x1F512;</span> RFQ Unlock Checkout Config
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600">
            Verifies the $50 RFQ unlock checkout is properly configured: Stripe key, API
            connectivity, frontend URL, and database access.
          </p>
          <Button onClick={testRfqUnlockConfig} disabled={rfqUnlockLoading}>
            {rfqUnlockLoading ? 'Testing...' : '🔓 Test RFQ Unlock Config'}
          </Button>
          {rfqUnlockResult && (
            <div className="space-y-2">
              <div className={`flex items-center gap-2 text-sm font-semibold ${
                rfqUnlockResult.ready ? 'text-green-700' : 'text-red-700'
              }`}>
                {rfqUnlockResult.ready
                  ? <><CheckCircle className="h-4 w-4" /> All checks passed — checkout is ready</>
                  : <><AlertCircle className="h-4 w-4" /> Config issue: {rfqUnlockResult.status}</>}
              </div>
              <div className="space-y-1">
                {rfqUnlockResult.steps.map((step, idx) => (
                  <div key={idx} className={`text-xs rounded px-2 py-1 ${
                    step.status === 'OK'
                      ? 'bg-green-50 text-green-800 border border-green-200'
                      : step.status === 'WARN'
                      ? 'bg-yellow-50 text-yellow-800 border border-yellow-200'
                      : 'bg-red-50 text-red-800 border border-red-200'
                  }`}>
                    <span className="font-mono font-medium">[{step.status}]</span>{'  '}{' '}
                    <span className="font-medium">{step.step}:</span>{'  '}{' '}
                    {step.message}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            PayPal Connection Test
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Tests PayPal API connectivity using stored credentials from the Settings page.
          </p>
          <Button
            onClick={testPaypalConnection}
            disabled={paypalLoading}
            variant="outline"
            size="sm"
          >
            {paypalLoading ? (
              <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Testing...</>
            ) : (
              <>Test PayPal Connection</>
            )}
          </Button>
          {paypalResult && (
            <div
              className={`rounded-md border p-3 text-sm ${
                paypalResult.success
                  ? 'border-green-200 bg-green-50 text-green-800'
                  : 'border-red-200 bg-red-50 text-red-800'
              }`}
            >
              {paypalResult.success ? (
                <div className="space-y-1">
                  <p className="font-semibold">Connected successfully</p>
                  {paypalResult.mode && <p><span className="font-medium">Mode:</span> {paypalResult.mode}</p>}
                  {paypalResult.app_id && <p><span className="font-medium">App ID:</span> {paypalResult.app_id}</p>}
                  {paypalResult.token_type && <p><span className="font-medium">Token type:</span> {paypalResult.token_type}</p>}
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="font-semibold">Connection failed</p>
                  {paypalResult.mode && <p><span className="font-medium">Mode:</span> {paypalResult.mode}</p>}
                  {paypalResult.error && <p className="font-mono text-xs break-all">{paypalResult.error}</p>}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Test Firm Ranking LLM (LLM 2) ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>🤖</span> Test Firm Ranking LLM (LLM 2)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Send a test prompt to the configured Firm Ranking LLM (LLM 2) used in the Pass 1 &amp; Pass 2 pipeline for query extraction and provider scoring.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 border rounded px-3 py-2 text-sm"
              placeholder="Enter a test prompt..."
              value={llmPrompt}
              onChange={(e) => setLlmPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') testLlm(); }}
            />
            <Button onClick={testLlm} disabled={llmLoading} size="sm">
              {llmLoading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Sending...</> : '🚀 Send'}
            </Button>
          </div>
          {llmResult && (
            <div className={`rounded-md border p-3 text-sm ${
              llmResult.success
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}>
              {llmResult.success ? (
                <div className="space-y-2">
                  <p className="font-semibold text-green-700">✅ LLM responded successfully</p>
                  <p><span className="font-medium">Model:</span> <code className="bg-green-100 px-1 rounded text-xs">{llmResult.model}</code></p>
                  <div className="bg-white border border-green-200 rounded p-2 text-gray-800 whitespace-pre-wrap">{llmResult.response}</div>
                  {llmResult.usage && (
                    <p className="text-xs text-gray-500">
                      Tokens used: {llmResult.usage.prompt_tokens} prompt + {llmResult.usage.completion_tokens} completion
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-1">
                  <p className="font-semibold">❌ LLM call failed</p>
                  <p className="font-mono text-xs break-all">{llmResult.error}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Test Document Collapse LLM (LLM 3) ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>📄</span> Test Document Collapse LLM (LLM 3)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Send a test prompt to the configured Document Collapse LLM (LLM 3) used to summarise and collapse RFQ documents uploaded by customers before ranking.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 border rounded px-3 py-2 text-sm"
              placeholder="Enter a test prompt..."
              value={docLlmPrompt}
              onChange={(e) => setDocLlmPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') testDocLlm(); }}
            />
            <Button onClick={testDocLlm} disabled={docLlmLoading} size="sm">
              {docLlmLoading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Sending...</> : '🚀 Send'}
            </Button>
          </div>
          {docLlmResult && (
            <div className={`rounded-md border p-3 text-sm ${
              docLlmResult.success
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}>
              {docLlmResult.success ? (
                <div className="space-y-2">
                  <p className="font-semibold text-green-700">✅ Document Collapse LLM responded successfully</p>
                  <p><span className="font-medium">Model:</span> <code className="bg-green-100 px-1 rounded text-xs">{docLlmResult.model}</code></p>
                  <div className="bg-white border border-green-200 rounded p-2 text-gray-800 whitespace-pre-wrap">{docLlmResult.response}</div>
                  {docLlmResult.usage && (
                    <p className="text-xs text-gray-500">
                      Tokens used: {docLlmResult.usage.prompt_tokens} prompt + {docLlmResult.usage.completion_tokens} completion
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="font-semibold text-red-700">❌ Document Collapse LLM test failed</p>
                  <p>{docLlmResult.error}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- Test Chatbot LLM (LLM 4) ---- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>💬</span> Test Chatbot LLM (LLM 4)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Send a test prompt to the configured Chatbot LLM (LLM 4) that powers the website help assistant. Falls back to LLM 3 then LLM 1 if no dedicated key is set.
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 border rounded px-3 py-2 text-sm"
              placeholder="Enter a test prompt..."
              value={chatLlmPrompt}
              onChange={(e) => setChatLlmPrompt(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') testChatLlm(); }}
            />
            <Button onClick={testChatLlm} disabled={chatLlmLoading} size="sm">
              {chatLlmLoading ? <><RefreshCw className="h-4 w-4 mr-2 animate-spin" />Sending...</> : '🚀 Send'}
            </Button>
          </div>
          {chatLlmResult && (
            <div className={`rounded-md border p-3 text-sm ${
              chatLlmResult.success
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-800'
            }`}>
              {chatLlmResult.success ? (
                <div className="space-y-2">
                  <p className="font-semibold text-green-700">✅ Chatbot LLM responded successfully</p>
                  <p><span className="font-medium">Model:</span> <code className="bg-green-100 px-1 rounded text-xs">{chatLlmResult.model}</code></p>
                  <div className="bg-white border border-green-200 rounded p-2 text-gray-800 whitespace-pre-wrap">{chatLlmResult.response}</div>
                  {chatLlmResult.usage && (
                    <p className="text-xs text-gray-500">
                      Tokens used: {chatLlmResult.usage.prompt_tokens} prompt + {chatLlmResult.usage.completion_tokens} completion
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="font-semibold text-red-700">❌ Chatbot LLM test failed</p>
                  <p>{chatLlmResult.error}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
