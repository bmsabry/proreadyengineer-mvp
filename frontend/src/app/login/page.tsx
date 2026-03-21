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
      const msg = error?.response?.data?.detail || error?.message || 'Invalid email or password';
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/50">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Sign in</CardTitle>
          <CardDescription>
            Enter your email and password to access your account
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>
            <div className="flex items-center space-x-2">
              <input
                id="rememberMe"
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={isSubmitting}
                className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
              />
              <Label htmlFor="rememberMe" className="text-sm font-normal cursor-pointer select-none">
                Keep me signed in for 30 days
              </Label>
            </div>
            {slowWarning && (
              <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded p-2">
                ⏳ Server is waking up (free tier) — this can take up to 60 seconds on first request. Please wait...
              </p>
            )}
          </CardContent>
          <CardFooter className="flex flex-col space-y-4">
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? 'Signing in...' : 'Sign in'}
            </Button>
            <div className="flex justify-between w-full text-sm">
              <Link href="/forgot-password" className="text-primary hover:underline">
                Forgot password?
              </Link>
              <Link
                href={(() => {
                  // Use state-stored extracted values (works even when invite is embedded inside redirect param)
                  const inv = extractedInvite || searchParams.get('invite') || '';
                  const rId = extractedRfqId || searchParams.get('rfq_id') || '';
                  if (inv) return `/register?invite=${encodeURIComponent(inv)}&rfq_id=${encodeURIComponent(rId)}`;
                  // Also try to extract from redirect path as last resort
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
                className="text-primary hover:underline"
              >
                Create account
              </Link>
            </div>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>}>
      <LoginPageContent />
    </Suspense>
  );
}
