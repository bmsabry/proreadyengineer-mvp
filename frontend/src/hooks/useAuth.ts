'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';

type Role = 'customer' | 'provider' | 'advertiser' | 'admin';

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

export function useRequireAuth(requiredRoles?: Role[]) {
  const { user, isLoading, isAuthenticated, hasRole } = useAuth();
  const router = useRouter();
  const checkDone = useRef(false);

  useEffect(() => {
    if (isLoading) return;

    if (!isAuthenticated) {
      if (checkDone.current) return;
      checkDone.current = true;

      const search = typeof window !== 'undefined' ? window.location.search : '';
      const params = new URLSearchParams(search);
      const inviteToken = params.get('invite') || '';
      const mode = params.get('mode'); // 'login' | 'register' | null (old links)
      const currentPath = typeof window !== 'undefined'
        ? window.location.pathname + window.location.search
        : '';

      if (inviteToken) {
        const jwt = decodeJwtPayload(inviteToken) || {};
        const rfqMatch = currentPath.match(/\/provider\/rfq\/([^/?]+)/);
        const rfqId = rfqMatch ? rfqMatch[1] : '';

        const buildRegisterUrl = (firmName: string, phone: string, city: string, state: string, email: string) => {
          const q = new URLSearchParams();
          q.set('invite', inviteToken);
          if (rfqId)    q.set('rfq_id',    rfqId);
          if (firmName) q.set('firm_name', firmName);
          if (phone)    q.set('phone',     phone);
          if (state)    q.set('state',     state);
          if (city)     q.set('city',      city);
          if (email)    q.set('email',     email);
          return `/register?${q.toString()}`;
        };

        console.log('[INVITE-DIAG] inviteToken present:', !!inviteToken);
        console.log('[INVITE-DIAG] mode from URL:', mode);
        console.log('[INVITE-DIAG] jwt payload:', JSON.stringify(jwt));

        if (mode === 'login') {
          // New invite link — provider HAS an existing account
          console.log('[INVITE-DIAG] mode=login → routing to LOGIN page');
          router.push(`/login?invite=${encodeURIComponent(inviteToken)}&redirect=${encodeURIComponent(currentPath)}`);
          return;
        }

        if (mode === 'register') {
          // New invite link — provider has NO account, prefill from JWT
          console.log('[INVITE-DIAG] mode=register → routing to REGISTER page with prefill');
          router.push(buildRegisterUrl(
            jwt.firm_name as string || '',
            jwt.phone as string || '',
            jwt.city as string || '',
            jwt.state as string || '',
            jwt.sent_to_email as string || '',
          ));
          return;
        }

        // No mode param (old invite links) — LIVE check against Users table
        console.log('[INVITE-DIAG] no mode param → calling live invite-check API');
        api.auth.checkInvite(inviteToken)
          .then(res => {
            const data = res.data;
            console.log('[INVITE-DIAG] live check result: has_account=', data?.has_account, 'firm_name=', data?.firm_name);
            const firmName = data?.firm_name || jwt.firm_name as string || '';
            const phone    = data?.phone     || jwt.phone     as string || '';
            const city     = data?.city      || jwt.city      as string || '';
            const state    = data?.state     || jwt.state     as string || '';
            const email    = data?.email     || jwt.sent_to_email as string || '';
            if (data?.has_account) {
              console.log('[INVITE-DIAG] live check: has_account=true → routing to LOGIN');
              router.push(`/login?invite=${encodeURIComponent(inviteToken)}&redirect=${encodeURIComponent(currentPath)}`);
            } else {
              console.log('[INVITE-DIAG] live check: has_account=false → routing to REGISTER');
              router.push(buildRegisterUrl(firmName, phone, city, state, email));
            }
          })
          .catch((err) => {
            // API failed — always route to login (safe fallback)
            console.log('[INVITE-DIAG] live check API FAILED:', err?.message || err, '→ routing to LOGIN (safe fallback)');
            router.push(`/login?invite=${encodeURIComponent(inviteToken)}&redirect=${encodeURIComponent(currentPath)}`);
          });
        return;
      }

      // No invite token — plain login redirect
      router.push('/login?redirect=' + encodeURIComponent(currentPath));
      return;
    }

    if (requiredRoles && !requiredRoles.some(role => hasRole(role))) {
      router.push('/');
    }
  }, [isLoading, isAuthenticated, requiredRoles, hasRole, router]);

  return { user, isLoading };
}

export function useRedirectIfAuthenticated() {
  const { isAuthenticated, isLoading, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated && user) {
      if (user.roles.includes('admin')) {
        router.push('/admin/dashboard');
      } else if (user.roles.includes('provider')) {
        router.push('/provider/dashboard');
      } else {
        router.push('/customer/dashboard');
      }
    }
  }, [isAuthenticated, isLoading, user, router]);
}
