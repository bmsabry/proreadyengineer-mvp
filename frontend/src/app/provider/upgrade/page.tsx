'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRequireAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import {
  CheckCircle,
  XCircle,
  Star,
  ArrowRight,
  Zap,
  Shield,
  TrendingUp,
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface PricingFeature {
  text: string;
  included: boolean;
}

interface PricingCardProps {
  title: string;
  price: string;
  priceSub?: string;
  priceNote?: string;
  features: PricingFeature[];
  ctaLabel: string;
  ctaHref?: string;
  ctaAction?: () => void;
  isFeatured?: boolean;
  isLoading?: boolean;
  note?: string;
  icon: React.ReactNode;
}

// ─── Pricing Card ─────────────────────────────────────────────────────────────

function PricingCard({
  title,
  price,
  priceSub,
  priceNote,
  features,
  ctaLabel,
  ctaHref,
  ctaAction,
  isFeatured = false,
  isLoading = false,
  note,
  icon,
}: PricingCardProps) {
  const borderClass = isFeatured
    ? 'border-2 border-primary shadow-2xl'
    : 'border border-slate-200 shadow-sm';

  const headerClass = isFeatured
    ? 'bg-primary text-white'
    : 'bg-slate-50 text-slate-800';

  const ctaClass = isFeatured
    ? 'bg-primary hover:bg-primary/90 text-white'
    : 'bg-slate-800 hover:bg-slate-900 text-white';

  const CtaContent = (
    <>
      {isLoading ? (
        <span className="flex items-center justify-center gap-2">
          <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          Processing…
        </span>
      ) : (
        <span className="flex items-center justify-center gap-2">
          {ctaLabel}
          <ArrowRight className="h-4 w-4" />
        </span>
      )}
    </>
  );

  return (
    <div className={`rounded-2xl overflow-hidden relative ${borderClass} flex flex-col`}>
      {/* Featured badge */}
      {isFeatured && (
        <div className="mb-3">
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-400 text-amber-900 text-xs font-bold uppercase tracking-wider">
            <Star className="h-3 w-3" /> Recommended
          </span>
        </div>
      )}

      {/* Header */}
      <div className={`p-6 pb-4 ${headerClass}`}>
        <div className="flex items-center gap-2 mb-3">
          {icon}
          <h3 className={`text-base font-bold ${isFeatured ? 'text-white' : 'text-slate-900'}`}>
            {title}
          </h3>
        </div>
        <p className={`text-3xl font-extrabold ${isFeatured ? 'text-white' : 'text-slate-900'}`}>
          {price}
        </p>
        {priceSub && (
          <p className={`text-sm mt-0.5 ${isFeatured ? 'text-blue-200' : 'text-slate-500'}`}>
            {priceSub}
          </p>
        )}
      </div>

      {/* Body */}
      <div className="p-6 pt-5 flex flex-col flex-1 bg-white">
        {priceNote && (
          <p className="text-xs text-slate-500 mb-4 -mt-1 italic">{priceNote}</p>
        )}

        <ul className="space-y-3 mb-6 flex-1">
          {features.map((f, i) => (
            <li key={i} className="flex items-start gap-2.5">
              {f.included ? (
                <CheckCircle className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
              )}
              <span
                className={`text-sm leading-snug ${
                  f.included ? 'text-slate-700 font-medium' : 'text-slate-500'
                }`}
              >
                {f.text}
              </span>
            </li>
          ))}
        </ul>

        {/* CTA */}
        {ctaAction ? (
          <button
            onClick={ctaAction}
            disabled={isLoading}
            className={`w-full py-3 px-4 rounded-xl text-sm font-bold transition-all duration-200 disabled:opacity-60 ${ctaClass}`}
          >
            {CtaContent}
          </button>
        ) : ctaHref ? (
          <Link
            href={ctaHref}
            className={`w-full block text-center py-3 px-4 rounded-xl text-sm font-bold transition-all duration-200 ${ctaClass}`}
          >
            {CtaContent}
          </Link>
        ) : null}

        {note && (
          <p className="text-xs text-slate-500 text-center mt-3">{note}</p>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ProviderUpgradePage() {
  const { user, isLoading: authLoading } = useRequireAuth(['provider']);
  const [annualLoading, setAnnualLoading] = useState(false);
  const [agreed, setAgreed] = useState(false);
  const [profileEditLoading, setProfileEditLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // ── Stripe checkout handlers ─────────────────────────────────────────

  const handleAnnualSubscription = async () => {
    if (!agreed) { setErrorMsg('Please agree to the Terms and refund policy to continue.'); return; }
    setAnnualLoading(true);
    setErrorMsg(null);
    try {
      const origin = typeof window !== 'undefined' ? window.location.origin : '';
      const res = await api.payments.createProviderAnnualSubscription({ origin });
      const data = (res as any).data ?? res;
      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        setErrorMsg('Unable to start checkout. Please try again.');
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Checkout failed. Please try again.';
      setErrorMsg(String(detail));
    } finally {
      setAnnualLoading(false);
    }
  };

  const handleProfileEditCheckout = async () => {
    if (!agreed) { setErrorMsg('Please agree to the Terms and refund policy to continue.'); return; }
    setProfileEditLoading(true);
    setErrorMsg(null);
    try {
      const origin = typeof window !== 'undefined' ? window.location.origin : '';
      const res = await api.payments.createProfileEditCheckout({ origin });
      const data = (res as any).data ?? res;
      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        setErrorMsg('Unable to start checkout. Please try again.');
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Checkout failed. Please try again.';
      setErrorMsg(String(detail));
    } finally {
      setProfileEditLoading(false);
    }
  };

  // ── Loading state ────────────────────────────────────────────────────

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // ── Pricing tiers ────────────────────────────────────────────────────

  const annualFeatures: PricingFeature[] = [
    { text: 'See the customer\u2019s direct contact info on every RFQ \u2014 reach out and win the deal', included: true },
    { text: 'Receive ALL matching RFQs automatically', included: true },
    { text: 'Unlimited RFQ access — no $50 per-unlock fee', included: true },
    { text: 'Quote every RFQ you receive', included: true },
    { text: 'Unlimited profile updates (all 17 fields)', included: true },
    { text: 'Request Rank Up for better search placement', included: true },
    { text: 'Priority listing in search results', included: true },
  ];

  const profileEditFeatures: PricingFeature[] = [
    { text: 'Update all 17 profile fields — once', included: true },
    { text: 'Improve your search ranking immediately', included: true },
    { text: 'RFQ access still requires $50/RFQ unlock', included: false },
    { text: 'Requires $50/RFQ unlock fee', included: false },
  ];

  const perRfqFeatures: PricingFeature[] = [
    { text: 'Access individual RFQ details', included: true },
    { text: 'Submit quotes on unlocked RFQs', included: true },
    { text: 'No profile editing included', included: false },
    { text: 'Requires $50/RFQ unlock fee', included: false },
  ];

  return (
    <div className="min-h-screen bg-slate-50">

      {/* ── Page Header ── */}
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-6 py-10 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-semibold mb-4">
            <TrendingUp className="h-3.5 w-3.5" />
            Provider Growth Plans
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 mb-3">
            Upgrade Your ProMechDirectory Account
          </h1>
          <p className="text-slate-500 text-base max-w-xl mx-auto">
            Grow your engineering business by connecting with customers who need exactly what you offer.
            Choose the plan that fits your goals.
          </p>
        </div>
      </div>

      {/* ── Error Banner ── */}
      {errorMsg && (
        <div className="max-w-5xl mx-auto px-6 pt-6">
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
            {errorMsg}
          </div>
        </div>
      )}

      {/* ── Pricing Cards ── */}
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="max-w-2xl mx-auto mb-6">
          <div className="mb-0 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            <p className="mb-2"><strong>Refund policy:</strong> Annual plans are refundable within <strong>14 days</strong> of payment; after that there is no refund and your plan continues until the end of the paid year. Monthly plans are refundable within <strong>5 days</strong> of payment; after that there is no refund and your plan continues until the end of the paid month. One-time fees (RFQ unlocks, NDA fees, profile-edit unlock) are non-refundable. You can cancel anytime to stop renewal.</p>
            <label className="flex items-start gap-2 cursor-pointer">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5" />
              <span>I have read and agree to the <a href="/terms" target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">Terms of Service</a> and the refund policy above.</span>
            </label>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">

          {/* Card 1 — Annual Professional (FEATURED) */}
          <PricingCard
            isFeatured
            title="Annual Professional"
            price="$1,000 / year"
            priceSub="~$83 / month — best value"
            priceNote="Billed annually. Cancel anytime."
            features={annualFeatures}
            ctaLabel="Subscribe — $1,000/year"
            ctaAction={handleAnnualSubscription}
            isLoading={annualLoading}
            note="Best value for active providers"
            icon={<Zap className="h-5 w-5 text-amber-400" />}
          />

          {/* Card 2 — Profile Edit Only */}
          <PricingCard
            title="Profile Edit — One Time"
            price="$500"
            priceSub="One-time payment"
            priceNote="No recurring charges."
            features={profileEditFeatures}
            ctaLabel="Unlock Profile Edit — $500"
            ctaAction={handleProfileEditCheckout}
            isLoading={profileEditLoading}            note="One-time payment, no recurring charges"
            icon={<Shield className="h-5 w-5 text-slate-500" />}
          />

          {/* Card 3 — Pay Per RFQ */}
          <PricingCard
            title="Pay Per RFQ"
            price="$50 / RFQ"
            priceSub="No commitment"
            priceNote="Pay only for the RFQs you want to access."
            features={perRfqFeatures}
            ctaLabel="Unlock RFQs as Needed"
            ctaHref="/provider/all-rfqs"
            note="No commitment required"
            icon={<ArrowRight className="h-5 w-5 text-slate-500" />}
          />

        </div>
      </div>

      {/* ── Social Proof / Motivating Copy ── */}
      <div className="max-w-5xl mx-auto px-6 pb-12">
        <div className="bg-primary rounded-2xl p-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center shrink-0">
              <TrendingUp className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-base mb-1">
                3x More RFQ Matches
              </p>
              <p className="text-blue-200 text-sm">
                Providers with complete, up-to-date profiles receive significantly more
                matching RFQ invitations from our AI search engine.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center shrink-0">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <div>
              <p className="text-white font-bold text-base mb-1">
                Pays for Itself in 20 RFQs
              </p>
              <p className="text-blue-200 text-sm">
                The $1,000/year Annual subscription saves $50 per RFQ — it pays for itself
                after just 50 unlocks compared to the per-RFQ rate.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Back Link ── */}
      <div className="max-w-5xl mx-auto px-6 pb-8 text-center">
        <Link
          href="/provider/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          ← Back to Dashboard
        </Link>
      </div>

    </div>
  );
}
