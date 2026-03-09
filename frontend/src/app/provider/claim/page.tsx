'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Search, Building2, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';

export default function ProviderClaimPage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<Provider[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    
    setIsSearching(true);
    setHasSearched(true);
    
    try {
      const response = await api.providers.claimSearch({ query: searchQuery });
      setResults(response.data.results || []);
    } catch (error) {
      console.error('Search failed:', error);
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
      toast.success('Claim request submitted for review');
    } catch (error) {
      toast.error('Failed to submit claim request');
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
      <h1 className="text-3xl font-bold mb-2">Claim Your Provider Profile</h1>
      <p className="text-muted-foreground mb-8">
        Search for your engineering firm in our directory and submit a claim request
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
                <p className="text-muted-foreground">No providers found</p>
                <p className="text-sm text-muted-foreground mt-2">
                  Can&apos;t find your firm?{' '}
                  <Link href="/provider/profile" className="text-primary hover:underline">
                    Create a new profile
                  </Link>
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                Found {results.length} providers. Click claim to request ownership.
              </p>
              {results.map((provider) => (
                <Card key={provider.id}>
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-semibold text-lg">{provider.name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {provider.city}, {provider.state}
                        </p>
                        {provider.primary_specialty && (
                          <p className="text-sm mt-1">
                            <span className="font-medium">Specialty:</span> {provider.primary_specialty}
                          </p>
                        )}
                      </div>
                      <Button onClick={() => handleClaim(provider.id)}>
                        <CheckCircle className="mr-2 h-4 w-4" />
                        Claim
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
