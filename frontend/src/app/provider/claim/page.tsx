'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Search, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';

interface ClaimSearchResult extends Provider {
  email_match?: boolean;
}

export default function ProviderClaimPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<ClaimSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [claimedIds, setClaimedIds] = useState<Set<string>>(new Set());
  const [showAddFirmBanner, setShowAddFirmBanner] = useState(false);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setHasSearched(true);
    setShowAddFirmBanner(false);
    try {
      const response = await api.providers.claimSearch({ query: searchQuery });
      const data = response.data || [];
      setResults(data);
      if (data.length === 0) setShowAddFirmBanner(true);
    } catch (error) {
      console.error('Search failed:', error);
      toast.error('Search failed. Please try again.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleClaim = async (providerId: string) => {
    try {
      await api.providerClaims.create({
        provider_id: providerId,
        proof_type: 'email_domain',
        proof_payload: { email: user?.email },
        submitted_notes: 'Claim request from dashboard',
      });
      setClaimedIds(prev => new Set([...prev, providerId]));
      toast.success('Claim request submitted successfully!');
    } catch (error: any) {
      const status = error?.response?.status;
      const detail = error?.response?.data?.detail;
      if (status === 403 && detail) {
        toast.error(detail);
        setShowAddFirmBanner(true);
      } else {
        toast.error('Failed to submit claim request. Please try again.');
      }
    }
  };

  if (authLoading) {
    return (
      <div className="container py-8">
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8 max-w-3xl">
      <h1 className="text-3xl font-bold mb-2">Find &amp; Claim Your Firm</h1>
      <p className="text-muted-foreground mb-8">
        Search our database of 5,400+ engineering firms. If your email matches a listed firm, you can claim it instantly.
      </p>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Search for Your Firm</CardTitle>
          <CardDescription>
            Enter your company name to find your existing profile
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Enter company name..."
                className="pl-10"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
            </div>
            <Button onClick={handleSearch} disabled={isSearching}>
              {isSearching ? 'Searching...' : 'Search'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {hasSearched && (
        <div className="space-y-4">
          {results.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center">
                <p className="text-muted-foreground">No providers found matching your search.</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Found {results.length} firm{results.length !== 1 ? 's' : ''}. Select yours to claim it.
              </p>
              {results.map((provider) => {
                const id = String(provider.id);
                const isClaimed = claimedIds.has(id);
                return (
                  <Card key={id} className={isClaimed ? 'opacity-60' : ''}>
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <h3 className="font-semibold text-lg">{provider.name}</h3>
                            {provider.email_match === true && (
                              <Badge className="bg-green-100 text-green-800 border-green-200 text-xs">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                Email matches — instant claim
                              </Badge>
                            )}
                            {provider.email_match === false && (
                              <Badge variant="outline" className="border-yellow-300 text-yellow-700 text-xs">
                                <AlertTriangle className="h-3 w-3 mr-1" />
                                Email mismatch — admin review
                              </Badge>
                            )}
                          </div>
                          {(provider.city || provider.state) && (
                            <p className="text-sm text-muted-foreground">
                              {[provider.city, provider.state].filter(Boolean).join(', ')}
                            </p>
                          )}
                          {provider.primary_specialty && (
                            <p className="text-sm mt-1">
                              <span className="font-medium">Specialty:</span> {provider.primary_specialty}
                            </p>
                          )}
                        </div>
                        <div className="flex-shrink-0">
                          {isClaimed ? (
                            <Badge className="bg-green-600 text-white">Submitted</Badge>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => handleClaim(id)}
                              className={provider.email_match === true
                                ? 'bg-green-600 hover:bg-green-700 text-white'
                                : 'bg-gray-600 hover:bg-gray-700 text-white'
                              }
                            >
                              <CheckCircle className="mr-2 h-4 w-4" />
                              {provider.email_match === true ? 'Claim Now' : 'Request Claim'}
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* Add Firm banner - shown when no results or after 403 */}
      {showAddFirmBanner && (
        <div className="mt-8 rounded-lg border border-blue-200 bg-blue-50 p-5">
          <h3 className="text-sm font-semibold text-blue-900 mb-1">Can&apos;t find your firm?</h3>
          <p className="text-xs text-blue-700 mb-3">
            Your firm may not be in our database yet, or your email does not match the record on file.
            You can create a new self-service listing for a one-time fee of $100.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link href="/provider/add-firm">
              <Button size="sm" className="bg-primary hover:bg-primary/90 text-white text-xs">
                Create New Listing ($100)
                <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </Link>
            <Link href="/provider/add-firm?tier=premium">
              <Button size="sm" variant="outline" className="border-purple-300 text-purple-700 text-xs">
                AI-Assisted Listing ($750)
                <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
