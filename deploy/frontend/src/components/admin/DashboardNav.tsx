'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, FileText, Building2, DollarSign, Megaphone, Users, Settings, LogOut, Home } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

const navItems = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/rfqs', label: 'RFQs', icon: FileText },
  { href: '/admin/claims', label: 'Claims', icon: Building2 },
  { href: '/admin/payments', label: 'Payments', icon: DollarSign },
  { href: '/admin/ads', label: 'Ads', icon: Megaphone },
  { href: '/admin/users', label: 'Users', icon: Users },
  { href: '/admin/settings', label: 'Settings', icon: Settings },
];

export function DashboardNav() {
  const pathname = usePathname();
  const { logout, user } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }
  };

  return (
    <div className="w-64 border-r bg-background min-h-screen flex flex-col">
      {/* Header */}
      <div className="p-6 border-b">
        <Link href="/admin/dashboard" className="flex items-center gap-2 font-bold text-xl">
          <Settings className="h-6 w-6" />
          <span>Admin Portal</span>
        </Link>
        {user?.email && (
          <p className="text-xs text-muted-foreground mt-1 truncate">{user.email}</p>
        )}
      </div>

      {/* Nav Items */}
      <nav className="px-4 py-4 space-y-1 flex-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');

          return (
            <Link key={item.href} href={item.href}>
              <Button
                variant={isActive ? 'secondary' : 'ghost'}
                className={cn(
                  'w-full justify-start gap-2',
                  isActive && 'bg-secondary'
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Button>
            </Link>
          );
        })}
      </nav>

      {/* Footer Actions */}
      <div className="p-4 border-t space-y-2">
        <Link href="/">
          <Button variant="outline" className="w-full justify-start gap-2">
            <Home className="h-4 w-4" />
            Back to Site
          </Button>
        </Link>
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 text-red-600 hover:text-red-700 hover:bg-red-50"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </Button>
      </div>
    </div>
  );
}
