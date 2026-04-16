'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { Archive, AlertCircle, ArrowRight, Lock } from 'lucide-react';
import NdaBadge from '@/components/ui/NdaBadge';

function UrgencyBadge({ urgency }: { urgency?: string }) {
  const m: Record<string, string> = {
    High: 'bg-red-100 text-red-700 border-red-200',
    Intermediate: 'bg-amber-100 text-amber-700 border-amber-200',
    Low: 'bg-green-100 text-green-700 border-green-200',
  };
  const cls = m[urgency ?? ''] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>{urgency ?? 'N/A'}</span>;
}

function StatusBadge({ status }: { status?: string }) {
  const m: Record<string, string> = {
    unlocked:   'bg-emerald-100 text-emerald-700 border-emerald-200',
    quoted:     'bg-blue-100 text-blue-700 border-blue-200',
    pending:    'bg-amber-100 text-amber-700 border-amber-200',
    dispatched: 'bg-slate-100 text-slate-600 border-slate-200',
    unknown:    'bg-slate-100 text-slate-500 border-slate-200',
  };
  const s = status ?? 'unknown';
  const cls = m[s] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border capitalize ${cls}`}>{s}</span>;
}

export default function AllRFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [items, setItems] = useState<RFQTeaser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await api.providerRFQ.getTeasers();
        const td = (res as any).data ?? res;
        const list: RFQTeaser[] = td?.teasers ?? td ?? [];
        setItems(
          (Array.isArray(list) ? list : []).sort((a, b) =>
            new Date((b as any).created_at ?? 0).getTime() -
            new Date((a as any).created_at ?? 0).getTime()
          )
        );
      } catch (e) { console.error(e); }
      finally { setIsLoading(false); }
    })();
  }, [user]);

  if (authLoading || isLoading) {
    return <div className="min-h-[60vh] flex items-center justify-center"><div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" /></div>;
  }

  const allStatuses = ['all', ...Array.from(new Set(items.map(t => t.status ?? 'unknown')))];
  const filtered = filter === 'all' ? items : items.filter(t => (t.status ?? 'unknown') === filter);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Archive className="h-6 w-6 text-slate-600" />
          All RFQs
        </h1>
        <p className="text-slate-500 text-sm mt-1 max-w-2xl">
          Complete history of every RFQ invitation you received, regardless of status or action taken.
        </p>
      </div>

      {allStatuses.length > 2 && (
        <div className="flex gap-1.5 mb-5 flex-wrap">
          {allStatuses.map(s => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors capitalize ${
                filter === s ? 'bg-blue-600 text-white shadow-sm' : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300'
              }`}>
              {s === 'all' ? `All (${items.length})` : `${s} (${items.filter(t => (t.status ?? 'unknown') === s).length})`}
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center max-w-lg mx-auto">
          <Archive className="h-10 w-10 mx-auto mb-3 text-slate-300" />
          <p className="text-base font-medium text-slate-500">
            {filter === 'all' ? 'No RFQs received yet' : `No ${filter} RFQs`}
          </p>
          <p className="text-sm text-slate-400 mt-1">RFQ invitations dispatched to your firm will appear here.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((t) => (
            <div key={t.rfq_id} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:border-blue-200 hover:shadow-md transition-all flex flex-col">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <UrgencyBadge urgency={t.urgency} />
                <StatusBadge status={t.status} />
                <NdaBadge ndaRequired={t.nda_required} ndaStatus={t.nda_status} />
              </div>

              {(t as any).project_description_preview && (
                <p className="text-sm text-slate-700 mb-2 line-clamp-2 flex-1">{(t as any).project_description_preview}</p>
              )}

              {t.tollgate_phases && t.tollgate_phases.length > 0 && (
                <p className="text-xs text-slate-500 mb-1"><span className="font-medium">Tollgates:</span> {t.tollgate_phases.join(', ')}</p>
              )}

              {(t as any).created_at && (
                <p className="text-xs text-slate-400 mb-3">Received {formatDate((t as any).created_at)}</p>
              )}

              {t.status === 'unlocked' || t.status === 'quoted' ? (
                <Button size="sm" variant="outline"
                  onClick={() => router.push(`/provider/rfq/${t.rfq_id}`)}
                  className="w-full text-xs flex items-center justify-center gap-1 mt-auto">
                  View Details <ArrowRight size={12} />
                </Button>
              ) : (
                <Button size="sm"
                  onClick={() => router.push(`/provider/rfq/${t.rfq_id}`)}
                  className="w-full text-xs bg-[#1e3a5f] hover:bg-[#2a4d7a] text-white flex items-center justify-center gap-1 mt-auto">
                  <Lock size={12} /> Unlock & View
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
