'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

type Role = 'customer' | 'provider' | 'advertiser' | 'admin';

export function useRequireAuth(requiredRoles?: Role[]) {
  const { user, isLoading, isAuthenticated, hasRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const currentPath = typeof window !== 'undefined'
        ? window.location.pathname + window.location.search
        : '';
      router.push('/login?redirect=' + encodeURIComponent(currentPath));
      return;
    }

    if (!isLoading && requiredRoles && !requiredRoles.some(role => hasRole(role))) {
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
