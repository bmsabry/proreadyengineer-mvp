'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  LayoutDashboard, FileText, CheckCircle, Clock,
  MessageSquare, Archive, User, LogOut, Home
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import ContactSupport from '@/components/ContactSupport';

const navItems = [
  { href: '/',                        label: 'Main Page',     icon: Home,            tooltip: 'Return to the ProMechDirectory landing page' },
  { href: '/provider/dashboard',      label: 'Dashboard',     icon: LayoutDashboard, tooltip: 'Account overview, analytics, tasks, and activity' },
  { href: '/provider/active-rfqs',    label: 'Active RFQs',   icon: FileText,        tooltip: 'Unlocked RFQs open for your quote submission' },
  { href: '/provider/accepted-rfqs',  label: 'Accepted RFQs', icon: CheckCircle,     tooltip: 'RFQs where the customer selected your firm' },
  { href: '/provider/pending-rfqs',   label: 'Pending RFQs',  icon: Clock,           tooltip: 'RFQ invitations awaiting your unlock decision' },
  { href: '/provider/quoted-rfqs',    label: 'Quoted RFQs',   icon: MessageSquare,   tooltip: 'RFQs where you have already submitted a quote' },
  { href: '/provider/all-rfqs',       label: 'All RFQs',      icon: Archive,         tooltip: 'Full history of all RFQs you have accessed' },
  { href: '/provider/profile',        label: 'Profile',       icon: User,            tooltip: 'Firm profile, subscription plan, and account settings' },
];

export default function ProviderLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useAuth();
  const handleSignOut = async () => {
    try { await logout(); } catch { /* ignore */ }
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-primary text-white shadow-lg sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-14 overflow-x-auto scrollbar-hide">
            <div className="flex items-center gap-1 flex-nowrap">
              <ContactSupport variant="dark" />
              <div className="w-px h-5 bg-blue-500 mx-1 flex-shrink-0" />
              {navItems.map(({ href, label, icon: Icon, tooltip }) => {
                const isActive = href === '/'
                  ? pathname === '/'
                  : pathname === href || pathname.startsWith(href + '/');
                return (
                  <Link
                    key={href}
                    href={href}
                    title={tooltip}
                    className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors duration-150 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-blue-100 hover:bg-primary/90 hover:text-white'
                    }`}
                  >
                    <Icon size={14} />
                    <span>{label}</span>
                  </Link>
                );
              })}
              <div className="w-px h-5 bg-blue-500 mx-1 flex-shrink-0" />
              <button
                onClick={handleSignOut}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium whitespace-nowrap text-blue-100 hover:bg-red-700 hover:text-white transition-colors duration-150"
              >
                <LogOut size={14} />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

    </div>
  );
}
