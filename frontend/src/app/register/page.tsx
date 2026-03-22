'use client';
import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

const ic = 'mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm';
const lc = 'block text-sm font-medium text-gray-700';

function RegisterPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [fd, setFd] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    company_name: '',
    phone: '',
    role: 'customer' as 'customer' | 'provider' | 'advertiser',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [inviteToken, setInviteToken] = useState('');
  const [inviteRfqId, setInviteRfqId] = useState('');
  const [hasInvite, setHasInvite] = useState(false);
  const { refreshUser } = useAuth();

  useEffect(() => {
    const invite = searchParams.get('invite') || '';
    const rfqId = searchParams.get('rfq_id') || '';

    // Also check localStorage as fallback (set by provider/rfq page or login page)
    const storedInvite = typeof window !== 'undefined' ? (localStorage.getItem('pendingInviteToken') || '') : '';
    const storedRfqId = typeof window !== 'undefined' ? (localStorage.getItem('pendingInviteRfqId') || '') : '';

    // FIX 4: Triple fallback - also extract invite from 'redirect' URL param
    // This handles the case where login page sends user to /register with invite embedded in redirect param
    let redirectInvite = '';
    let redirectRfqId = '';
    const redirect = searchParams.get('redirect') || '';
    if (redirect) {
      try {
        const redirectUrl = new URL(redirect, 'http://x');
        redirectInvite = redirectUrl.searchParams.get('invite') || '';
        const rfqMatch = redirect.match(/\/provider\/rfq\/([^/?]+)/);
        if (rfqMatch) redirectRfqId = rfqMatch[1];
      } catch {}
    }

    const finalInvite = invite || storedInvite || redirectInvite;
    const finalRfqId = rfqId || storedRfqId || redirectRfqId;

    if (finalInvite) {
      setInviteToken(finalInvite);
      setInviteRfqId(finalRfqId);
      setHasInvite(true);
      // Force role to provider and lock it
      setFd(prev => ({ ...prev, role: 'provider' }));
      // Ensure localStorage is set
      localStorage.setItem('pendingInviteToken', finalInvite);
      if (finalRfqId) localStorage.setItem('pendingInviteRfqId', finalRfqId);
    }
  }, [searchParams]);

  const hc = (e: React.ChangeEvent<HTMLInputElement>) =>
    setFd(p => ({ ...p, [e.target.name]: e.target.value }));

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (!hasInvite) {
      setFd(p => ({ ...p, role: e.target.value as 'customer' | 'provider' | 'advertiser' }));
    }
  };

  const hs = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (fd.password !== fd.confirmPassword) { setError('Passwords do not match'); return; }
    if (fd.password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        email: fd.email,
        password: fd.password,
        roles: [fd.role],
        // Pass invite_token in registration body for ATOMIC processing on backend
        // This ensures ProviderMembership is created in the same request as user creation
        ...(inviteToken ? { invite_token: inviteToken } : {}),
      };
      if (fd.full_name.trim()) body.full_name = fd.full_name.trim();
      if (fd.company_name.trim()) body.company_name = fd.company_name.trim();
      if (fd.phone.trim()) body.phone = fd.phone.trim();

      const regRes = await api.auth.register(body as unknown as Parameters<typeof api.auth.register>[0]);
      const regData = regRes?.data as { access_token?: string } | undefined;
      const accessToken = regData?.access_token || '';

      // Always store access token in localStorage
      if (accessToken) {
        localStorage.setItem('access_token', accessToken);
      }

      if (hasInvite && inviteToken) {
        // Redeem invite token immediately after registration
        try {
          // Use api client (has correct /api/v1 base URL)
          const redeemRes = await api.auth.redeemInvite(inviteToken);
          // NOTE: We intentionally do NOT remove pendingInviteToken here.
          // The profile page will remove it after confirming the firm is linked.
          // This ensures the profile page can redeem the token as a fallback.

          if (redeemRes?.data) {
            // FIX 3: Always redirect to /provider/dashboard after successful registration+invite.
            // The dashboard shows the amber 'Action Required' section listing pending RFQs to unlock.
            // Previously redirected to /provider/rfq/{id} which immediately bounced to /rfqs/{id}/unlock
            // (a $10 payment form with no context), confusing new users.
            await refreshUser();
            router.push(inviteRfqId ? `/provider/rfq/${inviteRfqId}` : '/provider/dashboard');
          } else {
            // Redemption failed — still navigate to dashboard as provider
            console.error('Invite redemption failed:', redeemRes.status);
            router.push(inviteRfqId ? `/provider/rfq/${inviteRfqId}` : '/provider/dashboard');
          }
        } catch (redeemErr) {
          console.error('Invite redemption error:', redeemErr);
          router.push('/provider/dashboard');
        }
      } else {
        router.push('/login?registered=1');
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
      const detail = axiosErr?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : axiosErr?.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  // Build sign-in href — pass invite params through if present
  const signInHref = hasInvite
    ? `/login?invite=${encodeURIComponent(inviteToken)}&rfq_id=${encodeURIComponent(inviteRfqId)}`
    : '/login';

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h1 className="text-center text-2xl font-bold text-blue-700">ProMechDirectory</h1>
        <h2 className="mt-4 text-center text-3xl font-extrabold text-gray-900">Create your account</h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Already have an account?{' '}
          <Link href={signInHref} className="font-medium text-blue-600 hover:text-blue-500">Sign in</Link>
        </p>
      </div>
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">

          {/* Invite banner */}
          {hasInvite && (
            <div className="mb-6 bg-blue-50 border border-blue-300 rounded-md p-4 flex items-start gap-3">
              <svg className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-sm font-semibold text-blue-900">You have been invited to bid on an engineering project</p>
                <p className="text-xs text-blue-700 mt-1">Create your provider account to proceed and view the full RFQ details.</p>
              </div>
            </div>
          )}

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded text-sm">
              {error}
            </div>
          )}

          <form onSubmit={hs} className="space-y-5">
            <div>
              <label className={lc}>I am a</label>
              {hasInvite ? (
                <>
                  <select
                    name="role"
                    value="provider"
                    disabled
                    className={`${ic} bg-gray-100 cursor-not-allowed opacity-75`}
                  >
                    <option value="provider">Provider (engineering firm)</option>
                  </select>
                  <p className="mt-1 text-xs text-blue-600">Role is locked to Provider for this invitation.</p>
                </>
              ) : (
                <select name="role" value={fd.role} onChange={handleRoleChange} className={ic}>
                  <option value="customer">Customer (seeking engineering services)</option>
                  <option value="provider">Provider (engineering firm)</option>
                  <option value="advertiser">Advertiser</option>
                </select>
              )}
            </div>
            <div>
              <label className={lc}>Full Name <span className="text-gray-400">(optional)</span></label>
              <input type="text" name="full_name" value={fd.full_name} onChange={hc} placeholder="Jane Smith" className={ic} />
            </div>
            <div>
              <label className={lc}>Company Name{fd.role === 'provider' ? '' : ' (optional)'}</label>
              <input
                type="text"
                name="company_name"
                value={fd.company_name}
                onChange={hc}
                placeholder="Acme Engineering LLC"
                className={ic}
                required={fd.role === 'provider'}
              />
            </div>
            <div>
              <label className={lc}>Phone <span className="text-gray-400">(optional)</span></label>
              <input type="tel" name="phone" value={fd.phone} onChange={hc} placeholder="+1 (555) 000-0000" className={ic} />
            </div>
            <div>
              <label className={lc}>Email address</label>
              <input type="email" name="email" value={fd.email} onChange={hc} required autoComplete="email" className={ic} />
            </div>
            <div>
              <label className={lc}>Password</label>
              <input type="password" name="password" value={fd.password} onChange={hc} required autoComplete="new-password" className={ic} />
              <p className="mt-1 text-xs text-gray-500">Minimum 8 characters</p>
            </div>
            <div>
              <label className={lc}>Confirm Password</label>
              <input type="password" name="confirmPassword" value={fd.confirmPassword} onChange={hc} required autoComplete="new-password" className={ic} />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating account...' : (hasInvite ? 'Create Account & Accept Invite' : 'Create account')}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-gray-500">
            By registering you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>}>
      <RegisterPageContent />
    </Suspense>
  );
}
