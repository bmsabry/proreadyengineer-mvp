'use client';

import { PipelineInfo } from '@/types';

interface AIPipelinePanelProps {
  pipeline: PipelineInfo | null;
  query: string;
}

export function AIPipelinePanel({ pipeline, query }: AIPipelinePanelProps) {
  if (!pipeline) return null;

  const isAI = pipeline.pipeline_used === 'ai_vector';
  const isKeyword = pipeline.pipeline_used === 'keyword_fallback';
  const noKey = pipeline.pipeline_used === 'no_api_key';

  const statusColor = isAI ? 'bg-green-50 border-green-200' : noKey ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200';
  const statusDot = isAI ? 'bg-green-500' : noKey ? 'bg-red-500' : 'bg-yellow-500';
  const statusText = isAI ? 'AI Vector Search Active' : noKey ? 'No API Key — Keyword Search' : 'Keyword Fallback (API error)';

  return (
    <div className={`rounded-lg border p-3 mb-4 text-sm ${statusColor}`}>
      <div className="flex items-center gap-2 mb-2 font-semibold">
        <span className={`inline-block w-2 h-2 rounded-full ${statusDot}`} />
        <span>🤖 AI Search Pipeline: {statusText}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1 text-xs">
        <Row label="Pipeline" value={pipeline.pipeline_used} />
        <Row label="API Key Source" value={pipeline.api_key_source} highlight={pipeline.api_key_source === 'database' ? 'green' : pipeline.api_key_source === 'missing' ? 'red' : 'yellow'} />
        <Row label="LLM Called" value={pipeline.llm_called ? '✅ Yes' : '❌ No'} />
        <Row label="LLM Response" value={pipeline.llm_response_received ? '✅ Received' : '❌ No response'} />
        <Row label="LLM Model" value={pipeline.llm_model || '—'} />
        <Row label="Embedding" value={pipeline.embedding_called ? `✅ ${pipeline.embedding_dims}d` : '❌ Not called'} />
        {pipeline.inferred_specialty && (
          <Row label="Inferred Specialty" value={pipeline.inferred_specialty} />
        )}
        {pipeline.inferred_keywords && pipeline.inferred_keywords.length > 0 && (
          <div className="col-span-2 md:col-span-3">
            <span className="text-gray-500 font-medium">Keywords: </span>
            <span>{pipeline.inferred_keywords.join(', ')}</span>
          </div>
        )}
        {pipeline.fallback_reason && (
          <div className="col-span-2 md:col-span-3 text-red-600">
            <span className="font-medium">Fallback reason: </span>{pipeline.fallback_reason}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: 'green' | 'yellow' | 'red' }) {
  const color = highlight === 'green' ? 'text-green-700 font-semibold' 
               : highlight === 'red' ? 'text-red-700 font-semibold'
               : highlight === 'yellow' ? 'text-yellow-700 font-semibold'
               : '';
  return (
    <div>
      <span className="text-gray-500 font-medium">{label}: </span>
      <span className={color}>{value}</span>
    </div>
  );
}
