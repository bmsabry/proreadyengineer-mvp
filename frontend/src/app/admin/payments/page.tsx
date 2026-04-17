'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRequireAuth } from '../../../hooks/useAuth';
import {
  DollarSign,
  TrendingUp,
  XCircle,
  RefreshCw,
  Download,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface AnalyticsData {
  total_revenue: number;
  total_this_month: number;
  total_failed_30d: number;
  total_refunded?: number;
  monthly_series: { month: string; revenue: number }[];
  by_purpose: { purpose: string; total: number; count: number }[];
  by_purpose_all?: { purpose: string; total: number; count: number }[];
}

interface Transaction {
  id: string;
  initiated_at: string | null;
  confirmed_at: string | null;
  failed_at: string | null;
  purpose: string;
  amount: number;
  currency: string;
  payment_status: string;
  provider_name: string;
  external_payment_id: string | null;
  external_checkout_id: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  user_email: string | null;
  user_name: string | null;
}

interface TransactionPage {
  items: Transaction[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

interface LLMEntry {
  label: string;
  available: boolean;
  model?: string;
  base_url?: string;
  status?: string;
  error?: string;
  note?: string;
  billing_source?: string;
  usage_total_usd?: number;
  usage_daily_usd?: number;
  usage_monthly_usd?: number;
  limit_remaining_usd?: number;
  billing_error?: string;
}

interface LLMsSpend {
  llm2?: LLMEntry;
  llm3?: LLMEntry;
  available?: boolean;
  error?: string;
}

interface AWSSpend {
  available: boolean;
  error?: string;
  total_this_month?: number;
  services?: { service: string; amount: number }[];
  period_start?: string;
  period_end?: string;
}

interface RenderService {
  id: string | null;
  name: string | null;
  type: string | null;
  status: string | null;
  updated_at: string | null;
  created_at: string | null;
}

interface RenderSpend {
  available: boolean;
  error?: string;
  services?: RenderService[];
  manual_budget?: number | null;
}

function fmtCurrency(val: number | null | undefined): string {
  if (val === null || val === undefined) return '$-';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtPurpose(raw: string): string {
  const map: { [k: string]: string } = {
    rfq_unlock: 'RFQ Unlock',
    nda_fee: 'NDA Fee',
    provider_profile_subscription: 'Provider Profile',
    advertisement_subscription: 'Ad Subscription',
    search_subscription: 'Search Subscription',
    provider_annual_subscription: 'Annual Subscription',
  };
  return map[raw] || raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtShortId(id: string | null | undefined): string {
  if (!id) return '-';
  return id.length > 16 ? id.substring(0, 8) + '...' + id.substring(id.length - 6) : id;
}

function fmtMonth(ym: string): string {
  const parts = ym.split('-');
  const y = parts[0];
  const m = parts[1];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const idx = parseInt(m, 10) - 1;
  const monthName = months[idx] || m;
  return monthName + ' ' + y.substring(2);
}

const PURPOSE_COLORS: { [k: string]: string } = {
  rfq_unlock: '#1e3a5f',
  nda_fee: '#6b21a8',
  provider_profile_subscription: '#065f46',
  provider_annual_subscription: '#1d4ed8',
  advertisement_subscription: '#92400e',
  search_subscription: '#374151',
};

function purposeColor(p: string): string {
  return PURPOSE_COLORS[p] || '#6b7280';
}

function statusBadgeClass(status: string): string {
  if (status === 'completed') return 'bg-emerald-100 text-emerald-800';
  if (status === 'failed') return 'bg-red-100 text-red-800';
  if (status === 'initiated' || status === 'processing') return 'bg-amber-100 text-amber-800';
  if (status === 'refunded') return 'bg-blue-100 text-blue-800';
  return 'bg-gray-100 text-gray-700';
}

function getAuthHeader(): { [k: string]: string } {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: 'Bearer ' + token } : {};
}

interface KpiCardProps {
  title: string;
  value: string;
  icon: React.ElementType;
  colorClass: string;
  bgClass: string;
}

function KpiCard(props: KpiCardProps) {
  const Icon = props.icon;
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${props.bgClass}`}>
        <Icon className={`h-6 w-6 ${props.colorClass}`} />
      </div>
      <div>
        <p className="text-sm text-gray-500 font-medium">{props.title}</p>
        <p className="text-2xl font-bold text-gray-900 mt-0.5">{props.value}</p>
      </div>
    </div>
  );
}

interface BarChartProps {
  series: { month: string; revenue: number }[];
}

function MonthlyBarChart(props: BarChartProps) {
  const maxVal = Math.max(...props.series.map((s) => s.revenue), 1);
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <h3 className="text-base font-semibold text-gray-800 mb-4">Monthly Revenue (last 6 months)</h3>
      <div className="flex items-end gap-3 h-40">
        {props.series.map((s) => {
          const pct = Math.round((s.revenue / maxVal) * 100);
          const barHeight = String(pct) + '%';
          const barLabel = s.revenue > 0 ? fmtCurrency(s.revenue) : '$0';
          return (
            <div key={s.month} className="flex flex-col items-center flex-1 h-full justify-end">
              <span className="text-xs font-medium text-gray-600 mb-1">{barLabel}</span>
              <div
                className="w-full rounded-t-md bg-blue-500 transition-all"
                style={{ height: barHeight, minHeight: '4px' }}
              />
              <span className="text-xs text-gray-400 mt-1">{fmtMonth(s.month)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface LLMsCardProps {
  data: LLMsSpend | null;
  loading: boolean;
  onRefresh: () => void;
}

function LLMsCard(props: LLMsCardProps) {
  const loading = props.loading;
  const onRefresh = props.onRefresh;
  const d = props.data;
  const llm2 = d?.llm2;
  const llm3 = d?.llm3;

  function renderRow(p: LLMEntry) {
    const hasSpend = p.usage_monthly_usd !== undefined && p.usage_monthly_usd !== null;
    const hasDailySpend = p.usage_daily_usd !== undefined && p.usage_daily_usd !== null;
    const monthlyVal = (p.usage_monthly_usd ?? 0).toFixed(4);
    const dailyVal = (p.usage_daily_usd ?? 0).toFixed(4);
    const hasLimit = p.limit_remaining_usd !== null && p.limit_remaining_usd !== undefined;
    const limitVal = (p.limit_remaining_usd ?? 0).toFixed(2);
    const isOk = p.available;
    const errText = p.error || 'Not configured';
    return (
      <div key={p.label} className="py-3 border-b border-gray-100 last:border-0">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-semibold text-gray-700">{p.label}</p>
            {p.model && <p className="text-xs text-gray-400 font-mono mt-0.5">{p.model}</p>}
            {p.note && <p className="text-xs text-blue-500 mt-0.5">{p.note}</p>}
          </div>
          {isOk ? (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">Connected</span>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded-full">{errText}</span>
          )}
        </div>
        {hasSpend && (
          <div className="mt-2 flex gap-4 bg-gray-50 rounded-lg p-2">
            <div>
              <p className="text-xs text-gray-400">This Month</p>
              <p className="text-sm font-bold text-emerald-700">${monthlyVal}</p>
            </div>
            {hasDailySpend && (
              <div>
                <p className="text-xs text-gray-400">Today</p>
                <p className="text-sm font-bold text-blue-700">${dailyVal}</p>
              </div>
            )}
            {hasLimit && (
              <div>
                <p className="text-xs text-gray-400">Limit Remaining</p>
                <p className="text-sm font-bold text-gray-700">${limitVal}</p>
              </div>
            )}
            {p.billing_source && (
              <div className="ml-auto">
                <span className="text-xs text-gray-400 bg-white border border-gray-200 px-1.5 py-0.5 rounded">{p.billing_source}</span>
              </div>
            )}
          </div>
        )}
        {p.billing_error && (
          <p className="text-xs text-amber-600 mt-1">Billing: {p.billing_error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0F2B54, #1a3a6b)' }}>
            <span className="text-white text-xs font-bold">AI</span>
          </div>
          <h3 className="text-base font-semibold text-gray-800">LLMs Spend</h3>
        </div>
        <button onClick={onRefresh} disabled={loading} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : !d ? (
        <div className="text-center py-4">
          <AlertCircle className="h-8 w-8 text-amber-400 mx-auto mb-2" />
          <p className="text-xs text-gray-500">No LLM data available</p>
        </div>
      ) : (
        <div>
          {llm2 && renderRow(llm2)}
          {llm3 && renderRow(llm3)}
          {!llm2 && !llm3 && (
            <div className="text-center py-4">
              <p className="text-xs text-gray-500">Configure LLM API keys in Admin Settings</p>
            </div>
          )}
        </div>
      )}
      <p className="text-xs text-gray-400 mt-1">Connectivity status only — billing data requires admin API key</p>
    </div>
  );
}

interface AWSCardProps {
  data: AWSSpend | null;
  loading: boolean;
  onRefresh: () => void;
}

function AWSCard(props: AWSCardProps) {
  const available = props.data?.available ?? false;
  const total = props.data?.total_this_month;
  const services = props.data?.services ?? [];
  const top3 = services.slice(0, 3);
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-orange-500" />
          <h3 className="text-base font-semibold text-gray-800">AWS Infrastructure</h3>
        </div>
        <button onClick={props.onRefresh} className="text-gray-400 hover:text-gray-600 transition-colors" title="Refresh">
          <RefreshCw className={`h-4 w-4 ${props.loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {props.loading && <p className="text-sm text-gray-400">Loading...</p>}
      {!props.loading && !available && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-gray-400" />
            <span className="text-sm text-gray-500">No Credentials</span>
          </div>
          {props.data?.error && <p className="text-xs text-gray-400">{props.data.error}</p>}
        </div>
      )}
      {!props.loading && available && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            <span className="text-sm font-medium text-emerald-700">Active</span>
          </div>
          {total !== undefined && (
            <div>
              <p className="text-xs text-gray-500">Total This Month</p>
              <p className="text-xl font-bold text-gray-900">{fmtCurrency(total)}</p>
            </div>
          )}
          {top3.length > 0 && (
            <div className="space-y-1.5">
              {top3.map((svc) => (
                <div key={svc.service} className="flex justify-between text-xs">
                  <span className="text-gray-600 truncate max-w-[140px]">{svc.service}</span>
                  <span className="font-medium text-gray-800">{fmtCurrency(svc.amount)}</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-amber-600 mt-2">Requires ce:GetCostAndUsage IAM permission</p>
        </div>
      )}
    </div>
  );
}

interface RenderCardProps {
  data: RenderSpend | null;
  loading: boolean;
  onRefresh: () => void;
}

function RenderCard(props: RenderCardProps) {
  const available = props.data?.available ?? false;
  const services = props.data?.services ?? [];
  const budget = props.data?.manual_budget;
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-indigo-500" />
          <h3 className="text-base font-semibold text-gray-800">Render Services</h3>
        </div>
        <button onClick={props.onRefresh} className="text-gray-400 hover:text-gray-600 transition-colors" title="Refresh">
          <RefreshCw className={`h-4 w-4 ${props.loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {props.loading && <p className="text-sm text-gray-400">Loading...</p>}
      {!props.loading && !available && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-gray-400" />
            <span className="text-sm text-gray-500">No Key Configured</span>
          </div>
          {props.data?.error && <p className="text-xs text-gray-400">{props.data.error}</p>}
        </div>
      )}
      {!props.loading && available && (
        <div className="space-y-3">
          <div className="space-y-1.5 max-h-36 overflow-y-auto">
            {services.map((svc, idx) => {
              const isActive = svc.status === 'not_suspended';
              const dotColor = isActive ? 'bg-emerald-500' : 'bg-red-400';
              const lastDeploy = svc.updated_at ? fmtDate(svc.updated_at) : '-';
              const svcType = svc.type || '';
              return (
                <div key={svc.id || String(idx)} className="flex items-start gap-2 text-xs">
                  <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${dotColor}`} />
                  <div>
                    <p className="font-medium text-gray-700">{svc.name || 'Unknown'}</p>
                    <p className="text-gray-400">{svcType} · {lastDeploy}</p>
                  </div>
                </div>
              );
            })}
            {services.length === 0 && <p className="text-xs text-gray-400">No services found</p>}
          </div>
          {budget !== null && budget !== undefined && (
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-500">Monthly Budget</span>
                <span className="font-medium text-gray-700">{fmtCurrency(budget)}</span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full">
                <div className="h-full bg-indigo-400 rounded-full" style={{ width: '40%' }} />
              </div>
            </div>
          )}
          <a
            href="https://dashboard.render.com/billing"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 transition-colors mt-1"
          >
            View Render Billing <ExternalLink className="h-3 w-3" />
          </a>
        </div>
      )}
    </div>
  );
}

type TabKey = 'all' | 'completed' | 'failed' | 'refunded';

const TAB_STATUS: { [k: string]: string | undefined } = {
  all: undefined,
  completed: 'completed',
  failed: 'failed',
  refunded: 'refunded',
};

const PURPOSES = [
  { value: '', label: 'All Purposes' },
  { value: 'rfq_unlock', label: 'RFQ Unlock' },
  { value: 'nda_fee', label: 'NDA Fee' },
  { value: 'provider_profile_subscription', label: 'Provider Profile' },
  { value: 'provider_annual_subscription', label: 'Annual Subscription' },
  { value: 'advertisement_subscription', label: 'Ad Subscription' },
  { value: 'search_subscription', label: 'Search Subscription' },
];

interface ReconcileReportDetail {
  payment_id: string;
  stripe_session_id: string;
  purpose: string;
  amount_usd: number;
  action: string;
  error: string | null;
  stripe_payment_status?: string;
}

interface ReconcileReportData {
  dry_run: boolean;
  total_checked: number;
  paid_found: number;
  fulfilled: number;
  stripe_errors: number;
  fulfill_errors: number;
  details: ReconcileReportDetail[];
}

export default function AdminPaymentsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);

  const [analytics, setAnalytics] = useState(null as AnalyticsData | null);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [txData, setTxData] = useState(null as TransactionPage | null);
  const [txLoading, setTxLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all' as TabKey);
  const [txPage, setTxPage] = useState(1);
  const [filterPurpose, setFilterPurpose] = useState('');
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo] = useState('');
  const [openaiData, setOpenaiData] = useState(null as LLMsSpend | null);
  const [openaiLoading, setOpenaiLoading] = useState(true);
  const [awsData, setAwsData] = useState(null as AWSSpend | null);
  const [awsLoading, setAwsLoading] = useState(true);
  const [renderData, setRenderData] = useState(null as RenderSpend | null);
  const [renderLoading, setRenderLoading] = useState(true);
  const [reconcileLoading, setReconcileLoading] = useState(false);
  const [ndaResolveLoading, setNdaResolveLoading] = useState(false);
  const [fulfillLoadingId, setFulfillLoadingId] = useState(null as string | null);
  const [fulfillMsg, setFulfillMsg] = useState(null as string | null);
  const [reconcileReport, setReconcileReport] = useState(null as ReconcileReportData | null);
  const [showReconcileModal, setShowReconcileModal] = useState(false);
  const [refundTarget, setRefundTarget] = useState(null as Transaction | null);
  const [refundReason, setRefundReason] = useState('');
  const [refundReverse, setRefundReverse] = useState(true);
  const [refundLoading, setRefundLoading] = useState(false);
  const [refundResult, setRefundResult] = useState(null as { status: string; stripe_refund_id?: string; stripe_error?: string; reversal?: string; reversal_error?: string; amount_usd?: number } | null);

  const fetchAnalytics = useCallback(() => {
    setAnalyticsLoading(true);
    const run = async () => {
      try {
        const res = await fetch(API_BASE + '/api/v1/admin/payments/analytics', { headers: getAuthHeader() });
        if (res.ok) setAnalytics(await res.json());
      } catch (e) { console.error(e); } finally { setAnalyticsLoading(false); }
    };
    run();
  }, []);

  const fetchTransactions = useCallback(
    (page: number, tab: string, purpose: string, dateFrom: string, dateTo: string) => {
      setTxLoading(true);
      const run = async () => {
        try {
          const statusVal = TAB_STATUS[tab];
          const params = new URLSearchParams();
          params.set('page', String(page));
          params.set('per_page', '20');
          if (statusVal) params.set('status', statusVal);
          if (purpose) params.set('purpose', purpose);
          if (dateFrom) params.set('date_from', dateFrom);
          if (dateTo) params.set('date_to', dateTo);
          const res = await fetch(API_BASE + '/api/v1/admin/payments/transactions?' + params.toString(), { headers: getAuthHeader() });
          if (res.ok) setTxData(await res.json());
        } catch (e) { console.error(e); } finally { setTxLoading(false); }
      };
      run();
    }, []
  );

  const fetchOpenAI = useCallback(() => {
    setOpenaiLoading(true);
    const run = async () => {
      try {
        const res = await fetch(API_BASE + '/api/v1/admin/spend/llms', { headers: getAuthHeader() });
        if (res.ok) setOpenaiData(await res.json());
      } catch (e) { setOpenaiData({ available: false, error: String(e) }); } finally { setOpenaiLoading(false); }
    };
    run();
  }, []);

  const fetchAWS = useCallback(() => {
    setAwsLoading(true);
    const run = async () => {
      try {
        const res = await fetch(API_BASE + '/api/v1/admin/spend/aws', { headers: getAuthHeader() });
        if (res.ok) setAwsData(await res.json());
      } catch (e) { setAwsData({ available: false, error: String(e) }); } finally { setAwsLoading(false); }
    };
    run();
  }, []);

  const fetchRender = useCallback(() => {
    setRenderLoading(true);
    const run = async () => {
      try {
        const res = await fetch(API_BASE + '/api/v1/admin/spend/render', { headers: getAuthHeader() });
        if (res.ok) setRenderData(await res.json());
      } catch (e) { setRenderData({ available: false, error: String(e) }); } finally { setRenderLoading(false); }
    };
    run();
  }, []);

  useEffect(() => {
    fetchAnalytics();
    fetchOpenAI();
    fetchAWS();
    fetchRender();
  }, [fetchAnalytics, fetchOpenAI, fetchAWS, fetchRender]);

  useEffect(() => {
    fetchTransactions(txPage, activeTab, filterPurpose, filterDateFrom, filterDateTo);
  }, [txPage, activeTab, filterPurpose, filterDateFrom, filterDateTo, fetchTransactions]);

  const handleTabChange = (tab: string) => { setActiveTab(tab as TabKey); setTxPage(1); };

  const handleFilterApply = () => {
    setTxPage(1);
    fetchTransactions(1, activeTab, filterPurpose, filterDateFrom, filterDateTo);
  };

  const handleForceFulfill = async (paymentId: string, purpose: string) => {
    if (!window.confirm('Force-run fulfillment for ' + purpose + '?\nSafe to run multiple times.')) return;
    setFulfillLoadingId(paymentId);
    setFulfillMsg(null);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const hdrs: { [k: string]: string } = { 'Content-Type': 'application/json' };
      if (token) hdrs['Authorization'] = 'Bearer ' + token;
      const res = await fetch(API_BASE + '/api/v1/admin/payments/' + paymentId + '/force-fulfill-subscription', { method: 'POST', headers: hdrs });
      if (res.ok) {
        const d = await res.json();
        setFulfillMsg('Done: ' + (d.message || 'Fulfillment complete'));
        fetchTransactions(txPage, activeTab, filterPurpose, filterDateFrom, filterDateTo);
      } else {
        const e = await res.json().catch(() => ({}));
        setFulfillMsg('Failed: ' + (e.detail || res.statusText));
      }
    } catch (ex) {
      setFulfillMsg('Error: ' + String(ex));
    } finally {
      setFulfillLoadingId(null);
      setTimeout(() => setFulfillMsg(null), 6000);
    }
  };

  const handleReconcile = async (dryRun: boolean) => {
    setReconcileLoading(true);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const res = await fetch(API_BASE + '/api/v1/admin/payments/reconcile-stripe', {
        method: 'POST',
        headers: { Authorization: token ? 'Bearer ' + token : '', 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun, limit: 20 }),
      });
      if (!res.ok) { const err = await res.json().catch(() => ({})); alert('Reconciliation failed: ' + (err.detail || res.status)); return; }
      const data = await res.json();
      setReconcileReport(data);
      setShowReconcileModal(true);
      if (!dryRun && data.fulfilled > 0) { fetchAnalytics(); fetchTransactions(1, activeTab, filterPurpose, filterDateFrom, filterDateTo); }
    } catch (e) { alert('Reconciliation error: ' + String(e)); } finally { setReconcileLoading(false); }
  };

  const handleBulkResolveNda = async () => {
    if (!confirm('This will mark ALL NDA fee payments stuck at "Initiated" as "Completed". Continue?')) return;
    setNdaResolveLoading(true);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const res = await fetch(API_BASE + '/api/v1/admin/payments/bulk-resolve-nda-initiated', {
        method: 'POST',
        headers: { Authorization: token ? 'Bearer ' + token : '', 'Content-Type': 'application/json' },
      });
      if (!res.ok) { const err = await res.json().catch(() => ({})); alert('Bulk resolve failed: ' + (err.detail || res.status)); return; }
      const data = await res.json();
      alert('Resolved ' + data.updated + ' NDA fee payment(s) to Completed.');
      if (data.updated > 0) { fetchAnalytics(); fetchTransactions(1, activeTab, filterPurpose, filterDateFrom, filterDateTo); }
    } catch (e) { alert('Bulk resolve error: ' + String(e)); } finally { setNdaResolveLoading(false); }
  };

  const handleExportCSV = () => {
    const statusVal = TAB_STATUS[activeTab];
    const params = new URLSearchParams();
    params.set('format', 'csv');
    if (statusVal) params.set('status', statusVal);
    if (filterPurpose) params.set('purpose', filterPurpose);
    if (filterDateFrom) params.set('date_from', filterDateFrom);
    if (filterDateTo) params.set('date_to', filterDateTo);
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const url = API_BASE + '/api/v1/admin/payments/transactions?' + params.toString();
    if (token) {
      fetch(url, { headers: { Authorization: 'Bearer ' + token } })
        .then((r) => r.blob())
        .then((blob) => { const objUrl = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = objUrl; a.download = 'payments.csv'; a.click(); URL.revokeObjectURL(objUrl); });
    } else {
      const a = document.createElement('a'); a.href = url; a.download = 'payments.csv'; a.click();
    }
  };

  const handleRefundOpen = (tx: Transaction) => {
    setRefundTarget(tx);
    setRefundReason('');
    setRefundReverse(true);
    setRefundResult(null);
  };

  const handleRefundSubmit = async () => {
    if (!refundTarget || !refundReason.trim() || refundLoading) return;
    setRefundLoading(true);
    setRefundResult(null);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const res = await fetch(API_BASE + '/api/v1/admin/payments/' + refundTarget.id + '/refund', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
        body: JSON.stringify({ reason: refundReason.trim(), reverse_fulfillment: refundReverse }),
      });
      const data = await res.json();
      if (res.ok) {
        setRefundResult(data);
        fetchAnalytics();
        fetchTransactions(txPage, activeTab, filterPurpose, filterDateFrom, filterDateTo);
      } else {
        setRefundResult({ status: 'error', stripe_error: data.detail || 'Refund failed' });
      }
    } catch (ex) {
      setRefundResult({ status: 'error', stripe_error: String(ex) });
    } finally {
      setRefundLoading(false);
    }
  };

  const totalRevenue = analytics ? fmtCurrency(analytics.total_revenue) : '-';
  const revenueThisMonth = analytics ? fmtCurrency(analytics.total_this_month) : '-';
  const failed30d = analytics ? String(analytics.total_failed_30d) : '-';
  const refundedTotal = analytics ? fmtCurrency(analytics.total_refunded ?? 0) : '-';
  const monthlySeries = analytics?.monthly_series ?? [];
  const byPurpose = analytics?.by_purpose ?? [];
  const grandTotal = analytics?.total_revenue ?? 0;
  const byPurposeAll = analytics?.by_purpose_all ?? byPurpose;
  const srcRfq = byPurposeAll.find((p) => p.purpose === 'rfq_unlock');
  const rfqTotal = srcRfq?.total ?? 0;
  const rfqCount = srcRfq?.count ?? 0;
  const srcNda = byPurposeAll.find((p) => p.purpose === 'nda_fee');
  const ndaTotal = srcNda?.total ?? 0;
  const ndaCount = srcNda?.count ?? 0;
  const srcCust = byPurposeAll.find((p) => p.purpose === 'search_subscription');
  const custTotal = srcCust?.total ?? 0;
  const custCount = srcCust?.count ?? 0;
  const provPurposes = ['provider_profile_subscription', 'annual_subscription', 'provider_annual_subscription'];
  const provTotal = byPurposeAll.filter((p) => provPurposes.includes(p.purpose)).reduce((s, p) => s + p.total, 0);
  const provCount = byPurposeAll.filter((p) => provPurposes.includes(p.purpose)).reduce((s, p) => s + p.count, 0);
  const srcAd = byPurposeAll.find((p) => p.purpose === 'advertisement_subscription');
  const adTotal = srcAd?.total ?? 0;
  const adCount = srcAd?.count ?? 0;
  const txItems = txData?.items ?? [];
  const txPages = txData?.pages ?? 1;
  const txTotal = txData?.total ?? 0;
  const rfqTotalStr = '$' + rfqTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const ndaTotalStr = '$' + ndaTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const custTotalStr = '$' + custTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const provTotalStr = '$' + provTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const rfqSubtitle = rfqCount + ' unlock' + (rfqCount !== 1 ? 's' : '') + ' · $50 each';
  const ndaSubtitle = ndaCount + ' NDA' + (ndaCount !== 1 ? 's' : '') + ' · $10 each';
  const custSubtitle = custCount + ' payment' + (custCount !== 1 ? 's' : '') + ' · $20/month';
  const provSubtitle = provCount + ' payment' + (provCount !== 1 ? 's' : '') + ' · $500 edit or $1,000/yr';
  const adTotalStr = '$' + adTotal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const adSubtitle = adCount + ' payment' + (adCount \!== 1 ? 's' : '') + ' · $50/month';

  const tabs = [
    { key: 'all', label: 'All' },
    { key: 'completed', label: 'Completed' },
    { key: 'failed', label: 'Failed' },
    { key: 'refunded', label: 'Refunded' },
  ];

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-400">Authenticating...</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">💳</span>
          <h1 className="text-2xl font-bold text-gray-900">Payment Monitoring</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => handleReconcile(true)} disabled={reconcileLoading} className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-300 rounded-lg text-sm font-medium text-amber-700 hover:bg-amber-100 transition-colors shadow-sm disabled:opacity-50" title="Preview which initiated payments Stripe shows as paid (no changes)">
            {reconcileLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Dry Run Check
          </button>
          <button onClick={() => handleReconcile(false)} disabled={reconcileLoading} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm disabled:opacity-50" title="Reconcile and fulfill all Stripe-confirmed initiated payments">
            {reconcileLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Reconcile Payments
          </button>
          <button onClick={handleBulkResolveNda} disabled={ndaResolveLoading} className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm disabled:opacity-50" title="Mark all NDA fee payments stuck at Initiated as Completed">
            {ndaResolveLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
            Resolve NDA Payments
          </button>
          <button onClick={handleExportCSV} className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm">
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard title="Total Revenue Collected" value={analyticsLoading ? '...' : totalRevenue} icon={DollarSign} colorClass="text-emerald-600" bgClass="bg-emerald-50" />
        <KpiCard title="Revenue This Month" value={analyticsLoading ? '...' : revenueThisMonth} icon={TrendingUp} colorClass="text-blue-600" bgClass="bg-blue-50" />
        <KpiCard title="Failed (30d)" value={analyticsLoading ? '...' : failed30d} icon={XCircle} colorClass="text-red-600" bgClass="bg-red-50" />
        <KpiCard title="Total Refunded" value={analyticsLoading ? '...' : refundedTotal} icon={RefreshCw} colorClass="text-amber-600" bgClass="bg-amber-50" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs font-medium text-gray-500">RFQ Income</span><span className="p-2 rounded-lg bg-violet-50"><svg className="h-5 w-5 text-violet-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg></span></div>
          <p className="text-xl font-bold text-gray-900">{analyticsLoading ? '...' : rfqTotalStr}</p>
          <p className="text-xs text-gray-400 mt-1">{analyticsLoading ? '' : rfqSubtitle}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs font-medium text-gray-500">NDA Income</span><span className="p-2 rounded-lg bg-rose-50"><svg className="h-5 w-5 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg></span></div>
          <p className="text-xl font-bold text-gray-900">{analyticsLoading ? '...' : ndaTotalStr}</p>
          <p className="text-xs text-gray-400 mt-1">{analyticsLoading ? '' : ndaSubtitle}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs font-medium text-gray-500">Customer Membership</span><span className="p-2 rounded-lg bg-blue-50"><svg className="h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg></span></div>
          <p className="text-xl font-bold text-gray-900">{analyticsLoading ? '...' : custTotalStr}</p>
          <p className="text-xs text-gray-400 mt-1">{analyticsLoading ? '' : custSubtitle}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs font-medium text-gray-500">Provider Membership</span><span className="p-2 rounded-lg bg-emerald-50"><svg className="h-5 w-5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg></span></div>
          <p className="text-xl font-bold text-gray-900">{analyticsLoading ? '...' : provTotalStr}</p>
          <p className="text-xs text-gray-400 mt-1">{analyticsLoading ? '' : provSubtitle}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="flex items-center justify-between mb-2"><span className="text-xs font-medium text-gray-500">Advertisement Income</span><span className="p-2 rounded-lg bg-amber-50"><svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" /></svg></span></div>
          <p className="text-xl font-bold text-gray-900">{analyticsLoading ? '...' : adTotalStr}</p>
          <p className="text-xs text-gray-400 mt-1">{analyticsLoading ? '' : adSubtitle}</p>
        </div>
      </div>

      <div className="max-w-2xl mx-auto w-full"><MonthlyBarChart series={monthlySeries} /></div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="flex border-b border-gray-200 px-6 pt-4">
          {tabs.map((t) => {
            const isActive = activeTab === t.key;
            const tabClass = isActive ? 'border-b-2 border-blue-600 text-blue-600 font-semibold' : 'text-gray-500 hover:text-gray-700';
            return (
              <button key={t.key} onClick={() => handleTabChange(t.key)} className={`px-4 py-2 text-sm mr-2 transition-colors ${tabClass}`}>
                {t.label}
              </button>
            );
          })}
          <div className="ml-auto flex items-center gap-1 pb-2">
            <span className="text-xs text-gray-400">{txTotal} total</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 px-6 py-4 border-b border-gray-100">
          <select value={filterPurpose} onChange={(e) => setFilterPurpose(e.target.value)} className="border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
            {PURPOSES.map((p) => (<option key={p.value} value={p.value}>{p.label}</option>))}
          </select>
          <input type="date" value={filterDateFrom} onChange={(e) => setFilterDateFrom(e.target.value)} className="border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <input type="date" value={filterDateTo} onChange={(e) => setFilterDateTo(e.target.value)} className="border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <button onClick={handleFilterApply} className="px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors">Apply</button>
          <button onClick={() => { setFilterPurpose(''); setFilterDateFrom(''); setFilterDateTo(''); setTxPage(1); }} className="px-3 py-1.5 border border-gray-300 text-gray-600 rounded-md text-sm hover:bg-gray-50 transition-colors">Clear</button>
        </div>
        <div className="overflow-x-auto">
          {fulfillMsg && (
            <div style={{ margin: '0 24px 12px', padding: '8px 16px', borderRadius: '8px', fontSize: '14px', background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0' }}>
              {fulfillMsg}
            </div>
          )}
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Purpose</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Amount</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">User</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Provider</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Payment ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {txLoading && (
                <tr><td colSpan={7} className="text-center py-8 text-gray-400">Loading...</td></tr>
              )}
              {!txLoading && txItems.length === 0 && (
                <tr><td colSpan={7} className="text-center py-8 text-gray-400">No transactions found</td></tr>
              )}
              {!txLoading && txItems.map((tx) => {
                const badgeClass = statusBadgeClass(tx.payment_status);
                const dateStr = fmtDate(tx.initiated_at);
                const purposeStr = fmtPurpose(tx.purpose);
                const amountStr = fmtCurrency(tx.amount);
                const statusLabel = tx.payment_status.charAt(0).toUpperCase() + tx.payment_status.slice(1);
                const userStr = tx.user_email || tx.user_name || '-';
                const providerStr = tx.provider_name || '-';
                const paymentIdStr = fmtShortId(tx.external_payment_id);
                return (
                  <tr key={tx.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{dateStr}</td>
                    <td className="px-4 py-3 text-gray-800 font-medium">{purposeStr}</td>
                    <td className="px-4 py-3 text-right font-semibold text-gray-900">{amountStr}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}`}>{statusLabel}</span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-[160px] truncate">{userStr}</td>
                    <td className="px-4 py-3 text-gray-600">{providerStr}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{paymentIdStr}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        {tx.payment_status === 'completed' && (tx.purpose === 'provider_annual_subscription' || tx.purpose === 'full_profile_edit_unlock' || tx.purpose === 'search_subscription') && (
                          <button onClick={() => handleForceFulfill(tx.id, tx.purpose)} disabled={fulfillLoadingId === tx.id} style={{ padding: '2px 10px', fontSize: '12px', fontWeight: 500, background: fulfillLoadingId === tx.id ? '#e0e7ff' : '#4f46e5', color: fulfillLoadingId === tx.id ? '#4f46e5' : 'white', borderRadius: '4px', border: 'none', cursor: 'pointer' }}>
                            {fulfillLoadingId === tx.id ? 'Running...' : 'Force Fulfill'}
                          </button>
                        )}
                        {(tx.payment_status === 'completed' || tx.payment_status === 'initiated') && (
                          <button onClick={() => handleRefundOpen(tx)} className="px-2.5 py-0.5 text-xs font-medium bg-red-50 text-red-700 border border-red-200 rounded hover:bg-red-100 transition-colors">
                            Refund
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {txPages > 1 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100">
            <button onClick={() => setTxPage((p) => Math.max(1, p - 1))} disabled={txPage <= 1} className="px-3 py-1.5 border border-gray-300 rounded-md text-sm text-gray-600 disabled:opacity-40 hover:bg-gray-50 transition-colors">Previous</button>
            <span className="text-sm text-gray-500">Page {txPage} of {txPages}</span>
            <button onClick={() => setTxPage((p) => Math.min(txPages, p + 1))} disabled={txPage >= txPages} className="px-3 py-1.5 border border-gray-300 rounded-md text-sm text-gray-600 disabled:opacity-40 hover:bg-gray-50 transition-colors">Next</button>
          </div>
        )}
      </div>

      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Infrastructure Spend</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <LLMsCard data={openaiData} loading={openaiLoading} onRefresh={fetchOpenAI} />
          <AWSCard data={awsData} loading={awsLoading} onRefresh={fetchAWS} />
          <RenderCard data={renderData} loading={renderLoading} onRefresh={fetchRender} />
        </div>
      </div>

      {/* ── Refund Modal ──────────────────────────────────────────── */}
      {refundTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full">
            <div className="p-6 border-b">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold text-gray-900">Refund Payment</h2>
                <button onClick={() => { setRefundTarget(null); setRefundResult(null); }} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
              </div>
              <p className="text-sm text-gray-500 mt-1">This will issue a Stripe refund and update internal records.</p>
            </div>

            <div className="p-6 space-y-4">
              {/* Payment info */}
              <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Purpose</span>
                  <span className="font-medium text-gray-900">{fmtPurpose(refundTarget.purpose)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Amount</span>
                  <span className="font-bold text-gray-900">{fmtCurrency(refundTarget.amount)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">User</span>
                  <span className="text-gray-700">{refundTarget.user_email || refundTarget.user_name || '-'}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Date</span>
                  <span className="text-gray-700">{fmtDate(refundTarget.initiated_at)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Status</span>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusBadgeClass(refundTarget.payment_status)}`}>
                    {refundTarget.payment_status.charAt(0).toUpperCase() + refundTarget.payment_status.slice(1)}
                  </span>
                </div>
              </div>

              {/* Reason */}
              {!refundResult && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Reason for refund <span className="text-red-500">*</span></label>
                    <textarea
                      value={refundReason}
                      onChange={(e) => setRefundReason(e.target.value)}
                      placeholder="e.g. Customer charged twice, unlock did not work, provider was inactive..."
                      rows={3}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-400"
                    />
                  </div>

                  <div className="flex items-center gap-2.5">
                    <input
                      id="refundReverse"
                      type="checkbox"
                      checked={refundReverse}
                      onChange={(e) => setRefundReverse(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
                    />
                    <label htmlFor="refundReverse" className="text-sm text-gray-700 cursor-pointer">
                      Reverse fulfillment (revoke unlock, cancel NDA/subscription)
                    </label>
                  </div>
                </>
              )}

              {/* Result */}
              {refundResult && (
                <div className={`rounded-lg p-4 text-sm ${refundResult.status === 'refunded' || refundResult.status === 'already_refunded' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <p className={`font-semibold ${refundResult.status === 'refunded' || refundResult.status === 'already_refunded' ? 'text-green-800' : 'text-red-800'}`}>
                    {refundResult.status === 'refunded' ? 'Refund processed successfully' : refundResult.status === 'already_refunded' ? 'Payment was already refunded' : 'Refund failed'}
                  </p>
                  {refundResult.stripe_refund_id && (
                    <p className="text-green-700 mt-1">Stripe Refund ID: <span className="font-mono">{refundResult.stripe_refund_id}</span></p>
                  )}
                  {refundResult.stripe_error && (
                    <p className="text-amber-700 mt-1">Note: {refundResult.stripe_error}</p>
                  )}
                  {refundResult.reversal && refundResult.reversal !== 'no_reversal_requested' && (
                    <p className="text-gray-700 mt-1">Fulfillment reversal: {refundResult.reversal.replace(/_/g, ' ')}</p>
                  )}
                  {refundResult.reversal_error && (
                    <p className="text-red-700 mt-1">Reversal error: {refundResult.reversal_error}</p>
                  )}
                  {refundResult.amount_usd && (
                    <p className="text-gray-700 mt-1">Amount: ${refundResult.amount_usd.toFixed(2)}</p>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 p-4 border-t">
              {!refundResult ? (
                <>
                  <button onClick={() => setRefundTarget(null)} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">Cancel</button>
                  <button
                    onClick={handleRefundSubmit}
                    disabled={refundLoading || !refundReason.trim()}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {refundLoading ? (
                      <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</>
                    ) : (
                      <>Issue Refund ({fmtCurrency(refundTarget.amount)})</>
                    )}
                  </button>
                </>
              ) : (
                <button onClick={() => { setRefundTarget(null); setRefundResult(null); }} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">Close</button>
              )}
            </div>
          </div>
        </div>
      )}

      {showReconcileModal && reconcileReport && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-6 border-b">
              <div>
                <h2 className="text-lg font-bold text-gray-900">
                  Stripe Reconciliation {reconcileReport.dry_run ? '— Dry Run Preview' : '— Complete'}
                </h2>
                <p className="text-sm text-gray-500 mt-0.5">
                  {reconcileReport.dry_run ? 'No changes were made. Click Reconcile Payments to apply.' : 'Changes have been applied to the database.'}
                </p>
              </div>
              <button onClick={() => setShowReconcileModal(false)} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">x</button>
            </div>
            <div className="grid grid-cols-3 gap-4 p-6 border-b bg-gray-50">
              <div className="text-center">
                <p className="text-2xl font-bold text-gray-900">{reconcileReport.total_checked}</p>
                <p className="text-xs text-gray-500">Initiated checked</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-amber-600">{reconcileReport.paid_found}</p>
                <p className="text-xs text-gray-500">Found paid in Stripe</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-emerald-600">{reconcileReport.fulfilled}</p>
                <p className="text-xs text-gray-500">{reconcileReport.dry_run ? 'Would fulfill' : 'Fulfilled'}</p>
              </div>
            </div>
            {(reconcileReport.stripe_errors > 0 || reconcileReport.fulfill_errors > 0) && (
              <div className="px-6 py-3 bg-red-50 border-b border-red-100 text-sm text-red-700">
                {reconcileReport.stripe_errors} Stripe lookup errors · {reconcileReport.fulfill_errors} fulfillment errors
              </div>
            )}
            <div className="overflow-y-auto flex-1 p-4">
              {reconcileReport.details.filter((d) => d.action !== 'not_paid').length === 0 ? (
                <p className="text-center text-gray-500 py-8">All initiated payments are genuinely unpaid — no action needed.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-gray-500 border-b">
                      <th className="pb-2 pr-3">Session ID</th>
                      <th className="pb-2 pr-3">Purpose</th>
                      <th className="pb-2 pr-3">Amount</th>
                      <th className="pb-2 pr-3">Stripe Status</th>
                      <th className="pb-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reconcileReport.details.map((d, i) => {
                      const stripeStatusClass = d.stripe_payment_status === 'paid' ? 'bg-emerald-100 text-emerald-700' : d.stripe_payment_status === 'unpaid' ? 'bg-gray-100 text-gray-600' : 'bg-red-100 text-red-700';
                      const actionClass = d.action === 'fulfilled' ? 'bg-emerald-100 text-emerald-700' : d.action === 'would_fulfill' ? 'bg-amber-100 text-amber-700' : d.action === 'stripe_error' || d.action === 'fulfill_failed' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600';
                      const shortSession = d.stripe_session_id ? d.stripe_session_id.slice(-12) : '-';
                      const purposeLabel = d.purpose ? d.purpose.replace(/_/g, ' ') : '-';
                      const actionLabel = d.action ? d.action.replace(/_/g, ' ') : '-';
                      const amountLabel = d.amount_usd ? '$' + d.amount_usd.toFixed(2) : '-';
                      return (
                        <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="py-2 pr-3 font-mono text-xs text-gray-500 truncate max-w-[120px]">{shortSession}</td>
                          <td className="py-2 pr-3 capitalize">{purposeLabel}</td>
                          <td className="py-2 pr-3">{amountLabel}</td>
                          <td className="py-2 pr-3"><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${stripeStatusClass}`}>{d.stripe_payment_status || '-'}</span></td>
                          <td className="py-2">
                            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${actionClass}`}>{actionLabel}</span>
                            {d.error && <span className="ml-2 text-red-500 text-xs" title={d.error}>!</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="flex justify-end gap-3 p-4 border-t">
              {reconcileReport.dry_run && reconcileReport.paid_found > 0 && (
                <button
                  onClick={() => { setShowReconcileModal(false); handleReconcile(false); }}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
                >
                  Apply Reconciliation ({reconcileReport.paid_found} payments)
                </button>
              )}
              <button onClick={() => setShowReconcileModal(false)} className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
