'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { SearchResult, PipelineInfo } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Search,
  Building2,
  MapPin,
  Star,
  AlertTriangle,
  Home,
  LogOut,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Layers,
  Sparkles,
  Trophy,
  Loader2,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline loading steps definition
// ─────────────────────────────────────────────────────────────────────────────
const PIPELINE_STEPS = [
  {
    id: 'analyze' as const,
    icon: Search,
    label: 'Analyzing your query',
    sublabel: 'Extracting engineering intent & requirements',
    durationMs: 900,
  },
  {
    id: 'embed' as const,
    icon: Cpu,
    label: 'Generating semantic embeddings',
    sublabel: 'Converting query to high-dimensional vector space',
    durationMs: 1100,
  },
  {
    id: 'match' as const,
    icon: Layers,
    label: 'Scanning 6,000+ providers',
    sublabel: 'Applying pgvector cosine similarity across directory',
    durationMs: 1000,
  },
  {
    id: 'score' as const,
    icon: Trophy,
    label: 'Scoring & ranking candidates',
    sublabel: 'Specialty · Capabilities · Tier composite scoring',
    durationMs: 800,
  },
  {
    id: 'finalize' as const,
    icon: Sparkles,
    label: 'Preparing your results',
    sublabel: 'Generating match explanations',
    durationMs: 600,
  },
];

type StepId = 'analyze' | 'embed' | 'match' | 'score' | 'finalize';

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton card component
// ─────────────────────────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="rounded-lg border bg-card p-4 animate-pulse">
      <div className="flex justify-between items-start">
        <div className="flex-1 space-y-2">
          <div className="h-5 bg-muted rounded w-2/5" />
          <div className="flex gap-3">
            <div className="h-4 bg-muted rounded w-24" />
            <div className="h-4 bg-muted rounded w-16" />
          </div>
          <div className="h-4 bg-muted rounded w-3/5 mt-1" />
          <div className="h-4 bg-muted rounded w-full" />
          <div className="h-4 bg-muted rounded w-4/5" />
        </div>
        <div className="ml-4 h-6 w-20 bg-muted rounded-full" />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline loader panel
// ─────────────────────────────────────────────────────────────────────────────
interface PipelineLoaderProps {
  activeStepIndex: number;
  completedSteps: Set<StepId>;
}

function PipelineLoader({ activeStepIndex, completedSteps }: PipelineLoaderProps) {
  return (
    <div className="max-w-2xl mx-auto py-10 px-4">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg mb-4">
          <Sparkles className="h-7 w-7 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-foreground">AI-Powered Matching</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Our pipeline is finding your best-fit engineering partners
        </p>
      </div>

      {/* Steps */}
      <div className="space-y-3">
        {PIPELINE_STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isDone = completedSteps.has(step.id as StepId);
          const isActive = idx === activeStepIndex && !isDone;

          return (
            <div
              key={step.id}
              className={[
                'flex items-start gap-4 rounded-xl border p-4 transition-all duration-500',
                isDone
                  ? 'border-green-200 bg-green-50/60 opacity-90'
                  : isActive
                  ? 'border-blue-300 bg-blue-50/80 shadow-sm scale-[1.01]'
                  : 'border-border bg-muted/30 opacity-40',
              ].join(' ')}
            >
              {/* Icon bubble */}
              <div
                className={[
                  'flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-xl transition-colors duration-300',
                  isDone
                    ? 'bg-green-100 text-green-600'
                    : isActive
                    ? 'bg-blue-100 text-blue-600'
                    : 'bg-muted text-muted-foreground',
                ].join(' ')}
              >
                {isDone ? (
                  <CheckCircle2 className="h-5 w-5" />
                ) : isActive ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Icon className="h-5 w-5" />
                )}
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p
                  className={[
                    'text-sm font-semibold leading-tight',
                    isDone
                      ? 'text-green-800'
                      : isActive
                      ? 'text-blue-900'
                      : 'text-muted-foreground',
                  ].join(' ')}
                >
                  {step.label}
                </p>
                <p
                  className={[
                    'text-xs mt-0.5',
                    isDone
                      ? 'text-green-600'
                      : isActive
                      ? 'text-blue-600'
                      : 'text-muted-foreground/60',
                  ].join(' ')}
                >
                  {step.sublabel}
                </p>
              </div>

              {/* Status chip */}
              <div className="flex-shrink-0 self-center">
                {isDone ? (
                  <span className="text-xs font-medium text-green-600 bg-green-100 px-2 py-0.5 rounded-full">
                    Done
                  </span>
                ) : isActive ? (
                  <span className="text-xs font-medium text-blue-600 bg-blue-100 px-2 py-0.5 rounded-full animate-pulse">
                    Running
                  </span>
                ) : (
                  <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    Queued
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="mt-8">
        <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
          <span>Progress</span>
          <span>{Math.round((completedSteps.size / PIPELINE_STEPS.length) * 100)}%</span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${(completedSteps.size / PIPELINE_STEPS.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}

// Main search page content
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
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<StepId>>(new Set());
  const [showResults, setShowResults] = useState(false);
  const stepTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => {
    return () => { stepTimersRef.current.forEach(clearTimeout); };
  }, []);
  useEffect(() => {
    if (initialQuery) handleSearch(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);
  const startPipelineAnimation = () => {
    stepTimersRef.current.forEach(clearTimeout);
    stepTimersRef.current = [];
    setActiveStepIndex(0);
    setCompletedSteps(new Set());
    setShowResults(false);
    let elapsed = 0;
    PIPELINE_STEPS.forEach((step, idx) => {
      const tActive = setTimeout(() => setActiveStepIndex(idx), elapsed);
      stepTimersRef.current.push(tActive);
      elapsed += step.durationMs;
      const tDone = setTimeout(() => {
        setCompletedSteps((prev) => {
          const next = new Set(prev);
          next.add(step.id as StepId);
          return next;
        });
      }, elapsed);
      stepTimersRef.current.push(tDone);
    });
  };
  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setIsLoading(true);
    setHasSearched(true);
    setSearchStatus('loading');
    setSearchError(null);
    setPipelineInfo(null);
    setShowResults(false);
    startPipelineAnimation();
    try {
      const response = await api.search.query({ query: searchQuery });
      const res = response.data.results || [];
      setResults(res);
      setResultCount(res.length);
      setTotalMatches(response.data.total_matches || 0);
      setPipelineInfo(response.data.pipeline_info || null);
      setSearchStatus('success');
      setTimeout(() => setShowResults(true), 400);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Search failed. Please try again.';
      setSearchError(msg);
      setSearchStatus('error');
      setShowResults(true);
    } finally {
      setIsLoading(false);
    }
  };
  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    const qs = rfqMode ? '&rfq=1' : '';
    router.push(`/search?q=${encodeURIComponent(query)}${qs}`);
  };
  const handleStartRfq = () => {
    setIsRequestingQuote(true);
    router.push(`/rfq/new?q=${encodeURIComponent(query)}`);
  };
  const getTierBadgeClass = (tier: string) => {
    switch ((tier || '').toUpperCase()) {
      case 'A': return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'B': return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'C': return 'bg-green-100 text-green-800 border-green-200';
      case 'D': return 'bg-orange-100 text-orange-800 border-orange-200';
      default:  return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 text-foreground hover:opacity-80 transition-opacity shrink-0">
            <Home className="h-4 w-4" />
            <span className="font-semibold text-sm hidden sm:block">ProReadyEngineer</span>
          </Link>
          <form onSubmit={handleFormSubmit} className="flex-1 max-w-xl flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                className="pl-9 h-9 text-sm"
                placeholder="Refine your search…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <Button type="submit" size="sm" className="h-9" disabled={isLoading || !query.trim()}>
              {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          </form>
          <div className="flex items-center gap-2 shrink-0">
            {user ? (
              <>
                <span className="text-xs text-muted-foreground hidden md:block truncate max-w-[140px]">{user.email}</span>
                <Button variant="ghost" size="sm" onClick={logout} className="gap-1.5 h-8 text-xs">
                  <LogOut className="h-3 w-3" />
                  Sign out
                </Button>
              </>
            ) : (
              <Link href="/auth/login">
                <Button variant="outline" size="sm" className="h-8 text-xs">Sign in</Button>
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        {rfqMode && (
          <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-blue-900">RFQ Mode Active</p>
              <p className="text-xs text-blue-700 mt-0.5">
                Review your matched providers below, then submit a Request for Quote to up to 5 firms simultaneously.
              </p>
            </div>
          </div>
        )}
        {isLoading && (
          <PipelineLoader activeStepIndex={activeStepIndex} completedSteps={completedSteps} />
        )}
        {isLoading && (
          <div className="space-y-3 mt-6">
            {[1, 2, 3, 4, 5].map((n) => <SkeletonCard key={n} />)}
          </div>
        )}
        {!isLoading && showResults && (
          <div>
            {searchStatus === "error" && searchError && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-4 flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-destructive">Search failed</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{searchError}</p>
                </div>
              </div>
            )}
            {searchStatus === "success" && (
              <>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {resultCount === 0
                        ? "No matches found"
                        : `Top ${resultCount} match${resultCount !== 1 ? "es" : ""}`}
                      {totalMatches > 0 && resultCount > 0 && (
                        <span className="text-muted-foreground font-normal">
                          {" "}from {totalMatches.toLocaleString()} providers screened
                        </span>
                      )}
                    </p>
                    {pipelineInfo?.fallback_reason && (
                      <p className="text-xs text-amber-600 mt-0.5 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {pipelineInfo.fallback_reason}
                      </p>
                    )}
                  </div>
                  {rfqMode && resultCount > 0 && (
                    <Button onClick={handleStartRfq} disabled={isRequestingQuote} className="gap-1.5">
                      {isRequestingQuote
                        ? <Loader2 className="h-4 w-4 animate-spin" />
                        : <ArrowRight className="h-4 w-4" />}
                      Submit RFQ
                    </Button>
                  )}
                </div>
                {resultCount === 0 && (
                  <div className="text-center py-16">
                    <Building2 className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
                    <p className="text-base font-medium text-foreground mb-1">No matching providers found</p>
                    <p className="text-sm text-muted-foreground max-w-md mx-auto">
                      Try broadening your search terms or describing your project differently.
                    </p>
                  </div>
                )}
                {resultCount > 0 && (
                  <div className="space-y-3">
                    {results.map((r, idx) => (
                      <Card key={r.provider.id} className="hover:shadow-md transition-shadow">
                        <CardContent className="p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-xs font-bold text-muted-foreground/60 w-5 text-center">#{idx + 1}</span>
                                <h3 className="font-semibold text-sm text-foreground truncate">{r.provider.name}</h3>
                                {r.provider.tier && (
                                  <Badge variant="outline" className={`text-xs ${getTierBadgeClass(r.provider.tier)}`}>
                                    Tier {r.provider.tier}
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                                {(r.provider.city || r.provider.state) && (
                                  <span className="flex items-center gap-1">
                                    <MapPin className="h-3 w-3" />
                                    {[r.provider.city, r.provider.state].filter(Boolean).join(', ')}
                                  </span>
                                )}
                                {r.provider.primary_specialty && (
                                  <span className="flex items-center gap-1">
                                    <Star className="h-3 w-3" />
                                    {r.provider.primary_specialty}
                                  </span>
                                )}
                              </div>
                              {r.provider.business_description && (
                                <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{r.provider.business_description}</p>
                              )}
                            </div>
                            <div className="shrink-0 text-right">
                              <div className="text-lg font-bold text-foreground">{r.composite_score}</div>
                              <div className="text-xs text-muted-foreground">/ 100</div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {!isLoading && !hasSearched && (
          <div className="text-center py-20">
            <Search className="h-16 w-16 text-muted-foreground/20 mx-auto mb-6" />
            <h2 className="text-xl font-semibold text-foreground mb-2">Find Engineering Service Providers</h2>
            <p className="text-sm text-muted-foreground max-w-md mx-auto">
              Describe your engineering project above and our AI will match you with the best-fit providers from our directory of 6,000+ firms.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    }>
      <SearchPageContent />
    </Suspense>
  );
}
