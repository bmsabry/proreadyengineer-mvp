'use client';

import { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

function CheckEmailContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get('email') || '';
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState('');

  const handleResend = async () => {
    if (!email || resending) return;
    setResending(true);
    setResendMsg('');
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
      const res = await fetch(`${apiBase}/api/v1/auth/resend-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (res.ok) {
        setResendMsg('A new verification link has been sent to your email.');
      } else {
        setResendMsg('Unable to resend. Please try again in a minute.');
      }
    } catch {
      setResendMsg('Unable to resend. Please try again later.');
    } finally {
      setResending(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
        {/* Brand */}
        <Link href="/" className="inline-flex items-center gap-2.5 mb-6 group">
          <div className="w-10 h-10 rounded-xl bg-[#0F2B54] flex items-center justify-center shadow-md">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <span className="font-bold text-xl text-[#0F2B54] tracking-tight">ProMechDirectory</span>
        </Link>

        {/* Email icon */}
        <div className="flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mx-auto mb-5">
          <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>

        <h1 className="text-2xl font-bold text-slate-900 mb-2">Check your email</h1>
        <p className="text-slate-600 mb-1">
          We sent a verification link to
        </p>
        {email && (
          <p className="font-semibold text-slate-900 mb-4">{email}</p>
        )}
        <p className="text-sm text-slate-500 mb-6">
          Click the link in the email to verify your account. The link expires in 24 hours.
        </p>

        {/* Resend */}
        {email && (
          <div className="mb-6">
            <button
              onClick={handleResend}
              disabled={resending}
              className="text-sm text-blue-600 hover:text-blue-700 font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {resending ? 'Sending...' : "Didn't receive the email? Resend verification link"}
            </button>
            {resendMsg && (
              <p className="mt-2 text-sm text-green-600">{resendMsg}</p>
            )}
          </div>
        )}

        <div className="space-y-3">
          <Link
            href="/login"
            className="block w-full bg-[#0F2B54] hover:bg-[#1a3a6b] text-white text-sm font-semibold py-3 px-4 rounded-xl transition-all duration-150 shadow-sm hover:shadow-md"
          >
            Go to Login
          </Link>
          <p className="text-xs text-slate-400">
            Already verified?{' '}
            <Link href="/login" className="text-blue-600 hover:text-blue-700">Sign in</Link>
          </p>
        </div>
      </div>
    </main>
  );
}

export default function CheckEmailPage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-sm p-8 text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-slate-200 border-t-[#0F2B54] mx-auto" />
        </div>
      </main>
    }>
      <CheckEmailContent />
    </Suspense>
  );
}
