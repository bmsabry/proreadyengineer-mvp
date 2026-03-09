'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, FileText, Building2, DollarSign, Megaphone, Users, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const navItems = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/rfqs', label: 'RFQs', icon: FileText },
  { href: '/admin/claims', label: 'Claims', icon: Building2 },
  { href: '/admin/payments', label: 'Payments', icon: DollarSign },
  { href: '/admin/ads', label: 'Ads', icon: Megaphone },
  { href: '/admin/users', label: 'Users', icon: Users },
];

export function DashboardNav() {
  const pathname = usePathname();

  return (
    <div className="w-64 border-r bg-background min-h-screen">
      <div className="p-6">
        <Link href="/admin/dashboard" className="flex items-center gap-2 font-bold text-xl">
          <Settings className="h-6 w-6" />
          <span>Admin Portal</span>
        </Link>
      </div>
      <nav className="px-4 space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          
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
      <div className="absolute bottom-4 left-4 right-4">
        <Link href="/">
          <Button variant="outline" className="w-full">
            Back to Site
          </Button>
        </Link>
      </div>
    </div>
  );
}
