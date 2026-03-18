'use client';

import { useEffect, useState } from 'react';
import { Loader2, AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useRequireAuth } from '@/hooks/useAuth';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'https://proreadyengineer-api.onrender.com/api/v1';

function getAuthHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

export default function BillingPage() {
  const { isLoading: authLoading } = useRequireAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading) return;
    const redirect = async () => {
      try {
        const res = await fetch(`${apiBase}/billing/portal`, {
          method: 'GET',
          headers: getAuthHeaders(),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || 'Failed to open billing portal');
        }
        const data = await res.json();
        if (data?.url) {
          window.location.href = data.url;
        } else {
          throw new Error('No billing portal URL returned');
        }
      } catch (err: unknown) {
        const e = err as Error;
        setError(e.message || 'Failed to open billing portal');
        setLoading(false);
      }
    };
    redirect();
  }, [authLoading]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-50">
        <Loader2 className="h-10 w-10 animate-spin text-blue-600" />
        <p className="text-gray-600 text-sm">Redirecting to billing portal...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-2" />
          <CardTitle>Billing Portal Unavailable</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button
            onClick={() => { setError(''); setLoading(true); }}
            className="w-full"
          >
            <ExternalLink className="mr-2 h-4 w-4" />Try Again
          </Button>
          <Button variant="outline" onClick={() => window.history.back()} className="w-full">
            Go Back
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
