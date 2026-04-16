'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser } from '@/types';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/lib/utils';
import { FileText, ArrowRight, AlertCircle } from 'lucide-react';
import NdaBadge from '@/components/ui/NdaBadge';

function UrgencyBadge({ urgency }: { urgency?: string }) {
  const m: Record<string, string> = {
    High: 'bg-red-100 text-red-700 border-red-200',
    Intermediate: 'bg-amber-100 text-amber-700 border-amber-200',
    Low: 'bg-green-100 text-green-700 border-green-200',
  };
  const cls = m[urgency ?? ''] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${cls}`}>
      {urgency ?? 'N/A'}
    </span>
  );
}

function DispatchStatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  const m: Record<string, string> = {
    unlocked: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    quoted:   'bg-blue-100 text-blue-700 border-blue-200',
    pending:  'bg-amber-100 text-amber-700 border-amber-200',
  };
  const cls = m[status] ?? 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border capitalize ${cls}`}>
      {status}
    </span>
  );
}

export default function ActiveRFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [items, setItems] = useState<RFQTeaser[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const res = await api.providerRFQ.getTeasers();
        const td = (res as any).data ?? res;
        const list: RFQTeaser[] = td?.teasers ?? td ?? [];
        // Active RFQs = RFQ is open_for_unlock (the admin classification)
        // AND provider has NOT yet quoted it (status != 'quoted')
        // This includes both 'unlocked' (paid) and 'pending' (received teaser, not yet paid)
        const active = (Array.isArray(list) ? list : [])
          .filter(t =>
            t.status !== 'quoted' &&
            (t as any).rfq_status === 'open_for_unlock'
          )
          .sort((a, b) =>
            new Date((b as any).created_at ?? 0).getTime() -
            new Date((a as any).created_at ?? 0).getTime()
          );
        setItems(active);
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    })();
  }, [user]);

  if (authLoading || isLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <FileText className="h-6 w-6 text-blue-600" />
          Active RFQs
        </h1>
        <p className="text-slate-500 text-sm mt-1 max-w-2xl">
          These are RFQs you have unlocked and can respond to. Submit your quote before the opportunity closes.
        </p>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center max-w-lg mx-auto">
          <AlertCircle className="h-10 w-10 mx-auto mb-3 text-slate-300" />
          <p className="text-base font-medium text-slate-500">No active RFQs right now</p>
          <p className="text-sm text-slate-400 mt-1 mb-4">
            Unlocked RFQs where you haven&apos;t submitted a quote yet will appear here.
          </p>
          <Link href="/provider/all-rfqs">
            <Button size="sm" variant="outline">Browse All RFQs</Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((t) => (
            <div
              key={t.rfq_id}
              className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:border-blue-300 hover:shadow-md transition-all flex flex-col"
            >
              {/* Badges */}
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <UrgencyBadge urgency={t.urgency} />
                <DispatchStatusBadge status={t.status} />
                <NdaBadge ndaRequired={t.nda_required} ndaStatus={t.nda_status} />
              </div>

              {/* Description preview */}
              {(t as any).project_description_preview && (
                <p className="text-sm text-slate-700 mb-2 line-clamp-3 flex-1">
                  {(t as any).project_description_preview}
                </p>
              )}

              {/* Tollgates */}
              {t.tollgate_phases && t.tollgate_phases.length > 0 && (
                <p className="text-xs text-slate-500 mb-1">
                  <span className="font-medium">Tollgates:</span> {t.tollgate_phases.join(', ')}
                </p>
              )}

              {/* Date */}
              {(t as any).created_at && (
                <p className="text-xs text-slate-400 mb-3">
                  Received {formatDate((t as any).created_at)}
                </p>
              )}

              <Button
                size="sm"
                onClick={() => router.push(`/provider/rfq/${t.rfq_id}`)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs flex items-center justify-center gap-1 mt-auto"
              >
                Submit Quote <ArrowRight size={12} />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
