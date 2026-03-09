'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Search, Users, Building2, Megaphone } from 'lucide-react';

export default function LandingPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  const tollgates = [
    { id: 'tg0', name: 'TG0: Idea Generation', description: 'Concept development and initial feasibility' },
    { id: 'tg1', name: 'TG1: Basic Engineering', description: '1D analysis and simple calculations' },
    { id: 'tg3', name: 'TG3: Intermediate Analysis', description: 'Advanced modeling and concept testing' },
    { id: 'tg4', name: 'TG4: Full Scale Modeling', description: 'Detailed simulation and optimization' },
    { id: 'tg6', name: 'TG6: Full System Testing', description: 'Prototype validation and certification' },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProReadyEngineer</span>
          </Link>
          <nav className="ml-auto flex gap-4">
            <Link href="/login">
              <Button variant="ghost">Sign In</Button>
            </Link>
            <Link href="/register">
              <Button>Get Started</Button>
            </Link>
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
            <form onSubmit={handleSearch} className="mt-10 flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Describe your engineering project..."
                  className="pl-10 h-12 text-lg"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <Button type="submit" size="lg">
                Search
              </Button>
            </form>
            
            <p className="mt-2 text-sm text-muted-foreground">
              Or <Button variant="link" className="p-0 h-auto">upload a document</Button> to search
            </p>
          </div>
        </section>

        {/* Tollgate Map */}
        <section className="container py-12 bg-muted/50">
          <h2 className="text-2xl font-bold text-center mb-8">Engineering Tollgate Map</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {tollgates.map((tg) => (
              <Card key={tg.id} className="hover:shadow-lg transition-shadow">
                <CardContent className="p-4">
                  <h3 className="font-semibold text-sm">{tg.name}</h3>
                  <p className="text-xs text-muted-foreground mt-1">{tg.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-center text-sm text-muted-foreground mt-4">
            Projects may include fabrication, physical testing, and data handling. You don&apos;t need to complete every phase.
          </p>
        </section>

        {/* Navigation Buttons */}
        <section className="container py-12">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Link href="/customer/rfq/new">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                  <Users className="h-8 w-8 mb-4 text-primary" />
                  <h3 className="font-semibold">For Customers</h3>
                  <p className="text-sm text-muted-foreground mt-2">Submit RFQs and get quotes</p>
                </CardContent>
              </Card>
            </Link>
            
            <Link href="/provider/claim">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                  <Building2 className="h-8 w-8 mb-4 text-primary" />
                  <h3 className="font-semibold">For Providers</h3>
                  <p className="text-sm text-muted-foreground mt-2">Claim your profile and receive RFQs</p>
                </CardContent>
              </Card>
            </Link>
            
            <Link href="/software-providers">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                  <Search className="h-8 w-8 mb-4 text-primary" />
                  <h3 className="font-semibold">Software Providers</h3>
                  <p className="text-sm text-muted-foreground mt-2">Browse engineering software</p>
                </CardContent>
              </Card>
            </Link>
            
            <Link href="/featured-firms">
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                  <Megaphone className="h-8 w-8 mb-4 text-primary" />
                  <h3 className="font-semibold">Advertise Your Firm</h3>
                  <p className="text-sm text-muted-foreground mt-2">Get featured placement</p>
                </CardContent>
              </Card>
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t py-6">
        <div className="container flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-muted-foreground">
            &copy; {new Date().getFullYear()} ProReadyEngineer. All rights reserved.
          </p>
          <div className="flex gap-4">
            <Link href="/software-providers" className="text-sm text-muted-foreground hover:underline">
              Software Providers
            </Link>
            <Link href="/featured-firms" className="text-sm text-muted-foreground hover:underline">
              Featured Firms
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
