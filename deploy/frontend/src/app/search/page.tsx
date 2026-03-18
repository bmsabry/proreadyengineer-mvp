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
  Loader2,
} from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// Adaptive progress loader helpers
// ─────────────────────────────────────────────────────────────────────────────
const LS_KEY = 'pme_avg_search_ms';
const DEFAULT_DURATION_MS = 52000;

function getEstimatedDuration(): number {
  try {
    const stored = localStorage.getItem(LS_KEY);
    if (stored) {
      const val = parseInt(stored, 10);
      if (val > 5000 && val < 180000) return val;
    }
  } catch {}
  return DEFAULT_DURATION_MS;
}

function saveSearchDuration(ms: number): void {
  try {
    const prev = getEstimatedDuration();
    const updated = Math.round(prev * 0.7 + ms * 0.3);
    localStorage.setItem(LS_KEY, String(updated));
  } catch {}
}

const SEARCH_PHASES = [
  { icon: "🔍", text: 'Analyzing your engineering query...' },
  { icon: "🧠", text: 'Extracting technical intent with AI...' },
  { icon: "⚡", text: 'Generating semantic embeddings...' },
  { icon: "🗄️", text: 'Scanning 6,000+ provider profiles...' },
  { icon: "📐", text: 'Applying specialty & capability filters...' },
  { icon: "🏆", text: 'Scoring top candidates...' },
  { icon: "✨", text: 'Ranking providers by project fit...' },
  { icon: "📋", text: 'Preparing your match results...' },
];

const SEARCH_FACTS = [
  'Our directory includes 6,000+ engineering service firms across North America.',
  'Providers are scored on specialty match, capabilities, and project history.',
  'Vector similarity compares your query against thousands of provider profiles.',
  'Tier ratings reflect provider track record and project complexity.',
  'AI extracts your technical requirements to find precise capability matches.',
  'Case studies and notable projects boost provider relevance scores.',
  'The top 100 candidates undergo detailed LLM-based evaluation.',
  'Results are ranked by composite score: specialty + capabilities + tier.',
];

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
// Main search page content
function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, logout } = useAuth();
  const initialQuery = searchParams.get('q') || '';
  const rfqMode = searchParams.get('rfq') === '1';
  const uploadedDoc = searchParams.get('uploaded') === '1';
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
  const [showResults, setShowResults] = useState(false);
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadPhase, setLoadPhase] = useState(0);
  const [loadFact, setLoadFact] = useState(0);
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const phaseTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const factTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const searchStartTimeRef = useRef<number>(0);
  useEffect(() => {
    return () => {
      if (progressTimerRef.current) clearInterval(progressTimerRef.current);
      if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
      if (factTimerRef.current) clearInterval(factTimerRef.current);
    };
  }, []);
  useEffect(() => {
    if (initialQuery) handleSearch(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);
  const startLoadingAnimation = () => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
    if (factTimerRef.current) clearInterval(factTimerRef.current);
    setLoadProgress(0);
    setLoadPhase(0);
    setLoadFact(0);
    setShowResults(false);
    searchStartTimeRef.current = Date.now();
    const estimatedMs = getEstimatedDuration();
    const targetProgress = 90;
    const updateIntervalMs = 200;
    const incrementPerUpdate = (targetProgress / estimatedMs) * updateIntervalMs;
    progressTimerRef.current = setInterval(() => {
      setLoadProgress(prev => {
        if (prev >= targetProgress) {
          if (progressTimerRef.current) clearInterval(progressTimerRef.current);
          return targetProgress;
        }
        return Math.min(prev + incrementPerUpdate, targetProgress);
      });
    }, updateIntervalMs);
    phaseTimerRef.current = setInterval(() => {
      setLoadPhase(prev => (prev + 1) % SEARCH_PHASES.length);
    }, 7000);
    factTimerRef.current = setInterval(() => {
      setLoadFact(prev => (prev + 1) % SEARCH_FACTS.length);
    }, 13000);
  };
  const stopLoadingAnimation = (success: boolean) => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
    if (factTimerRef.current) clearInterval(factTimerRef.current);
    if (success) {
      const elapsed = Date.now() - searchStartTimeRef.current;
      if (elapsed > 3000) saveSearchDuration(elapsed);
    }
    setLoadProgress(100);
  };
  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    setIsLoading(true);
    setHasSearched(true);
    setSearchStatus('loading');
    setSearchError(null);
    setPipelineInfo(null);
    setShowResults(false);
    startLoadingAnimation();
    try {
      const response = await api.search.query({ query: searchQuery });
      const res = response.data.results || [];
      setResults(res);
      setResultCount(res.length);
      setTotalMatches(response.data.total_matches || 0);
      setPipelineInfo(response.data.pipeline_info || null);
      setSearchStatus('success');
      stopLoadingAnimation(true);
      setTimeout(() => setShowResults(true), 400);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Search failed. Please try again.';
      setSearchError(msg);
      stopLoadingAnimation(false);
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
            <span className="font-semibold text-sm hidden sm:block">ProMechDirectory</span>
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
        {uploadedDoc && (
          <div className="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-indigo-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-indigo-900">Document uploaded!</p>
              <p className="text-xs text-indigo-700 mt-0.5">
                Describe your project in the search bar above for best results.
              </p>
            </div>
          </div>
        )}
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
          <div className="max-w-2xl mx-auto py-10 px-4">
            {/* Header */}
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg mb-4">
                <Search className="h-7 w-7 text-white animate-pulse" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">AI-Powered Matching</h2>
              <p className="text-sm text-muted-foreground mt-1">Analyzing 6,000+ engineering firms for your project</p>
            </div>

            {/* Current phase message */}
            <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50/80 px-5 py-4 mb-6 min-h-[64px]">
              <span className="text-2xl">{SEARCH_PHASES[loadPhase].icon}</span>
              <div>
                <p className="text-sm font-semibold text-blue-900">{SEARCH_PHASES[loadPhase].text}</p>
                <p className="text-xs text-blue-600 mt-0.5">Pipeline running — this takes about {Math.round(getEstimatedDuration() / 1000)}s</p>
              </div>
              <Loader2 className="h-4 w-4 animate-spin text-blue-500 ml-auto shrink-0" />
            </div>

            {/* Progress bar */}
            <div className="mb-6">
              <div className="flex justify-between text-xs text-muted-foreground mb-2">
                <span>Matching progress</span>
                <span>{Math.round(loadProgress)}%</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-200 ease-linear"
                  style={{ width: `${loadProgress}%` }}
                />
              </div>
            </div>

            {/* Rotating fact */}
            <div className="rounded-xl border border-border bg-muted/40 px-5 py-4">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Did you know?</p>
              <p className="text-sm text-foreground">{SEARCH_FACTS[loadFact]}</p>
            </div>
          </div>
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
                    {pipelineInfo?.fallback_reason && !pipelineInfo.fallback_reason.includes('_failed') && !pipelineInfo.fallback_reason.includes('Error') && (
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
                  <div className="flex gap-6 items-start">
                    <div className="flex-1 space-y-3">
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
                              {r.explanation && (
                                <div className="mt-2 flex items-start gap-1.5">
                                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 mt-0.5 shrink-0" />
                                  <p className="text-xs text-green-700 font-medium leading-relaxed">{r.explanation}</p>
                                </div>
                              )}
                            </div>
                            <div className="shrink-0 text-right flex flex-col items-end gap-2 ml-4">
                              <div>
                                <div className="text-2xl font-bold text-foreground leading-none">{r.score != null ? Math.round(r.score) : "—"}</div>
                                <div className="text-xs text-muted-foreground text-right">/ 100</div>
                                {r.score != null && (
                                  <div className="w-16 h-1.5 bg-muted rounded-full mt-1 overflow-hidden">
                                    <div
                                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-500"
                                      style={{ width: `${Math.min(100, Math.round(r.score))}%` }}
                                    />
                                  </div>
                                )}
                              </div>

                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                    </div>
                    <div className="w-72 shrink-0">
                      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-5 sticky top-6">
                        <div className="flex items-center gap-2 mb-3">
                          <div className="h-8 w-8 rounded-full bg-blue-600 flex items-center justify-center shrink-0">
                            <ArrowRight className="h-4 w-4 text-white" />
                          </div>
                          <h3 className="font-semibold text-sm text-gray-900">Ready to get quotes?</h3>
                        </div>
                        <Button
                          className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold mb-4"
                          onClick={handleStartRfq}
                          disabled={isRequestingQuote}
                        >
                          {isRequestingQuote
                            ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />Submitting...</>
                            : <>Submit RFQ &amp; Get Quotes</>}
                        </Button>
                        <ul className="space-y-2.5">
                          <li className="flex items-start gap-2 text-xs text-gray-600">
                            <CheckCircle2 className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
                            <span>Contacts <strong>all matched providers</strong> in your database &mdash; not just the 5 shown &mdash; in sequential batches</span>
                          </li>
                          <li className="flex items-start gap-2 text-xs text-gray-600">
                            <CheckCircle2 className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
                            <span>Track dispatch progress <strong>live</strong> from your dashboard as each firm is contacted</span>
                          </li>
                          <li className="flex items-start gap-2 text-xs text-gray-600">
                            <CheckCircle2 className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
                            <span>Process <strong>stops automatically</strong> once 5 quotes are received &mdash; no spam, no excess</span>
                          </li>
                          <li className="flex items-start gap-2 text-xs text-gray-600">
                            <CheckCircle2 className="h-3.5 w-3.5 text-blue-500 mt-0.5 shrink-0" />
                            <span>You will be <strong>notified each time</strong> a provider signs an NDA (if required) before accessing your files</span>
                          </li>
                        </ul>
                        <p className="text-xs text-gray-400 mt-4 pt-3 border-t border-blue-100">
                          Quotes are non-binding rough estimates. Final pricing follows direct engagement.
                        </p>
                      </div>
                    </div>
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
