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
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  // Load existing ads
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const { apiClient } = await import('@/lib/api');
        const resp = await apiClient.get('/me/promotions');
        setMyAds(resp.data ?? []);
      } catch {
        // Ignore — might not have ads yet
      } finally {
        setLoadingAds(false);
      }
    })();
  }, [user]);

  // Poll for status changes whenever we're showing the post-submit screen
  // or whenever the provider has an ad in a non-terminal state. Updates
  // the "Your ad is being generated" screen in place, and keeps the
  // existing-ads list fresh so the provider sees approvals/rejections
  // persistently until they dismiss.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const { apiClient } = await import('@/lib/api');
        const resp = await apiClient.get('/me/promotions');
        if (cancelled) return;
        const ads = resp.data ?? [];
        setMyAds(ads);
        // If the success screen is up, reflect the latest status for that ad.
        if (result?.ad_id) {
          const match = ads.find((a: any) => a.id === result.ad_id);
          if (match && match.ad_status !== result.ad_status) {
            setResult({
              ...result,
              ad_status: match.ad_status,
              admin_review_notes: match.admin_review_notes ?? null,
              title: match.title ?? result.title,
            });
          }
        }
      } catch {}
    };
    // Kick off one tick, then poll every 5s.
    tick();
    const id = setInterval(tick, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, [user, result?.ad_id]);

  // Hydrate the post-submit banner from existing ads (persistent feedback):
  // if the provider has an ad that is pending/active/rejected and they have
  // not dismissed it, keep showing the banner across refreshes.
  useEffect(() => {
    if (!user) return;
    if (result) return;
    if (!myAds || myAds.length === 0) return;
    try {
      const raw = localStorage.getItem('prw_ad_dismissed_v2');
      const dismissed: string[] = raw ? JSON.parse(raw) : [];
      const relevantStatuses = new Set(['processing', 'pending_review', 'reserved_checkout_pending', 'active', 'rejected']);
      // Dismiss key is `${ad.id}:${ad.ad_status}` so a new status on the
      // same ad always produces a fresh banner (e.g. pending_review -> reserved_checkout_pending).
      const sorted = [...myAds]
        .filter((a: any) => relevantStatuses.has(a.ad_status) && !dismissed.includes(`${a.id}:${a.ad_status}`))
        .sort((a: any, b: any) => {
          const ta = new Date(a.updated_at || a.reviewed_at || a.created_at || 0).getTime();
          const tb = new Date(b.updated_at || b.reviewed_at || b.created_at || 0).getTime();
          return tb - ta;
        });
      const latest = sorted[0];
      if (latest) {
        setResult({
          ad_id: latest.id,
          ad_status: latest.ad_status,
          title: latest.title,
          admin_review_notes: latest.admin_review_notes ?? null,
          message: latest.ad_status === 'active'
            ? 'Approved — an email confirmation has been sent.'
            : latest.ad_status === 'rejected'
              ? 'An email with the reason and next steps has been sent.'
              : latest.ad_status === 'reserved_checkout_pending'
                ? 'Approved — complete the $50/month subscription to publish your ad.'
                : latest.ad_status === 'pending_review'
                  ? 'Generated successfully and queued for admin review.'
                  : 'Generating your ad — this usually takes 1–2 minutes.',
        });
      }
    } catch {}
  }, [user, myAds, result]);


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

  // Success / status-feedback state persists until dismissed.
  const startAdCheckout = async (adId: string) => {
    if (!adId) return;
    setCheckoutLoading(true);
    setCheckoutError(null);
    try {
      const { apiClient } = await import('@/lib/api');
      const resp = await apiClient.post(`/me/promotions/${adId}/checkout-session`);
      const data = resp.data || {};
      if (data.already_paid) {
        // Webhook may still be catching up; refresh once.
        window.location.reload();
        return;
      }
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
        return;
      }
      throw new Error('Checkout URL was not returned by the server.');
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Unable to start checkout.';
      setCheckoutError(msg);
      setCheckoutLoading(false);
    }
  };

  const dismissAdBanner = (id: string, status: string) => {
    try {
      const key = 'prw_ad_dismissed_v2';
      const raw = localStorage.getItem(key);
      const set: string[] = raw ? JSON.parse(raw) : [];
      const compound = `${id}:${status}`;
      if (!set.includes(compound)) set.push(compound);
      localStorage.setItem(key, JSON.stringify(set));
    } catch {}
    setResult(null);
    setError(null);
  };

  if (result) {
    const status = result.ad_status as string;
    const isProcessing = status === 'processing';
    const isPending = status === 'pending_review';
    const isCheckoutPending = status === 'reserved_checkout_pending';
    const isActive = status === 'active';
    const isRejected = status === 'rejected';

    const title = isProcessing
      ? 'Your ad is being generated!'
      : isPending
        ? 'Ad generated — awaiting admin review'
        : isCheckoutPending
          ? 'Approved — complete payment to publish'
          : isActive
            ? 'Your ad is live!'
            : isRejected
              ? 'Your ad was not approved'
              : 'Ad Submitted!';

    const iconBgClass = isRejected
      ? 'bg-red-100'
      : isActive
        ? 'bg-emerald-100'
        : (isPending || isCheckoutPending)
          ? 'bg-amber-100'
          : 'bg-emerald-100';

    const iconColorClass = isRejected
      ? 'text-red-600'
      : isActive
        ? 'text-emerald-600'
        : (isPending || isCheckoutPending)
          ? 'text-amber-600'
          : 'text-emerald-600';

    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
        <div className="w-full max-w-lg bg-white border border-slate-200 rounded-2xl p-10 text-center shadow-sm">
          <div className={`w-14 h-14 rounded-full ${iconBgClass} flex items-center justify-center mx-auto mb-5`}>
            {isProcessing
              ? <Loader2 className={`h-7 w-7 ${iconColorClass} animate-spin`} />
              : isRejected
                ? <AlertCircle className={`h-7 w-7 ${iconColorClass}`} />
                : <CheckCircle className={`h-7 w-7 ${iconColorClass}`} />}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">{title}</h1>
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
              <p className="mt-3 text-xs text-blue-500">This usually takes 1–2 minutes. You can safely close this page — we'll update this screen when there is news.</p>
            </div>
          )}

          {isPending && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 text-left mb-6 text-sm text-amber-800">
              <p className="font-semibold mb-1">Ad generated and sent for review</p>
              <p className="text-amber-700">An admin will review the generated ad copy and approve or reject it within 1 business day. We'll email you as soon as there's a decision.</p>
            </div>
          )}
          {isCheckoutPending && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 text-left mb-6 text-sm text-amber-800">
              <p className="font-semibold mb-1">Approved — one last step</p>
              <p className="text-amber-700 mb-3">Your ad has been approved by our review team. Complete the $50/month subscription to publish it to the public directory. The ad will go live within seconds of a successful payment.</p>
              <p className="text-amber-700 text-xs mb-3"><span className="font-semibold">Founding rate:</span> $50/month is our introductory price (rising to $350/month after the introductory period). Subscribe now and you keep $50/month for your full first year.</p>
              {checkoutError && (
                <p className="text-red-700 text-xs mt-2">{checkoutError}</p>
              )}
              <button
                type="button"
                disabled={checkoutLoading}
                onClick={() => startAdCheckout(result.ad_id)}
                className="w-full mt-2 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
              >
                {checkoutLoading ? 'Redirecting to Stripe…' : 'Pay & Publish ($50/month)'}
              </button>
            </div>
          )}

          {isActive && (
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 text-left mb-6 text-sm text-emerald-800">
              <p className="font-semibold mb-1">Approved and live</p>
              <p className="text-emerald-700">Your ad is now visible in the directory. An email confirming approval has been sent to your inbox.</p>
            </div>
          )}

          {isRejected && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-left mb-6 text-sm text-red-800">
              <p className="font-semibold mb-1">Rejection reason</p>
              <p className="text-red-700 whitespace-pre-wrap">{result.admin_review_notes || 'An admin reviewed your ad and decided not to publish it. A detailed email has been sent to your inbox explaining why and what to adjust before resubmitting.'}</p>
            </div>
          )}

          <div className="flex gap-3">
            <Link
              href="/provider/dashboard"
              className="flex-1 text-center py-2.5 rounded-xl bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#0a1f3e] transition-colors"
            >
              Go to Dashboard
            </Link>
            {(isActive || isRejected || isPending) ? (
              <button
                onClick={() => dismissAdBanner(result.ad_id, result.ad_status)}
                className="flex-1 text-center py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                {isRejected ? 'Submit Another Ad' : 'Dismiss'}
              </button>
            ) : (
              <button
                onClick={() => { setResult(null); setError(null); }}
                className="flex-1 text-center py-2.5 rounded-xl border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
              >
                Submit Another Ad
              </button>
            )}
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
                <div key={ad.id} className="flex flex-col gap-2 py-2 px-3 rounded-lg bg-slate-50">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{ad.title}</p>
                      <p className="text-xs text-slate-500">{ad.page_type} &middot; {ad.ad_status}</p>
                    </div>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      ad.ad_status === 'active' ? 'bg-emerald-100 text-emerald-700' :
                      ad.ad_status === 'pending_review' ? 'bg-amber-100 text-amber-700' :
                      ad.ad_status === 'reserved_checkout_pending' ? 'bg-amber-100 text-amber-700' :
                      ad.ad_status === 'rejected' ? 'bg-red-100 text-red-700' :
                      'bg-slate-100 text-slate-600'
                    }`}>
                      {ad.ad_status === 'pending_review' ? 'Pending Review'
                        : ad.ad_status === 'reserved_checkout_pending' ? 'Awaiting Payment'
                        : ad.ad_status === 'processing' ? 'Generating…'
                        : ad.ad_status}
                    </span>
                  </div>
                  {ad.ad_status === 'reserved_checkout_pending' && (
                    <button
                      type="button"
                      disabled={checkoutLoading}
                      onClick={() => startAdCheckout(ad.id)}
                      className="w-full py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
                    >
                      {checkoutLoading ? 'Redirecting to Stripe…' : 'Pay & Publish ($50/month)'}
                    </button>
                  )}
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
