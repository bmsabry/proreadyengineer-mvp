'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser, Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate } from '@/lib/utils';
import { Mail, FileText, DollarSign, PlusCircle } from 'lucide-react';

export default function ProviderDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [teasers, setTeasers] = useState<RFQTeaser[]>([]);
  const [unlockedRFQs, setUnlockedRFQs] = useState<any[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [teasersResponse, quotesResponse] = await Promise.all([
          api.providerRFQ.getTeasers(),
          api.quotes.getForProvider(),
        ]);
        setTeasers(teasersResponse.data);
        setQuotes(quotesResponse.data);
      } catch (error) {
        console.error('Failed to fetch provider data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    if (user) {
      fetchData();
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
          <h1 className="text-3xl font-bold">Provider Dashboard</h1>
          <p className="text-muted-foreground">Manage your profile and respond to RFQs</p>
        </div>
        <Link href="/provider/profile">
          <Button variant="outline">Edit Profile</Button>
        </Link>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* RFQ Teasers */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              New RFQ Teasers
            </CardTitle>
            <CardDescription>
              Opportunities matching your profile
            </CardDescription>
          </CardHeader>
          <CardContent>
            {teasers.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">
                No new RFQ teasers at this time
              </p>
            ) : (
              <div className="space-y-4">
                {teasers.slice(0, 5).map((teaser) => (
                  <Link key={teaser.rfq_id} href={`/provider/rfq/${teaser.rfq_id}/teaser`}>
                    <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
                      <CardContent className="p-4">
                        <div className="flex justify-between items-start">
                          <div>
                            <Badge className="mb-2">{teaser.urgency}</Badge>
                            <p className="text-sm text-muted-foreground">
                              Tollgates: {teaser.tollgate_phases?.join(', ') || 'N/A'}
                            </p>
                          </div>
                          {teaser.nda_required && (
                            <Badge variant="outline">NDA</Badge>
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

        {/* My Quotes */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              My Quotes
            </CardTitle>
            <CardDescription>
              Quotes you have submitted
            </CardDescription>
          </CardHeader>
          <CardContent>
            {quotes.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">
                No quotes submitted yet
              </p>
            ) : (
              <div className="space-y-4">
                {quotes.slice(0, 5).map((quote) => (
                  <Card key={quote.id}>
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-medium">{quote.provider?.name}</p>
                          <p className="text-sm text-muted-foreground">
                            Submitted {quote.submitted_at ? formatDate(quote.submitted_at) : "Unknown"}
                          </p>
                        </div>
                        <Badge>{quote.quote_status}</Badge>
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
