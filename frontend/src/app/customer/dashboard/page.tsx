'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQ } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate, getRFQStatusBadgeColor } from '@/lib/utils';
import { PlusCircle, FileText, MessageSquare } from 'lucide-react';

export default function CustomerDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchRFQs = async () => {
      try {
        const response = await api.admin.listRFQs({ page: 1, page_size: 10 });
        setRfqs(response.data.items);
      } catch (error) {
        console.error('Failed to fetch RFQs:', error);
      } finally {
        setIsLoading(false);
      }
    };
    
    if (user) {
      fetchRFQs();
    }
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
        <Link href="/customer/rfq/new">
          <Button>
            <PlusCircle className="mr-2 h-4 w-4" />
            New RFQ
          </Button>
        </Link>
      </div>

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Your RFQs
            </CardTitle>
            <CardDescription>
              Track the status of your request for quotes
            </CardDescription>
          </CardHeader>
          <CardContent>
            {rfqs.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-muted-foreground mb-4">No RFQs yet</p>
                <Link href="/customer/rfq/new">
                  <Button variant="outline">Create your first RFQ</Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {rfqs.map((rfq) => (
                  <Link key={rfq.id} href={`/customer/rfq/${rfq.id}`}>
                    <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
                      <CardContent className="p-4">
                        <div className="flex justify-between items-start">
                          <div>
                            <h3 className="font-semibold">{rfq.project_description.slice(0, 100)}...</h3>
                            <p className="text-sm text-muted-foreground">
                              Created {formatDate(rfq.created_at)} • Urgency: {rfq.urgency}
                            </p>
                          </div>
                          <Badge className={getRFQStatusBadgeColor(rfq.rfq_status)}>
                            {rfq.rfq_status.replace(/_/g, ' ')}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 mt-4 text-sm">
                          <span className="flex items-center gap-1">
                            <MessageSquare className="h-4 w-4" />
                            {rfq.quote_count} quotes
                          </span>
                          {rfq.nda_required && (
                            <Badge variant="outline">NDA Required</Badge>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
