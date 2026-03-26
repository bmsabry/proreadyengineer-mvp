'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { RFQ, QuoteForCustomerResponse } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate, getRFQStatusBadgeColor, formatCurrency } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { FileText, MessageSquare, CheckCircle, Phone, Globe, Mail, MapPin, Trophy, Download , ShieldAlert } from 'lucide-react';

export default function RFQDetailPage() {
  const { id } = useParams();
  const { user, isLoading: authLoading } = useRequireAuth(['customer', 'admin']);
  const [rfq, setRfq] = useState<RFQ | null>(null);
  const [quotes, setQuotes] = useState<QuoteForCustomerResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [downloadingQuoteId, setDownloadingQuoteId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [ndaFullySigned, setNdaFullySigned] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [rfqResponse, quotesResponse] = await Promise.all([
          api.rfqs.get(id as string),
          api.quotes.getForCustomer(id as string),
        ]);
        setRfq(rfqResponse.data);
        setQuotes(quotesResponse.data);
      } catch (error: unknown) {
        console.error('Failed to fetch RFQ data:', error);
        const err = error as { response?: { status?: number; data?: { detail?: string } } };
        const httpStatus = err?.response?.status;
        if (httpStatus === 404) {
          setFetchError('This RFQ was not found. The link may be incorrect.');
        } else if (httpStatus === 403) {
          setFetchError('You do not have permission to view this RFQ.');
        } else if (httpStatus === 401) {
          setFetchError('Your session has expired. Please log in again.');
        } else {
          setFetchError('Failed to load RFQ details. Please try again.');
        }
      } finally {
        setIsLoading(false);
      }
    };
    if (user && id) fetchData();
  }, [user, id]);

  const handleAcceptQuote = async (quoteId: string) => {
    setAcceptError(null);
    try {
      await api.quotes.accept(quoteId);
      const [rfqResponse, quotesResponse] = await Promise.all([
        api.rfqs.get(id as string),
        api.quotes.getForCustomer(id as string),
      ]);
      setRfq(rfqResponse.data);
      setQuotes(quotesResponse.data);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      setAcceptError(err?.response?.data?.detail || 'Failed to accept quote. Please try again.');
    }
  };

  const handleDownloadQuoteDocument = async (quote: QuoteForCustomerResponse) => {
    setDownloadingQuoteId(quote.id);
    try {
      if (quote.document_download_url) {
        window.open(quote.document_download_url, '_blank');
      } else {
        const response = await api.quotes.getQuoteDocumentDownload(quote.id);
        window.open(response.data.download_url, '_blank');
      }
    } catch (error) {
      console.error('Failed to get document download URL:', error);
    } finally {
      setDownloadingQuoteId(null);
    }
  };

  // Check NDA signed status when provider selected
  useEffect(() => {
    if (isProviderSelected && rfq?.nda_required) {
      api.rfqs.ndaStatus(id as string)
        .then((res) => {
          const data = res.data as { nda_status?: string; fully_signed_at?: string };
          if (data.nda_status === 'fully_signed' || data.fully_signed_at) {
            setNdaFullySigned(true);
          }
        })
        .catch(() => {});
    } else if (isProviderSelected) {
      setNdaFullySigned(true);
    }
  }, [isProviderSelected, rfq?.nda_required, id]);

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
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <p className="text-red-600 font-medium text-lg mb-2">Unable to Load RFQ</p>
          <p className="text-muted-foreground text-sm max-w-md">
            {fetchError || 'RFQ not found. Please check the link or return to your dashboard.'}
          </p>
          <a href="/customer/dashboard" className="mt-4 text-blue-600 hover:underline text-sm">
            ← Back to Dashboard
          </a>
        </div>
      </div>
    );
  }

  const isProviderSelected = rfq.rfq_status === 'customer_selected_provider';
  const acceptedQuote = quotes.find(q => q.quote_status === 'accepted');
  const acceptedProvider = acceptedQuote?.provider;

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
          <p className="text-muted-foreground">Created {formatDate(rfq.created_at)}</p>
        </div>
      </div>

      {/* Provider Contact Card - shown when a provider has been selected */}
      {isProviderSelected && acceptedProvider && (
        <div className="bg-green-50 border border-green-300 rounded-lg p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <Trophy className="h-6 w-6 text-green-600" />
            <h2 className="text-lg font-bold text-green-900">Provider Selected!</h2>
            <Badge className="bg-green-600 text-white">Engagement Started</Badge>
          </div>
          <p className="text-sm text-green-800 mb-4">
            You have selected a provider. Their contact details are shown below. Please reach out directly to begin engagement.
          </p>
          <div className="bg-white border border-green-200 rounded-md p-4">
            <h3 className="font-semibold text-gray-900 text-lg mb-3">
              {(acceptedProvider as any).firm_name || (acceptedProvider as any).provider_name || 'Selected Provider'}
            </h3>
            {(acceptedProvider as any).primary_specialty && (
              <p className="text-sm text-gray-500 mb-3">{(acceptedProvider as any).primary_specialty}</p>
            )}
            {rfq.nda_required && !ndaFullySigned ? (
              <div className="bg-amber-50 border border-amber-200 rounded-md p-4 mt-2">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldAlert className="h-4 w-4 text-amber-600" />
                  <span className="font-medium text-amber-900 text-sm">NDA Signing In Progress</span>
                </div>
                <p className="text-sm text-amber-800">
                  A Non-Disclosure Agreement has been sent to both you and the selected
                  provider. Contact details will be revealed once both parties have signed.
                </p>
                <p className="text-xs text-amber-700 mt-2">Check your email for signing instructions from Signwell.</p>
              </div>
            ) : (
            <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(acceptedProvider as any).email && (
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  <a href={`mailto:${(acceptedProvider as any).email}`} className="text-blue-600 hover:underline break-all">
                    {(acceptedProvider as any).email}
                  </a>
                </div>
              )}
              {(acceptedProvider as any).phone && (
                <div className="flex items-center gap-2 text-sm">
                  <Phone className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  <a href={`tel:${(acceptedProvider as any).phone}`} className="text-blue-600 hover:underline">
                    {(acceptedProvider as any).phone}
                  </a>
                </div>
              )}
              {(acceptedProvider as any).website && (
                <div className="flex items-center gap-2 text-sm">
                  <Globe className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  <a href={(acceptedProvider as any).website} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline break-all">
                    {(acceptedProvider as any).website}
                  </a>
                </div>
              )}
              {((acceptedProvider as any).city || (acceptedProvider as any).state) && (
                <div className="flex items-center gap-2 text-sm">
                  <MapPin className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  <span className="text-gray-700">
                    {[(acceptedProvider as any).city, (acceptedProvider as any).state].filter(Boolean).join(', ')}
                  </span>
                </div>
              )}
            </div>
            {!(acceptedProvider as any).email && !(acceptedProvider as any).phone && !(acceptedProvider as any).website && (
              <p className="text-sm text-gray-500 italic">Contact information not available. A confirmation email has been sent to you and the provider.</p>
            )}
            </>
            {acceptedQuote && (acceptedQuote.document_download_url || acceptedQuote.document_s3_key) && (
              <div className="mt-4 pt-4 border-t border-green-100">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownloadQuoteDocument(acceptedQuote)}
                  disabled={downloadingQuoteId === acceptedQuote.id}
                  className="flex items-center gap-2 text-blue-600 border-blue-200 hover:bg-blue-50"
                >
                  <Download className="h-4 w-4" />
                  {downloadingQuoteId === acceptedQuote.id ? 'Preparing...' : 'Download Provider Official Quote'}
                </Button>
                {acceptedQuote.document_filename && (
                  <p className="text-xs text-gray-400 mt-1">{acceptedQuote.document_filename}</p>
                )}
              </div>
            )}
          </div>
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
            <strong>Reminder:</strong> The accepted quote was a rough, non-binding, order-of-magnitude estimate. A refined final estimate will follow direct engagement.
          </div>
        </div>
      )}

      {acceptError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-sm text-red-700">{acceptError}</p>
        </div>
      )}

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
            <CardHeader><CardTitle>Project Information</CardTitle></CardHeader>
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
                <p className="text-sm text-muted-foreground mt-2">Providers are reviewing your RFQ. You will be notified when quotes arrive.</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <div className="p-3 bg-gray-50 border rounded text-xs text-gray-600">
                Quotes are rough, non-binding, order-of-magnitude estimates. A refined final estimate will follow direct engagement.
              </div>
              {quotes.map((quote) => (
                <Card key={quote.id} className={quote.quote_status === 'accepted' ? 'border-green-400 bg-green-50/30' : ''}>
                  <CardContent className="p-6">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold">
                            {(quote as any).provider?.firm_name || (quote as any).provider?.name || ('Provider #' + quote.provider_id)}
                          </h3>
                          {quote.quote_status === 'accepted' && (
                            <Badge className="bg-green-600 text-white">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Selected
                            </Badge>
                          )}
                          {quote.quote_status === 'not_selected' && (
                            <Badge variant="secondary">Not Selected</Badge>
                          )}
                          {quote.quote_status === 'submitted' && (
                            <Badge variant="outline">Submitted</Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Submitted {quote.submitted_at ? formatDate(quote.submitted_at) : 'Unknown'}
                        </p>
                      </div>
                      <div className="text-right">
                        {quote.rough_price_min != null && quote.rough_price_max != null && (
                          <p className="font-semibold text-lg">
                            {formatCurrency(quote.rough_price_min)} &ndash; {formatCurrency(quote.rough_price_max)}
                          </p>
                        )}
                        {quote.rough_price_min != null && quote.rough_price_max == null && (
                          <p className="font-semibold text-lg">From {formatCurrency(quote.rough_price_min)}</p>
                        )}
                        {quote.currency && (
                          <p className="text-xs text-muted-foreground">{quote.currency}</p>
                        )}
                      </div>
                    </div>

                    {quote.turnaround_estimate_text && (
                      <div className="mb-3">
                        <h4 className="font-medium text-sm text-muted-foreground">Turnaround Estimate</h4>
                        <p className="mt-1 text-sm">{quote.turnaround_estimate_text}</p>
                      </div>
                    )}

                    {quote.assumptions_text && (
                      <div className="mb-3">
                        <h4 className="font-medium text-sm text-muted-foreground">Assumptions</h4>
                        <p className="mt-1 text-sm whitespace-pre-wrap">{quote.assumptions_text}</p>
                      </div>
                    )}

                    {quote.scope_notes && (
                      <div className="mb-3">
                        <h4 className="font-medium text-sm text-muted-foreground">Additional Scope Notes</h4>
                        <p className="mt-1 text-sm">{quote.scope_notes}</p>
                      </div>
                    )}

                    {/* Download provider official quote - only visible on accepted quote */}
                    {quote.quote_status === 'accepted' && (quote.document_download_url || quote.document_s3_key) && (
                      <div className="mb-3">
                        <button
                          onClick={() => handleDownloadQuoteDocument(quote)}
                          disabled={downloadingQuoteId === quote.id}
                          className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 underline disabled:opacity-50"
                        >
                          <Download className="h-4 w-4" />
                          {downloadingQuoteId === quote.id ? 'Preparing download...' : 'Download Provider Official Quote'}
                        </button>
                        {quote.document_filename && (
                          <p className="text-xs text-gray-400 mt-0.5 ml-6">{quote.document_filename}</p>
                        )}
                      </div>
                    )}

                    {!isProviderSelected && quote.quote_status === 'submitted' && (
                      <div className="mt-4 pt-4 border-t">
                        <button
                          onClick={() => handleAcceptQuote(quote.id)}
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-green-600 hover:bg-green-700 text-white text-sm font-medium transition-colors"
                        >
                          <CheckCircle className="h-4 w-4" />
                          Accept This Quote &amp; Reveal Contact
                        </button>
                        <p className="text-xs text-muted-foreground mt-2">
                          Accepting a quote will reveal the provider&apos;s direct contact information and mark other quotes as not selected.
                        </p>
                      </div>
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
              <CardDescription>Files uploaded with this RFQ</CardDescription>
            </CardHeader>
            <CardContent>
              {(rfq as any).files && (rfq as any).files.length > 0 ? (
                <ul className="space-y-2">
                  {(rfq as any).files.map((file: any) => (
                    <li key={file.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded border">
                      <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
                      <span className="text-sm flex-1 truncate">{file.original_filename}</span>
                      {file.download_url && (
                        <a
                          href={file.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-blue-600 hover:underline flex-shrink-0"
                        >
                          Download
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground py-4 text-center">No files attached to this RFQ.</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
