'use client';
import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

const ic = 'mt-1.5 block w-full border border-slate-200 rounded-lg bg-white py-0 px-4 h-11 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 transition-all duration-150 text-sm';
const lc = 'block text-sm font-medium text-slate-700';

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
    state: '',
    role: 'customer' as 'customer' | 'provider' | 'advertiser',
    entity_type: 'Individual' as 'Individual' | 'Company',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [inviteToken, setInviteToken] = useState('');
  const [inviteRfqId, setInviteRfqId] = useState('');
  const [hasInvite, setHasInvite] = useState(false);
  // prefillLoaded is ONLY true when firm data was successfully loaded from API
  // This prevents field locking or messages from triggering on manual user input
  const [prefillLoaded, setPrefillLoaded] = useState(false);
  const { refreshUser } = useAuth();

  useEffect(() => {
    // Resolve invite token from URL params or localStorage
    const invite = searchParams.get('invite') || '';
    const rfqId = searchParams.get('rfq_id') || '';
    const storedInvite = typeof window !== 'undefined' ? (localStorage.getItem('pendingInviteToken') || '') : '';
    const storedRfqId = typeof window !== 'undefined' ? (localStorage.getItem('pendingInviteRfqId') || '') : '';

    // Extract invite from redirect param as last fallback
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

    if (!finalInvite) return;

    // Set invite mode — show banner and lock role to provider
    setInviteToken(finalInvite);
    setInviteRfqId(finalRfqId);
    setHasInvite(true);
    localStorage.setItem('pendingInviteToken', finalInvite);
    if (finalRfqId) localStorage.setItem('pendingInviteRfqId', finalRfqId);

    // Helper to apply firm data to form and mark prefill as loaded
    const applyFirmData = (firmName: string, phone: string, state: string, email: string) => {
      setFd(prev => ({
        ...prev,
        role: 'provider',
        entity_type: 'Company',
        company_name: firmName || prev.company_name,
        phone: phone || prev.phone,
        state: state || prev.state,
        email: email || prev.email,
      }));
      if (firmName || phone || state || email) {
        setPrefillLoaded(true);
      }
    };

    // STEP 1: Read URL params passed by useRequireAuth (synchronous, immediate)
    // useRequireAuth decodes JWT client-side and passes data as URL params before navigating here
    const urlFirmName = searchParams.get('firm_name') || '';
    const urlPhone    = searchParams.get('phone')     || '';
    const urlState    = searchParams.get('state')     || '';
    const urlEmail    = searchParams.get('email')     || '';
    if (urlFirmName || urlPhone || urlState || urlEmail) {
      applyFirmData(urlFirmName, urlPhone, urlState, urlEmail);
      return; // Done — data already applied synchronously
    }

    // STEP 2: Decode JWT client-side directly (synchronous, no API needed)
    // Works for all new tokens that have embedded firm data
    try {
      const parts = finalInvite.split('.');
      if (parts.length === 3) {
        const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
        const payload = JSON.parse(atob(padded));
        const jwtFirmName = (payload.firm_name as string) || '';
        const jwtPhone = (payload.phone as string) || '';
        const jwtState = (payload.state as string) || '';
        const jwtEmail = (payload.sent_to_email as string) || '';
        if (jwtFirmName || jwtPhone || jwtState || jwtEmail) {
          applyFirmData(jwtFirmName, jwtPhone, jwtState, jwtEmail);
          return; // Done — data applied from JWT payload
        }
      }
    } catch {}

    // STEP 3: API call fallback for older tokens without embedded data
    // (tokens issued before the embed-firm-data-in-JWT fix)
    setFd(prev => ({ ...prev, role: 'provider', entity_type: 'Company' }));
    api.auth.checkInvite(finalInvite)
      .then(res => {
        const data = res.data;
        applyFirmData(data.firm_name || '', data.phone || '', data.state || '', data.email || '');
      })
      .catch(() => {
        // Silent fail — form stays fully editable with no locking
      });
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
    if (!fd.full_name.trim()) { setError('Name is required'); return; }
    setLoading(true);
    try {
      const fullNameTrimmed = fd.full_name.trim();
      const nameParts = fullNameTrimmed.split(' ').filter(p => p.length > 0);
      const firstName = nameParts.length > 0 ? nameParts[0] : '';
      const lastName = nameParts.length > 1 ? nameParts.slice(1).join(' ') : '';

      const body: Record<string, unknown> = {
        email: fd.email,
        password: fd.password,
        roles: [fd.role],
        entity_type: fd.entity_type,
        ...(inviteToken ? { invite_token: inviteToken } : {}),
      };
      if (fullNameTrimmed) {
        body.full_name = fullNameTrimmed;
        if (firstName) body.first_name = firstName;
        if (lastName) body.last_name = lastName;
      }
      if (fd.company_name.trim()) body.company_name = fd.company_name.trim();
      if (fd.phone.trim()) body.phone = fd.phone.trim();

      const regRes = await api.auth.register(body as unknown as Parameters<typeof api.auth.register>[0]);
      const regData = regRes?.data as { access_token?: string } | undefined;
      const accessToken = regData?.access_token || '';

      if (accessToken) {
        localStorage.setItem('access_token', accessToken);
      }

      if (hasInvite && inviteToken) {
        try {
          const redeemRes = await api.auth.redeemInvite(inviteToken);
          if (redeemRes?.data) {
            await refreshUser();
            router.push(inviteRfqId ? `/provider/rfq/${inviteRfqId}` : '/provider/dashboard');
          } else {
            router.push(inviteRfqId ? `/provider/rfq/${inviteRfqId}` : '/provider/dashboard');
          }
        } catch {
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

  const signInHref = hasInvite
    ? `/login?invite=${encodeURIComponent(inviteToken)}&rfq_id=${encodeURIComponent(inviteRfqId)}`
    : '/login';

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

      {/* Main card */}
      <div className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-8 pt-8 pb-6">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Create your account</h1>
          {/* Only show firm representative message when data was ACTUALLY loaded from API (not on manual input) */}
          {prefillLoaded && fd.company_name && (
            <div className="mt-4 p-3 rounded-lg border border-blue-200 bg-blue-50 text-sm text-blue-800">
              <span className="font-semibold">You are registering as a representative of {fd.company_name}.</span>
              {' '}Your firm details have been pre-filled. Please verify and complete your personal details.
            </div>
          )}
          <p className="text-sm text-slate-500 mt-1.5">
            Already have an account?{' '}
            <Link href={signInHref} className="text-blue-600 hover:text-blue-700 font-medium transition-colors duration-150">Sign in</Link>
          </p>
        </div>

        <form onSubmit={hs}>
          <div className="px-8 pb-8 space-y-5">

            {/* Invite banner */}
            {hasInvite && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3.5 flex items-start gap-3">
                <svg className="w-5 h-5 text-blue-600 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p className="text-sm font-semibold text-blue-900">You have been invited to bid on an engineering project</p>
                  <p className="text-xs text-blue-700 mt-1">Create your provider account to proceed and view the full RFQ details.</p>
                </div>
              </div>
            )}

            {/* Error banner */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm flex items-start gap-2">
                <svg className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{error}</span>
              </div>
            )}

            {/* Role selector — hidden for invited providers */}
            {!hasInvite && (
              <div className="space-y-1.5">
                <label className={lc}>I am a</label>
                <select
                  name="role"
                  value={fd.role}
                  onChange={handleRoleChange}
                  className="mt-1.5 block w-full border border-slate-200 rounded-lg bg-white py-0 px-4 h-11 text-slate-900 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 transition-all duration-150"
                >
                  <option value="customer">Customer (seeking engineering services)</option>
                  <option value="provider">Provider (engineering firm)</option>
                  <option value="advertiser">Advertiser</option>
                </select>
              </div>
            )}

            {/* Entity Type — hidden for invited providers */}
            {!hasInvite && (
              <div className="space-y-1.5">
                <label className={lc}>Account type</label>
                <div className="flex gap-4 mt-1.5">
                  {(['Individual', 'Company'] as const).map(type => (
                    <label key={type} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="entity_type"
                        value={type}
                        checked={fd.entity_type === type}
                        onChange={hc}
                        className="h-4 w-4 text-blue-600 border-slate-300 focus:ring-blue-500"
                      />
                      <span className="text-sm text-slate-700">{type}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Two-column: Full Name + Phone */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className={lc}>
                  {fd.entity_type === 'Company' ? 'Full Name or Firm Name' : 'Full Name'}
                  <span className="text-red-500 ml-1">*</span>
                </label>
                <input
                  type="text"
                  name="full_name"
                  value={fd.full_name}
                  onChange={hc}
                  placeholder={fd.entity_type === 'Company' ? 'Acme Engineering LLC' : 'Jane Smith'}
                  className={ic}
                  required
                />
                <p className="text-xs text-slate-400 mt-1">
                  {fd.entity_type === 'Company' ? 'Enter your firm name' : 'Enter your full name'}
                </p>
              </div>
              <div className="space-y-1.5">
                <label className={lc}>Phone <span className="text-slate-400 font-normal text-xs">(optional)</span></label>
                <input type="tel" name="phone" value={fd.phone} onChange={hc} placeholder="+1 (555) 000-0000" className={ic} />
              </div>
            </div>

            {/* Company Name — readOnly ONLY when prefill was successfully loaded from API */}
            <div className="space-y-1.5">
              <label className={lc}>
                Company Name{fd.role !== 'provider' && <span className="text-slate-400 font-normal text-xs"> (optional)</span>}
                {prefillLoaded && fd.company_name && <span className="ml-2 text-xs text-blue-600 font-normal">(pre-filled)</span>}
              </label>
              <input
                type="text"
                name="company_name"
                readOnly={prefillLoaded && !!fd.company_name}
                value={fd.company_name}
                onChange={hc}
                placeholder="Your company name"
                className={prefillLoaded && fd.company_name ? ic + ' bg-slate-50 cursor-default' : ic}
                required={fd.role === 'provider'}
              />
            </div>

            {/* State */}
            <div className="space-y-1.5">
              <label className={lc}>State</label>
              <input
                type="text"
                name="state"
                placeholder="e.g. Ohio, Texas, California"
                value={fd.state}
                onChange={hc}
                className={ic}
              />
            </div>

            {/* Email */}
            <div className="space-y-1.5">
              <label className={lc}>Email address</label>
              <input
                type="email"
                name="email"
                value={fd.email}
                onChange={hc}
                required
                autoComplete="email"
                placeholder="name@company.com"
                className={ic}
              />
            </div>

            {/* Passwords */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className={lc}>Password</label>
                <input type="password" name="password" value={fd.password} onChange={hc} required autoComplete="new-password" placeholder="Min. 8 characters" className={ic} />
              </div>
              <div className="space-y-1.5">
                <label className={lc}>Confirm Password</label>
                <input type="password" name="confirmPassword" value={fd.confirmPassword} onChange={hc} required autoComplete="new-password" placeholder="Repeat password" className={ic} />
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 h-11 px-4 rounded-xl bg-[#0F2B54] hover:bg-[#1a3a6b] text-white text-sm font-semibold transition-all duration-150 shadow-sm hover:shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating account...
                </>
              ) : (
                hasInvite ? 'Create Account & Accept Invite' : 'Create account'
              )}
            </button>

          </div>
        </form>

        <div className="border-t border-slate-100 px-8 py-4">
          <p className="text-center text-xs text-slate-400">
            By registering you agree to our{' '}
            <Link href="/terms" className="text-blue-600 hover:text-blue-700 transition-colors duration-150">Terms of Service</Link>
            {' '}and{' '}
            <Link href="/privacy" className="text-blue-600 hover:text-blue-700 transition-colors duration-150">Privacy Policy</Link>.
          </p>
        </div>
      </div>

      <p className="mt-8 text-xs text-slate-400 text-center">Trusted by engineering firms across North America</p>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#0F2B54] flex items-center justify-center animate-pulse"></div>
          <div className="animate-spin rounded-full h-5 w-5 border-2 border-slate-200 border-t-[#0F2B54]"></div>
        </div>
      </div>
    }>
      <RegisterPageContent />
    </Suspense>
  );
}
