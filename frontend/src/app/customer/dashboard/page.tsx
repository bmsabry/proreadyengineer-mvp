'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate, getRFQStatusBadgeColor } from '@/lib/utils';
import { Search, FileText, MessageSquare, Activity, AlertCircle } from 'lucide-react';

interface CustomerRFQ {
  id: string;
  project_description: string;
  rfq_status: string;
  urgency: string | null;
  nda_required: boolean;
  quote_count: number;
  is_closed: boolean;
  created_at: string | null;
  submitted_at: string | null;
}

export default function CustomerDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const router = useRouter();
  const [rfqs, setRfqs] = useState<CustomerRFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!user) return;
    const fetchRFQs = async () => {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';
        const res = await fetch(`${apiBase}/rfqs/customer/my-rfqs`, {
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) {
          // Don't surface the error - just show empty state
          setLoadError(true);
          return;
        }
        const data = await res.json();
        setRfqs(Array.isArray(data) ? data : data.items ?? []);
      } catch {
        // Silently fail - show empty state
        setLoadError(true);
      } finally {
        setIsLoading(false);
      }
    };
    fetchRFQs();
  }, [user]);

  if (authLoading || isLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold">Customer Dashboard</h1>
          <p className="text-muted-foreground">Manage your RFQs and view quotes</p>
        </div>
        <Button onClick={() => router.push('/')} className="flex items-center gap-2">
          <Search className="h-4 w-4" />
          New RFQ
        </Button>
      </div>

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Your RFQs
            </CardTitle>
            <CardDescription>Track the status of your request for quotes</CardDescription>
          </CardHeader>
          <CardContent>
            {loadError && rfqs.length === 0 ? (
              /* Friendly message instead of red error box */
              <div className="text-center py-10">
                <AlertCircle className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
                <p className="text-muted-foreground mb-4">
                  No RFQs found. Start by searching for engineering providers on the home page.
                </p>
                <Button onClick={() => router.push('/')} className="flex items-center gap-2 mx-auto">
                  <Search className="h-4 w-4" />
                  Search &amp; Create RFQ
                </Button>
              </div>
            ) : rfqs.length === 0 ? (
              <div className="text-center py-10">
                <FileText className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
                <p className="text-muted-foreground mb-4">
                  No RFQs yet. Start by searching for engineering providers.
                </p>
                <Button onClick={() => router.push('/')} className="flex items-center gap-2 mx-auto">
                  <Search className="h-4 w-4" />
                  Search &amp; Create RFQ
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                {rfqs.map((rfq) => (
                  <Card key={rfq.id} className="hover:bg-muted/50 transition-colors">
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <Link href={`/customer/rfq/${rfq.id}`}>
                            <h3 className="font-semibold hover:text-blue-600 transition-colors">
                              {rfq.project_description.slice(0, 120)}
                              {rfq.project_description.length > 120 ? '...' : ''}
                            </h3>
                          </Link>
                          <p className="text-sm text-muted-foreground mt-1">
                            {rfq.created_at ? formatDate(rfq.created_at) : 'Unknown date'}
                            {rfq.urgency ? ` · Urgency: ${rfq.urgency}` : ''}
                          </p>
                        </div>
                        <Badge className={getRFQStatusBadgeColor(rfq.rfq_status)}>
                          {rfq.rfq_status.replace(/_/g, ' ')}
                        </Badge>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 mt-3">
                        <span className="flex items-center gap-1 text-sm text-muted-foreground">
                          <MessageSquare className="h-4 w-4" />
                          {rfq.quote_count} quote{rfq.quote_count !== 1 ? 's' : ''}
                        </span>
                        {rfq.nda_required && (
                          <Badge variant="outline" className="text-xs">NDA Required</Badge>
                        )}
                        <div className="ml-auto flex items-center gap-2">
                          <Link href={`/customer/rfq/${rfq.id}`}>
                            <Button variant="outline" size="sm">
                              <FileText className="mr-1 h-3 w-3" />
                              Details
                            </Button>
                          </Link>
                          <Link href={`/customer/rfq/${rfq.id}/tracking`}>
                            <Button variant="outline" size="sm" className="text-blue-600 border-blue-200 hover:bg-blue-50">
                              <Activity className="mr-1 h-3 w-3" />
                              Track
                            </Button>
                          </Link>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
