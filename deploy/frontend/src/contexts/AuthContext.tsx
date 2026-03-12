'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { User, AuthResponse } from '@/types';
import { api } from '@/lib/api';

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

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
      try {
        // First try to get current user (works if access token is still valid)
        const response = await api.auth.me();
        setUser(response.data);
      } catch {
        // Access token expired or missing - try to refresh
        try {
          await api.auth.refresh();
          // Refresh succeeded - now get user data
          const response = await api.auth.me();
          setUser(response.data);
        } catch {
          // Refresh also failed - user is not authenticated
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
    try {
      const response = await api.auth.register({ email, password, roles });
      setUser(response.data.user);
      router.push(getDashboardPath(response.data.user.roles));
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await api.auth.logout();
    } catch {
      // Ignore errors - proceed with client-side logout regardless
    } finally {
      setUser(null);
      setIsLoading(false);
      // Hard redirect clears all state including incognito cookie cache
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      } else {
        router.push('/login');
      }
    }
  };

  const logoutAll = async () => {
    setIsLoading(true);
    try {
      await api.auth.logoutAll();
      setUser(null);
      router.push('/login');
    } finally {
      setIsLoading(false);
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
