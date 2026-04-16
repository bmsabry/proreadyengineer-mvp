'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useAuth';
import {
  Megaphone, Globe, FileUp, CheckCircle, Loader2,
  AlertCircle, Sparkles, Upload, X, FileText,
} from 'lucide-react';
import { Suspense } from 'react';

function AdvertiseInner() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedType = searchParams.get('type') || '';

  const [pageType, setPageType] = useState<string>(preselectedType || 'software-providers');
  const [websiteUrl, setWebsiteUrl] = useState('');
  const [descriptionText, setDescriptionText] = useState('');
  const [outboundUrl, setOutboundUrl] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [myAds, setMyAds] = useState<any[]>([]);
  const [loadingAds, setLoadingAds] = useState(true);

  // File upload state
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load existing ads
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const { apiClient } = await import('@/lib/api');
        const resp = await apiClient.get('/advertiser/ads/me');
        setMyAds(resp.data ?? []);
      } catch {
        // Ignore — might not have ads yet
      } finally {
        setLoadingAds(false);
      }
    })();
  }, [user]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadedFile(file);
    setParseError(null);
    setDescriptionText('');
    setIsParsing(true);

    try {
      const { apiClient } = await import('@/lib/api');
      const form = new FormData();
      form.append('file', file);
      const resp = await apiClient.post('/ads/parse-doc', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setDescriptionText(resp.data.text || '');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || 'Could not read this file.';
      setParseError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      setUploadedFile(null);
    } finally {
      setIsParsing(false);
    }
  };

  const removeFile = () => {
    setUploadedFile(null);
    setDescriptionText('');
    setParseError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);

    if (!websiteUrl && !descriptionText) {
      setError('Please provide either a website URL or upload a brochure / enter a description.');
      return;
    }

    const normalizeUrl = (url: string) => {
      if (!url) return null;
      const trimmed = url.trim();
      if (!trimmed) return null;
      if (/^https?:\/\//i.test(trimmed)) return trimmed;
      return `https://${trimmed}`;
    };

    const normalizedWebsite = normalizeUrl(websiteUrl);
    const normalizedOutbound = normalizeUrl(outboundUrl);

    setIsSubmitting(true);
    try {
      const { apiClient } = await import('@/lib/api');
      const resp = await apiClient.post('/ads/submit', {
        page_type: pageType,
        website_url: normalizedWebsite,
        description_text: descriptionText || null,
        outbound_url: normalizedOutbound || normalizedWebsite,
      });
      setResult(resp.data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Submission failed';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Success / processing state
  if (result) {
    const isProcessing = result.ad_status === 'processing';
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
        <div className="w-full max-w-lg bg-white border border-slate-200 rounded-2xl p-10 text-center shadow-sm">
          <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-5">
            {isProcessing
              ? <Loader2 className="h-7 w-7 text-emerald-600 animate-spin" />
              : <CheckCircle className="h-7 w-7 text-emerald-600" />}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">
            {isProcessing ? 'Your ad is being generated!' : 'Ad Submitted!'}
          </h1>
          <p className="text-slate-500 text-sm mb-6">{result.message}</p>

          {isProcessing && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl px-5 py-4 text-left mb-6 text-sm text-blue-800">
              <p className="font-semibold mb-1">What happens next:</p>
              <ol className="list-decimal list-inside space-y-1 text-blue-700">
                <li>Our AI reads all pages of your website</li>
                <li>Your ad card is professionally generated</li>
                <li>An admin reviews and approves the ad</li>
                <li>Your ad goes live on the directory</li>
              </ol>
              <p className="mt-3 text-xs text-blue-500">This usually takes 1–2 minutes. You can safely close this page.</p>
            </div>
          )}

          <div className="flex gap-3">
            <Link
              href="/provider/dashboard"
              className="flex-1 text-center py-2.5 rounded-xl bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#0a1f3e] transition-colors"
            >
              Go to Dashboard
            </Link>
            <button
              onClick={() => { setResult(null); setError(null); }}
              className="flex-1 text-center py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              Submit Another Ad
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center">
              <Megaphone className="h-5 w-5 text-violet-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">Advertise with Us</h1>
              <p className="text-sm text-slate-500">$50/month per ad — AI-generated, admin-reviewed</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Existing ads */}
        {!loadingAds && myAds.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-2xl p-5 mb-6">
            <h2 className="text-sm font-bold text-slate-700 mb-3">Your Existing Ads</h2>
            <div className="space-y-2">
              {myAds.map((ad: any) => (
                <div key={ad.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-50">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{ad.title}</p>
                    <p className="text-xs text-slate-500">{ad.page_type} &middot; {ad.ad_status}</p>
                  </div>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    ad.ad_status === 'active' ? 'bg-emerald-100 text-emerald-700' :
                    ad.ad_status === 'pending_review' ? 'bg-amber-100 text-amber-700' :
                    ad.ad_status === 'rejected' ? 'bg-red-100 text-red-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>
                    {ad.ad_status === 'pending_review' ? 'Pending Review'
                      : ad.ad_status === 'processing' ? 'Generating…'
                      : ad.ad_status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Submission form */}
        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-2xl p-6 space-y-6">
          <div className="flex items-center gap-2 pb-4 border-b border-slate-100">
            <Sparkles className="h-4 w-4 text-violet-500" />
            <p className="text-sm font-medium text-slate-700">
              Our AI will read your materials and generate a professional ad card.
            </p>
          </div>

          {/* Ad placement */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-2">Ad Placement</label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setPageType('software-providers')}
                className={`rounded-xl border-2 p-4 text-left transition-all ${
                  pageType === 'software-providers'
                    ? 'border-violet-400 bg-violet-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <p className="text-sm font-bold text-slate-900">Software Providers</p>
                <p className="text-xs text-slate-500 mt-0.5">For software tools &amp; products</p>
              </button>
              <button
                type="button"
                onClick={() => setPageType('featured-firms')}
                className={`rounded-xl border-2 p-4 text-left transition-all ${
                  pageType === 'featured-firms'
                    ? 'border-violet-400 bg-violet-50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <p className="text-sm font-bold text-slate-900">Featured Firms</p>
                <p className="text-xs text-slate-500 mt-0.5">For engineering firms</p>
              </button>
            </div>
          </div>

          {/* ── PRIMARY: File upload ── */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">
              <Upload className="inline h-3.5 w-3.5 mr-1 text-slate-400" />
              Upload Brochure or Flyer
              <span className="font-normal text-slate-400 ml-1">(PDF, Word, or text file)</span>
            </label>

            {!uploadedFile ? (
              <label
                htmlFor="doc-upload"
                className="flex flex-col items-center justify-center gap-2 w-full rounded-xl border-2 border-dashed border-slate-200 bg-slate-50 hover:border-violet-300 hover:bg-violet-50 px-6 py-8 cursor-pointer transition-all"
              >
                <FileUp className="h-8 w-8 text-slate-300" />
                <span className="text-sm font-medium text-slate-600">Click to upload</span>
                <span className="text-xs text-slate-400">PDF · DOCX · TXT — up to 10 MB</span>
                <input
                  id="doc-upload"
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </label>
            ) : (
              <div className="flex items-center gap-3 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3">
                {isParsing
                  ? <Loader2 className="h-5 w-5 text-violet-500 animate-spin shrink-0" />
                  : <FileText className="h-5 w-5 text-violet-500 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{uploadedFile.name}</p>
                  <p className="text-xs text-slate-500">
                    {isParsing ? 'Reading file…' : `${descriptionText.length.toLocaleString()} characters extracted`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={removeFile}
                  className="p-1 rounded-lg hover:bg-violet-100 text-slate-400 hover:text-slate-600 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {parseError && (
              <div className="flex items-start gap-2 mt-2 p-2.5 rounded-lg bg-red-50 border border-red-200">
                <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
                <p className="text-xs text-red-700">{parseError}</p>
              </div>
            )}
          </div>

          {/* ── Divider ── */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-slate-100" />
            <span className="text-xs text-slate-400 font-medium">or provide content another way</span>
            <div className="flex-1 h-px bg-slate-100" />
          </div>

          {/* Website URL */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">
              <Globe className="inline h-3.5 w-3.5 mr-1 text-slate-400" />
              Website URL <span className="font-normal text-slate-400">(optional)</span>
            </label>
            <input
              type="text"
              value={websiteUrl}
              onChange={e => setWebsiteUrl(e.target.value)}
              placeholder="www.your-company.com"
              className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400"
            />
            <p className="text-xs text-slate-400 mt-1">Our AI will read all pages of your site to build your ad.</p>
          </div>

          {/* Description text — shown as editable area; populated by file upload or manual entry */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">
              Description <span className="font-normal text-slate-400">(optional — edit or add to the text above)</span>
            </label>
            <textarea
              value={descriptionText}
              onChange={e => setDescriptionText(e.target.value)}
              rows={5}
              placeholder="Your brochure or flyer text will appear here after upload, or type your description directly…"
              className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400 resize-none"
            />
          </div>

          {/* Click-through URL */}
          <div>
            <label className="block text-sm font-semibold text-slate-700 mb-1.5">
              Click-Through URL <span className="font-normal text-slate-400">(optional)</span>
            </label>
            <input
              type="text"
              value={outboundUrl}
              onChange={e => setOutboundUrl(e.target.value)}
              placeholder="www.your-company.com/product (defaults to website URL)"
              className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-violet-400"
            />
            <p className="text-xs text-slate-400 mt-1">Where should ad clicks redirect? Defaults to your website URL.</p>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-200">
              <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={isSubmitting || isParsing}
            className="w-full py-3 rounded-xl bg-[#0F2B54] text-white text-sm font-semibold hover:bg-[#0a1f3e] disabled:opacity-60 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating your ad with AI…
              </>
            ) : isParsing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Reading your file…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate &amp; Submit Ad for Review
              </>
            )}
          </button>

          <p className="text-xs text-center text-slate-400">
            Your ad will be reviewed by an admin before going live. $50/month subscription starts after approval.
          </p>
        </form>
      </div>
    </div>
  );
}

export default function ProviderAdvertisePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0F2B54] border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <AdvertiseInner />
    </Suspense>
  );
}
