'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw, MessageSquareWarning } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface GapItem {
  id: string;
  created_at: string | null;
  category: 'refused_scope' | 'error' | 'thumbs_down' | 'manual_gap';
  user_email: string | null;
  user_role: string | null;
  user_message: string;
  assistant_reply: string;
  error: string | null;
  feedback: number | null;
}
interface GapsData {
  scanned: number;
  gap_count: number;
  summary: Record<string, number>;
  items: GapItem[];
}

const CATEGORY: Record<string, { label: string; cls: string }> = {
  manual_gap: { label: 'Manual gap', cls: 'bg-amber-100 text-amber-800' },
  refused_scope: { label: 'Refused (off-topic)', cls: 'bg-slate-100 text-slate-600' },
  thumbs_down: { label: 'Thumbs down', cls: 'bg-red-100 text-red-700' },
  error: { label: 'Error', cls: 'bg-red-100 text-red-700' },
};

export default function AssistantGapsPage() {
  useRequireAuth(['admin']);
  const [data, setData] = useState<GapsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.admin.helpGaps(300);
      setData(res.data as GapsData);
    } catch (e) {
      setError((e as Error).message || 'Failed to load assistant gaps.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <MessageSquareWarning className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-bold text-slate-900">Assistant Gaps</h1>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">
            Questions the AI assistant handled poorly &mdash; refusals, errors, thumbs-down, and
            &ldquo;couldn&rsquo;t answer&rdquo; replies. Use these to improve the help manual.
          </p>
        </div>
        <Button onClick={load} variant="outline" size="sm" disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {loading && !data && (
        <div className="flex items-center gap-2 text-slate-500 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading&hellip;
        </div>
      )}

      {data && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-slate-700">
                {data.gap_count} gap{data.gap_count === 1 ? '' : 's'} in the last {data.scanned} conversations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.summary).map(([cat, n]) => (
                  <span key={cat} className={`text-xs font-semibold px-2 py-1 rounded ${CATEGORY[cat]?.cls || 'bg-slate-100 text-slate-600'}`}>
                    {CATEGORY[cat]?.label || cat}: {n}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>

          {data.items.length === 0 ? (
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
              No answer gaps in the recent conversations. The assistant is handling questions cleanly.
            </div>
          ) : (
            <div className="space-y-3">
              {data.items.map((it) => (
                <Card key={it.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${CATEGORY[it.category]?.cls || 'bg-slate-100 text-slate-600'}`}>
                        {CATEGORY[it.category]?.label || it.category}
                      </span>
                      <span className="text-[11px] text-slate-400 whitespace-nowrap">
                        {it.created_at ? new Date(it.created_at).toLocaleString() : ''}
                        {it.user_role ? ` · ${it.user_role}` : ''}
                      </span>
                    </div>
                    <div className="text-sm text-slate-900 font-medium">{it.user_message || '(empty)'}</div>
                    {it.assistant_reply && (
                      <div className="mt-1.5 text-xs text-slate-500 line-clamp-3 whitespace-pre-wrap">{it.assistant_reply}</div>
                    )}
                    {it.error && (
                      <div className="mt-1.5 text-[11px] text-red-600 font-mono">error: {it.error}</div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
