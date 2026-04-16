"use client";
import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft, RefreshCw, Users, MessageSquare, Activity, Clock } from 'lucide-react';
import React from 'react';
import NdaBadge from '@/components/ui/NdaBadge';

interface DispatchedProvider {
  provider_id: number;
  provider_name: string;
  city: string | null;
  state: string | null;
  tier: string | null;
  dispatch_status: string;
  teaser_email_sent_at: string | null;
  batch_id: string | null;
}
interface BatchDetail {
  id: string;
  batch_number: number;
  status: string;
  scheduled_for: string | null;
  dispatched_at: string | null;
  providers_contacted: DispatchedProvider[];
}
interface QuoteDetail {
  id: string;
  quote_status: string;
  rough_price_min: number | null;
  rough_price_max: number | null;
  currency: string | null;
  turnaround_estimate_text: string | null;
  submitted_at: string | null;
}
interface RfqSummary {
  id: string;
  project_description: string;
  rfq_status: string;
  urgency: string | null;
  nda_required: boolean;
  nda_status?: string;
  quote_count: number;
  submitted_at: string | null;
}
interface TrackingData {
  rfq: RfqSummary;
  total_matches: number;
  total_dispatched: number;
  quotes_received: number;
  batches: BatchDetail[];
  quotes: QuoteDetail[];
}

const STATUS_COLORS: Record<string, string> = {
  submitted: "bg-blue-100 text-blue-800",
  open_for_dispatch: "bg-green-100 text-green-800",
  dispatching: "bg-yellow-100 text-yellow-800",
  open_for_unlock: "bg-purple-100 text-purple-800",
  quote_limit_reached: "bg-orange-100 text-orange-800",
  customer_selected_provider: "bg-emerald-100 text-emerald-800",
  closed_no_selection: "bg-gray-100 text-gray-600",
  cancelled: "bg-red-100 text-red-700",
  draft: "bg-gray-100 text-gray-500",
  sent: "bg-blue-50 text-blue-700",
  pending: "bg-gray-50 text-gray-500",
  completed: "bg-green-50 text-green-700",
  accepted: "bg-emerald-100 text-emerald-800",
  dispatched: "bg-blue-100 text-blue-700",
};

function fmtStatus(s: string) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function StatusPill({ s }: { s: string }) {
  const cls = STATUS_COLORS[s] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {fmtStatus(s)}
    </span>
  );
}

function StatBox({ icon: Icon, label, value, sub }: {
  icon: React.ElementType; label: string; value: number | string; sub?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="h-4 w-4 text-gray-400" />
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}

function ProviderRow({ p }: { p: DispatchedProvider }) {
  const loc = [p.city, p.state].filter(Boolean).join(', ');
  return (
    <div className="flex items-center justify-between rounded bg-gray-50 px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-gray-900">{p.provider_name}</p>
        {loc && (
          <p className="text-xs text-gray-500">
            {loc}{p.tier ? ` · Tier ${p.tier}` : ""}
          </p>
        )}
        {p.teaser_email_sent_at && (
          <p className="text-xs text-gray-400">
            Emailed {new Date(p.teaser_email_sent_at).toLocaleString()}
          </p>
        )}
      </div>
      <StatusPill s={p.dispatch_status} />
    </div>
  );
}

function BatchCard({ batch }: { batch: BatchDetail }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="font-semibold text-gray-900">Batch {batch.batch_number}</h4>
        <StatusPill s={batch.status} />
      </div>
      <div className="mb-3 space-y-0.5 text-xs text-gray-500">
        {batch.scheduled_for && (
          <p>Scheduled: {new Date(batch.scheduled_for).toLocaleString()}</p>
        )}
        {batch.dispatched_at && (
          <p>Dispatched: {new Date(batch.dispatched_at).toLocaleString()}</p>
        )}
      </div>
      {batch.providers_contacted.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Firms Contacted ({batch.providers_contacted.length})
          </p>
          {batch.providers_contacted.map((prov, i) => (
            <ProviderRow key={i} p={prov} />
          ))}
        </div>
      ) : (
        <p className="text-xs italic text-gray-400">No providers contacted yet in this batch.</p>
      )}
    </div>
  );
}

function QuoteCard({ q }: { q: QuoteDetail }) {
  const parts: string[] = [];
  if (q.rough_price_min != null) parts.push(`$${q.rough_price_min.toLocaleString()}`);
  if (q.rough_price_max != null && q.rough_price_max !== q.rough_price_min)
    parts.push(`$${q.rough_price_max.toLocaleString()}`);
  const currency = q.currency ?? "";
  const price = parts.join(" – ") + (currency && parts.length ? ` ${currency}` : "");
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <StatusPill s={q.quote_status} />
        {q.submitted_at && (
          <span className="text-xs text-gray-400">
            {new Date(q.submitted_at).toLocaleDateString()}
          </span>
        )}
      </div>
      {price && <p className="mb-1 text-sm font-semibold text-gray-800">Estimate: {price}</p>}
      {q.turnaround_estimate_text && (
        <p className="mb-1 text-xs text-gray-600">Turnaround: {q.turnaround_estimate_text}</p>
      )}
      <p className="mt-2 text-xs italic text-orange-600">
        Rough estimate only — non-binding, order-of-magnitude figure.
      </p>
    </div>
  );
}
export default function RFQTrackingPage() {
  const params = useParams();
  const router = useRouter();
  const rfqId = params?.id as string;
  const [data, setData] = useState<TrackingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchTracking = useCallback(async (isManual = false) => {
    if (!rfqId) return;
    if (isManual) setRefreshing(true);
    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1";
      const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
      const res = await fetch(`${apiBase}/customer/rfqs/${rfqId}/tracking`, {
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
      });
      if (res.status === 401) { router.push("/login"); return; }
      if (res.status === 403) { setError("Not authorized to view this RFQ."); return; }
      if (res.status === 404) { setError("RFQ not found."); return; }
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setData(await res.json());
      setLastRefresh(new Date());
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load tracking data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [rfqId, router]);

  useEffect(() => {
    fetchTracking();
    const iv = setInterval(() => fetchTracking(), 30000);
    return () => clearInterval(iv);
  }, [fetchTracking]);

  if (loading) return (
    <div className="container py-8">
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Loading tracking data...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="container py-8">
      <Link href="/customer/dashboard">
        <Button variant="ghost" size="sm" className="mb-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
        </Button>
      </Link>
      <div className="rounded-md bg-red-50 p-4 text-red-700">{error}</div>
    </div>
  );

  if (!data) return null;

  const { rfq, total_matches, total_dispatched, quotes_received, batches, quotes } = data;

  return (
    <div className="container py-8 max-w-4xl">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/customer/dashboard">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-2 h-4 w-4" /> Back
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Activity className="h-6 w-6 text-blue-600" />
              RFQ Dispatch Tracker
            </h1>
            {rfq.submitted_at && (
              <p className="text-sm text-gray-500">
                Submitted {new Date(rfq.submitted_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-xs text-gray-400">
              <Clock className="inline h-3 w-3 mr-1" />
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={() => fetchTracking(true)} disabled={refreshing}>
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      {/* RFQ Summary Card */}
      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-4">
            <p className="flex-1 text-sm font-medium text-gray-900 line-clamp-2">
              {rfq.project_description}
            </p>
            <span className={`shrink-0 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[rfq.rfq_status] ?? "bg-gray-100 text-gray-600"}`}>
              {fmtStatus(rfq.rfq_status)}
            </span>
          </div>
          <div className="flex flex-wrap gap-3 mt-3 text-xs text-gray-500">
            {rfq.urgency && <span>Urgency: <strong>{rfq.urgency}</strong></span>}
            <NdaBadge ndaRequired={rfq.nda_required} ndaStatus={rfq.nda_status} variant="full" />
          </div>
        </CardContent>
      </Card>

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatBox icon={Users} label="Matched" value={total_matches} sub="firms found" />
        <StatBox icon={Activity} label="Dispatched" value={total_dispatched} sub="teasers sent" />
        <StatBox icon={MessageSquare} label="Quotes" value={quotes_received} sub="received" />
        <StatBox icon={Clock} label="Batches" value={batches.length} sub="dispatch rounds" />
      </div>

      {/* Progress Bar */}
      <Card className="mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-gray-700">Quote Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-200 rounded-full h-2">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all"
                style={{ width: `${Math.min(100, (quotes_received / 5) * 100)}%` }}
              />
            </div>
            <span className="text-xs font-medium text-gray-600">{quotes_received} / 5 quotes received</span>
          </div>
          <p className="mt-2 text-xs text-gray-400">
            The first 5 quotes received will be shown. All matched providers are contacted in batches until 5 quotes are collected.
          </p>
        </CardContent>
      </Card>

      {/* Dispatch Batches */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">
          Dispatch Batches
        </h2>
        {batches.length === 0 ? (
          <div className="rounded-lg border border-dashed border-gray-300 p-8 text-center">
            <p className="text-sm text-gray-500">No dispatch batches yet. Your RFQ will be dispatched shortly after submission.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {batches.map((batch) => (
              <BatchCard key={batch.id} batch={batch} />
            ))}
          </div>
        )}
      </div>

      {/* Quotes Received */}
      {quotes.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">
            Quotes Received
          </h2>
          <div className="space-y-3">
            {quotes.map((q) => <QuoteCard key={q.id} q={q} />)}
          </div>
          <div className="mt-3 text-right">
            <Link href={`/customer/rfq/${rfqId}`}>
              <Button size="sm">View Full Quote Details</Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
