'use client';

import { useState, useEffect , Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { useRedirectIfAuthenticated } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';

function LoginPageContent() {
  const { login } = useAuth();
  useRedirectIfAuthenticated();

  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [slowWarning, setSlowWarning] = useState(false);
  const [extractedInvite, setExtractedInvite] = useState('');
  const [extractedRfqId, setExtractedRfqId] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (isSubmitting) {
      timer = setTimeout(() => setSlowWarning(true), 8000);
    } else {
      setSlowWarning(false);
    }
    return () => clearTimeout(timer);
  }, [isSubmitting]);

  // Store invite token from URL params on mount
  useEffect(() => {
    const invite = searchParams.get('invite') || '';
    const redirect = searchParams.get('redirect') || '';

    // Extract invite token from redirect URL if present
    let extractedInvite = invite;
    let extractedRfqId = searchParams.get('rfq_id') || '';

    if (!extractedInvite && redirect) {
      try {
        const redirectUrl = new URL(redirect, 'http://x');
        extractedInvite = redirectUrl.searchParams.get('invite') || '';
        // Extract rfq_id from path like /provider/rfq/{id}
        const rfqMatch = redirect.match(/\/provider\/rfq\/([^/?]+)/);
        if (rfqMatch) extractedRfqId = rfqMatch[1];
      } catch {}
    }

    // Also extract rfq_id from redirect path for non-invite case
    if (!extractedRfqId && redirect) {
      const rfqMatch = redirect.match(/\/provider\/rfq\/([^/?]+)/);
      if (rfqMatch) localStorage.setItem('pendingInviteRfqId', rfqMatch[1]);
    }

    if (extractedInvite) {
      localStorage.setItem('pendingInviteToken', extractedInvite);
      setExtractedInvite(extractedInvite);
    }
    if (extractedRfqId) {
      localStorage.setItem('pendingInviteRfqId', extractedRfqId);
      setExtractedRfqId(extractedRfqId);
    }
  }, [searchParams]);

  // Prefill email from invite token when present
  useEffect(() => {
    if (!extractedInvite) return;
    api.auth.getInviteInfo(extractedInvite)
      .then(res => {
        const info = res.data;
        if (info?.sent_to_email) {
          setEmail(info.sent_to_email);
          setInviteEmail(info.sent_to_email);
        }
      })
      .catch((e) => console.debug('ignored error', e));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extractedInvite]);


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await login(email, password, rememberMe);
      // Redeem invite token if present
      const pendingToken = localStorage.getItem('pendingInviteToken');
      if (pendingToken) {
        try {
          // Use api client (has correct /api/v1 base URL + auth headers)
          const redeemRes = await api.auth.redeemInvite(pendingToken);
          if (redeemRes?.data) {
            localStorage.removeItem('pendingInviteToken');
            localStorage.removeItem('pendingInviteRfqId');
            toast.success('Logged in successfully');
            // Redirect directly to the specific RFQ after invite redemption.
            // If rfq_id is known, take them straight to the project; otherwise fall back to dashboard.
            const pendingRfqId = localStorage.getItem('pendingInviteRfqId') || extractedRfqId;
            router.push(pendingRfqId ? `/provider/rfq/${pendingRfqId}` : '/provider/dashboard');
            return;
          }
        } catch {
          // ignore redemption errors, proceed with normal login
        }
        localStorage.removeItem('pendingInviteToken');
        localStorage.removeItem('pendingInviteRfqId');
      }
      toast.success('Logged in successfully');
    } catch (error: any) {
      const detail = error?.response?.data?.detail || '';
      if (detail === 'email_not_verified') {
        // Redirect to check-email page with the email for resend capability
        router.push(`/check-email?email=${encodeURIComponent(email)}`);
        return;
      }
      const msg = detail || error?.message || 'Invalid email or password';
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-4 py-12">

      {/* Brand header */}
      <div className="mb-8 text-center">
        <Link href="/" className="inline-flex items-center gap-2.5 mb-3 group">
          <div className="w-10 h-10 rounded-xl bg-[#0F2B54] flex items-center justify-center shadow-md group-hover:shadow-lg transition-all duration-150">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <span className="font-bold text-xl text-[#0F2B54] tracking-tight">ProMechDirectory</span>
        </Link>
        <p className="text-sm text-slate-500 font-medium">Engineering Services Marketplace</p>
      </div>

      {/* Invite banner */}
      {extractedInvite && (
        <div className="w-full max-w-md mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 flex items-start gap-3">
          <span className="text-amber-500 text-base mt-0.5">&#128274;</span>
          <div>
            <p className="text-sm font-semibold text-amber-900">You have a provider invitation</p>
            {inviteEmail ? (
              <p className="text-xs text-amber-700 mt-0.5">This invitation was sent to <strong>{inviteEmail}</strong>. Please log in with that email to access this RFQ opportunity.</p>
            ) : (
              <p className="text-xs text-amber-700 mt-0.5">Sign in or create an account to access this RFQ opportunity.</p>
            )}
          </div>
        </div>
      )}

      {/* Main card */}
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-8 pt-8 pb-6">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Welcome back</h1>
          <p className="text-sm text-slate-500 mt-1.5">Sign in to your account to continue</p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="px-8 pb-8 space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="email" className="text-sm font-medium text-slate-700">Email address</Label>
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
                className="h-11 border border-slate-200 rounded-lg bg-white px-4 text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 transition-all duration-150"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-sm font-medium text-slate-700">Password</Label>
                <Link href="/forgot-password" className="text-xs text-blue-600 hover:text-blue-700 font-medium transition-colors duration-150">
                  Forgot password?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
                className="h-11 border border-slate-200 rounded-lg bg-white px-4 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 transition-all duration-150"
              />
            </div>

            <div className="flex items-center gap-2.5">
              <input
                id="rememberMe"
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={isSubmitting}
                className="h-4 w-4 rounded border-slate-300 text-[#0F2B54] focus:ring-blue-500 cursor-pointer accent-[#0F2B54]"
              />
              <Label htmlFor="rememberMe" className="text-sm font-normal text-slate-600 cursor-pointer select-none">
                Keep me signed in for 30 days
              </Label>
            </div>

            {slowWarning && (
              <div className="rounded-xl bg-blue-50 border border-blue-200 px-4 py-3 flex items-start gap-2.5">
                <svg className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-sm text-blue-800">Server is waking up &mdash; this can take up to 60 seconds on first request. Please wait...</p>
              </div>
            )}

            <Button
              type="submit"
              className="w-full h-11 bg-[#0F2B54] hover:bg-[#1a3a6b] text-white rounded-xl font-semibold transition-all duration-150 shadow-sm hover:shadow-md"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in...
                </span>
              ) : 'Sign in'}
            </Button>
          </div>
        </form>

        <div className="border-t border-slate-100 px-8 py-5">
          <p className="text-center text-sm text-slate-500">
            Don&apos;t have an account?{' '}
            <Link
              href={(() => {
                const inv = extractedInvite || searchParams.get('invite') || '';
                const rId = extractedRfqId || searchParams.get('rfq_id') || '';
                if (inv) return `/register?invite=${encodeURIComponent(inv)}&rfq_id=${encodeURIComponent(rId)}`;
                const redirect = searchParams.get('redirect') || '';
                const rfqMatch = redirect.match(/\/provider\/rfq\/([^/?]+)/);
                if (rfqMatch) {
                  try {
                    const redirectUrl = new URL(redirect, 'http://x');
                    const invFromRedirect = redirectUrl.searchParams.get('invite') || '';
                    if (invFromRedirect) return `/register?invite=${encodeURIComponent(invFromRedirect)}&rfq_id=${encodeURIComponent(rfqMatch[1])}`;
                  } catch {}
                }
                return '/register';
              })()}
              className="text-blue-600 hover:text-blue-700 font-medium transition-colors duration-150"
            >
              Create account
            </Link>
          </p>
        </div>
      </div>

      {/* Footer trust line */}
      <p className="mt-8 text-xs text-slate-400 text-center">
        Trusted by engineering firms across North America
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#0F2B54] flex items-center justify-center animate-pulse">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <div className="animate-spin rounded-full h-5 w-5 border-2 border-slate-200 border-t-[#0F2B54]"></div>
        </div>
      </div>
    }>
      <LoginPageContent />
    </Suspense>
  );
}
