'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useConfig } from '@/contexts/ConfigContext';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Search, Users, Building2, Megaphone, LogOut, LayoutDashboard } from 'lucide-react';


function Footer() {
  const { setShowSetup, missingServices } = useConfig();
  const { hasRole } = useAuth();
  const needsConfig = hasRole('admin') && missingServices.length > 0;

  return (
    <footer className="border-t py-6">
      <div className="container flex flex-col md:flex-row justify-between items-center gap-4">
        <p className="text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} ProMechDirectory. All rights reserved.
        </p>
        <div className="flex gap-4 items-center">
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
          <Link href="/software-providers" className="text-sm text-muted-foreground hover:underline">
            Software Providers
          </Link>
          <Link href="/featured-firms" className="text-sm text-muted-foreground hover:underline">
            Featured Firms
          </Link>
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
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProMechDirectory</span>
          </Link>
          <nav className="ml-auto flex gap-4 items-center">
            {user ? (
              <>
                <Link href={getDashboardLink()}>
                  <Button variant="ghost" className="flex items-center gap-2">
                    <LayoutDashboard className="h-4 w-4" />
                    Dashboard
                  </Button>
                </Link>
                <Button variant="ghost" onClick={handleLogout} className="flex items-center gap-2 text-red-600 hover:text-red-700 hover:bg-red-50">
                  <LogOut className="h-4 w-4" />
                  Sign Out
                </Button>
              </>
            ) : (
              <>
                <Link href="/login">
                  <Button variant="ghost">Sign In</Button>
                </Link>
                <Link href="/register">
                  <Button>Get Started</Button>
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1">
        <section className="container py-24 md:py-32">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
              Find the Perfect Engineering Partner
            </h1>
            <p className="mt-6 text-lg text-muted-foreground">
              Connect with 6,000+ verified engineering service providers.
              Submit RFQs, compare quotes, and get your project done right.
            </p>

            {/* Search Bar */}
            <form onSubmit={handleSearch} className="mt-10 flex gap-3 max-w-2xl mx-auto">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Describe your engineering project..."
                  className="pl-10 h-12 text-base"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <Button type="submit" size="lg" className="h-12 px-8">
                <Search className="mr-2 h-4 w-4" />
                Search
              </Button>
            </form>

            <p className="mt-4 text-sm text-muted-foreground">
              Or{' '}
              <Link href="/search/upload" className="text-primary underline hover:no-underline">
                upload a project document
              </Link>{' '}
              to find matching providers
            </p>
          </div>
        </section>

        {/* Navigation Buttons */}
        <section className="container pb-16">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto items-stretch">
            <Link href="/for-customers" className="h-full flex">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer text-center h-full w-full">
                <CardContent className="p-6">
                  <Users className="h-8 w-8 mx-auto mb-2 text-blue-600" />
                  <h3 className="font-semibold">For Customers</h3>
                  <p className="text-sm text-muted-foreground mt-1">Find & hire engineering firms</p>
                </CardContent>
              </Card>
            </Link>
            <Link href="/for-providers" className="h-full flex">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer text-center h-full w-full">
                <CardContent className="p-6">
                  <Building2 className="h-8 w-8 mx-auto mb-2 text-green-600" />
                  <h3 className="font-semibold">For Providers</h3>
                  <p className="text-sm text-muted-foreground mt-1">List your firm, get RFQs</p>
                </CardContent>
              </Card>
            </Link>
            <Link href="/software-providers" className="h-full flex">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer text-center h-full w-full">
                <CardContent className="p-6">
                  <Search className="h-8 w-8 mx-auto mb-2 text-purple-600" />
                  <h3 className="font-semibold">Software Providers</h3>
                  <p className="text-sm text-muted-foreground mt-1">Engineering software tools</p>
                </CardContent>
              </Card>
            </Link>
            <Link href="/featured-firms" className="h-full flex">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer text-center h-full w-full">
                <CardContent className="p-6">
                  <Megaphone className="h-8 w-8 mx-auto mb-2 text-orange-600" />
                  <h3 className="font-semibold">Advertise Your Firm</h3>
                  <p className="text-sm text-muted-foreground mt-1">Get featured placement</p>
                </CardContent>
              </Card>
            </Link>
          </div>
        </section>

      </main>

      <Footer />
    </div>
  );
}
