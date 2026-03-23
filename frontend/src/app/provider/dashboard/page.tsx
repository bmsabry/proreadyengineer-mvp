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
import { Mail, FileText, AlertCircle, Trophy, Phone, Globe, ArrowRight } from 'lucide-react';

export default function ProviderDashboard() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const [teasers, setTeasers] = useState<RFQTeaser[]>([]);
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
        const teasersData = teasersResponse.data as any;
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

  const acceptedQuotes = quotes.filter(q => q.quote_status === 'accepted');
  const pendingTeasers = teasers.filter(t => t.status !== 'unlocked' && t.status !== 'accepted');

  return (
    <div className="container py-8">

      {/* ACCEPTED QUOTE BANNER - highest priority, shown at very top */}
      {acceptedQuotes.length > 0 && (
        <div className="bg-green-50 border-2 border-green-400 rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <Trophy className="h-6 w-6 text-green-600" />
            <h2 className="text-lg font-bold text-green-900">
              {acceptedQuotes.length === 1 ? 'Your Quote Was Accepted!' : acceptedQuotes.length + ' Quotes Were Accepted!'}
            </h2>
            <Badge className="bg-green-600 text-white">Congratulations</Badge>
          </div>
          <p className="text-sm text-green-800 mb-4">
            A customer has selected your quote. Please reach out to the customer directly to begin engagement and provide a refined estimate.
          </p>
          <div className="space-y-3">
            {acceptedQuotes.map((quote) => (
              <div key={quote.id} className="bg-white border border-green-200 rounded-md p-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="font-medium text-gray-900 text-sm">RFQ Project</p>
                    <p className="text-xs text-gray-500">
                      Accepted {quote.submitted_at ? formatDate(quote.submitted_at) : 'recently'}
                    </p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-600">
                      {quote.rough_price_min && quote.rough_price_max && (
                        <span className="font-medium">
                          ${Number(quote.rough_price_min).toLocaleString()} &ndash; ${Number(quote.rough_price_max).toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    className="bg-green-600 hover:bg-green-700 text-white gap-1"
                    onClick={() => router.push('/provider/rfq/' + quote.rfq_id)}
                  >
                    View Project
                    <ArrowRight className="h-3 w-3" />
                  </Button>
                </div>
                {/* Customer contact card */}
                <div className="bg-white border border-green-200 rounded-md p-4">
                  <p className="text-xs font-semibold text-green-700 uppercase mb-2">Customer Contact Information</p>
                  <div className="grid grid-cols-1 gap-1 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-700 w-20">Name:</span>
                      <span className="text-gray-900">{quote.customer_contact_name || 'Not provided'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-700 w-20">Company:</span>
                      <span className="text-gray-900">{quote.customer_company || 'Not provided'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-700 w-20">Email:</span>
                      {quote.customer_email ? (
                        <a href={`mailto:${quote.customer_email}`} className="text-blue-600 hover:underline">{quote.customer_email}</a>
                      ) : <span className="text-gray-500">Not provided</span>}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* PENDING ACTION SECTION */}
      {pendingTeasers.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="h-5 w-5 text-amber-600" />
            <h2 className="text-lg font-semibold text-amber-900">Action Required: Pending RFQ Opportunities</h2>
          </div>
          <p className="text-sm text-amber-700 mb-4">
            You have {pendingTeasers.length} RFQ{pendingTeasers.length > 1 ? 's' : ''} waiting.
            Unlock to submit a quote &mdash; only the first 5 quotes per RFQ are accepted.
          </p>
          <div className="space-y-2">
            {pendingTeasers.map(teaser => (
              <div key={teaser.rfq_id} className="flex items-center justify-between bg-white border border-amber-100 rounded-md px-4 py-3">
                <span className="text-sm font-medium text-gray-800">RFQ #{String(teaser.rfq_id).slice(0, 8)}&hellip;</span>
                <Button
                  size="sm"
                  className="bg-amber-600 hover:bg-amber-700 text-white"
                  onClick={() => router.push('/provider/rfq/' + teaser.rfq_id)}
                >
                  View &amp; Unlock ($10)
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

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
            <CardDescription>Opportunities matching your profile</CardDescription>
          </CardHeader>
          <CardContent>
            {teasers.length === 0 ? (
              <div className="space-y-4">
                <div className="text-center py-4">
                  <p className="text-muted-foreground text-sm">No new RFQ teasers at this time</p>
                </div>
                {hasMembership === false && (
                  <div className="mt-2 space-y-3">
                    <p className="text-sm font-medium text-gray-700">Choose how to list your firm:</p>

                    <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold bg-green-600 text-white px-2 py-0.5 rounded">FREE</span>
                        <h3 className="text-sm font-semibold text-green-900">Find &amp; Claim Existing Listing</h3>
                      </div>
                      <p className="text-xs text-green-700 mb-2">
                        Search our database of 5,400+ firms. If your firm is listed and your email matches, claim it instantly.
                      </p>
                      <Link href="/provider/claim">
                        <Button size="sm" className="bg-green-600 hover:bg-green-700 text-white text-xs w-full">
                          Search My Firm
                        </Button>
                      </Link>
                    </div>

                    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold bg-blue-600 text-white px-2 py-0.5 rounded">$100</span>
                        <h3 className="text-sm font-semibold text-blue-900">Self-Service New Listing</h3>
                      </div>
                      <p className="text-xs text-blue-700 mb-2">
                        Create your own profile with description, specialties, and notable projects. One-time fee.
                      </p>
                      <Link href="/provider/add-firm">
                        <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white text-xs w-full">
                          Create My Listing
                        </Button>
                      </Link>
                    </div>

                    <div className="rounded-lg border border-purple-200 bg-purple-50 p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold bg-purple-600 text-white px-2 py-0.5 rounded">$750</span>
                        <h3 className="text-sm font-semibold text-purple-900">AI-Assisted Premium Listing</h3>
                      </div>
                      <p className="text-xs text-purple-700 mb-2">
                        Our team uses AI to build a comprehensive, optimized profile from your website and materials.
                      </p>
                      <Link href="/provider/add-firm?tier=premium">
                        <Button size="sm" className="bg-purple-600 hover:bg-purple-700 text-white text-xs w-full">
                          Request AI Listing
                        </Button>
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {teasers.slice(0, 5).map((teaser) => (
                  <Link key={teaser.rfq_id} href={'/provider/rfq/' + teaser.rfq_id + '/teaser'}>
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
            <CardDescription>Quotes you have submitted</CardDescription>
          </CardHeader>
          <CardContent>
            {quotes.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">No quotes submitted yet</p>
            ) : (
              <div className="space-y-4">
                {quotes.slice(0, 5).map((quote) => (
                  <Card
                    key={quote.id}
                    className={quote.quote_status === 'accepted' ? 'border-green-400 bg-green-50/50' : ''}
                  >
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <p className="font-medium text-sm">
                              RFQ #{String(quote.rfq_id).slice(0, 8)}&hellip;
                            </p>
                            {quote.quote_status === 'accepted' && (
                              <Badge className="bg-green-600 text-white text-xs">
                                <Trophy className="h-3 w-3 mr-1" />
                                Accepted!
                              </Badge>
                            )}
                            {quote.quote_status === 'submitted' && (
                              <Badge variant="outline" className="text-xs">Submitted</Badge>
                            )}
                            {quote.quote_status === 'not_selected' && (
                              <Badge variant="secondary" className="text-xs">Not Selected</Badge>
                            )}
                            {quote.quote_status === 'withdrawn' && (
                              <Badge variant="secondary" className="text-xs">Withdrawn</Badge>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {quote.submitted_at ? formatDate(quote.submitted_at) : 'Draft'}
                          </p>
                          {quote.rough_price_min != null && quote.rough_price_max != null && (
                            <p className="text-sm font-medium mt-1">
                              ${Number(quote.rough_price_min).toLocaleString()} &ndash; ${Number(quote.rough_price_max).toLocaleString()}
                            </p>
                          )}
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => router.push('/provider/rfq/' + quote.rfq_id)}
                          className="gap-1"
                        >
                          View
                          <ArrowRight className="h-3 w-3" />
                        </Button>
                      </div>
                      {quote.quote_status === 'accepted' && (
                        <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded text-xs text-green-800 space-y-1">
                          <p className="font-semibold">🎉 Your quote was accepted! Contact the customer directly:</p>
                          <p><span className="font-medium">Name:</span> {quote.customer_contact_name || 'See email'}</p>
                          <p><span className="font-medium">Company:</span> {quote.customer_company || 'See email'}</p>
                          {quote.customer_email && (
                            <p><span className="font-medium">Email:</span> <a href={`mailto:${quote.customer_email}`} className="underline">{quote.customer_email}</a></p>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
                {quotes.length > 5 && (
                  <p className="text-xs text-center text-muted-foreground">
                    Showing 5 of {quotes.length} quotes
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
