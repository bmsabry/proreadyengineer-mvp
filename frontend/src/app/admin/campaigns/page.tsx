'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Mail, Play, Pause, BarChart2, Users, Search,
  Download, Eye, RefreshCw, CheckCircle,
  Loader2, Plus, Zap, ChevronDown, ChevronUp, XCircle, X
} from 'lucide-react';

type CampaignStatus = 'draft' | 'active' | 'paused' | 'completed' | 'cancelled';
type InviteStatus = 'pending' | 'sent' | 'bounced' | 'opened' | 'clicked' | 'registered' | 'unsubscribed';

interface Campaign {
  id: string;
  name: string;
  status: CampaignStatus;
  email_subject: string;
  email_body_html: string;
  founding_slots_total: number;
  founding_slots_claimed: number;
  founding_slots_remaining: number;
  founding_duration_days: number;
  batch_size_per_day: number;
  total_providers: number;
  total_sent: number;
  total_bounced: number;
  total_opened: number;
  total_clicked: number;
  total_registered: number;
  registration_rate_pct: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

interface Invite {
  id: string;
  provider_id: number;
  firm_name: string;
  city: string;
  state: string;
  email: string;
  status: InviteStatus;
  sent_at: string | null;
  registered_at: string | null;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const PG = 50;

const STATUS_CFG: Record<CampaignStatus, { label: string; color: string; bg: string }> = {
  draft:     { label: 'Draft',     color: 'text-slate-600',   bg: 'bg-slate-100' },
  active:    { label: 'Active',    color: 'text-emerald-700', bg: 'bg-emerald-100' },
  paused:    { label: 'Paused',    color: 'text-amber-700',   bg: 'bg-amber-100' },
  completed: { label: 'Completed', color: 'text-blue-700',    bg: 'bg-blue-100' },
  cancelled: { label: 'Cancelled', color: 'text-red-700',     bg: 'bg-red-100' },
};

const INV_CFG: Record<InviteStatus, { label: string; dot: string }> = {
  pending:      { label: 'Pending',      dot: 'bg-slate-400' },
  sent:         { label: 'Sent',         dot: 'bg-blue-500' },
  opened:       { label: 'Opened',       dot: 'bg-amber-500' },
  clicked:      { label: 'Clicked',      dot: 'bg-violet-500' },
  registered:   { label: 'Registered',   dot: 'bg-emerald-500' },
  bounced:      { label: 'Bounced',      dot: 'bg-red-500' },
  unsubscribed: { label: 'Unsubscribed', dot: 'bg-slate-500' },
};

const VARS = [
  '{{firm_name}}', '{{city}}', '{{state}}', '{{specialty}}',
  '{{invite_link}}', '{{founding_slots_remaining}}', '{{unsubscribe_link}}',
];

async function apiFetch(path: string, opts: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const authH: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...authH, ...((opts.headers || {}) as Record<string, string>) },
    ...opts,
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((errData as { detail?: string }).detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function StatCard({
  label, value, sub, color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  const colorClass = color || 'text-[#0F2B54]';
  return (
    <div className="bg-slate-50 rounded-xl p-4 border border-slate-200">
      <div className={`text-2xl font-bold ${colorClass}`}>{value}</div>
      <div className="text-xs font-medium text-slate-600 mt-0.5">{label}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function SectionCard({
  title, icon, children, collapsible, defaultOpen,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
}) {
  const Icon = icon;
  const [open, setOpen] = useState(defaultOpen !== false);
  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div
        className={`flex items-center gap-3 px-6 py-4 border-b border-slate-100${collapsible ? ' cursor-pointer hover:bg-slate-50' : ''}`}
        onClick={() => { if (collapsible) setOpen((o) => !o); }}
      >
        <div className="w-8 h-8 rounded-lg bg-[#0F2B54]/10 flex items-center justify-center">
          <Icon className="h-4 w-4 text-[#0F2B54]" />
        </div>
        <h2 className="font-semibold text-[#0F2B54] text-sm flex-1">{title}</h2>
        {collapsible && (open
          ? <ChevronUp className="h-4 w-4 text-slate-400" />
          : <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </div>
      {open && <div className="p-6">{children}</div>}
    </div>
  );
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [cam, setCam] = useState<Campaign | null>(null);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [invTotal, setInvTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [statusF, setStatusF] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [flashErr, setFlashErr] = useState<string | null>(null);
  const [flashOk, setFlashOk] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [fName, setFName] = useState('Provider Founding Member Campaign 2026');
  const [fSubj, setFSubj] = useState('You are invited to join ProMechDirectory - Founding Member Offer');
  const [fBody, setFBody] = useState('');
  const [fSlots, setFSlots] = useState(250);
  const [fDays, setFDays] = useState(90);
  const [fBatch, setFBatch] = useState(150);
  const [targetMode, setTargetMode] = useState<'all' | 'selected'>('all');
  const [firmSearch, setFirmSearch] = useState('');
  const [firmResults, setFirmResults] = useState<{id: number; firm_name: string; city: string; state: string; primary_specialty: string; email: string}[]>([]);
  const [selectedFirms, setSelectedFirms] = useState<{id: number; firm_name: string; city: string; state: string; email: string}[]>([]);
  const [firmSearching, setFirmSearching] = useState(false);
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [searchErr, setSearchErr] = useState<string | null>(null);
  const [firmSearched, setFirmSearched] = useState(false);


  const flash = (msg: string, type: 'ok' | 'err') => {
    if (type === 'ok') {
      setFlashOk(msg);
      setTimeout(() => setFlashOk(null), 4000);
    } else {
      setFlashErr(msg);
      setTimeout(() => setFlashErr(null), 6000);
    }
  };

  // Debounced provider search for campaign targeting
  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!firmSearch.trim() || targetMode !== 'selected') {
      setFirmResults([]);
      setSearchErr(null);
      setFirmSearched(false);
      return;
    }
    searchDebounceRef.current = setTimeout(async () => {
      setFirmSearching(true);
      setSearchErr(null);
      setFirmSearched(false);
      try {
        const d = await apiFetch('/api/v1/admin/campaigns/provider-search?q=' + encodeURIComponent(firmSearch.trim()));
        setFirmResults(d.providers || []);
        setFirmSearched(true);
      } catch (e) {
        setFirmResults([]);
        setSearchErr((e as Error).message || 'Search failed');
      } finally {
        setFirmSearching(false);
      }
    }, 300);
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [firmSearch, targetMode]);
  const loadDetail = useCallback(async (id: string) => {
    try {
      const d = await apiFetch(`/api/v1/admin/campaigns/${id}`);
      setCam(d.campaign);
    } catch (e) {
      flash((e as Error).message, 'err');
    }
  }, []);

  const loadCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/api/v1/admin/campaigns');
      const list: Campaign[] = d.campaigns || [];
      setCampaigns(list);
      if (list.length > 0 && !cam) {
        await loadDetail(list[0].id);
      }
    } catch (e) {
      flash((e as Error).message, 'err');
    } finally {
      setLoading(false);
    }
  }, [cam, loadDetail]);

  const loadInvites = useCallback(async (cid: string, pg: number, sf: string) => {
    try {
      const params = new URLSearchParams({ skip: String(pg * PG), limit: String(PG) });
      if (sf) params.set('status', sf);
      const d = await apiFetch(`/api/v1/admin/campaigns/${cid}/invites?${params}`);
      setInvites(d.invites || []);
      setInvTotal(d.total || 0);
    } catch (e) {
      flash((e as Error).message, 'err');
    }
  }, []);

  useEffect(() => { loadCampaigns(); }, []);

  useEffect(() => {
    if (cam) {
      loadInvites(cam.id, page, statusF);
    }
  }, [cam, page, statusF]);

  const doAction = async (action: string, cid: string) => {
    setBusy(action);
    try {
      const d = await apiFetch(`/api/v1/admin/campaigns/${cid}/${action}`, { method: 'POST' });
      flash(d.message || `Campaign ${action}ed`, 'ok');
      await loadDetail(cid);
      await loadCampaigns();
    } catch (e) {
      flash((e as Error).message, 'err');
    } finally {
      setBusy(null);
    }
  };

  const createCampaign = async () => {
    setBusy('create');
    try {
      const d = await apiFetch('/api/v1/admin/campaigns', {
        method: 'POST',
        body: JSON.stringify({
          name: fName,
          email_subject: fSubj,
          email_body_html: fBody,
          founding_slots_total: fSlots,
          founding_duration_days: fDays,
          batch_size_per_day: fBatch,
          target_provider_ids: targetMode === 'selected' ? selectedFirms.map((f) => f.id) : [],
        }),
      });
      flash(`Campaign created - ${d.campaign.total_providers} eligible invites`, 'ok');
      setCampaigns((prev) => [d.campaign, ...prev]);
      await loadDetail(d.campaign.id);
    } catch (e) {
      flash((e as Error).message, 'err');
    } finally {
      setBusy(null);
    }
  };

  const doPreview = async () => {
    if (!cam) return;
    setBusy('preview');
    try {
      const d = await apiFetch(`/api/v1/admin/campaigns/${cam.id}/preview-email`, {
        method: 'POST',
        body: JSON.stringify({
          firm_name: 'Acme Engineering LLC',
          city: 'Houston',
          state: 'TX',
          specialty: 'Structural Fatigue Analysis',
        }),
      });
      setPreviewHtml(d.html_preview);
      setShowPreview(true);
    } catch (e) {
      flash((e as Error).message, 'err');
    } finally {
      setBusy(null);
    }
  };

  const totalPages = Math.ceil(invTotal / PG);
  const scfg = cam ? STATUS_CFG[cam.status] : null;
  const sentPct = cam && cam.total_providers > 0
    ? Math.min(100, (cam.total_sent / cam.total_providers) * 100)
    : 0;
  const slotPct = cam && cam.founding_slots_total > 0
    ? Math.min(100, (cam.founding_slots_claimed / cam.founding_slots_total) * 100)
    : 0;
  const invStatusTabs = ['', 'pending', 'sent', 'opened', 'clicked', 'registered', 'bounced', 'unsubscribed'];

  return (
    <div className="min-h-screen bg-slate-50">

      {/* Header */}
      <div style={{ background: 'linear-gradient(135deg, #0F2B54 0%, #1a3a6b 100%)' }} className="px-8 py-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-white/15 flex items-center justify-center">
              <Mail className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Campaign Command Room</h1>
              <p className="text-white/60 text-sm">Mass email invite system · Provider onboarding · Founding member offer</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {campaigns.length > 0 && (
              <select
                className="bg-white/10 text-white text-sm rounded-lg px-3 py-2 border border-white/20 focus:outline-none"
                value={cam?.id || ''}
                onChange={(e) => loadDetail(e.target.value)}
              >
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id} className="text-slate-900">{c.name}</option>
                ))}
              </select>
            )}
            <button
              onClick={loadCampaigns}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm transition-all"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Toast notifications */}
      {flashOk && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 bg-emerald-600 text-white px-4 py-3 rounded-xl shadow-lg text-sm">
          <CheckCircle className="h-4 w-4" />{flashOk}
        </div>
      )}
      {flashErr && (
        <div className="fixed top-4 right-4 z-50 flex items-center gap-2 bg-red-600 text-white px-4 py-3 rounded-xl shadow-lg text-sm">
          <XCircle className="h-4 w-4" />Error: {flashErr}
        </div>
      )}

      {/* Email Preview Modal */}
      {showPreview && previewHtml && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setShowPreview(false)}
        >
          <div
            className="bg-white rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h3 className="font-semibold text-[#0F2B54]">Email Preview</h3>
              <button onClick={() => setShowPreview(false)} className="text-slate-400 hover:text-slate-600 text-xl">&times;</button>
            </div>
            <div style={{ maxHeight: '72vh', overflowY: 'auto' }}>
              <iframe srcDoc={previewHtml} style={{ width: '100%', height: '640px', border: 'none' }} title="Email preview" />
            </div>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-8 py-6 space-y-6">

        {/* Section 1: Email Composer */}
        <SectionCard title="Email Composer" icon={Mail} collapsible defaultOpen>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Subject Line</label>
              <input
                type="text"
                value={fSubj}
                onChange={(e) => setFSubj(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20"
                placeholder="Email subject line..."
              />
            </div>
            <div>
              <div className="flex items-start justify-between mb-1.5">
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider">HTML Body</label>
                <div className="flex flex-wrap gap-1 justify-end">
                  {VARS.map((v) => (
                    <span
                      key={v}
                      onClick={() => setFBody((b) => b + v)}
                      className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded cursor-pointer hover:bg-[#0F2B54]/10 transition-colors"
                    >
                      {v}
                    </span>
                  ))}
                </div>
              </div>
              <textarea
                value={fBody}
                onChange={(e) => setFBody(e.target.value)}
                rows={10}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20 resize-y"
                placeholder="Leave blank to use the default branded template. Click variable chips above to insert them."
              />
              <p className="text-xs text-slate-400 mt-1">Leave blank to use the default ProMechDirectory branded template.</p>
            </div>
            {cam && (
              <button
                onClick={doPreview}
                disabled={busy === 'preview'}
                className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors"
              >
                {busy === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                Preview Email
              </button>
            )}
          </div>
        </SectionCard>

        {/* Section 2: Campaign Config */}
        <SectionCard title="Campaign Configuration" icon={Zap} collapsible defaultOpen>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Campaign Name</label>
              <input
                type="text"
                value={fName}
                onChange={(e) => setFName(e.target.value)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Founding Slots</label>
              <input type="number" value={fSlots} onChange={(e) => setFSlots(Number(e.target.value))} min={1} max={10000}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20" />
              <p className="text-xs text-slate-400 mt-1">First N registrants get free access</p>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Free Duration (days)</label>
              <input type="number" value={fDays} onChange={(e) => setFDays(Number(e.target.value))} min={1} max={365}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">Batch Size / Day</label>
              <input type="number" value={fBatch} onChange={(e) => setFBatch(Number(e.target.value))} min={1} max={1000}
                className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20" />
              <p className="text-xs text-slate-400 mt-1">Emails sent per batch</p>
            </div>
          </div>

          {/* ── Target Audience ── */}
          <div className="mt-5 pt-4 border-t border-slate-100">
            <label className="block text-xs font-semibold text-slate-500 mb-3 uppercase tracking-wider">
              Target Audience
            </label>
            <div className="flex gap-2 mb-3">
              <button
                type="button"
                onClick={() => setTargetMode('all')}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors border ${
                  targetMode === 'all'
                    ? 'bg-[#0F2B54] text-white border-[#0F2B54]'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                All Firms
              </button>
              <button
                type="button"
                onClick={() => setTargetMode('selected')}
                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors border ${
                  targetMode === 'selected'
                    ? 'bg-[#0F2B54] text-white border-[#0F2B54]'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                Selected Firms
              </button>
            </div>

            {targetMode === 'all' && (
              <p className="text-sm text-slate-500 bg-slate-50 rounded-lg px-4 py-3 border border-slate-100">
                Campaign will be sent to all eligible providers with a valid email who have not registered yet.
              </p>
            )}

            {targetMode === 'selected' && (
              <div className="space-y-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={firmSearch}
                    onChange={(e) => setFirmSearch(e.target.value)}
                    placeholder="Search firm by name..."
                    className="w-full pl-9 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/20"
                  />
                  {firmSearching && (
                    <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-slate-400" />
                  )}
                  {firmResults.length > 0 && (
                    <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                      {firmResults.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => {
                            if (!selectedFirms.find((f) => f.id === r.id)) {
                              setSelectedFirms((prev) => [...prev, { id: r.id, firm_name: r.firm_name, city: r.city, state: r.state, email: r.email || "" }]);
                            } else {
                              setSelectedFirms((prev) => prev.filter((f) => f.id !== r.id));
                            }
                          }}
                          className={`w-full text-left px-4 py-2.5 hover:bg-slate-50 border-b border-slate-50 last:border-0 flex items-center justify-between ${
                            selectedFirms.find((f) => f.id === r.id) ? 'bg-[#0F2B54]/5' : ''
                          }`}
                        >
                          <div>
                            <div className="text-sm font-medium text-slate-800">{r.firm_name}</div>
                            <div className="text-xs text-slate-400">
                              {r.city}{r.city && r.state ? ', ' : ''}{r.state}
                              {r.primary_specialty ? ' · ' + r.primary_specialty : ''}
                            </div>
                            {r.email && (
                              <div className="text-xs text-blue-500 font-mono mt-0.5">{r.email}</div>
                            )}
                          </div>
                          {selectedFirms.find((f) => f.id === r.id) && (
                            <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0 ml-2" />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                  {searchErr && (
                    <p className="mt-1 text-xs text-red-600 flex items-center gap-1">
                      <XCircle className="h-3 w-3" /> {searchErr}
                    </p>
                  )}
                  {firmSearched && !firmSearching && firmResults.length === 0 && !searchErr && (
                    <p className="mt-1 text-xs text-slate-400">No firms found matching &ldquo;{firmSearch}&rdquo;</p>
                  )}
                </div>

                {selectedFirms.length > 0 && (
                  <div>
                    <p className="text-xs text-slate-500 mb-2">
                      {selectedFirms.length} firm{selectedFirms.length !== 1 ? 's' : '' } selected
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {selectedFirms.map((f) => (
                        <span key={f.id} className="inline-flex items-center gap-1.5 bg-[#0F2B54]/10 text-[#0F2B54] text-xs font-medium px-3 py-1.5 rounded-full">
                          {f.firm_name}
                          {f.city ? ', ' + f.city : ''}
                          <button
                            type="button"
                            onClick={() => setSelectedFirms((prev) => prev.filter((x) => x.id !== f.id))}
                            className="ml-0.5 hover:text-red-600 transition-colors"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {selectedFirms.length === 0 && (
                  <p className="text-xs text-slate-400">Search and select firms above to build your target list.</p>
                )}
              </div>
            )}
          </div>

          <div className="mt-5 pt-4 border-t border-slate-100">
            <button
              onClick={createCampaign}
              disabled={busy === 'create'}
              className="flex items-center gap-2 px-6 py-2.5 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white text-sm font-semibold rounded-lg transition-colors disabled:opacity-60"
            >
              {busy === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create Campaign
            </button>
          </div>
        </SectionCard>

        {/* Section 3: Launch Control */}
        {cam && scfg && (
          <SectionCard title="Launch Control" icon={Play}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className={`inline-flex px-3 py-1 rounded-full text-sm font-semibold ${scfg.bg} ${scfg.color}`}>
                    {scfg.label}
                  </span>
                  <span className="text-sm text-slate-500 font-medium">{cam.name}</span>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                    <span>Emails Sent</span>
                    <span className="font-semibold">{cam.total_sent.toLocaleString()} / {cam.total_providers.toLocaleString()}</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2.5">
                    <div className="bg-[#0F2B54] h-2.5 rounded-full transition-all" style={{ width: `${sentPct}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs text-slate-500 mb-1.5">
                    <span>Founding Slots</span>
                    <span className="font-semibold text-emerald-700">{cam.founding_slots_claimed} / {cam.founding_slots_total}</span>
                  </div>
                  <div className="w-full bg-emerald-50 rounded-full h-2.5">
                    <div className="bg-emerald-500 h-2.5 rounded-full transition-all" style={{ width: `${slotPct}%` }} />
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-3 items-start">
                {(cam.status === 'draft' || cam.status === 'paused') && (
                  <button
                    onClick={() => doAction('start', cam.id)}
                    disabled={!!busy}
                    className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-lg disabled:opacity-60"
                  >
                    {busy === 'start' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    {cam.status === 'paused' ? 'Resume' : 'Start Campaign'}
                  </button>
                )}
                {cam.status === 'active' && (
                  <button
                    onClick={() => doAction('pause', cam.id)}
                    disabled={!!busy}
                    className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg disabled:opacity-60"
                  >
                    {busy === 'pause' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pause className="h-4 w-4" />}
                    Pause
                  </button>
                )}
                {cam.status !== 'cancelled' && cam.status !== 'completed' && (
                  <button
                    onClick={() => doAction('cancel', cam.id)}
                    disabled={!!busy}
                    className="flex items-center gap-2 px-5 py-2.5 bg-red-100 hover:bg-red-200 text-red-700 text-sm font-semibold rounded-lg disabled:opacity-60"
                  >
                    {busy === 'cancel' ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                    Cancel
                  </button>
                )}
              </div>
            </div>
          </SectionCard>
        )}

        {/* Section 4: Analytics */}
        {cam && (
          <SectionCard title="Analytics" icon={BarChart2}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Total Providers" value={cam.total_providers.toLocaleString()} />
              <StatCard label="Emails Sent" value={cam.total_sent.toLocaleString()} color="text-blue-700" />
              <StatCard label="Bounced" value={cam.total_bounced.toLocaleString()} color="text-red-600" />
              <StatCard label="Opened" value={cam.total_opened.toLocaleString()} color="text-amber-700" />
              <StatCard label="Clicked" value={cam.total_clicked.toLocaleString()} color="text-violet-700" />
              <StatCard label="Registered" value={cam.total_registered.toLocaleString()} color="text-emerald-700" />
              <StatCard
                label="Founding Slots"
                value={`${cam.founding_slots_claimed} / ${cam.founding_slots_total}`}
                sub={`${cam.founding_slots_remaining} remaining`}
                color="text-emerald-700"
              />
              <StatCard
                label="Registration Rate"
                value={`${cam.registration_rate_pct}%`}
                sub={cam.total_sent > 0 ? `${cam.total_registered} of ${cam.total_sent} sent` : 'No emails yet'}
                color={cam.registration_rate_pct >= 5 ? 'text-emerald-700' : 'text-slate-600'}
              />
            </div>
          </SectionCard>
        )}

        {/* Section 5: Invite Log */}
        {cam && (
          <SectionCard title={`Invite Log (${invTotal.toLocaleString()} total)`} icon={Users}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex gap-2 flex-wrap">
                {invStatusTabs.map((s) => {
                  const tabLabel = s === '' ? 'All' : (INV_CFG[s as InviteStatus]?.label || s);
                  return (
                    <button
                      key={s}
                      onClick={() => { setStatusF(s); setPage(0); }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${statusF === s ? 'bg-[#0F2B54] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                    >
                      {tabLabel}
                    </button>
                  );
                })}
              </div>
              <button
                onClick={() => window.open(`${API_BASE}/api/v1/admin/campaigns/${cam.id}/invites/export`, '_blank')}
                className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg"
              >
                <Download className="h-3.5 w-3.5" /> Export CSV
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    {['Firm Name', 'City', 'State', 'Email', 'Status', 'Sent At', 'Registered At'].map((h) => (
                      <th key={h} className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider py-2 pr-4">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {invites.length === 0 && (
                    <tr><td colSpan={7} className="py-8 text-center text-slate-400 text-sm">No invites to display</td></tr>
                  )}
                  {invites.map((inv) => {
                    const sc = INV_CFG[inv.status] || { label: inv.status, dot: 'bg-slate-400' };
                    return (
                      <tr key={inv.id} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2.5 pr-4 font-medium text-slate-800 max-w-[180px] truncate">{inv.firm_name || '—'}</td>
                        <td className="py-2.5 pr-4 text-slate-500">{inv.city || '—'}</td>
                        <td className="py-2.5 pr-4 text-slate-500">{inv.state || '—'}</td>
                        <td className="py-2.5 pr-4 text-slate-500 font-mono text-xs max-w-[180px] truncate">{inv.email || '—'}</td>
                        <td className="py-2.5 pr-4">
                          <span className="inline-flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${sc.dot}`} />
                            <span className="text-xs font-medium text-slate-600">{sc.label}</span>
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-slate-400 text-xs">{inv.sent_at ? new Date(inv.sent_at).toLocaleDateString() : '—'}</td>
                        <td className="py-2.5 text-slate-400 text-xs">{inv.registered_at ? new Date(inv.registered_at).toLocaleDateString() : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-100">
                <p className="text-xs text-slate-400">Page {page + 1} of {totalPages} ({invTotal} total)</p>
                <div className="flex gap-2">
                  <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0} className="px-3 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded disabled:opacity-40">Previous</button>
                  <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1} className="px-3 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded disabled:opacity-40">Next</button>
                </div>
              </div>
            )}
          </SectionCard>
        )}

      </div>
    </div>
  );

}
