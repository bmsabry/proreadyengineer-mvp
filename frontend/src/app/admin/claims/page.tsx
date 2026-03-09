'use client';

import { useState, useEffect } from 'react';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { ProviderClaimRequest } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatDate } from '@/lib/utils';
import { CheckCircle, XCircle } from 'lucide-react';
import { toast } from 'sonner';

export default function AdminClaimsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [claims, setClaims] = useState<ProviderClaimRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchClaims = async () => {
      try {
        const response = await api.admin.listProviderClaims();
        setClaims(response.data);
      } catch (error) {
        console.error('Failed to fetch claims:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchClaims();
  }, []);

  const handleApprove = async (claimId: string) => {
    try {
      await api.admin.approveProviderClaim(claimId);
      toast.success('Claim approved');
      setClaims(claims.map(c => c.id === claimId ? { ...c, status: 'approved' } : c));
    } catch (error) {
      toast.error('Failed to approve claim');
    }
  };

  const handleReject = async (claimId: string) => {
    try {
      await api.admin.rejectProviderClaim(claimId);
      toast.success('Claim rejected');
      setClaims(claims.map(c => c.id === claimId ? { ...c, status: 'rejected' } : c));
    } catch (error) {
      toast.error('Failed to reject claim');
    }
  };

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
      <h1 className="text-3xl font-bold mb-8">Provider Claim Requests</h1>

      <Card>
        <CardHeader>
          <CardTitle>Pending Claims ({claims.filter(c => c.status === 'pending').length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Claimant</TableHead>
                <TableHead>Proof Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Submitted</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {claims.map((claim) => (
                <TableRow key={claim.id}>
                  <TableCell>{claim.provider_name}</TableCell>
                  <TableCell>{claim.claimant_email}</TableCell>
                  <TableCell>{claim.proof_type}</TableCell>
                  <TableCell>
                    <Badge variant={claim.status === 'pending' ? 'default' : claim.status === 'approved' ? 'success' : 'destructive'}>
                      {claim.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{formatDate(claim.created_at)}</TableCell>
                  <TableCell>
                    {claim.status === 'pending' && (
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => handleApprove(claim.id)}>
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleReject(claim.id)}>
                          <XCircle className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    )}
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
