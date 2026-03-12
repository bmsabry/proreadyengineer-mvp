"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { PipelineInfo } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AlertCircle, CheckCircle, Database, Search, RefreshCw, Activity, Zap } from "lucide-react";

interface DebugInfo {
  database: {
    connection_ok: boolean;
    provider_count: number;
    providers_with_embeddings: number;
    embedding_coverage_pct: number;
    sample_provider: string | null;
  };
  api_config: {
    openai_configured: boolean;
    openai_base_url: string | null;
    embedding_model: string;
    llm_model: string;
  };
  last_error: string | null;
}

function PipelineBadge({ pipeline }: { pipeline: string | undefined }) {
  if (!pipeline) return null;
  const colors: Record<string, string> = {
    ai_vector: "bg-green-100 text-green-800 border-green-300",
    keyword_fallback: "bg-yellow-100 text-yellow-800 border-yellow-300",
    no_api_key: "bg-red-100 text-red-800 border-red-300",
  };
  const cls = colors[pipeline] ?? "bg-gray-100 text-gray-800 border-gray-300";
  return <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${cls}`}>{pipeline}</span>;
}

function AIPipelineBanner({ pipeline, query }: { pipeline: PipelineInfo; query: string }) {
  const isAI = pipeline.pipeline_used === "ai_vector";
  const isKeyword = pipeline.pipeline_used === "keyword_fallback";
  const bannerClass = isAI ? "bg-green-50 border-green-200" : isKeyword ? "bg-yellow-50 border-yellow-200" : "bg-red-50 border-red-200";
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
        <div><span className="font-medium">Keywords:</span> {pipeline.inferred_keywords?.join(", ") ?? "n/a"}</div>
      </div>
      {pipeline.fallback_reason && (
        <div className="text-xs text-yellow-700"><span className="font-medium">Fallback Reason:</span> {pipeline.fallback_reason}</div>
      )}
    </div>
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

  const loadDebugInfo = useCallback(async () => {
    setDebugLoading(true);
    setDebugError(null);
    try {
      const response = await api.search.debug();
      setDebugInfo(response.data as DebugInfo);
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
      const results = response.data.results ?? [];
      const pipeline = response.data.pipeline_info ?? null;
      setSearchResult({ pipeline, count: results.length });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setSearchError(e.response?.data?.detail ?? e.message ?? "Search failed");
    } finally {
      setSearchLoading(false);
    }
  };
  return (
    <div className="space-y-6">
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
              onKeyDown={(e) => e.key === "Enter" && runTestSearch()}
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
                <span>Search completed — <strong>{searchResult.count}</strong> result{searchResult.count !== 1 ? "s" : ""} returned</span>
              </div>
              {searchResult.pipeline ? (
                <AIPipelineBanner pipeline={searchResult.pipeline} query={testQuery} />
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
                  {debugInfo.database.connection_ok ? (
                    <Badge className="bg-green-600 text-white text-xs"><CheckCircle className="h-3 w-3 mr-1 inline" /> OK</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs"><AlertCircle className="h-3 w-3 mr-1 inline" /> Error</Badge>
                  )}
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
                  <span className="text-muted-foreground">OpenAI Configured</span>
                  {debugInfo.api_config.openai_configured ? (
                    <Badge className="bg-green-600 text-white text-xs"><CheckCircle className="h-3 w-3 mr-1 inline" /> Yes</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs"><AlertCircle className="h-3 w-3 mr-1 inline" /> No</Badge>
                  )}
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
                    Last Error
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-red-50 p-3 rounded overflow-x-auto whitespace-pre-wrap text-red-800">{debugInfo.last_error}</pre>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
