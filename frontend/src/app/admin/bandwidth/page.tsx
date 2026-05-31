'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, AlertCircle, RefreshCw, Gauge, TrendingUp, TrendingDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';

interface Summary { avg: number | null; peak: number | null; p95: number | null; latest: number | null; count: number; spark: number[]; }
interface Rec { status: string; headline: string; detail: string; suggested_plan?: { label: string; cpu: number; ram_gb: number; usd_mo: number } | null; }
interface SvcMetrics {
  service: string; plan: string | null; plan_cpu: number; plan_ram_gb: number;
  cpu: Summary & { peak_pct: number | null; trend_pct: number | null };
  memory: Summary & { peak_pct: number | null; peak_gb: number | null };
  http_requests: Summary; latency_ms: Summary; recommendation: Rec;
}
interface BandwidthData {
  available: boolean; error?: string; window_hours?: number;
  services?: SvcMetrics[]; overall?: Rec; notes?: string;
}

const STATUS_STYLE: Record<string, { box: string; dot: string; label: string }> = {
  scale_now: { box: 'border-red-200 bg-red-50 text-red-800', dot: 'bg-red-500', label: 'Scale up' },
  watch:     { box: 'border-amber-200 bg-amber-50 text-amber-800', dot: 'bg-amber-500', label: 'Watch' },
  healthy:   { box: 'border-emerald-200 bg-emerald-50 text-emerald-800', dot: 'bg-emerald-500', label: 'Healthy' },
  unknown:   { box: 'border-slate-200 bg-slate-50 text-slate-600', dot: 'bg-slate-400', label: 'No data' },
};

function Spark({ data, color = '#0F2B54' }: { data: number[]; color?: string }) {
  if (!data || data.length < 2) return <span className="text-xs text-slate-400">—</span>;
  const w = 120, h = 28, min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function pct(n: number | null | undefined) { return n == null ? '—' : `${Number(n).toFixed(0)}%`; }
function num(n: number | null | undefined, d = 0) { return n == null ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }); }

export default function BandwidthPage() {
  useRequireAuth(['admin']);
  const [data, setData] = useState<BandwidthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowHours, setWindowHours] = useState(24);

  const load = useCallback(async (wh: number) => {
    setLoading(true); setError(null);
    try {
      const res = await api.admin.bandwidth(wh);
      setData(res.data as BandwidthData);
    } catch (e) { setError((e as Error).message || 'Failed to load metrics.'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(windowHours); }, [load, windowHours]);

  const overall = data?.overall;
  const st = overall ? (STATUS_STYLE[overall.status] || STATUS_STYLE.unknown) : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-[#0F2B54]" />
            <h1 className="text-xl font-bold text-slate-900">Bandwidth</h1>
          </div>
          <p className="text-sm text-slate-500 mt-0.5">Live CPU, memory, request volume & latency from Render — with scale recommendations.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={windowHours} onChange={(e) => setWindowHours(Number(e.target.value))}
            className="border border-slate-300 rounded-md px-2 py-1.5 text-sm">
            <option value={6}>Last 6h</option>
            <option value={24}>Last 24h</option>
            <option value={72}>Last 3 days</option>
            <option value={168}>Last 7 days</option>
          </select>
          <Button onClick={() => load(windowHours)} variant="outline" size="sm" disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {loading && !data ? (
        <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-[#0F2B54]" /></div>
      ) : data && !data.available ? (
        <Card><CardContent className="pt-5 text-sm text-slate-600">
          <AlertCircle className="h-4 w-4 inline mr-1.5 text-amber-500" />
          {data.error || 'Metrics unavailable.'} Render metrics require a paid instance and a RENDER_API_KEY set in Settings.
        </CardContent></Card>
      ) : data ? (
        <>
          {overall && st && (
            <div className={`rounded-xl border p-4 ${st.box}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className={`h-2.5 w-2.5 rounded-full ${st.dot}`} />
                <span className="text-xs font-bold uppercase tracking-wide">{st.label}</span>
              </div>
              <p className="font-semibold">{overall.headline}</p>
              <p className="text-sm mt-1">{overall.detail}</p>
              {overall.suggested_plan && (
                <p className="text-sm mt-2 font-medium">
                  → Suggested next step: upgrade to <strong>{overall.suggested_plan.label}</strong>
                  {' '}({overall.suggested_plan.cpu} vCPU / {overall.suggested_plan.ram_gb} GB RAM, ~${overall.suggested_plan.usd_mo}/mo).
                </p>
              )}
            </div>
          )}

          {(data.services || []).map((svc) => {
            const sst = STATUS_STYLE[svc.recommendation.status] || STATUS_STYLE.unknown;
            const tr = svc.cpu.trend_pct;
            return (
              <Card key={svc.service}>
                <CardHeader>
                  <CardTitle className="text-base flex items-center justify-between">
                    <span>{svc.service}</span>
                    <span className="text-xs font-normal text-slate-500">
                      {svc.plan || 'unknown'} plan · {svc.plan_cpu} vCPU / {svc.plan_ram_gb} GB
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className={`mb-3 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${sst.box}`}>
                    <span className={`h-2 w-2 rounded-full ${sst.dot}`} />{svc.recommendation.headline}
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <p className="text-xs text-slate-500 mb-1">CPU (peak {pct(svc.cpu.peak_pct)} of capacity)</p>
                      <Spark data={svc.cpu.spark} color={svc.cpu.peak_pct && svc.cpu.peak_pct >= 85 ? '#dc2626' : '#0F2B54'} />
                      <p className="text-xs text-slate-500 mt-1">
                        avg {num(svc.cpu.avg, 2)} · peak {num(svc.cpu.peak, 2)} vCPU
                        {tr != null && <span className={`ml-1 ${tr >= 0 ? 'text-amber-600' : 'text-emerald-600'}`}>
                          {tr >= 0 ? <TrendingUp className="inline h-3 w-3" /> : <TrendingDown className="inline h-3 w-3" />} {tr}%
                        </span>}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Memory (peak {pct(svc.memory.peak_pct)} of capacity)</p>
                      <Spark data={svc.memory.spark} color={svc.memory.peak_pct && svc.memory.peak_pct >= 85 ? '#dc2626' : '#7c3aed'} />
                      <p className="text-xs text-slate-500 mt-1">peak {num(svc.memory.peak_gb, 2)} GB</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">HTTP requests</p>
                      <Spark data={svc.http_requests.spark} color="#0891b2" />
                      <p className="text-xs text-slate-500 mt-1">peak {num(svc.http_requests.peak)} / bucket</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-1">Latency</p>
                      <Spark data={svc.latency_ms.spark} color="#ea580c" />
                      <p className="text-xs text-slate-500 mt-1">p95 {num(svc.latency_ms.p95, 1)} · peak {num(svc.latency_ms.peak, 1)}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}

          {data.notes && <p className="text-xs text-slate-400">{data.notes}</p>}
        </>
      ) : null}
    </div>
  );
}
