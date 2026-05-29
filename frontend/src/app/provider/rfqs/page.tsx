'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser } from '@/types';
import { Button } from '@/components/ui/button';
import { Mail, ArrowRight, Lock } from 'lucide-react';
import NdaBadge from '@/components/ui/NdaBadge';

type RFQFilterTab = 'all' | 'pending' | 'unlocked' | 'quoted';

function UrgencyBadge({ urgency }: { urgency?: string }) {
  const m: Record<string,string> = {
    High:'bg-red-100 text-red-700 border-red-200',
    Intermediate:'bg-amber-100 text-amber-700 border-amber-200',
    Low:'bg-green-100 text-green-700 border-green-200',
  };
  const c = m[urgency||''] || 'bg-slate-100 text-slate-600 border-slate-200';
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${c}`}>{urgency||'N/A'}</span>;
}

const TABS: { key: RFQFilterTab; label: string }[] = [
  { key:'all', label:'All' }, { key:'pending', label:'Pending' },
  { key:'unlocked', label:'Unlocked' }, { key:'quoted', label:'Quoted' },
];

export default function RFQsPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [teasers, setTeasers] = useState<RFQTeaser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMembership, setHasMembership] = useState<boolean|null>(null);
  const [activeTab, setActiveTab] = useState<RFQFilterTab>('all');

  useEffect(() => {
    const load = async () => {
      try {
        const r = await api.providerRFQ.getTeasers();
        const d = r.data as any;
        const list = d?.teasers || d || [];
        setHasMembership(d?.has_membership !== undefined ? d.has_membership : (list.length > 0 ? true : null));
        setTeasers(Array.isArray(list) ? list : []);
      } catch(e) { console.error(e); } finally { setIsLoading(false); }
    };
    if (user) load();
  }, [user]);

  const filtered = teasers.filter(t => {
    if (activeTab === 'all') return true;
    if (activeTab === 'pending') return t.status !== 'unlocked' && t.status !== 'quoted';
    return t.status === activeTab;
  });

  if (authLoading || isLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="mb-6"><h1 className="text-2xl font-bold text-slate-900">RFQs Received</h1><p className="text-slate-500 text-sm mt-1">All project requests matching your profile</p></div>
        <div className="flex gap-1 mb-6 bg-white rounded-xl border border-slate-200 p-1">
          {TABS.map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)} className={`flex-1 py-1.5 px-3 rounded-lg text-sm font-medium transition-colors ${activeTab === tab.key ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'}`}>{tab.label}</button>
          ))}
        </div>
        {filtered.length === 0 && hasMembership === false ? (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-slate-700">Choose how to list your firm to start receiving RFQs:</p>
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><div className="flex items-center gap-2 mb-1.5"><span className="rounded-full px-2.5 py-0.5 text-xs font-semibold bg-emerald-600 text-white">FREE</span><h3 className="text-sm font-semibold text-emerald-900">Find &amp; Claim Existing Listing</h3></div><p className="text-xs text-emerald-700 mb-3">Search our database of 5,400+ firms. If yours is listed, claim it instantly.</p><Link href="/provider/claim"><Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs w-full rounded-xl">Search My Firm</Button></Link></div>
            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4"><div className="flex items-center gap-2 mb-1.5"><span className="rounded-full px-2.5 py-0.5 text-xs font-semibold bg-[#0F2B54] text-white">$100</span><h3 className="text-sm font-semibold text-blue-900">Self-Service New Listing</h3></div><p className="text-xs text-blue-700 mb-3">Create your own profile with description, specialties, and notable projects.</p><Link href="/provider/add-firm"><Button size="sm" className="bg-[#0F2B54] hover:bg-[#1a3a6b] text-white text-xs w-full rounded-xl">Create My Listing</Button></Link></div>
            <div className="rounded-2xl border border-purple-200 bg-purple-50 p-4"><div className="flex items-center gap-2 mb-1.5"><span className="rounded-full px-2.5 py-0.5 text-xs font-semibold bg-purple-600 text-white">$750</span><h3 className="text-sm font-semibold text-purple-900">AI-Assisted Premium Listing</h3></div><p className="text-xs text-purple-700 mb-3">Our team builds a comprehensive, optimized profile from your materials.</p><Link href="/provider/add-firm?tier=premium"><Button size="sm" className="bg-purple-600 hover:bg-purple-700 text-white text-xs w-full rounded-xl">Request AI Listing</Button></Link></div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-10 text-center"><Mail className="h-10 w-10 mx-auto mb-3 text-slate-300" /><p className="text-slate-500">No RFQs found for this filter.</p></div>
        ) : (
          <div className="space-y-4">
            {filtered.map(t => (
              <div key={t.rfq_id} className="rounded-xl border border-slate-200 bg-white shadow-sm p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <p className="text-sm font-semibold text-slate-900">RFQ #{String(t.rfq_id).slice(0,8)}&hellip;</p>
                      <UrgencyBadge urgency={t.urgency} />
                      <NdaBadge ndaRequired={t.nda_required} ndaStatus={t.nda_status} />
                      {t.status === 'unlocked' && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">Unlocked</span>}
                      {t.status === 'quoted' && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700">Quoted</span>}
                    </div>
                    <p className="text-xs text-slate-500">Tollgates: {t.tollgate_phases?.join(', ') || 'N/A'}</p>
                  </div>
                  {(t.status === 'unlocked' || t.status === 'quoted') ? (
                    <Button size="sm" variant="outline" onClick={() => router.push('/provider/rfq/' + t.rfq_id)} className="gap-1 rounded-xl text-xs shrink-0">View Details <ArrowRight className="h-3 w-3" /></Button>
                  ) : (
                    <Button size="sm" onClick={() => router.push('/provider/rfq/' + t.rfq_id)} className="bg-[#0F2B54] hover:bg-[#1a3a6b] text-white gap-1 rounded-xl text-xs shrink-0"><Lock className="h-3 w-3" /> View &amp; Unlock ($50)</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
