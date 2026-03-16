'use client';
export const dynamic = 'force-dynamic';

import { useState } from 'react';
import { Download, Search, Users, DollarSign, FileText, Building2, FileSignature, Megaphone, Shield, BarChart3, Loader2, CheckCircle, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';

interface ExportType {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
  jsonOnly?: boolean;
  csvOnly?: boolean;
}

const EXPORT_TYPES: ExportType[] = [
  {
    id: 'search_queries',
    label: 'Search Queries',
    description: 'All search activity, queries, AI pipeline results, fallback reasons, and embedding models used.',
    icon: Search,
  },
  {
    id: 'users_basic',
    label: 'Users (Basic)',
    description: 'User accounts, subscription tiers, payment totals, NDA count, and login history.',
    icon: Users,
  },
  {
    id: 'users_full',
    label: 'Users (Full)',
    description: 'All user data including search history, RFQ activity, quote counts, and last search query.',
    icon: Users,
  },
  {
    id: 'financial_transactions',
    label: 'Financial Transactions',
    description: 'All payment attempts, Stripe/PayPal records, subscription linkage, and confirmation status.',
    icon: DollarSign,
  },
  {
    id: 'rfq_analytics',
    label: 'RFQ Analytics',
    description: 'Requests for quotes with dispatch stats, quote counts, provider contacts, and lifecycle status.',
    icon: FileText,
  },
  {
    id: 'provider_activity',
    label: 'Provider Activity',
    description: 'Provider records, ownership, claim status, RFQ unlock history, quote activity, and embeddings.',
    icon: Building2,
  },
  {
    id: 'nda_records',
    label: 'NDA Records',
    description: 'All NDA signing workflows, completion status, SignRequest document IDs, and timestamps.',
    icon: FileSignature,
  },
  {
    id: 'advertising_performance',
    label: 'Advertising Performance',
    description: 'Ad placements, active duration, advertiser info, slot details, and promotional content.',
    icon: Megaphone,
  },
  {
    id: 'audit_logs',
    label: 'Audit Logs',
    description: 'Admin actions, sensitive operation history, before/after state snapshots, and actor details.',
    icon: Shield,
  },
  {
    id: 'full_platform_snapshot',
    label: 'Platform Snapshot',
    description: 'Complete summary statistics: users, searches, RFQs, providers, revenue, NDAs, and ads.',
    icon: BarChart3,
    jsonOnly: true,
  },
];

type ToastType = 'success' | 'error';

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

export default function DataExtractionPage() {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState<Record<string, boolean>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = (type: ToastType, message: string) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  };

  const downloadExport = async (exportType: string, format: 'csv' | 'json') => {
    const key = `${exportType}_${format}`;
    setLoading(prev => ({ ...prev, [key]: true }));
    try {
      const token = localStorage.getItem('access_token');
      const params = new URLSearchParams({ export_type: exportType, format });
      if (dateFrom) params.set('date_from', dateFrom);
      if (dateTo) params.set('date_to', dateTo);

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const response = await fetch(
        `${apiUrl}/api/v1/admin/data-export?${params}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Export failed' }));
        throw new Error(err.detail || 'Export failed');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${exportType}_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      addToast('success', `${exportType} exported successfully`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Export failed';
      addToast('error', message);
    } finally {
      setLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const isLoading = (exportType: string, format: string) =>
    loading[`${exportType}_${format}`] === true;

  return (
    <div className="flex-1 space-y-6 p-6">
      {/* Toast notifications */}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {toasts.map(toast => (
          <div
            key={toast.id}
            className={`flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-all ${
              toast.type === 'success'
                ? 'bg-green-50 text-green-800 border border-green-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {toast.type === 'success' ? (
              <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
            ) : (
              <XCircle className="h-4 w-4 text-red-500 shrink-0" />
            )}
            {toast.message}
          </div>
        ))}
      </div>

      {/* Page header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Download className="h-8 w-8" />
          Data Extraction
        </h1>
        <p className="text-muted-foreground mt-1">
          Export platform data for analysis, compliance, and reporting.
        </p>
      </div>

      {/* Date range filter */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Date Range Filter</CardTitle>
          <CardDescription>Optionally filter all exports by creation date. Leave blank for all records.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="space-y-1.5">
              <Label htmlFor="date-from">From</Label>
              <Input
                id="date-from"
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                className="w-44"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="date-to">To</Label>
              <Input
                id="date-to"
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                className="w-44"
              />
            </div>
            {(dateFrom || dateTo) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setDateFrom(''); setDateTo(''); }}
              >
                Clear Filter
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Export cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {EXPORT_TYPES.map(exportType => {
          const Icon = exportType.icon;
          return (
            <Card key={exportType.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Icon className="h-5 w-5 text-muted-foreground" />
                  {exportType.label}
                  {exportType.jsonOnly && (
                    <Badge variant="secondary" className="text-xs ml-auto">JSON only</Badge>
                  )}
                </CardTitle>
                <CardDescription className="text-xs leading-relaxed">
                  {exportType.description}
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0 mt-auto">
                <div className="flex gap-2">
                  {!exportType.jsonOnly && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 gap-1.5"
                      onClick={() => downloadExport(exportType.id, 'csv')}
                      disabled={isLoading(exportType.id, 'csv')}
                    >
                      {isLoading(exportType.id, 'csv') ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Download className="h-3.5 w-3.5" />
                      )}
                      CSV
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant={exportType.jsonOnly ? 'default' : 'outline'}
                    className="flex-1 gap-1.5"
                    onClick={() => downloadExport(exportType.id, 'json')}
                    disabled={isLoading(exportType.id, 'json')}
                  >
                    {isLoading(exportType.id, 'json') ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5" />
                    )}
                    JSON
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
