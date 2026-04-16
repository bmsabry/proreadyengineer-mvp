'use client';

import { useState, useEffect } from 'react';
import { useRequireAuth } from '../../../hooks/useAuth';
import { api } from '../../../lib/api';
import { Advertisement } from '../../../types';
import { Button } from '../../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Badge } from '../../../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../../components/ui/table';
import { formatDate } from '../../../lib/utils';
import { Pause } from 'lucide-react';
import { toast } from 'sonner';

// Helper to map ad_status to valid Badge variants
const getStatusVariant = (status: string): "default" | "secondary" | "destructive" | "outline" => {
  switch (status) {
    case 'active': return 'default';
    case 'paused': return 'destructive';
    case 'empty': return 'outline';
    default: return 'secondary';
  }
};

export default function AdminAdsPage() {
  const { isLoading: authLoading } = useRequireAuth(['admin']);
  const [ads, setAds] = useState<Advertisement[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchAds = async () => {
      try {
        const response = await api.admin.listAds();
        setAds(response.data.items);
      } catch (error) {
        console.error('Failed to fetch ads:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchAds();
  }, []);

  const handlePause = async (adId: string) => {
    try {
      await api.admin.pauseAd(adId);
      toast.success('Ad paused');
      setAds(ads.map(ad => ad.id === adId ? { ...ad, ad_status: 'paused' } : ad));
    } catch (error) {
      toast.error('Failed to pause ad');
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
      <h1 className="text-3xl font-bold mb-8">Ad Moderation</h1>

      <Card>
        <CardHeader>
          <CardTitle>All Advertisements ({ads.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ads.map((ad) => (
                <TableRow key={ad.id}>
                  <TableCell>{ad.title}</TableCell>
                  <TableCell>
                    <Badge variant={getStatusVariant(ad.ad_status)}>
                      {ad.ad_status}
                    </Badge>
                  </TableCell>
                  <TableCell>{ad.started_at ? formatDate(ad.started_at) : "N/A"}</TableCell>
                  <TableCell>
                    {ad.ad_status === 'active' && (
                      <Button variant="ghost" size="sm" onClick={() => handlePause(ad.id)}>
                        <Pause className="h-4 w-4" />
                      </Button>
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
