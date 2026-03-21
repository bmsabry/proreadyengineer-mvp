'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQTeaser, Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate } from '@/lib/utils';
import { Mail, FileText, DollarSign, PlusCircle, AlertCircle } from 'lucide-react';

export default function ProviderDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [teasers, setTeasers] = useState<RFQTeaser[]>([]);
  const [unlockedRFQs, setUnlockedRFQs] = useState<any[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMembership, setHasMembership] = useState<boolean | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [teasersResponse, quotesResponse] = await Promise.all([
          api.providerRFQ.getTeasers(),
          api.quotes.getForProvider(),
        ]);
        const teasersData = teasersResponse.data as any; // backend returns {teasers, has_membership}
        const teasersList = teasersData?.teasers || teasersData || [];
        const membershipStatus = teasersData?.has_membership;
        if (membershipStatus !== undefined) {
          setHasMembership(membershipStatus);
        } else {
          setHasMembership(Array.isArray(teasersList) && teasersList.length > 0 ? true : null);
        }
        setTeasers(Array.isArray(teasersList) ? teasersList : []);
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
      {/* PENDING ACTION SECTION - at top */}
      {(() => {
        const pendingTeasers = teasers.filter(t => t.status !== 'unlocked' && t.status !== 'accepted');
        if (pendingTeasers.length === 0) return null;
        return (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <AlertCircle className="h-5 w-5 text-amber-600" />
              <h2 className="text-lg font-semibold text-amber-900">Action Required: Pending RFQ Opportunities</h2>
            </div>
            <p className="text-sm text-amber-700 mb-4">
              You have {pendingTeasers.length} RFQ{pendingTeasers.length > 1 ? 's' : ''} waiting. Unlock to submit a quote — only the first 5 quotes per RFQ are accepted.
            </p>
            <div className="space-y-2">
              {pendingTeasers.map(teaser => (
                <div key={teaser.rfq_id} className="flex items-center justify-between bg-white border border-amber-100 rounded-md px-4 py-3">
                  <span className="text-sm font-medium text-gray-800">RFQ #{teaser.rfq_id}</span>
                  <Button
                    size="sm"
                    className="bg-amber-600 hover:bg-amber-700 text-white"
                    onClick={() => router.push(`/provider/rfq/${teaser.rfq_id}`)}
                  >
                    View &amp; Unlock ($10)
                  </Button>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

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
              <div className="space-y-4">
                <div className="text-center py-4">
                  <p className="text-muted-foreground text-sm">No new RFQ teasers at this time</p>
                </div>
                {hasMembership === false && (
                  <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-4">
                    <h3 className="text-sm font-semibold text-blue-900 mb-1">Link Your Engineering Firm</h3>
                    <p className="text-xs text-blue-700 mb-3">
                      Link your account to your firm in our directory to receive RFQ opportunities matching your specialties.
                    </p>
                    <Link href="/provider/claim">
                      <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white text-xs">
                        Search &amp; Link My Firm
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
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
