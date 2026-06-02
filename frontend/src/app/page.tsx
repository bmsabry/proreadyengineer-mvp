'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useConfig } from '@/contexts/ConfigContext';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import HelpTip from '@/components/ui/HelpTip';
import { Search, Users, Building2, Megaphone, LogOut, LayoutDashboard, Cpu, ChevronRight, Info } from 'lucide-react';

function Footer() {
  const { setShowSetup, missingServices } = useConfig();
  const { hasRole } = useAuth();
  const needsConfig = hasRole('admin') && missingServices.length > 0;

  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col sm:flex-row justify-between items-center gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-800">ProMechDirectory</p>
          <p className="text-xs text-slate-500 mt-0.5">&copy; {new Date().getFullYear()} All rights reserved.</p>
        </div>
        <div className="flex flex-wrap gap-6 items-center">
          {needsConfig && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSetup(true)}
              className="text-amber-600 border-amber-300 hover:bg-amber-50"
            >
              ⚙️ Configure APIs
            </Button>
          )}
          <Link href="/about" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">About Us</Link>
          <Link href="/software-providers" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">Software Providers</Link>
          <Link href="/featured-firms" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">Featured Firms</Link>
          <Link href="/contact" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">Contact Us</Link>
          <Link href="/terms" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">Terms</Link>
          <Link href="/privacy" className="text-sm text-slate-500 hover:text-slate-900 transition-colors duration-150">Privacy</Link>
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const router = useRouter();
  const { user, logout } = useAuth();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Providers can't search for/hire other engineering firms. Send them to their dashboard.
    if (user) {
      const roles = user.roles || [];
      const isProvider = roles.includes('provider');
      const isCustomerOrAdmin = roles.includes('customer') || roles.includes('admin');
      if (isProvider && !isCustomerOrAdmin) {
        router.push('/provider/dashboard');
        return;
      }
    }
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  const handleLogout = async () => {
    await logout();
    router.push('/');
  };

  const getDashboardLink = () => {
    if (!user) return '/login';
    const roles = user.roles || [];
    if (roles.includes('admin')) return '/admin/dashboard';
    if (roles.includes('provider')) return '/provider/dashboard';
    return '/customer/dashboard';
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-lg text-slate-900 tracking-tight">ProMechDirectory</span>
          </Link>
          <nav className="flex gap-1 items-center">
            {user ? (
              <>
                <Link href={getDashboardLink()}>
                  <Button variant="ghost" size="sm" className="flex items-center gap-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors duration-150">
                    <LayoutDashboard className="h-4 w-4" />
                    Dashboard
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" onClick={handleLogout} className="flex items-center gap-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50 transition-colors duration-150">
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </Button>
              </>
            ) : (
              <>
                <Link href="/contact" className="text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 px-3 py-2 rounded-md transition-colors duration-150 font-medium">Contact Us</Link>
                <Link href="/login">
                  <Button variant="ghost" size="sm" className="text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors duration-150">
                    Sign In
                  </Button>
                </Link>
                <Link href="/register">
                  <Button size="sm" className="bg-primary hover:bg-primary/90 text-white rounded-lg px-5 ml-1 transition-colors duration-150">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="bg-gradient-to-br from-slate-50 via-white to-blue-50/40 border-b border-slate-100">
          <div className="max-w-7xl mx-auto px-6 py-24 md:py-32">
            <div className="max-w-3xl mx-auto text-center">
              <div className="inline-flex items-center gap-2 bg-blue-50 border border-blue-100 rounded-full px-4 py-1.5 mb-8">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                <span className="text-xs font-semibold text-blue-700 tracking-wide uppercase">5,000+ Verified Engineering Firms</span>
              </div>
              <h1 className="text-5xl sm:text-6xl font-bold text-slate-900 leading-tight mb-6" style={{ letterSpacing: '-0.02em' }}>
                Find the Right{' '}
                <span className="text-primary">Engineering Partner</span>
              </h1>
              <p className="text-lg text-slate-500 mb-10 max-w-2xl mx-auto leading-relaxed">
                Connect with verified engineering service providers. Submit RFQs, compare quotes,
                and get your project done right — with full NDA support.
              </p>
              <form onSubmit={handleSearch} className="flex gap-3 max-w-2xl mx-auto">
                <div className="relative flex-1">
                  <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-500 pointer-events-none" />
                  <Input
                    type="text"
                    placeholder="Describe your engineering project or challenge..."
                    className="pl-12 h-14 text-base bg-white border border-slate-200 rounded-xl shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10 transition-all duration-150"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <Button type="submit" className="h-14 px-8 bg-primary hover:bg-primary/90 text-white rounded-xl font-semibold shadow-sm transition-colors duration-150 flex-shrink-0">
                  Search
                </Button>
                <span className="flex items-center pl-1"><HelpTip id="search.query" size={18} /></span>
              </form>
              <p className="mt-4 text-sm text-slate-500">
                Or{' '}
                <Link href="/search/upload" className="text-blue-600 hover:text-blue-700 font-medium hover:underline transition-colors duration-150">
                  upload a project document
                </Link>
                {' '}to find matching providers
              </p>
            </div>
          </div>
        </section>

        {/* Navigation Cards */}
        <section className="max-w-7xl mx-auto px-6 py-16">
          <div className="text-center mb-10">
            <h2 className="text-2xl font-bold text-slate-900" style={{ letterSpacing: '-0.02em' }}>How can we help you?</h2>
            <p className="text-slate-500 mt-2 text-sm">Choose your path to get started</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">

            <Link href="/about" className="group block h-full">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full flex flex-col">
                <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-4 flex-shrink-0">
                  <Info className="h-6 w-6 text-slate-600" />
                </div>
                <h3 className="font-semibold text-slate-900 text-base mb-1.5">About Us</h3>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">How ProMechDirectory works and our founding provider offer.</p>
                <div className="flex items-center gap-1 mt-4 text-blue-600 text-sm font-medium group-hover:gap-2 transition-all duration-150">
                  Learn more <ChevronRight className="h-4 w-4" />
                </div>
              </div>
            </Link>

            <Link href="/for-customers" className="group block h-full">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full flex flex-col">
                <div className="w-12 h-12 rounded-xl bg-blue-50 flex items-center justify-center mb-4 flex-shrink-0">
                  <Users className="h-6 w-6 text-blue-600" />
                </div>
                <h3 className="font-semibold text-slate-900 text-base mb-1.5">For Customers</h3>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">Find and compare engineering service providers for your project needs.</p>
                <div className="flex items-center gap-1 mt-4 text-blue-600 text-sm font-medium group-hover:gap-2 transition-all duration-150">
                  Learn more <ChevronRight className="h-4 w-4" />
                </div>
              </div>
            </Link>

            <Link href="/for-providers" className="group block h-full">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full flex flex-col">
                <div className="w-12 h-12 rounded-xl bg-green-50 flex items-center justify-center mb-4 flex-shrink-0">
                  <Building2 className="h-6 w-6 text-green-600" />
                </div>
                <h3 className="font-semibold text-slate-900 text-base mb-1.5">For Providers</h3>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">Claim your firm profile, receive RFQ invitations, and grow your business.</p>
                <div className="flex items-center gap-1 mt-4 text-blue-600 text-sm font-medium group-hover:gap-2 transition-all duration-150">
                  Learn more <ChevronRight className="h-4 w-4" />
                </div>
              </div>
            </Link>

            <Link href="/software-providers" className="group block h-full">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full flex flex-col">
                <div className="w-12 h-12 rounded-xl bg-purple-50 flex items-center justify-center mb-4 flex-shrink-0">
                  <Cpu className="h-6 w-6 text-purple-600" />
                </div>
                <h3 className="font-semibold text-slate-900 text-base mb-1.5">Software Providers</h3>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">Engineering software tools and CAE solutions for your workflow.</p>
                <div className="flex items-center gap-1 mt-4 text-blue-600 text-sm font-medium group-hover:gap-2 transition-all duration-150">
                  Browse tools <ChevronRight className="h-4 w-4" />
                </div>
              </div>
            </Link>

            <Link href="/advertise" className="group block h-full">
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-150 h-full flex flex-col">
                <div className="w-12 h-12 rounded-xl bg-orange-50 flex items-center justify-center mb-4 flex-shrink-0">
                  <Megaphone className="h-6 w-6 text-orange-600" />
                </div>
                <h3 className="font-semibold text-slate-900 text-base mb-1.5">Advertise Your Firm</h3>
                <p className="text-sm text-slate-500 leading-relaxed flex-1">Get featured placement and reach customers searching for engineering expertise.</p>
                <div className="flex items-center gap-1 mt-4 text-blue-600 text-sm font-medium group-hover:gap-2 transition-all duration-150">
                  Get started <ChevronRight className="h-4 w-4" />
                </div>
              </div>
            </Link>

          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
