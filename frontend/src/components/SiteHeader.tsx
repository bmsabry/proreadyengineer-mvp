'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Building2, LayoutDashboard, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

/** Routes that render their own header/nav — the shared header is hidden there to
 *  avoid a doubled header. Matched as exact path or as a path prefix. */
const HIDE_PREFIXES = ['/admin', '/customer', '/provider', '/providers', '/search'];
const HIDE_EXACT = [
  '/',
  '/advertise',
  '/featured-firms',
  '/help',
  '/privacy',
  '/reset-password',
  '/software-providers',
  '/terms',
  '/trust',
];

function dashboardLink(roles: string[]): string {
  if (roles.includes('admin')) return '/admin/dashboard';
  if (roles.includes('provider')) return '/provider/dashboard';
  return '/customer/dashboard';
}

/** A consistent brand header whose logo links home. Rendered globally on public
 *  pages that don't ship their own header, so every public page has a way home. */
export default function SiteHeader() {
  const pathname = usePathname() || '';
  const { user, logout } = useAuth();

  const hidden =
    HIDE_EXACT.includes(pathname) ||
    HIDE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'));
  if (hidden) return null;

  const roles = (user?.roles as string[] | undefined) || [];

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80 shadow-sm">
      <div className="max-w-7xl mx-auto px-6 flex h-16 items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5" aria-label="ProMechDirectory home">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
            <Building2 className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-lg text-slate-900 tracking-tight">ProMechDirectory</span>
        </Link>
        <nav className="flex gap-1 items-center">
          {user ? (
            <>
              <Link href={dashboardLink(roles)}>
                <Button variant="ghost" size="sm" className="flex items-center gap-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100">
                  <LayoutDashboard className="h-4 w-4" />
                  Dashboard
                </Button>
              </Link>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { void logout(); }}
                className="flex items-center gap-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
              >
                <LogOut className="h-4 w-4" />
                Sign Out
              </Button>
            </>
          ) : (
            <>
              <Link href="/contact" className="text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3 py-2 rounded-md font-medium">Contact Us</Link>
              <Link href="/login">
                <Button variant="ghost" size="sm" className="text-slate-600 hover:text-slate-900 hover:bg-slate-100">Sign In</Button>
              </Link>
              <Link href="/register">
                <Button size="sm" className="bg-primary hover:bg-primary/90 text-white rounded-lg px-5 ml-1">Get Started</Button>
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
