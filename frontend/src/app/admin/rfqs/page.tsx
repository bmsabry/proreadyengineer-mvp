'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQ } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatDate, getRFQStatusBadgeColor } from '@/lib/utils';
import { Search, Eye } from 'lucide-react';

export default function AdminRFQsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [rfqs, setRfqs] = useState<RFQ[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    const fetchRFQs = async () => {
      try {
        const response = await api.admin.listRFQs({ page: 1, page_size: 50 });
        setRfqs(response.data.items);
      } catch (error) {
        console.error('Failed to fetch RFQs:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchRFQs();
  }, []);

  const filteredRFQs = rfqs.filter(rfq => 
    rfq.project_description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    rfq.customer_email.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
        <h1 className="text-3xl font-bold">Manage RFQs</h1>
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search RFQs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All RFQs ({filteredRFQs.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Description</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Urgency</TableHead>
                <TableHead>Quotes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRFQs.map((rfq) => (
                <TableRow key={rfq.id}>
                  <TableCell className="font-medium max-w-xs truncate">
                    {rfq.project_description.slice(0, 50)}...
                  </TableCell>
                  <TableCell>{rfq.customer_email}</TableCell>
                  <TableCell>
                    <Badge className={getRFQStatusBadgeColor(rfq.rfq_status)}>
                      {rfq.rfq_status.replace(/_/g, ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell>{rfq.urgency}</TableCell>
                  <TableCell>{rfq.quote_count}</TableCell>
                  <TableCell>{formatDate(rfq.created_at)}</TableCell>
                  <TableCell>
                    <Link href={`/admin/rfqs/${rfq.id}`}>
                      <Button variant="outline" size="sm" className="flex items-center gap-1.5 text-xs">
                        <Eye className="h-3.5 w-3.5" />
                        Dispatch Tracking
                      </Button>
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
