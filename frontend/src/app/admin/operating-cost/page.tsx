'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw, Wallet } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface LlmRow { label: string; model: string; prompt_tokens: number; completion_tokens: number; calls: number; cost_usd: number; basis: string; }
interface OtherRow { label: string; detail?: string; cost_usd: number; basis: string; }
interface CostData {
  month: string;
  llm: { rows: LlmRow[]; total_usd: number };
  other: { rows: OtherRow[]; total_usd: number };
  grand_total_usd: number;
  untracked_services: string[];
  notes: string;
}

const usd = (n: number) => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const num = (n: number) => Number(n || 0).toLocaleString();

function BasisBadge({ basis }: { basis: string }) {
  const map: Record<string, string> = {
    actual: 'bg-emerald-100 text-emerald-700',
    estimate: 'bg-amber-100 text-amber-700',
    manual: 'bg-slate-100 text-slate-600',
  };
  return <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${map[basis] || 'bg-slate-100 text-slate-600'}`}>{basis}</span>;
}

export default function OperatingCostPage() {
  useRequireAuth(['admin']);
  const [data, setData] = useState<CostData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.admin.operatingCost();
      setData(res.data as CostData);
    } catch (e) {
      const err = e as Error;
      setError(err.message || 'Failed to load operating cost.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Wallet className="h-5 w-5 text-[#0F2B54]" />
            <h1 className="text-xl font-bold text-slate-900">Operating Cost</h1>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">
            Where the money goes — LLM spend by model, processing fees, hosting, and other monthly costs{data ? ` (${data.month})` : ''}.
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

      {loading && !data ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-[#0F2B54]" /></div>
      ) : data ? (
        <>
          {/* KPI cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <Card><CardContent className="pt-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total this month (est.)</p>
              <p className="text-3xl font-bold text-slate-900 mt-1">{usd(data.grand_total_usd)}</p>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">LLM / AI</p>
              <p className="text-3xl font-bold text-violet-700 mt-1">{usd(data.llm.total_usd)}</p>
            </CardContent></Card>
            <Card><CardContent className="pt-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Other costs</p>
              <p className="text-3xl font-bold text-slate-700 mt-1">{usd(data.other.total_usd)}</p>
            </CardContent></Card>
          </div>

          {/* LLM by model */}
          <Card>
            <CardHeader><CardTitle className="text-base">LLM cost by model (tokens consumed)</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b">
                      <th className="py-2 pr-3">Use</th><th className="py-2 pr-3">Model</th>
                      <th className="py-2 pr-3 text-right">Calls</th>
                      <th className="py-2 pr-3 text-right">Input tok</th>
                      <th className="py-2 pr-3 text-right">Output tok</th>
                      <th className="py-2 pr-3 text-right">Cost</th>
                      <th className="py-2">Basis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.llm.rows.length === 0 ? (
                      <tr><td colSpan={7} className="py-4 text-slate-400 text-center">No LLM usage recorded this month yet.</td></tr>
                    ) : data.llm.rows.map((r, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-2 pr-3 font-medium text-slate-700">{r.label}</td>
                        <td className="py-2 pr-3 font-mono text-xs text-slate-500">{r.model}</td>
                        <td className="py-2 pr-3 text-right">{num(r.calls)}</td>
                        <td className="py-2 pr-3 text-right">{num(r.prompt_tokens)}</td>
                        <td className="py-2 pr-3 text-right">{num(r.completion_tokens)}</td>
                        <td className="py-2 pr-3 text-right font-semibold">{usd(r.cost_usd)}</td>
                        <td className="py-2"><BasisBadge basis={r.basis} /></td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t font-semibold">
                      <td className="py-2 pr-3" colSpan={5}>LLM subtotal</td>
                      <td className="py-2 pr-3 text-right">{usd(data.llm.total_usd)}</td><td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Other costs */}
          <Card>
            <CardHeader><CardTitle className="text-base">Other monthly costs</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b">
                      <th className="py-2 pr-3">Item</th><th className="py-2 pr-3">Detail</th>
                      <th className="py-2 pr-3 text-right">Cost</th><th className="py-2">Basis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.other.rows.length === 0 ? (
                      <tr><td colSpan={4} className="py-4 text-slate-400 text-center">No other costs configured. Add them via OPERATING_COST_ITEMS / RENDER_MONTHLY_BUDGET in Settings.</td></tr>
                    ) : data.other.rows.map((r, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-2 pr-3 font-medium text-slate-700">{r.label}</td>
                        <td className="py-2 pr-3 text-slate-500">{r.detail || '—'}</td>
                        <td className="py-2 pr-3 text-right font-semibold">{usd(r.cost_usd)}</td>
                        <td className="py-2"><BasisBadge basis={r.basis} /></td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t font-semibold">
                      <td className="py-2 pr-3" colSpan={2}>Other subtotal</td>
                      <td className="py-2 pr-3 text-right">{usd(data.other.total_usd)}</td><td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </CardContent>
          </Card>

          {data.untracked_services?.length > 0 && (
            <Card>
              <CardHeader><CardTitle className="text-base">Services billing separately (not auto-totaled)</CardTitle></CardHeader>
              <CardContent>
                <ul className="list-disc list-inside text-sm text-slate-600 space-y-1">
                  {data.untracked_services.map((sv, i) => <li key={i}>{sv}</li>)}
                </ul>
                <p className="text-xs text-slate-400 mt-2">Add their monthly figures via OPERATING_COST_ITEMS in Settings to include them in the total.</p>
              </CardContent>
            </Card>
          )}

          <p className="text-xs text-slate-400">{data.notes}</p>
        </>
      ) : null}
    </div>
  );
}
