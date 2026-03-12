"use client";

import { useState, useEffect } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, FileText, Building2, Cpu, CheckCircle, XCircle, RefreshCw, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface AdminStatus {
  database: {
    user_count: number;
    provider_count: number;
    rfq_count: number;
    providers_with_embeddings: number;
    connection_ok: boolean;
    error?: string;
  };
  api_keys: {
    openai_configured: boolean;
    stripe_configured: boolean;
    paypal_configured: boolean;
    signrequest_configured: boolean;
    aws_s3_configured: boolean;
  };
  timestamp: string;
}

export const dynamic = 'force-dynamic';

export default function AdminDashboard() {
  const { isLoading: authLoading, user } = useRequireAuth(['admin']);
  const [status, setStatus] = useState<AdminStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchStatus = async () => {
    setIsLoading(true);
    setError('');
    try {
      const res = await api.admin.getStats();
      setStatus(res.data);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load dashboard stats';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Only fetch AFTER auth has finished loading and user is confirmed
  useEffect(() => {
    if (!authLoading && user) {
      fetchStatus();
    }
  }, [authLoading, user]);

  if (authLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Authenticating...</p>
        </div>
      </div>
    );
  }

  const db = status?.database;
  const keys = status?.api_keys;

  const statCards = [
    {
      title: 'Total Users',
      value: isLoading ? '...' : (db?.user_count ?? 0).toLocaleString(),
      icon: Users,
      description: 'Registered accounts',
    },
    {
      title: 'Providers',
      value: isLoading ? '...' : (db?.provider_count ?? 0).toLocaleString(),
      icon: Building2,
      description: 'Directory listings',
    },
    {
      title: 'RFQs',
      value: isLoading ? '...' : (db?.rfq_count ?? 0).toLocaleString(),
      icon: FileText,
      description: 'Total requests for quotes',
    },
    {
      title: 'AI Embeddings',
      value: isLoading ? '...' : (db?.providers_with_embeddings ?? 0).toLocaleString(),
      icon: Cpu,
      description: `of ${isLoading ? '...' : (db?.provider_count ?? 0).toLocaleString()} providers indexed`,
    },
  ];

  const apiKeyItems = [
    { label: 'AI / Search (DeepInfra / OpenAI)', ok: keys?.openai_configured },
    { label: 'Stripe Payments', ok: keys?.stripe_configured },
    { label: 'PayPal / Braintree', ok: keys?.paypal_configured },
    { label: 'SignRequest (NDA)', ok: keys?.signrequest_configured },
    { label: 'AWS S3 (File Storage)', ok: keys?.aws_s3_configured },
  ];

  return (
    <div className="container py-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Admin Dashboard</h1>
        <Button variant="outline" size="sm" onClick={fetchStatus} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="mb-6 rounded-md bg-red-50 border border-red-200 p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-800">Could not load stats</p>
            <p className="text-sm text-red-600 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4 mb-8">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground">{stat.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* DB Connection Warning */}
      {status && db && !db.connection_ok && (
        <div className="mb-6 rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800">
          Database query issue: {db.error || 'Check Render logs for details'}
        </div>
      )}

      {/* API Keys Status */}
      <Card>
        <CardHeader>
          <CardTitle>API & Integration Status</CardTitle>
          <CardDescription>
            Configure missing keys in{' '}
            <a href="/admin/settings" className="text-blue-600 underline">Admin Settings</a>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {apiKeyItems.map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                {isLoading ? (
                  <div className="h-4 w-4 rounded-full bg-gray-200 animate-pulse" />
                ) : item.ok ? (
                  <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                ) : (
                  <XCircle className="h-4 w-4 text-red-400 shrink-0" />
                )}
                <span className="text-sm">{item.label}</span>
              </div>
            ))}
          </div>
          {status?.timestamp && (
            <p className="text-xs text-muted-foreground mt-4">
              Last updated: {new Date(status.timestamp).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
