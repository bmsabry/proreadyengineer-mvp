'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Provider } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Search, Building2, MapPin, Star } from 'lucide-react';

export default function SearchPage() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get('q') || '';
  
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<Provider[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    if (initialQuery) {
      handleSearch(initialQuery);
    }
  }, [initialQuery]);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    
    setIsLoading(true);
    setHasSearched(true);
    
    try {
      const response = await api.search.query({ query: searchQuery });
      setResults(response.data.results || []);
    } catch (error) {
      console.error('Search failed:', error);
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

          {hasSearched && (
            <div className="space-y-4">
              {results.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No providers found matching your search.
                </p>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    Found {results.length} providers
                  </p>
                  {results.map((provider) => (
                    <Link key={provider.id} href={`/providers/${provider.id}`}>
                      <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
                        <CardContent className="p-4">
                          <div className="flex justify-between items-start">
                            <div>
                              <h3 className="font-semibold text-lg">{provider.name}</h3>
                              <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                                <span className="flex items-center gap-1">
                                  <MapPin className="h-3 w-3" />
                                  {provider.city}, {provider.state}
                                </span>
                                {provider.tier && (
                                  <span className="flex items-center gap-1">
                                    <Star className="h-3 w-3" />
                                    Tier {provider.tier}
                                  </span>
                                )}
                              </div>
                              {provider.primary_specialty && (
                                <p className="text-sm mt-2">
                                  <span className="font-medium">Specialty:</span> {provider.primary_specialty}
                                </p>
                              )}
                              {provider.business_description && (
                                <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                                  {provider.business_description}
                                </p>
                              )}
                            </div>
                            <Badge variant="outline">
                              {provider.is_engineering_service ? 'Engineering' : 'Service'}
                            </Badge>
                          </div>
                        </CardContent>
                      </Card>
                    </Link>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
