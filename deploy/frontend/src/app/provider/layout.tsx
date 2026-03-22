'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Building2, LayoutDashboard, Search, UserCircle, Home, LogOut } from 'lucide-react';

export default function ProviderLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { logout } = useAuth();
  const router = useRouter();
  const [hasFirm, setHasFirm] = useState(false);

  useEffect(() => {
    api.providers.getMemberships()
      .then((res: any) => {
        const data = res.data ?? res;
        setHasFirm(Array.isArray(data) && data.length > 0);
      })
      .catch(() => setHasFirm(false));
  }, []);

  const handleLogout = async () => {
    await logout();
    router.push('/');
  };

  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center gap-2">
          <Link href="/provider/dashboard" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>Provider Portal</span>
          </Link>
          <nav className="ml-auto flex gap-2 items-center">
            <Link href="/">
              <Button variant="ghost" size="sm" className="flex items-center gap-1">
                <Home className="h-4 w-4" />
                Main Page
              </Button>
            </Link>
            <Link href="/provider/dashboard">
              <Button variant="ghost" size="sm" className="flex items-center gap-1">
                <LayoutDashboard className="h-4 w-4" />
                Dashboard
              </Button>
            </Link>
            {!hasFirm && (
              <Link href="/provider/claim">
                <Button variant="ghost" size="sm" className="flex items-center gap-1">
                  <Search className="h-4 w-4" />
                  Claim Firm
                </Button>
              </Link>
            )}
            <Link href="/provider/profile">
              <Button variant="ghost" size="sm" className="flex items-center gap-1">
                <UserCircle className="h-4 w-4" />
                Profile
              </Button>
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="flex items-center gap-1 text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </Button>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
