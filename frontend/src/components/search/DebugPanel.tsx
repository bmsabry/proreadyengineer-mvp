"use client";

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle, Database, Key, Server, ChevronDown, ChevronUp } from 'lucide-react';

interface DebugInfo {
  timestamp: string;
  database: {
    provider_count?: number;
    providers_with_embeddings?: number;
    sample_provider?: {
      id: string;
      name: string;
      has_embedding: boolean;
    };
    connection_ok?: boolean;
    error?: string;
  };
  api_keys: {
    openai_configured: boolean;
    openai_base_url: string;
    embedding_model: string;
    llm_model: string;
  };
  last_error: {
    error: string | null;
    timestamp: string | null;
    query: string | null;
  };
}

interface DebugPanelProps {
  searchQuery: string;
  searchStatus: 'idle' | 'loading' | 'success' | 'error';
  searchError: string | null;
  resultCount: number;
  showOnEmpty?: boolean;
}

export function DebugPanel({
  searchQuery,
  searchStatus,
  searchError,
  resultCount,
  showOnEmpty = true
}: DebugPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [debugInfo, setDebugInfo] = useState<DebugInfo | null>(null);
  const [isLoadingDebug, setIsLoadingDebug] = useState(false);
  const [debugError, setDebugError] = useState<string | null>(null);

  const shouldShow = !showOnEmpty || (searchStatus === 'success' && resultCount === 0) || searchStatus === 'error';

  useEffect(() => {
    if (shouldShow && isExpanded && !debugInfo) {
      fetchDebugInfo();
    }
  }, [shouldShow, isExpanded]);

  const fetchDebugInfo = async () => {
    setIsLoadingDebug(true);
    setDebugError(null);
    try {
      const response = await api.search.debug();
      setDebugInfo(response.data);
    } catch (err: any) {
      setDebugError(err.response?.data?.detail || err.message || 'Failed to fetch debug info');
    } finally {
      setIsLoadingDebug(false);
    }
  };

  if (!shouldShow) return null;

  return (
    <Card className="mt-6 border-yellow-200 bg-yellow-50/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-yellow-600" />
            <CardTitle className="text-base font-semibold text-yellow-800">
              Debug Information
            </CardTitle>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-yellow-700 hover:text-yellow-800 hover:bg-yellow-100"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="h-4 w-4 mr-1" />
                Hide
              </>
            ) : (
              <>
                <ChevronDown className="h-4 w-4 mr-1" />
                Show Details
              </>
            )}
          </Button>
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          {/* Search Request Summary */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-yellow-800">Search Request</h4>
            <div className="bg-white rounded-md p-3 text-sm space-y-1">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Query:</span>
                <span className="font-mono truncate max-w-[400px]" title={searchQuery}>
                  {searchQuery || '(none)'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status:</span>
                <Badge 
                  variant={searchStatus === 'success' ? 'default' : searchStatus === 'error' ? 'destructive' : 'secondary'}
                  className="text-xs"
                >
                  {searchStatus}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Results:</span>
                <span>{resultCount}</span>
              </div>
              {searchError && (
                <div className="mt-2 p-2 bg-red-50 rounded border border-red-200">
                  <span className="text-red-600 text-xs font-medium">Error:</span>
                  <p className="text-red-700 text-xs mt-1">{searchError}</p>
                </div>
              )}
            </div>
          </div>

          {/* Database Status */}
          {isLoadingDebug ? (
            <div className="text-sm text-yellow-700">Loading debug info...</div>
          ) : debugError ? (
            <div className="text-sm text-red-600">Failed to load debug info: {debugError}</div>
          ) : debugInfo ? (
            <>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-yellow-700" />
                  <h4 className="text-sm font-medium text-yellow-800">Database Status</h4>
                </div>
                <div className="bg-white rounded-md p-3 text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Connection:</span>
                    {debugInfo.database.connection_ok ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="h-3 w-3" />
                        OK
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-600">
                        <AlertCircle className="h-3 w-3" />
                        Failed
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total Providers:</span>
                    <span className="font-mono">{debugInfo.database.provider_count ?? 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">With Embeddings:</span>
                    <span className="font-mono">{debugInfo.database.providers_with_embeddings ?? 'N/A'}</span>
                  </div>
                  {debugInfo.database.sample_provider && (
                    <div className="mt-2 pt-2 border-t border-gray-100">
                      <span className="text-muted-foreground">Sample Provider:</span>
                      <div className="mt-1 text-xs">
                        <div>{debugInfo.database.sample_provider.name}</div>
                        <div className="text-muted-foreground">
                          ID: {debugInfo.database.sample_provider.id} | 
                          Embedding: {debugInfo.database.sample_provider.has_embedding ? 'Yes' : 'No'}
                        </div>
                      </div>
                    </div>
                  )}
                  {debugInfo.database.error && (
                    <div className="mt-2 p-2 bg-red-50 rounded border border-red-200">
                      <span className="text-red-600 text-xs">Error: {debugInfo.database.error}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* API Keys Status */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Key className="h-4 w-4 text-yellow-700" />
                  <h4 className="text-sm font-medium text-yellow-800">API Configuration</h4>
                </div>
                <div className="bg-white rounded-md p-3 text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">OpenAI Key:</span>
                    {debugInfo.api_keys.openai_configured ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="h-3 w-3" />
                        Configured
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-600">
                        <AlertCircle className="h-3 w-3" />
                        Missing
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Base URL:</span>
                    <span className="font-mono text-xs">{debugInfo.api_keys.openai_base_url}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Embedding Model:</span>
                    <span className="font-mono text-xs">{debugInfo.api_keys.embedding_model}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">LLM Model:</span>
                    <span className="font-mono text-xs">{debugInfo.api_keys.llm_model}</span>
                  </div>
                </div>
              </div>

              {/* Last Error */}
              {debugInfo.last_error?.error && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Server className="h-4 w-4 text-red-600" />
                    <h4 className="text-sm font-medium text-red-800">Last Server Error</h4>
                  </div>
                  <div className="bg-red-50 rounded-md p-3 text-sm border border-red-200">
                    <div className="text-red-700">{debugInfo.last_error.error}</div>
                    <div className="text-red-600 text-xs mt-1">
                      Time: {new Date(debugInfo.last_error.timestamp || '').toLocaleString()}
                    </div>
                    <div className="text-red-600 text-xs">
                      Query: {debugInfo.last_error.query}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : null}

          <Button
            variant="outline"
            size="sm"
            onClick={fetchDebugInfo}
            disabled={isLoadingDebug}
            className="w-full border-yellow-300 text-yellow-700 hover:bg-yellow-100"
          >
            {isLoadingDebug ? 'Refreshing...' : 'Refresh Debug Info'}
          </Button>
        </CardContent>
      )}
    </Card>
  );
}
