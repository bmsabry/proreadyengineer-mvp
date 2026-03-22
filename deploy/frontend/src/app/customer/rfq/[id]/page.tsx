'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQ, Quote } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate, getRFQStatusBadgeColor, formatCurrency } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FileText, MessageSquare, Download, CheckCircle } from 'lucide-react';

export default function RFQDetailPage() {
  const { id } = useParams();
  const { user, isLoading: authLoading } = useRequireAuth(['customer']);
  const [rfq, setRfq] = useState<RFQ | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [rfqResponse, quotesResponse] = await Promise.all([
          api.rfqs.get(id as string),
          api.quotes.getForCustomer(id as string),
        ]);
        setRfq(rfqResponse.data);
        setQuotes(quotesResponse.data);
      } catch (error) {
        console.error('Failed to fetch RFQ data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    if (user && id) {
      fetchData();
    }
  }, [user, id]);

  const handleAcceptQuote = async (quoteId: string) => {
    try {
      await api.quotes.accept(quoteId);
      // Refresh data
      const [rfqResponse, quotesResponse] = await Promise.all([
        api.rfqs.get(id as string),
        api.quotes.getForCustomer(id as string),
      ]);
      setRfq(rfqResponse.data);
      setQuotes(quotesResponse.data);
    } catch (error) {
      console.error('Failed to accept quote:', error);
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

  if (!rfq) {
    return (
      <div className="container py-8">
        <p className="text-center text-muted-foreground">RFQ not found</p>
      </div>
    );
  }

  return (
    <div className="container py-8">
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">RFQ Details</h1>
            <Badge className={getRFQStatusBadgeColor(rfq.rfq_status)}>
              {rfq.rfq_status.replace(/_/g, ' ')}
            </Badge>
          </div>
          <p className="text-muted-foreground">
            Created {formatDate(rfq.created_at)}
          </p>
        </div>
      </div>

      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="quotes">
            <MessageSquare className="h-4 w-4 mr-1" />
            Quotes ({rfq.quote_count})
          </TabsTrigger>
          <TabsTrigger value="files">
            <FileText className="h-4 w-4 mr-1" />
            Files
          </TabsTrigger>
        </TabsList>

        <TabsContent value="details" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Project Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="font-medium text-sm text-muted-foreground">Description</h4>
                <p className="mt-1">{rfq.project_description}</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="font-medium text-sm text-muted-foreground">Urgency</h4>
                  <p className="mt-1">{rfq.urgency}</p>
                </div>
                <div>
                  <h4 className="font-medium text-sm text-muted-foreground">NDA Required</h4>
                  <p className="mt-1">{rfq.nda_required ? 'Yes' : 'No'}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="quotes">
          {quotes.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-muted-foreground">No quotes received yet</p>
                <p className="text-sm text-muted-foreground mt-2">
                  Providers are reviewing your RFQ. You will be notified when quotes arrive.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {quotes.map((quote) => (
                <Card key={quote.id}>
                  <CardContent className="p-6">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-semibold">{quote.provider?.name}</h3>
                        <p className="text-sm text-muted-foreground">
                          Submitted {quote.submitted_at ? formatDate(quote.submitted_at) : "Unknown"}
                        </p>
                      </div>
                      <div className="text-right">
                        {quote.rough_price_min && quote.rough_price_max && (
                          <p className="font-semibold text-lg">
                            {formatCurrency(quote.rough_price_min)} - {formatCurrency(quote.rough_price_max)}
                          </p>
                        )}
                      </div>
                    </div>
                    
                    {quote.assumptions_text && (
                      <div className="mt-4">
                        <h4 className="font-medium text-sm text-muted-foreground">Assumptions</h4>
                        <p className="mt-1 text-sm">{quote.assumptions_text}</p>
                      </div>
                    )}
                    
                    {quote.turnaround_estimate_text && (
                      <div className="mt-2">
                        <h4 className="font-medium text-sm text-muted-foreground">Timeline Estimate</h4>
                        <p className="mt-1 text-sm">{quote.turnaround_estimate_text}</p>
                      </div>
                    )}
                    {quote.scope_notes && (
                      <div className="mt-2">
                        <h4 className="font-medium text-sm text-muted-foreground">Additional Scope Notes</h4>
                        <p className="mt-1 text-sm">{quote.scope_notes}</p>
                      </div>
                    )}

                    {rfq.rfq_status !== 'customer_selected_provider' && rfq.rfq_status !== 'closed_no_selection' && (
                      <Button 
                        className="mt-4"
                        onClick={() => handleAcceptQuote(quote.id)}
                      >
                        <CheckCircle className="mr-2 h-4 w-4" />
                        Accept Quote
                      </Button>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="files">
          <Card>
            <CardHeader>
              <CardTitle>Attached Files</CardTitle>
              <CardDescription>Project documents and specifications</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-center py-8">No files attached</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
