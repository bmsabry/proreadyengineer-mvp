'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Building2 } from 'lucide-react';

const apiBase = process.env.NEXT_PUBLIC_API_URL || 'https://proreadyengineer-api.onrender.com/api/v1';
const TOTAL_SLOTS = 6;

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
  image_s3_key: string | null;
  optional_price_text: string | null;
  ad_status: string;
}

function ActiveAdCard({ ad }: { ad: Ad }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow flex flex-col h-full">
      <div className="h-36 bg-gray-100 flex items-center justify-center overflow-hidden">
        {ad.image_s3_key ? (
          <img
            src={`https://proreadyengineer-assets.s3.amazonaws.com/${ad.image_s3_key}`}
            alt={ad.title}
            className="object-cover w-full h-full"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <Building2 className="h-12 w-12 text-gray-300" />
        )}
      </div>
      <div className="p-5 flex flex-col flex-1">
        <h3 className="text-lg font-bold text-gray-900 mb-2">{ad.title}</h3>
        {ad.promotional_text && (
          <p className="text-gray-600 text-sm mb-3 flex-1 leading-relaxed">{ad.promotional_text}</p>
        )}
        {ad.optional_price_text && (
          <p className="text-blue-700 font-semibold text-sm mb-3">{ad.optional_price_text}</p>
        )}
        <div className="mt-auto">
          {ad.outbound_url ? (
            <a
              href={ad.outbound_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full text-center bg-blue-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Visit Website
            </a>
          ) : (
            <span className="block w-full text-center bg-gray-100 text-gray-400 text-sm px-4 py-2 rounded-lg">No Website</span>
          )}
        </div>
      </div>
    </div>
  );
}

function PlaceholderCard() {
  return (
    <div className="bg-white border-2 border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center p-8 min-h-[240px] hover:border-blue-300 hover:bg-blue-50/50 transition-colors group">
      <div className="text-4xl font-light text-gray-300 group-hover:text-blue-300 transition-colors mb-3">+</div>
      <h3 className="text-gray-400 font-semibold mb-2 group-hover:text-blue-500 transition-colors">Advertise Here</h3>
      <p className="text-gray-300 text-sm text-center mb-4 leading-relaxed">
        Reach thousands of engineering professionals looking for software tools.
      </p>
      <Link
        href="/advertise"
        className="text-blue-600 text-sm font-medium border border-blue-200 px-4 py-1.5 rounded-lg hover:bg-blue-100 hover:border-blue-400 transition-colors"
      >
        Learn More
      </Link>
    </div>
  );
}

export default function SoftwareProvidersPage() {
  const [ads, setAds] = useState<Ad[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAds() {
      try {
        const res = await fetch(`${apiBase}/ads/software-providers`, {
          credentials: 'include',
          headers: getAuthHeaders(),
        });
        if (res.ok) {
          const data = await res.json();
          const list: Ad[] = Array.isArray(data) ? data : (data.ads ?? data.items ?? []);
          setAds(list.filter((a) => a.ad_status === 'active'));
        }
      } catch (err) {
        console.error('Failed to load software provider ads:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchAds();
  }, []);

  const placeholderCount = Math.max(0, TOTAL_SLOTS - ads.length);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white shadow-sm sticky top-0 z-50">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl text-blue-700">
            <Building2 className="h-6 w-6" />
            <span>ProMechDirectory</span>
          </Link>
          <nav className="ml-auto flex gap-4 text-sm">
            <Link href="/search" className="text-gray-600 hover:text-blue-700 px-3 py-1 rounded">Search</Link>
            <Link href="/featured-firms" className="text-gray-600 hover:text-blue-700 px-3 py-1 rounded">Featured Firms</Link>
            <Link href="/advertise" className="text-gray-600 hover:text-blue-700 px-3 py-1 rounded">Advertise</Link>
            <Link href="/auth/login" className="bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700">Sign In</Link>
          </nav>
        </div>
      </header>

      <section className="bg-gradient-to-br from-blue-700 to-blue-900 text-white py-14 px-6 text-center">
        <h1 className="text-4xl font-extrabold mb-3">Engineering Software Providers</h1>
        <p className="text-blue-200 text-lg max-w-2xl mx-auto">
          Discover the software tools and platforms trusted by engineering professionals worldwide.
        </p>
      </section>

      <main className="container py-12">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
            <span className="ml-4 text-gray-500">Loading software providers&hellip;</span>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {ads.map((ad) => (
              <ActiveAdCard key={ad.id} ad={ad} />
            ))}
            {Array.from({ length: placeholderCount }).map((_, i) => (
              <PlaceholderCard key={`placeholder-${i}`} />
            ))}
          </div>
        )}

        <div className="mt-16 text-center bg-white border border-gray-100 rounded-2xl p-10 shadow-sm">
          <h2 className="text-2xl font-bold text-gray-900 mb-3">Advertise Your Software</h2>
          <p className="text-gray-500 mb-6 max-w-xl mx-auto">
            Put your engineering software in front of thousands of professionals. $50/month per slot.
          </p>
          <Link
            href="/advertise"
            className="inline-block bg-blue-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-blue-700 transition-colors"
          >
            Get Started &rarr;
          </Link>
        </div>
      </main>
    </div>
  );
}
