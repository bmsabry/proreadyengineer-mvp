'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { SearchResult } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Search, Building2, MapPin, Star, AlertTriangle } from 'lucide-react';
import { DebugPanel } from '@/components/search/DebugPanel';

function SearchPageContent() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get('q') || '';

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  // Debug tracking state
  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [searchError, setSearchError] = useState<string | null>(null);
  const [resultCount, setResultCount] = useState(0);
  const [totalMatches, setTotalMatches] = useState(0);

  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery);
    }
  }, [initialQuery]);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    setHasSearched(true);
    setSearchStatus('loading');
    setSearchError(null);

    try {
      console.log('[Search] Sending query:', searchQuery);
      const response = await api.search.query({ query: searchQuery });

      const results = response.data.results || [];
      setResults(results);
      setResultCount(results.length);
      setTotalMatches(response.data.total_matches || 0);
      setSearchStatus('success');

      console.log('[Search] Success:', results.length, 'results,', response.data.total_matches, 'total matches');
    } catch (error: any) {
      console.error('[Search] Search failed:', error);
      setSearchStatus('error');
      setResults([]);
      setResultCount(0);

      const errorMsg = error.response?.data?.detail || error.message || 'Search failed';
      setSearchError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProReadyEngineer</span>
          </Link>
          <div className="ml-auto flex gap-4">
            <Link href="/login">
              <Button variant="ghost">Sign In</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="container py-8">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold mb-6">Search Engineering Providers</h1>

          <form onSubmit={handleSubmit} className="flex gap-2 mb-8">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Describe your engineering project..."
                className="pl-10"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? 'Searching...' : 'Search'}
            </Button>
          </form>

          {/* Search Status Indicator */}
          {hasSearched && (
            <div className="mb-4">
              {searchStatus === 'loading' && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <div className="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full" />
                  <span>Searching...</span>
                </div>
              )}
              {searchStatus === 'error' && (
                <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-md">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Search error: {searchError}</span>
                </div>
              )}
              {searchStatus === 'success' && resultCount > 0 && (
                <p className="text-sm text-muted-foreground">
                  Found {resultCount} providers (of {totalMatches} total matches)
                </p>
              )}
            </div>
          )}

          {/* Results */}
          {hasSearched && (
            <div className="space-y-4">
              {results.length === 0 ? (
                <div className="space-y-4">
                  <p className="text-center text-muted-foreground py-8">
                    No providers found matching your search.
                  </p>

                  {/* Debug Panel - shows automatically when no results */}
                  <DebugPanel
                    searchQuery={query}
                    searchStatus={searchStatus}
                    searchError={searchError}
                    resultCount={resultCount}
                    showOnEmpty={true}
                  />
                </div>
              ) : (
                <>
                  {results.map((provider) => (
                    <Link key={provider.provider.id} href={`/providers/${provider.provider.id}`}>
                      <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
                        <CardContent className="p-4">
                          <div className="flex justify-between items-start">
                            <div>
                              <h3 className="font-semibold text-lg">{provider.provider.name}</h3>
                              <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                                <span className="flex items-center gap-1">
                                  <MapPin className="h-3 w-3" />
                                  {provider.provider.city}, {provider.provider.state}
                                </span>
                                {provider.provider.tier && (
                                  <span className="flex items-center gap-1">
                                    <Star className="h-3 w-3" />
                                    Tier {provider.provider.tier}
                                  </span>
                                )}
                              </div>
                              {provider.provider.primary_specialty && (
                                <p className="text-sm mt-2">
                                  <span className="font-medium">Specialty:</span> {provider.provider.primary_specialty}
                                </p>
                              )}
                              {provider.provider.business_description && (
                                <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                                  {provider.provider.business_description}
                                </p>
                              )}
                              {provider.explanation && (
                                <p className="text-xs text-muted-foreground mt-2">
                                  <span className="font-medium">Match:</span> {provider.explanation}
                                </p>
                              )}
                            </div>
                            <Badge variant="outline">
                              {provider.provider.is_engineering_service ? 'Engineering' : 'Service'}
                            </Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </Link>
                  ))}

                  {/* Debug Panel - collapsible for successful searches too */}
                  <DebugPanel
                    searchQuery={query}
                    searchStatus={searchStatus}
                    searchError={searchError}
                    resultCount={resultCount}
                    showOnEmpty={false}
                  />
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}


export default function SearchPage() {
  return (
    <Suspense fallback={<div className="container py-8"><p className="text-center">Loading...</p></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
