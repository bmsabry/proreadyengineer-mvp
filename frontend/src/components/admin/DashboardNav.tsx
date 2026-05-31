'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  LayoutDashboard, FileText, Building2, Factory, DollarSign,
  Megaphone, Users, Settings, LogOut, Home, Activity, Download,
  Webhook, Mail, LifeBuoy, Wallet, Gauge,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000') + '/api/v1';

function getAuthHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const navItems = [
  { href: '/admin/dashboard',       label: 'Dashboard',        icon: LayoutDashboard },
  { href: '/admin/rfqs',            label: 'RFQs',             icon: FileText },
  { href: '/admin/claims',          label: 'Claims',           icon: Building2 },
  { href: '/admin/providers',       label: 'Providers',        icon: Factory },
  { href: '/admin/payments',        label: 'Payments',         icon: DollarSign },
  { href: '/admin/operating-cost',  label: 'Operating Cost',   icon: Wallet },
  { href: '/admin/bandwidth',       label: 'Bandwidth',        icon: Gauge },
  { href: '/admin/webhooks',        label: 'Webhooks',         icon: Webhook },
  { href: '/admin/campaigns',       label: 'Email Campaigns',  icon: Mail },
  { href: '/admin/support',         label: 'Support Tickets',  icon: LifeBuoy,  badgeKey: 'tickets' },
  { href: '/admin/ads',             label: 'Ads',              icon: Megaphone, badgeKey: 'ads' },
  { href: '/admin/users',           label: 'Users',            icon: Users },
  { href: '/admin/data-extraction', label: 'Data Extraction',  icon: Download },
  { href: '/admin/settings',        label: 'Settings',         icon: Settings },
  { href: '/admin/debugging',       label: 'Debugging',        icon: Activity, badgeKey: 'emailFailures', redWhenPending: true },
];

export function DashboardNav() {
  const pathname = usePathname();
  const { logout, user } = useAuth();

  const [pendingAds, setPendingAds] = useState(0);
  const [pendingTickets, setPendingTickets] = useState(0);
  const [pendingEmailFailures, setPendingEmailFailures] = useState(0);

  useEffect(() => {
    if (!user) return;

    const fetchCounts = async () => {
      try {
        const [adsRes, ticketsRes, failuresRes] = await Promise.all([
          fetch(`${API_BASE}/admin/ads/pending`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/admin/support/tickets?status_filter=new&size=1`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/admin/email-failures/unresolved-count`, { headers: getAuthHeaders() }),
        ]);

        if (adsRes.ok) {
          const ads = await adsRes.json();
          setPendingAds(Array.isArray(ads) ? ads.length : 0);
        }
        if (ticketsRes.ok) {
          const tickets = await ticketsRes.json();
          // SupportTicketListOut has { total, items, page, size }
          setPendingTickets(tickets?.total ?? 0);
        }
        if (failuresRes.ok) {
          const f = await failuresRes.json();
          setPendingEmailFailures(typeof f?.count === 'number' ? f.count : 0);
        }
      } catch {
        // Silent — nav badge is best-effort
      }
    };

    fetchCounts();
    // Refresh every 60 seconds so the badge stays current
    const interval = setInterval(fetchCounts, 60_000);
    return () => clearInterval(interval);
  }, [user]);

  const badgeCounts: Record<string, number> = {
    ads: pendingAds,
    tickets: pendingTickets,
    emailFailures: pendingEmailFailures,
  };

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
    <div className="w-64 min-h-screen flex flex-col" style={{ background: 'linear-gradient(180deg, #0F2B54 0%, #1a3a6b 100%)' }}>
      {/* Logo / Brand Header */}
      <div className="px-6 py-6 border-b border-white/10">
        <Link href="/admin/dashboard" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center group-hover:bg-white/25 transition-all duration-150">
            <Settings className="h-4 w-4 text-white" />
          </div>
          <div>
            <p className="font-bold text-white text-sm tracking-tight">Admin Portal</p>
            <p className="text-white/50 text-xs">ProMechDirectory</p>
          </div>
        </Link>
        {user?.email && (
          <div className="mt-4 px-3 py-2 rounded-lg bg-white/10">
            <p className="text-xs text-white/60 truncate">{user.email}</p>
          </div>
        )}
      </div>

      {/* Navigation Items */}
      <nav className="px-3 py-4 flex-1 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          const pendingCount = item.badgeKey ? badgeCounts[item.badgeKey] ?? 0 : 0;
          const hasPending = pendingCount > 0;
          // 'Urgent' items (e.g. Debugging when email failures unresolved)
          // turn the whole row red so the admin can't miss it from across the page.
          const urgent = (item as { redWhenPending?: boolean }).redWhenPending && hasPending;

          return (
            <Link key={item.href} href={item.href}>
              <div className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 cursor-pointer',
                urgent
                  ? 'bg-red-600 text-white shadow-sm hover:bg-red-500 ring-1 ring-red-300/60'
                  : isActive
                    ? 'bg-white/20 text-white shadow-sm'
                    : 'text-white/65 hover:bg-white/10 hover:text-white'
              )}>
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="flex-1">{item.label}</span>

                {/* Pending alert badge — red dot with count */}
                {hasPending && (
                  <span className="flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-red-500 text-white text-[10px] font-bold flex-shrink-0">
                    {pendingCount > 99 ? '99+' : pendingCount}
                  </span>
                )}

                {/* Active indicator dot — only shown when active and no pending badge */}
                {isActive && !hasPending && (
                  <div className="w-1.5 h-1.5 rounded-full bg-blue-300 flex-shrink-0" />
                )}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Footer Actions */}
      <div className="px-3 py-4 border-t border-white/10 space-y-1">
        <Link href="/">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-white/65 hover:bg-white/10 hover:text-white transition-all duration-150 cursor-pointer">
            <Home className="h-4 w-4 flex-shrink-0" />
            Back to Site
          </div>
        </Link>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-rose-300 hover:bg-rose-500/20 hover:text-rose-200 transition-all duration-150"
        >
          <LogOut className="h-4 w-4 flex-shrink-0" />
          Sign Out
        </button>
      </div>
    </div>
  );
}
