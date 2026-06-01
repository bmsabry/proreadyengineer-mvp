"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { SearchResult, PipelineInfo } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Search, Building2, MapPin, Star, AlertTriangle, Home,
  LogOut, ArrowRight, CheckCircle2, Loader2,
} from "lucide-react";

const LS_KEY = "pme_avg_search_ms";
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
  { icon: "🔍", text: "Analyzing your engineering query..." },
  { icon: "🧠", text: "Extracting technical intent with AI..." },
  { icon: "⚡", text: "Generating semantic embeddings..." },
  { icon: "🗄️", text: "Scanning 6,000+ provider profiles..." },
  { icon: "📐", text: "Applying specialty & capability filters..." },
  { icon: "🏆", text: "Scoring top candidates..." },
  { icon: "✨", text: "Ranking providers by project fit..." },
  { icon: "📋", text: "Preparing your match results..." },
];

const SEARCH_FACTS = [
  "Our directory includes 6,000+ engineering service firms across North America.",
  "Providers are scored on specialty match, capabilities, and project history.",
  "Vector similarity compares your query against thousands of provider profiles.",
  "Tier ratings reflect provider track record and project complexity.",
  "AI extracts your technical requirements to find precise capability matches.",
  "Case studies and notable projects boost provider relevance scores.",
  "The top 100 candidates undergo detailed LLM-based evaluation.",
  "Results are ranked by composite score: specialty + capabilities + tier.",
];

function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 animate-pulse">
      <div className="flex justify-between items-start gap-4">
        <div className="flex-1 space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-slate-200" />
            <div className="h-5 bg-slate-200 rounded w-2/5" />
            <div className="h-5 bg-slate-200 rounded-full w-16" />
          </div>
          <div className="flex gap-3"><div className="h-3.5 bg-slate-100 rounded w-24" /><div className="h-3.5 bg-slate-100 rounded w-20" /></div>
          <div className="h-4 bg-slate-100 rounded w-full" /><div className="h-4 bg-slate-100 rounded w-4/5" />
          <div className="h-10 bg-emerald-50 rounded-xl w-full" />
        </div>
        <div className="shrink-0 text-right">
          <div className="h-8 w-12 bg-slate-200 rounded mb-1" />
          <div className="h-3 w-8 bg-slate-100 rounded mx-auto" />
          <div className="h-1.5 w-16 bg-slate-100 rounded-full mt-2" />
        </div>
      </div>
    </div>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user, logout, isLoading: authLoading, isAuthenticated } = useAuth();

  // Account required: no one may search without signing in.
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      const q = searchParams.get('q') || '';
      const next = '/search' + (q ? ('?q=' + encodeURIComponent(q)) : '');
      router.replace('/login?next=' + encodeURIComponent(next));
    }
  }, [authLoading, isAuthenticated, router, searchParams]);

  // Block providers from using customer project search
  useEffect(() => {
    if (user) {
      const roles = user.roles || [];
      const isCustomerOrAdmin = roles.includes('customer') || roles.includes('admin');
      const isProvider = roles.includes('provider');
      if (isProvider && !isCustomerOrAdmin) {
        router.replace('/provider/dashboard');
      }
    }
  }, [user, router]);
  const initialQuery = searchParams.get("q") || "";
  const rfqMode = searchParams.get("rfq") === "1";
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [isRequestingQuote, setIsRequestingQuote] = useState(false);
  const [searchStatus, setSearchStatus] = useState<"idle"|"loading"|"success"|"error">("idle");
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
    setLoadProgress(0); setLoadPhase(0); setLoadFact(0); setShowResults(false);
    searchStartTimeRef.current = Date.now();
    const estimatedMs = getEstimatedDuration();
    const targetProgress = 90; const updateIntervalMs = 200;
    const incrementPerUpdate = (targetProgress / estimatedMs) * updateIntervalMs;
    progressTimerRef.current = setInterval(() => {
      setLoadProgress(prev => {
        if (prev >= targetProgress) { if (progressTimerRef.current) clearInterval(progressTimerRef.current); return targetProgress; }
        return Math.min(prev + incrementPerUpdate, targetProgress);
      });
    }, updateIntervalMs);
    phaseTimerRef.current = setInterval(() => { setLoadPhase(p => (p+1)%SEARCH_PHASES.length); }, 7000);
    factTimerRef.current = setInterval(() => { setLoadFact(p => (p+1)%SEARCH_FACTS.length); }, 13000);
  };
  const stopLoadingAnimation = (success: boolean) => {
    if (progressTimerRef.current) clearInterval(progressTimerRef.current);
    if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
    if (factTimerRef.current) clearInterval(factTimerRef.current);
    if (success) { const e = Date.now()-searchStartTimeRef.current; if (e>3000) saveSearchDuration(e); }
    setLoadProgress(100);
  };
  useEffect(() => {
    const docQuery = sessionStorage.getItem("docSearchQuery");
    if (docQuery) { sessionStorage.removeItem("docSearchQuery"); setQuery(docQuery); handleSearch(docQuery); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    if (!isAuthenticated) { router.replace('/login?next=' + encodeURIComponent('/search')); return; }
    setIsLoading(true); setHasSearched(true); setSearchStatus("loading");
    setSearchError(null); setPipelineInfo(null); setShowResults(false);
    startLoadingAnimation();
    try {
      const response = await api.search.query({ query: searchQuery });
      const res = response.data.results || [];
      setResults(res); setResultCount(res.length);
      setTotalMatches(response.data.total_matches || 0);
      setPipelineInfo(response.data.pipeline_info || null);
      setSearchStatus("success"); stopLoadingAnimation(true);
      setTimeout(() => setShowResults(true), 400);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Search failed. Please try again.";
      setSearchError(msg); stopLoadingAnimation(false);
      setSearchStatus("error"); setShowResults(true);
    } finally { setIsLoading(false); }
  };
  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault(); if (!query.trim()) return;
    const qs = rfqMode ? "&rfq=1" : "";
    router.push(`/search?q=${encodeURIComponent(query)}${qs}`);
  };
  const handleStartRfq = () => { setIsRequestingQuote(true); router.push(`/customer/rfq/new?q=${encodeURIComponent(query)}`); };
  const getTierBadgeClass = (tier: string) => {
    switch ((tier||"").toUpperCase()) {
      case "A": return "bg-amber-100 text-amber-800 border-amber-200";
      case "B": return "bg-blue-100 text-blue-800 border-blue-200";
      case "C": return "bg-green-100 text-green-800 border-green-200";
      case "D": return "bg-orange-100 text-orange-800 border-orange-200";
      default: return "bg-slate-100 text-slate-600 border-slate-200";
    }
  };
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 bg-white/95 backdrop-blur border-b border-slate-200 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2 shrink-0">
            <div className="w-8 h-8 rounded-lg bg-[#0F2B54] flex items-center justify-center">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-sm text-slate-900 hidden sm:block tracking-tight">ProMechDirectory</span>
          </Link>
          <form onSubmit={handleFormSubmit} className="flex-1 max-w-xl flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <Input className="pl-9 h-10 border-slate-200 rounded-xl text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
                placeholder="Refine your search…" value={query} onChange={(e) => setQuery(e.target.value)} disabled={isLoading} />
            </div>
            <Button type="submit" disabled={isLoading || !query.trim()}
              className="h-10 px-4 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl text-sm font-medium">
              {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><Search className="h-3.5 w-3.5 mr-1.5" />Search</>}
            </Button>
          </form>
          <div className="flex items-center gap-2 shrink-0">
            {user ? (
              <><span className="text-xs text-slate-500 hidden md:block truncate max-w-[140px]">{user.email}</span>
              <Button variant="ghost" size="sm" onClick={logout} className="gap-1.5 h-8 text-xs text-slate-600 hover:text-slate-900">
                <LogOut className="h-3 w-3" />Sign out
              </Button></>
            ) : (
              <Link href="/login"><Button variant="outline" size="sm" className="h-8 text-xs border-slate-200">Sign in</Button></Link>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-8">
        {rfqMode && (
          <div className="mb-6 bg-blue-50 border border-blue-200 rounded-2xl px-5 py-4 flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-blue-600 mt-0.5 shrink-0" />
            <div><p className="text-sm font-semibold text-blue-900">RFQ Mode Active</p>
            <p className="text-xs text-blue-700 mt-0.5">Review your matched providers below, then submit a Request for Quote to up to 5 firms simultaneously.</p></div>
          </div>
        )}
        {isLoading && (
          <div className="max-w-2xl mx-auto py-10">
            <div className="text-center mb-8">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#0F2B54] shadow-lg mb-4">
                <Search className="h-8 w-8 text-white animate-pulse" />
              </div>
              <h2 className="text-2xl font-bold text-slate-900">AI-Powered Matching in Progress</h2>
              <p className="text-sm text-slate-500 mt-1">Analyzing 6,000+ engineering firms for your project</p>
            </div>
            <div className="flex items-center gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-5 py-4 mb-6">
              <span className="text-2xl">{SEARCH_PHASES[loadPhase].icon}</span>
              <div className="flex-1">
                <p className="text-sm font-bold text-blue-900">{SEARCH_PHASES[loadPhase].text}</p>
                <p className="text-xs text-blue-600 mt-0.5">Pipeline running — approx. {Math.round(getEstimatedDuration()/1000)}s total</p>
              </div>
              <Loader2 className="h-5 w-5 animate-spin text-blue-500 shrink-0" />
            </div>
            <div className="mb-6">
              <div className="flex justify-between text-xs text-slate-500 mb-2">
                <span>Matching progress</span><span>{Math.round(loadProgress)}%</span>
              </div>
              <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-600 transition-all duration-300" style={{ width: `${loadProgress}%` }} />
              </div>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-5 py-4 mb-8">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Did you know?</p>
              <p className="text-sm text-slate-700">{SEARCH_FACTS[loadFact]}</p>
            </div>
            <div className="space-y-3">{[0,1,2,3,4].map(i => <SkeletonCard key={i} />)}</div>
          </div>
        )}
        {!isLoading && showResults && searchStatus === "error" && (
          <div className="max-w-2xl mx-auto">
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 flex items-start gap-4">
              <AlertTriangle className="h-5 w-5 text-rose-500 mt-0.5 shrink-0" />
              <div><p className="text-sm font-semibold text-rose-900">Search failed</p>
              <p className="text-xs text-rose-700 mt-1">{searchError}</p></div>
            </div>
          </div>
        )}
        {!isLoading && showResults && searchStatus === "success" && (
          <div className="flex gap-6 items-start">
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="font-semibold text-slate-900 text-sm">
                    Showing top {resultCount} provider{resultCount !== 1 ? "s" : ""}
                  </p>
                  {pipelineInfo?.fallback_reason && (
                    <p className="text-xs text-amber-600 mt-0.5">{pipelineInfo.fallback_reason}</p>
                  )}
                </div>
              </div>
              {results.length === 0 ? (
                <div className="text-center py-20">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-slate-100 mb-4">
                    <Building2 className="h-8 w-8 text-slate-400" />
                  </div>
                  <h3 className="text-base font-semibold text-slate-700 mb-1">No matches found</h3>
                  <p className="text-sm text-slate-500">Try broadening your search terms or describing the engineering discipline differently.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {results.map((r, idx) => (
                    <div key={r.provider.id || idx}
                      className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5 hover:shadow-md hover:-translate-y-0.5 transition-all duration-150">
                      <div className="flex justify-between items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className="w-7 h-7 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center shrink-0">{idx+1}</span>
                            <span className="text-base font-bold text-slate-900 truncate">{r.provider.name}</span>
                            {r.provider.tier && (
                              <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold border ${getTierBadgeClass(r.provider.tier)}`}>Tier {r.provider.tier}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 flex-wrap mb-2">
                            {(r.provider.city || r.provider.state) && (
                              <span className="flex items-center gap-1 text-xs text-slate-500"><MapPin className="h-3 w-3" />{[r.provider.city, r.provider.state].filter(Boolean).join(", ")}</span>
                            )}
                            {r.provider.primary_specialty && (
                              <span className="flex items-center gap-1 text-xs text-slate-500"><Star className="h-3 w-3" />{r.provider.primary_specialty}</span>
                            )}
                          </div>
                          {r.provider.business_description && (
                            <p className="text-sm text-slate-600 line-clamp-2 mt-1">{r.provider.business_description}</p>
                          )}
                          {r.explanation && (
                            <div className="flex items-start gap-2 bg-emerald-50 border border-emerald-100 rounded-xl px-3 py-2 mt-2">
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                              <p className="text-xs text-emerald-800">{r.explanation}</p>
                            </div>
                          )}
                        </div>
                        <div className="shrink-0 text-right">
                          {typeof r.composite_score === "number" && (
                            <div>
                              <span className="text-3xl font-black text-[#0F2B54] leading-none">{Math.round(r.composite_score)}</span>
                              <span className="text-sm text-slate-400">/100</span>
                              <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden mt-1 ml-auto">
                                <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-600" style={{ width: `${Math.min(100,Math.round(r.composite_score))}%` }} />
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="w-72 shrink-0">
              <div className="bg-gradient-to-br from-[#0F2B54] to-[#1a3a6b] text-white rounded-2xl p-6 sticky top-24">
                <h3 className="font-bold text-white text-base mb-1">Ready to get quotes?</h3>
                <p className="text-blue-200 text-xs mb-4">Submit one RFQ and we’ll contact all matched providers in sequential batches. Only the top 5 are shown to you.</p>
                <Button onClick={handleStartRfq} disabled={isRequestingQuote}
                  className="w-full bg-white text-[#0F2B54] hover:bg-blue-50 rounded-xl font-semibold text-sm h-10 mb-5">
                  {isRequestingQuote ? <Loader2 className="h-4 w-4 animate-spin" /> : <><ArrowRight className="h-4 w-4 mr-1.5" />Submit RFQ</>}
                </Button>
                <ul className="space-y-2 mb-5">
                  {["Top 5 providers are shown","Non-binding rough quotes","NDA option available","No obligation to proceed"].map(item => (
                    <li key={item} className="flex items-center gap-2 text-xs text-blue-100">
                      <CheckCircle2 className="h-3.5 w-3.5 text-blue-300 shrink-0" />{item}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-blue-200/60 border-t border-white/10 pt-4">Quotes are rough order-of-magnitude estimates. Refined pricing follows direct engagement.</p>
              </div>
            </div>
          </div>
        )}
        {!isLoading && !hasSearched && (
          <div className="text-center py-24">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-[#0F2B54] shadow-lg mb-6">
              <Search className="h-10 w-10 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Find Engineering Service Providers</h2>
            <p className="text-sm text-slate-500 max-w-md mx-auto">Describe your engineering project above and our AI will match you with the best-fit providers from our directory of 6,000+ firms.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-[#0F2B54] mb-4">
            <Loader2 className="h-8 w-8 animate-spin text-white" />
          </div>
          <p className="text-sm text-slate-500">Loading search...</p>
        </div>
      </div>
    }>
      <SearchPageContent />
    </Suspense>
  );
}
