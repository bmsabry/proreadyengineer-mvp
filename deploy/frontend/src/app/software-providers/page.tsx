'use client';

import Link from 'next/link';
import { Building2, Cpu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function SoftwareProvidersPage() {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center">
          <Link href="/" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>ProMechDirectory</span>
          </Link>
          <nav className="ml-auto flex gap-4">
            <Link href="/search">
              <Button variant="ghost">Search</Button>
            </Link>
            <Link href="/login">
              <Button variant="ghost">Sign In</Button>
            </Link>
          </nav>
        </div>
      </header>

      <main className="container py-12">
        <div className="text-center max-w-3xl mx-auto mb-12">
          <h1 className="text-4xl font-bold mb-4">Software Providers</h1>
          <p className="text-lg text-muted-foreground">
            Engineering software and tool vendors on our platform
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="flex flex-col">
              <CardHeader>
                <div className="h-32 bg-muted rounded-lg flex items-center justify-center mb-4">
                  <Cpu className="h-12 w-12 text-muted-foreground" />
                </div>
                <CardTitle>Software Vendor {i}</CardTitle>
                <CardDescription>
                  CAD, FEA, and simulation software solutions
                </CardDescription>
              </CardHeader>
              <CardContent className="mt-auto">
                <Link href="/advertise">
                  <Button variant="outline" className="w-full">
                    Advertise Here
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-16 text-center">
          <p className="text-muted-foreground mb-4">
            Are you a software vendor? Reach engineers directly.
          </p>
          <Link href="/register?role=advertiser">
            <Button size="lg">Become a Software Partner</Button>
          </Link>
        </div>
      </main>
    </div>
  );
}
