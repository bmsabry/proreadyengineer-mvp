'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Building2, Search, Loader2, ExternalLink, CheckCircle, Sparkles } from 'lucide-react';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'https://proreadyengineer-api.onrender.com/api/v1';

function getAuthHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) h['Authorization'] = `Bearer ${token}`;
  }
  return h;
}

interface Ad {
  id: string;
  title: string;
  promotional_text: string | null;
  outbound_url: string | null;
  image_url: string | null;
  image_s3_key?: string | null;
  optional_price_text: string | null;
  provider_id?: number | null;
  page_type?: string | null;
  llm_extracted_content?: Record<string, any> | null;
  click_count?: number;
  impression_count?: number;
}

function FirmCard({ ad }: { ad: Ad }) {
  const content = ad.llm_extracted_content ?? {};

  const handleClick = async () => {
    try {
      await fetch(`${apiBase}/ads/${ad.id}/click`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders(),
      });
    } catch {}
    if (ad.outbound_url) {
      window.open(ad.outbound_url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden hover:shadow-lg hover:border-slate-300 transition-all flex flex-col h-full group">
      <div className="h-32 bg-gradient-to-br from-blue-50 to-slate-100 flex items-center justify-center overflow-hidden">
        {ad.image_url ? (
          <img
            src={ad.image_url}
            alt={ad.title}
            className="object-cover w-full h-full"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <Building2 className="h-10 w-10 text-blue-300" />
        )}
      </div>

      <div className="p-5 flex flex-col flex-1">
        <h3 className="text-base font-bold text-slate-900 mb-1 line-clamp-2">{ad.title}</h3>

        {content.tagline && (
          <p className="text-xs text-blue-600 font-medium mb-2">{content.tagline}</p>
        )}

        {ad.promotional_text && (
          <p className="text-slate-600 text-sm mb-3 flex-1 leading-relaxed line-clamp-3">{ad.promotional_text}</p>
        )}

        {content.specialties?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {content.specialties.slice(0, 4).map((s: string, i: number) => (
              <span key={i} className="px-2 py-0.5 rounded-full text-[10px] bg-blue-50 text-blue-700 font-medium">
                {s}
              </span>
            ))}
            {content.specialties.length > 4 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-500">
                +{content.specialties.length - 4} more
              </span>
            )}
          </div>
        )}

        {content.proof_points?.length > 0 && (
          <div className="space-y-1 mb-3">
            {content.proof_points.slice(0, 2).map((p: string, i: number) => (
              <div key={i} className="flex items-start gap-1.5">
                <CheckCircle className="h-3 w-3 text-emerald-500 mt-0.5 shrink-0" />
                <span className="text-[11px] text-slate-500 line-clamp-1">{p}</span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-auto pt-3 border-t border-slate-100">
          <button
            onClick={handleClick}
            className="w-full flex items-center justify-center gap-2 bg-[#0F2B54] text-white text-sm px-4 py-2.5 rounded-xl hover:bg-[#0a1f3e] transition-colors font-medium"
          >
            {content.cta_label || 'Contact Firm'}
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function FeaturedFirmsPage() {
  const [ads, setAds] = useState<Ad[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [isSearchResult, setIsSearchResult] = useState(false);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const PAGE_SIZE = 24;

  const fetchAds = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/ads/featured-firms?page=${p}&page_size=${PAGE_SIZE}`, {
        credentials: 'include',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        const list: Ad[] = data.advertisements ?? data.ads ?? data.items ?? [];
        setAds(list);
        setTotalCount(data.total_count ?? list.length);
        setIsSearchResult(false);
      }
    } catch (err) {
      console.error('Failed to load featured firm ads:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAds(1);
  }, [fetchAds]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      fetchAds(1);
      return;
    }

    setSearching(true);
    try {
      const res = await fetch(`${apiBase}/ads/search`, {
        method: 'POST',
        credentials: 'include',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          query: searchQuery,
          page_type: 'featured-firms',
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setAds(data.advertisements ?? []);
        setTotalCount(data.total_count ?? 0);
        setIsSearchResult(true);
      }
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setPage(1);
    fetchAds(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    fetchAds(newPage);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white shadow-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto flex h-14 items-center px-6">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl text-[#0F2B54]">
            <Building2 className="h-6 w-6" />
            <span>ProMechDirectory</span>
          </Link>
          <nav className="ml-auto flex gap-4 text-sm items-center">
            <Link href="/search" className="text-slate-600 hover:text-[#0F2B54] px-3 py-1 rounded">Search</Link>
            <Link href="/software-providers" className="text-slate-600 hover:text-[#0F2B54] px-3 py-1 rounded">Software</Link>
            <Link href="/advertise" className="text-slate-600 hover:text-[#0F2B54] px-3 py-1 rounded">Advertise</Link>
            <Link href="/login" className="bg-[#0F2B54] text-white px-4 py-1.5 rounded-lg hover:bg-[#0a1f3e]">Sign In</Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="bg-gradient-to-br from-slate-800 to-[#0F2B54] text-white py-14 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-3xl md:text-4xl font-extrabold mb-3">Featured Engineering Firms</h1>
          <p className="text-blue-200 text-lg max-w-2xl mx-auto mb-8">
            Premium engineering service providers with direct access to customers — no RFQ required.
          </p>

          {/* Search bar */}
          <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
            <div className="relative flex items-center">
              <div className="absolute left-4 flex items-center">
                {searching ? (
                  <Loader2 className="h-5 w-5 text-slate-400 animate-spin" />
                ) : (
                  <Sparkles className="h-5 w-5 text-blue-400" />
                )}
              </div>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by engineering specialty, capability, or service..."
                className="w-full py-3.5 pl-12 pr-28 rounded-2xl bg-white text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-300 shadow-lg"
              />
              <button
                type="submit"
                disabled={searching}
                className="absolute right-2 px-5 py-2 rounded-xl bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#0a1f3e] disabled:opacity-60 transition-colors"
              >
                <Search className="h-4 w-4" />
              </button>
            </div>
            {isSearchResult && (
              <div className="mt-3 flex items-center justify-center gap-2">
                <p className="text-sm text-blue-200">
                  Showing {totalCount} results for &ldquo;{searchQuery}&rdquo;
                </p>
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="text-xs text-blue-300 hover:text-white underline"
                >
                  Clear search
                </button>
              </div>
            )}
          </form>
        </div>
      </section>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-6 py-10">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="h-8 w-8 text-[#0F2B54] animate-spin" />
            <span className="ml-4 text-slate-500">Loading featured firms&hellip;</span>
          </div>
        ) : ads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Building2 className="h-12 w-12 text-slate-300 mb-4" />
            <h3 className="text-lg font-bold text-slate-700 mb-2">
              {isSearchResult ? 'No matching firms found' : 'No featured firms yet'}
            </h3>
            <p className="text-sm text-slate-500 mb-6 max-w-md">
              {isSearchResult
                ? 'Try a different search term or browse all firms.'
                : 'Be the first to feature your engineering firm here!'}
            </p>
            {isSearchResult && (
              <button onClick={handleClearSearch} className="text-sm text-[#0F2B54] font-medium hover:underline">
                View all firms
              </button>
            )}
          </div>
        ) : (
          <>
            {!isSearchResult && (
              <div className="flex items-center justify-between mb-6">
                <p className="text-sm text-slate-500">{totalCount} featured firms</p>
              </div>
            )}

            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {ads.map((ad) => (
                <FirmCard key={ad.id} ad={ad} />
              ))}
            </div>

            {/* Pagination */}
            {!isSearchResult && totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-10">
                <button
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page <= 1}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <span className="text-sm text-slate-500 px-4">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= totalPages}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}

        {/* CTA */}
        <div className="mt-16 text-center bg-white border border-slate-200 rounded-2xl p-10">
          <h2 className="text-2xl font-bold text-slate-900 mb-3">Feature Your Engineering Firm</h2>
          <p className="text-slate-500 mb-2 max-w-xl mx-auto">
            Direct access to customers outside the standard RFQ flow. AI-powered ad generation, $50/month.
          </p>
          <Link
            href="/advertise"
            className="inline-block bg-[#0F2B54] text-white px-8 py-3 rounded-xl font-semibold hover:bg-[#0a1f3e] transition-colors mt-4"
          >
            Advertise Your Firm &rarr;
          </Link>
        </div>
      </main>
    </div>
  );
}
