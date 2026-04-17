'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { Building2, Search, Loader2, ExternalLink, CheckCircle, Sparkles, Star, ArrowUpRight, MapPin, Award, Users, Zap, Mail } from 'lucide-react';

// Normalize API base so `${apiBase}/ads/...` always produces `.../api/v1/ads/...`
// regardless of whether NEXT_PUBLIC_API_URL is set with or without the /api/v1 suffix.
const _rawApiBase = process.env.NEXT_PUBLIC_API_URL || 'https://proreadyengineer-api.onrender.com';
const apiBase = _rawApiBase.replace(/\/+$/, '').replace(/\/api\/v1$/, '') + '/api/v1';

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
  // Enriched public fields set by backend _to_public_response
  company_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  website?: string | null;
}

// ──────────────────────────────────────────────────────────────────────────
// Deterministic accent colour per-firm so cards have personality without
// making every ad identical. Produces one of six gradient presets from the
// ad's id hash — a firm always gets the SAME colour every visit.
// ──────────────────────────────────────────────────────────────────────────
const GRADIENT_PRESETS = [
  { hero: 'from-blue-600 via-indigo-600 to-violet-600', soft: 'from-blue-50 via-indigo-50 to-violet-50', text: 'text-indigo-700', ring: 'ring-indigo-100', chip: 'bg-indigo-50 text-indigo-700', accent: 'bg-indigo-600 hover:bg-indigo-700' },
  { hero: 'from-emerald-600 via-teal-600 to-cyan-600', soft: 'from-emerald-50 via-teal-50 to-cyan-50', text: 'text-teal-700', ring: 'ring-teal-100', chip: 'bg-teal-50 text-teal-700', accent: 'bg-teal-600 hover:bg-teal-700' },
  { hero: 'from-orange-500 via-rose-500 to-pink-600', soft: 'from-orange-50 via-rose-50 to-pink-50', text: 'text-rose-700', ring: 'ring-rose-100', chip: 'bg-rose-50 text-rose-700', accent: 'bg-rose-600 hover:bg-rose-700' },
  { hero: 'from-slate-800 via-slate-700 to-slate-900', soft: 'from-slate-50 via-slate-100 to-slate-50', text: 'text-slate-700', ring: 'ring-slate-200', chip: 'bg-slate-100 text-slate-700', accent: 'bg-slate-800 hover:bg-slate-900' },
  { hero: 'from-amber-500 via-orange-600 to-red-600', soft: 'from-amber-50 via-orange-50 to-red-50', text: 'text-orange-700', ring: 'ring-orange-100', chip: 'bg-orange-50 text-orange-700', accent: 'bg-orange-600 hover:bg-orange-700' },
  { hero: 'from-fuchsia-600 via-purple-600 to-indigo-700', soft: 'from-fuchsia-50 via-purple-50 to-indigo-50', text: 'text-purple-700', ring: 'ring-purple-100', chip: 'bg-purple-50 text-purple-700', accent: 'bg-purple-600 hover:bg-purple-700' },
];

function pickPreset(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return GRADIENT_PRESETS[h % GRADIENT_PRESETS.length];
}

function getInitials(name: string): string {
  // Strip legal-entity suffixes so 'ProReadyEngineer LLC' -> 'PR', not 'PL'.
  const cleaned = name
    .replace(/[,.]/g, ' ')
    .replace(/\b(llc|inc|incorporated|corp|corporation|co|company|ltd|limited|plc|gmbh|llp|pllc|pc|pa|sa|bv|ag)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const words = (cleaned || name).trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return 'EF';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + (words[1][0] || '')).toUpperCase();
}

function FirmCard({ ad, featured = false }: { ad: Ad; featured?: boolean }) {
  const content = ad.llm_extracted_content ?? {};
  const preset = pickPreset(ad.id);
  // Use the REAL company name for initials, not the ad headline. The
  // previous version was deriving initials from the title which produced
  // nonsense like 'GE' for 'Gas Turbine ... Engineering'.
  const companyName = (
    ad.company_name ||
    (content as any).company_name ||
    ''
  ).trim();
  const initials = getInitials(companyName || ad.title || 'Engineering Firm');
  const contactInfo = (content as any).contact_info || {};
  const email = ad.contact_email || contactInfo.email || null;
  const phone = ad.contact_phone || contactInfo.phone || null;

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

  // Featured (hero) variant — used for the first card in the list.
  if (featured) {
    return (
      <div
        onClick={handleClick}
        className={`group relative overflow-hidden rounded-3xl bg-white shadow-xl ring-1 ${preset.ring} cursor-pointer transition-all hover:shadow-2xl hover:-translate-y-0.5`}
      >
        <div className="grid md:grid-cols-5 gap-0">
          {/* Left: Hero image/gradient */}
          <div className={`relative md:col-span-2 bg-gradient-to-br ${preset.hero} p-8 flex items-center justify-center min-h-[260px]`}>
            {/* Featured ribbon pinned to the hero panel — never overlaps the
                content panel text regardless of headline length. */}
            <div className="absolute top-4 left-4 z-10 flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-400 shadow-md">
              <Star className="h-3.5 w-3.5 text-amber-900 fill-amber-900" />
              <span className="text-[11px] font-bold text-amber-900 uppercase tracking-wider">Featured</span>
            </div>
            {ad.image_url ? (
              <img
                src={ad.image_url}
                alt={ad.title}
                className="object-cover w-full h-full absolute inset-0"
                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
              />
            ) : (
              <div className="relative flex flex-col items-center gap-4 text-white">
                <div className="w-24 h-24 rounded-2xl bg-white/20 backdrop-blur-sm border-2 border-white/40 flex items-center justify-center shadow-2xl">
                  <span className="text-3xl font-black text-white tracking-wider">{initials}</span>
                </div>
                <Sparkles className="h-5 w-5 text-white/70" />
              </div>
            )}
            {/* subtle radial overlay for dimensionality */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/10 to-transparent pointer-events-none" />
          </div>

          {/* Right: Content */}
          <div className="md:col-span-3 p-8 flex flex-col">
            {/* Company name eyebrow — the REAL firm name, not the ad headline */}
            {companyName && (
              <div className="flex items-center gap-2 mb-2">
                <Building2 className={`h-4 w-4 ${preset.text}`} />
                <span className={`text-sm font-bold uppercase tracking-wider ${preset.text}`}>{companyName}</span>
              </div>
            )}
            <h2 className="text-2xl md:text-3xl font-black text-slate-900 mb-2 leading-tight">
              {ad.title}
            </h2>

            {content.tagline && (
              <p className={`${preset.text} font-semibold text-base mb-4`}>{content.tagline}</p>
            )}

            {ad.promotional_text && (
              <p className="text-slate-600 leading-relaxed mb-5 line-clamp-4">
                {ad.promotional_text}
              </p>
            )}

            {content.specialties?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-5">
                {content.specialties.slice(0, 6).map((sp: string, i: number) => (
                  <span key={i} className={`px-2.5 py-1 rounded-full text-xs ${preset.chip} font-medium`}>
                    {sp}
                  </span>
                ))}
              </div>
            )}

            {content.proof_points?.length > 0 && (
              <div className="grid sm:grid-cols-2 gap-2 mb-6">
                {content.proof_points.slice(0, 4).map((pp: string, i: number) => (
                  <div key={i} className="flex items-start gap-2">
                    <CheckCircle className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
                    <span className="text-sm text-slate-600 leading-snug">{pp}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Contact (email/phone) — this is what the provider paid for:
                buyers get direct access. */}
            {(email || phone) && (
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mb-4 pt-3 border-t border-slate-100">
                {email && (
                  <a
                    href={`mailto:${email}`}
                    onClick={(e) => e.stopPropagation()}
                    className={`inline-flex items-center gap-1.5 text-sm font-semibold ${preset.text} hover:underline`}
                  >
                    <Mail className="h-4 w-4" />
                    {email}
                  </a>
                )}
                {phone && (
                  <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a11 11 0 0012 12v-1a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2A18 18 0 013 5z"/></svg>
                    {phone}
                  </span>
                )}
              </div>
            )}

            <div className="mt-auto flex items-center justify-between pt-4 border-t border-slate-100">
              {ad.optional_price_text && (
                <div className="flex items-center gap-1.5">
                  <Award className={`h-4 w-4 ${preset.text}`} />
                  <span className={`text-sm font-semibold ${preset.text}`}>{ad.optional_price_text}</span>
                </div>
              )}
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); handleClick(); }}
                className={`ml-auto inline-flex items-center gap-2 ${preset.accent} text-white px-5 py-2.5 rounded-xl font-semibold text-sm shadow-md transition-all group-hover:shadow-lg`}
              >
                {content.cta_label || 'Visit Website'}
                <ArrowUpRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Regular card variant.
  return (
    <div
      onClick={handleClick}
      className={`group relative flex flex-col bg-white rounded-2xl overflow-hidden shadow-sm ring-1 ${preset.ring} hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer h-full`}
    >
      {/* Top gradient strip with avatar/image */}
      <div className={`relative h-40 bg-gradient-to-br ${preset.hero} overflow-hidden`}>
        {ad.image_url ? (
          <img
            src={ad.image_url}
            alt={ad.title}
            className="absolute inset-0 object-cover w-full h-full"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-20 h-20 rounded-2xl bg-white/20 backdrop-blur-sm border-2 border-white/40 flex items-center justify-center shadow-lg">
              <span className="text-2xl font-black text-white tracking-wider">{initials}</span>
            </div>
          </div>
        )}
        {/* Corner shine */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-3xl" />
        {/* Premium badge */}
        <div className="absolute top-3 left-3 flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/95 backdrop-blur-sm shadow-sm">
          <Zap className="h-3 w-3 text-amber-500 fill-amber-500" />
          <span className="text-[10px] font-bold text-slate-800 uppercase tracking-wider">Premium</span>
        </div>
      </div>

      <div className="p-5 flex flex-col flex-1">
        {companyName && (
          <div className="flex items-center gap-1.5 mb-1">
            <Building2 className={`h-3.5 w-3.5 ${preset.text}`} />
            <span className={`text-[11px] font-bold uppercase tracking-wider ${preset.text} truncate`}>{companyName}</span>
          </div>
        )}
        <h3 className="text-lg font-extrabold text-slate-900 mb-1 leading-tight line-clamp-2 group-hover:text-slate-700 transition-colors">
          {ad.title}
        </h3>

        {content.tagline && (
          <p className={`text-xs ${preset.text} font-semibold mb-3`}>{content.tagline}</p>
        )}

        {ad.promotional_text && (
          <p className="text-slate-600 text-sm mb-4 line-clamp-3 leading-relaxed">{ad.promotional_text}</p>
        )}

        {content.specialties?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {content.specialties.slice(0, 3).map((sp: string, i: number) => (
              <span key={i} className={`px-2 py-0.5 rounded-full text-[10px] ${preset.chip} font-medium`}>
                {sp}
              </span>
            ))}
            {content.specialties.length > 3 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-500 font-medium">
                +{content.specialties.length - 3}
              </span>
            )}
          </div>
        )}

        {content.proof_points?.length > 0 && (
          <div className="space-y-1.5 mb-4">
            {content.proof_points.slice(0, 2).map((pp: string, i: number) => (
              <div key={i} className="flex items-start gap-1.5">
                <CheckCircle className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                <span className="text-xs text-slate-600 leading-snug line-clamp-1">{pp}</span>
              </div>
            ))}
          </div>
        )}

        {ad.optional_price_text && (
          <div className="flex items-center gap-1 mb-3">
            <Award className={`h-3.5 w-3.5 ${preset.text}`} />
            <span className={`text-xs font-semibold ${preset.text}`}>{ad.optional_price_text}</span>
          </div>
        )}

        {email && (
          <a
            href={`mailto:${email}`}
            onClick={(e) => e.stopPropagation()}
            className={`mb-3 inline-flex items-center gap-1.5 text-xs font-semibold ${preset.text} hover:underline truncate`}
          >
            <Mail className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{email}</span>
          </a>
        )}

        <div className="mt-auto pt-3 border-t border-slate-100">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handleClick(); }}
            className={`w-full flex items-center justify-center gap-2 ${preset.accent} text-white text-sm px-4 py-2.5 rounded-xl font-semibold shadow-sm transition-all group-hover:shadow-md`}
          >
            {content.cta_label || 'Visit Website'}
            <ArrowUpRight className="h-3.5 w-3.5" />
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
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const PAGE_SIZE = 24;

  const fetchAds = useCallback(async (p: number) => {
    setLoading(true);
    setFetchError(null);
    try {
      const res = await fetch(`${apiBase}/ads/featured-firms?page=${p}&page_size=${PAGE_SIZE}`, {
        credentials: 'include',
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        setFetchError(`HTTP ${res.status}: ${res.statusText}`);
      } else {
        const data = await res.json();
        const list: Ad[] = data.advertisements ?? data.ads ?? data.items ?? [];
        setAds(list);
        setTotalCount(data.total_count ?? list.length);
        setDiagnostics(data.diagnostics ?? null);
        setIsSearchResult(false);
        // eslint-disable-next-line no-console
        console.log('[featured-firms] fetch ok, ads:', list.length, 'diagnostics:', data.diagnostics);
      }
    } catch (err: any) {
      const msg = err?.message || 'unknown error';
      setFetchError(msg);
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
          <div className="flex flex-col items-center justify-center py-20 text-center">
            {fetchError ? (
              <>
                <div className="w-14 h-14 rounded-full bg-red-100 flex items-center justify-center mb-4">
                  <svg className="w-7 h-7 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <h3 className="text-lg font-bold text-slate-700 mb-2">Could not load featured firms</h3>
                <p className="text-sm text-red-600 mb-6 max-w-md">{fetchError}</p>
                <button onClick={() => fetchAds(1)} className="text-sm text-[#0F2B54] font-semibold hover:underline">Retry</button>
              </>
            ) : (
              <>
                <Building2 className="h-12 w-12 text-slate-300 mb-4" />
                <h3 className="text-lg font-bold text-slate-700 mb-2">
                  {isSearchResult ? 'No matching firms found' : 'No featured firms yet'}
                </h3>
                <p className="text-sm text-slate-500 mb-4 max-w-md">
                  {isSearchResult
                    ? 'Try a different search term or browse all firms.'
                    : 'Be the first to feature your engineering firm here!'}
                </p>
                {!isSearchResult && diagnostics && diagnostics.total_in_db > 0 && (
                  <div className="mt-2 max-w-lg w-full text-left bg-amber-50 border border-amber-200 rounded-xl p-4">
                    <p className="text-xs font-bold text-amber-900 uppercase tracking-wider mb-2">Status</p>
                    <p className="text-sm text-amber-900 mb-3">
                      There {diagnostics.total_in_db === 1 ? 'is' : 'are'} <strong>{diagnostics.total_in_db}</strong> ad{diagnostics.total_in_db === 1 ? '' : 's'} in the system but none are currently published. Ads appear here once they reach <code className="bg-amber-100 px-1 py-0.5 rounded text-[11px]">active</code> status.
                    </p>
                    <div className="text-xs text-amber-800">
                      <p className="font-semibold mb-1">Current ad statuses:</p>
                      <ul className="space-y-0.5">
                        {Object.entries(diagnostics.status_counts as Record<string, number>).map(([k, v]) => (
                          <li key={k} className="flex justify-between">
                            <code className="bg-amber-100 px-1.5 py-0.5 rounded text-[11px]">{k}</code>
                            <span className="font-semibold">{v}</span>
                          </li>
                        ))}
                      </ul>
                      {(diagnostics.status_counts?.reserved_checkout_pending ?? 0) > 0 && (
                        <p className="mt-3 text-amber-900">A payment was started but the Stripe webhook did not fire to activate it. Admin: verify <code className="bg-amber-100 px-1 py-0.5 rounded text-[11px]">STRIPE_WEBHOOK_SECRET</code> on Render.</p>
                      )}
                      {(diagnostics.status_counts?.pending_review ?? 0) > 0 && (
                        <p className="mt-3 text-amber-900">Ad{(diagnostics.status_counts.pending_review as number) === 1 ? ' is' : 's are'} waiting for admin review.</p>
                      )}
                      {(diagnostics.status_counts?.processing ?? 0) > 0 && (
                        <p className="mt-3 text-amber-900">Ad{(diagnostics.status_counts.processing as number) === 1 ? ' is' : 's are'} still being generated by the LLM.</p>
                      )}
                    </div>
                    <p className="mt-3 text-[10px] text-amber-700/70 font-mono">{diagnostics.endpoint_version}</p>
                  </div>
                )}
                {isSearchResult && (
                  <button onClick={handleClearSearch} className="text-sm text-[#0F2B54] font-medium hover:underline mt-4">
                    View all firms
                  </button>
                )}
              </>
            )}
          </div>
        ) : (
          <>
            {!isSearchResult && (
              <div className="flex items-center justify-between mb-6">
                <p className="text-sm text-slate-500"><span className="font-semibold text-slate-900">{totalCount}</span> premium {totalCount === 1 ? 'firm' : 'firms'} available</p>
              </div>
            )}

            {/* Hero feature card (first ad) + responsive grid for the rest */}
            {ads.length > 0 && !isSearchResult && (
              <div className="mb-8">
                <FirmCard key={ads[0].id} ad={ads[0]} featured />
              </div>
            )}
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {(isSearchResult ? ads : ads.slice(1)).map((ad) => (
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
