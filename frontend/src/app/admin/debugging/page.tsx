"use client";
export const dynamic = "force-dynamic";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { PipelineInfo } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertCircle, CheckCircle, Database, Search, RefreshCw, Activity, Zap, Mail } from "lucide-react";

interface DatabaseStatus {
  connection_ok: boolean;
  provider_count: number;
  providers_with_embeddings: number;
  embedding_coverage_pct: number;
  sample_provider: string | null;
  error?: string;
}

interface ApiConfigInfo {
  openai_configured: boolean;
  openai_base_url: string | null;
  embedding_model: string;
  llm_model: string;
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

function StatusBadge({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 border border-green-300">
      <CheckCircle className="h-3 w-3" /> OK
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 border border-red-300">
      <AlertCircle className="h-3 w-3" /> Error
    </span>
  );
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
  error: string | null;
  domains: Array<{ name: string; status: string; region: string }>;
  configured_domain: string;
  from_address: string;
  domain_verified: boolean;
  tip: string | null;
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
          error: db.error != null ? String(db.error) : undefined,
        },
        api_config: {
          openai_configured: Boolean(apiCfg.openai_configured),
          openai_base_url: apiCfg.openai_base_url != null ? String(apiCfg.openai_base_url) : null,
          embedding_model: String(apiCfg.embedding_model ?? ""),
          llm_model: String(apiCfg.llm_model ?? ""),
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
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">AI Configured</span>
                  <StatusBadge ok={debugInfo.api_config.openai_configured} />
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Base URL</span>
                  <span className="font-medium text-xs truncate max-w-40">{debugInfo.api_config.openai_base_url ?? "default"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Embedding Model</span>
                  <span className="font-medium text-xs">{debugInfo.api_config.embedding_model}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">LLM Model</span>
                  <span className="font-medium text-xs">{debugInfo.api_config.llm_model}</span>
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
    </div>
  );
}
