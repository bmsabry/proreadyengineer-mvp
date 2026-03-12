'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { User, AuthResponse } from '@/types';
import { api, setLoggingOut } from '@/lib/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (email: string, password: string, roles?: ('customer' | 'provider' | 'advertiser')[]) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasRole: (role: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const LOGOUT_FLAG_KEY = 'pre_logged_out';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const isLoggingOutRef = useRef(false);

  const refreshUser = useCallback(async () => {
    try {
      const response = await api.auth.me();
      setUser(response.data);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const initAuth = async () => {
      // If we just logged out, skip auth check entirely
      if (typeof window !== 'undefined' && localStorage.getItem(LOGOUT_FLAG_KEY)) {
        localStorage.removeItem(LOGOUT_FLAG_KEY);
        setUser(null);
        setIsLoading(false);
        return;
      }

      try {
        const response = await api.auth.me();
        setUser(response.data);
      } catch {
        try {
          await api.auth.refresh();
          const response = await api.auth.me();
          setUser(response.data);
        } catch {
          setUser(null);
        }
      } finally {
        setIsLoading(false);
      }
    };
    initAuth();
  }, []);

  const login = async (email: string, password: string, rememberMe: boolean = false) => {
    setIsLoading(true);
    // Clear logout flag on login
    if (typeof window !== 'undefined') {
      localStorage.removeItem(LOGOUT_FLAG_KEY);
    }
    try {
      const response = await api.auth.login({ email, password, remember_me: rememberMe });
      setUser(response.data.user);
      router.push(getDashboardPath(response.data.user.roles));
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (
    email: string,
    password: string,
    roles: ('customer' | 'provider' | 'advertiser')[] = ['customer']
  ) => {
    setIsLoading(true);
    if (typeof window !== 'undefined') {
      localStorage.removeItem(LOGOUT_FLAG_KEY);
    }
    try {
      const response = await api.auth.register({ email, password, roles });
      setUser(response.data.user);
      router.push(getDashboardPath(response.data.user.roles));
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    isLoggingOutRef.current = true;
    setLoggingOut(true); // prevent interceptor from auto-refreshing
    // Set logout flag BEFORE any async operations
    if (typeof window !== 'undefined') {
      localStorage.setItem(LOGOUT_FLAG_KEY, '1');
    }
    // Clear user state immediately
    setUser(null);
    try {
      await api.auth.logout();
    } catch {
      // Ignore errors - client-side logout already done
    } finally {
      isLoggingOutRef.current = false;
      setLoggingOut(false);
      setIsLoading(false);
      // Hard redirect to home page
      if (typeof window !== 'undefined') {
        window.location.replace('/');
      } else {
        router.push('/');
      }
    }
  };

  const logoutAll = async () => {
    isLoggingOutRef.current = true;
    if (typeof window !== 'undefined') {
      localStorage.setItem(LOGOUT_FLAG_KEY, '1');
    }
    setUser(null);
    try {
      await api.auth.logoutAll();
    } catch {
      // ignore
    } finally {
      isLoggingOutRef.current = false;
      if (typeof window !== 'undefined') {
        window.location.replace('/');
      } else {
        router.push('/');
      }
    }
  };

  const hasRole = (role: string): boolean => {
    return user?.roles.includes(role as any) || false;
  };

  const getDashboardPath = (roles: string[]): string => {
    if (roles.includes('admin')) return '/admin/dashboard';
    if (roles.includes('provider')) return '/provider/dashboard';
    if (roles.includes('customer')) return '/customer/dashboard';
    if (roles.includes('advertiser')) return '/customer/dashboard';
    return '/';
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        logoutAll,
        refreshUser,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
