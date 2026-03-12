'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { SearchResult, PipelineInfo } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Search, Building2, MapPin, Star, AlertTriangle, Home, LogOut, ArrowRight, CheckCircle2 } from 'lucide-react';
import { DebugPanel } from '@/components/search/DebugPanel';
import { AIPipelinePanel } from '@/components/search/AIPipelinePanel';

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, logout } = useAuth();
  const initialQuery = searchParams.get('q') || '';
  const rfqMode = searchParams.get('rfq') === '1';

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [isRequestingQuote, setIsRequestingQuote] = useState(false);

  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [searchError, setSearchError] = useState<string | null>(null);
  const [resultCount, setResultCount] = useState(0);
  const [totalMatches, setTotalMatches] = useState(0);
  const [pipelineInfo, setPipelineInfo] = useState<PipelineInfo | null>(null);

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
    setPipelineInfo(null);
    try {
      const response = await api.search.query({ query: searchQuery });
      const res = response.data.results || [];
      setResults(res);
      setResultCount(res.length);
      setTotalMatches(response.data.total_matches || 0);
      setPipelineInfo(response.data.pipeline_info || null);
      setSearchStatus('success');
    } catch (error: any) {
      setSearchStatus('error');
      setResults([]);
      setResultCount(0);
      setSearchError(error.response?.data?.detail || error.message || 'Search failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  const handleRequestQuote = async () => {
    setIsRequestingQuote(true);
    if (!user) {
      // Redirect to register/login, preserving query for post-auth return
      router.push(`/register?next=/customer/rfq/new&q=${encodeURIComponent(query)}`);
      return;
    }
    // Logged in — go directly to new RFQ form with query pre-filled
    router.push(`/customer/rfq/new?q=${encodeURIComponent(query)}`);
  };

  const handleLogout = async () => {
    await logout();
    router.push('/');
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center gap-2">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProReadyEngineer</span>
          </Link>
          <div className="ml-auto flex gap-2 items-center">
            <Link href="/">
              <Button variant="ghost" size="sm" className="flex items-center gap-1">
                <Home className="h-4 w-4" />
                Home
              </Button>
            </Link>
            {user ? (
              <Button variant="ghost" size="sm" onClick={handleLogout} className="flex items-center gap-1 text-red-600 hover:text-red-700 hover:bg-red-50">
                <LogOut className="h-4 w-4" />
                Sign Out
              </Button>
            ) : (
              <Link href="/login">
                <Button variant="ghost" size="sm">Sign In</Button>
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="container py-8">
        {/* Search bar */}
        <div className="max-w-3xl mx-auto mb-8">
          <h1 className="text-2xl font-bold mb-4">
            {rfqMode ? 'Find Providers for Your Project' : 'Search Engineering Providers'}
          </h1>
          <form onSubmit={handleSubmit} className="flex gap-2">
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
        </div>

        {/* Status */}
              {pipelineInfo && <AIPipelinePanel pipeline={pipelineInfo} query={query} />}
      {hasSearched && searchStatus === 'error' && (
          <div className="max-w-3xl mx-auto mb-4">
            <div className="flex items-center gap-2 text-red-600 bg-red-50 p-3 rounded-md">
              <AlertTriangle className="h-4 w-4" />
              <span>Search error: {searchError}</span>
            </div>
          </div>
        )}

        {/* Results + Request Quote side-by-side */}
        {hasSearched && results.length > 0 && (
          <div className="flex gap-6 items-start">
            {/* Left: results list */}
            <div className="flex-1 space-y-4">
              <p className="text-sm text-muted-foreground">
                Top {resultCount} providers matched (of {totalMatches} total)
              </p>
              {results.map((provider) => (
                <Link key={provider.provider.id} href={`/providers/${provider.provider.id}`}>
                  <Card className="hover:bg-muted/50 transition-colors cursor-pointer mb-4">
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="font-semibold text-lg">{provider.provider.name}</h3>
                          <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                            {provider.provider.city && (
                              <span className="flex items-center gap-1">
                                <MapPin className="h-3 w-3" />
                                {provider.provider.city}{provider.provider.state ? `, ${provider.provider.state}` : ''}
                              </span>
                            )}
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
                            <p className="text-xs text-blue-600 mt-2">
                              <span className="font-medium">Match:</span> {provider.explanation}
                            </p>
                          )}
                        </div>
                        <Badge variant="outline">Score: {Math.round(provider.score || 0)}</Badge>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
              <DebugPanel
                searchQuery={query}
                searchStatus={searchStatus}
                searchError={searchError}
                resultCount={resultCount}
                showOnEmpty={false}
              />
            </div>

            {/* Right: Request Quote panel */}
            <div className="w-80 flex-shrink-0 sticky top-20">
              <Card className="border-2 border-blue-200 bg-blue-50/50">
                <CardContent className="p-6">
                  <h3 className="font-bold text-lg mb-2 text-blue-900">Ready to Get Quotes?</h3>
                  <Button
                    size="lg"
                    className="w-full bg-blue-600 hover:bg-blue-700 text-white mb-4"
                    onClick={handleRequestQuote}
                    disabled={isRequestingQuote}
                  >
                    {isRequestingQuote ? 'Redirecting...' : 'Request Quote'}
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                  <div className="space-y-3 text-sm text-blue-800">
                    <p className="font-medium">Once you click, an automated workflow will start:</p>
                    <div className="space-y-2">
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-blue-600 flex-shrink-0" />
                        <span>Contacting all matched suppliers in ranked order</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-blue-600 flex-shrink-0" />
                        <span>Collecting up to 5 rough quotes on your behalf</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="h-4 w-4 mt-0.5 text-blue-600 flex-shrink-0" />
                        <span>Live tracking available in your Customer Portal</span>
                      </div>
                    </div>
                    <p className="text-xs text-blue-600 mt-3 italic">
                      Quotes are rough, non-binding estimates. A refined final estimate follows direct engagement.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {/* No results */}
        {hasSearched && results.length === 0 && searchStatus !== 'loading' && searchStatus !== 'error' && (
          <div className="max-w-3xl mx-auto space-y-4">
            <p className="text-center text-muted-foreground py-8">No providers found matching your search.</p>
            <DebugPanel
              searchQuery={query}
              searchStatus={searchStatus}
              searchError={searchError}
              resultCount={resultCount}
              showOnEmpty={true}
            />
          </div>
        )}
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
