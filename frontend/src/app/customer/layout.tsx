'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Building2, LayoutDashboard, FileText, Home, LogOut, Activity, CheckCircle, List, XCircle, MessageSquare, UserCircle } from 'lucide-react';

const RFQ_DRAFT_KEY = 'rfq_draft';

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  const { logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [hasDraft, setHasDraft] = useState(false);
  const [draftQuery, setDraftQuery] = useState('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const check = () => {
      const saved = localStorage.getItem(RFQ_DRAFT_KEY);
      if (saved) {
        try {
          const draft = JSON.parse(saved);
          setDraftQuery(draft.query || draft.formData?.project_description || 'your project');
          setHasDraft(true);
        } catch { setHasDraft(false); }
      } else {
        setHasDraft(false);
      }
    };
    check();
    // Re-check when navigating between pages
    window.addEventListener('focus', check);
    return () => window.removeEventListener('focus', check);
  }, [pathname]);

  const handleCancelDraft = () => {
    localStorage.removeItem(RFQ_DRAFT_KEY);
    setHasDraft(false);
  };

  const handleLogout = async () => {
    await logout();
    router.push('/');
  };

  const navItems = [
    { href: '/',                          label: 'Main Page',      icon: Home,          tooltip: 'Return to the ProReadyEngineer landing page' },
    { href: '/customer/dashboard',        label: 'Dashboard',      icon: LayoutDashboard, tooltip: 'Account overview, tasks, and subscription status' },
    { href: '/customer/quotes',           label: 'Quotes',         icon: FileText,      tooltip: 'Compare quotes received from engineering firms' },
    { href: '/customer/active-rfqs',      label: 'Active RFQs',    icon: Activity,      tooltip: 'RFQs currently dispatched and open for quotes' },
    { href: '/customer/quoted-rfqs',      label: 'Quoted RFQs',    icon: MessageSquare, tooltip: 'RFQs that have at least one quote submitted' },
    { href: '/customer/accepted-rfqs',    label: 'Accepted RFQs',  icon: CheckCircle,   tooltip: 'RFQs where you have selected a winning provider' },
    { href: '/customer/all-rfqs',         label: 'All RFQs',       icon: List,          tooltip: 'Complete history of all your RFQ submissions' },
    { href: '/customer/cancelled-rfqs',   label: 'Canceled RFQs',  icon: XCircle,       tooltip: 'RFQs you have canceled' },
    { href: '/customer/profile',          label: 'Profile',        icon: UserCircle,    tooltip: 'Account settings, tier, search quota, and subscription' },
  ];

  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center gap-1 overflow-x-auto">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl shrink-0 mr-2">
            <Building2 className="h-6 w-6" />
            <span className="hidden md:inline">Customer Portal</span>
          </Link>
          <nav className="ml-auto flex gap-1 items-center shrink-0">
            {navItems.map(({ href, label, icon: Icon, tooltip }) => {
              const isActive = pathname === href;
              return (
                <Link key={href} href={href} title={tooltip}>
                  <Button
                    variant={isActive ? 'default' : 'ghost'}
                    size="sm"
                    className={`flex items-center gap-1 text-xs px-2 ${
                      isActive ? 'bg-slate-900 text-white' : ''
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span className="hidden lg:inline">{label}</span>
                  </Button>
                </Link>
              );
            })}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="flex items-center gap-1 text-xs px-2 text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">Sign Out</span>
            </Button>
          </nav>
        </div>
      </header>
      {hasDraft && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center gap-3 text-sm">
          <span className="text-amber-600 font-medium flex-shrink-0">&#128203; Unfinished RFQ:</span>
          <span className="text-amber-800 truncate flex-1">
            {draftQuery.length > 60 ? draftQuery.slice(0, 60) + '...' : draftQuery}
          </span>
          <a
            href={`/customer/rfq/new?q=${encodeURIComponent(draftQuery)}`}
            className="flex-shrink-0 px-3 py-1 bg-amber-600 text-white rounded-md text-xs font-semibold hover:bg-amber-700 transition-colors"
          >
            Continue
          </a>
          <button
            onClick={handleCancelDraft}
            className="flex-shrink-0 px-3 py-1 bg-white border border-amber-300 text-amber-700 rounded-md text-xs font-semibold hover:bg-amber-50 transition-colors"
          >
            Cancel Draft
          </button>
        </div>
      )}
      {children}
    </div>
  );
}
