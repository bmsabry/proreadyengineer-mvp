import { Metadata } from 'next';
import Link from 'next/link';
import { Building2, LayoutDashboard, Search, UserCircle } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Provider Portal - ProReadyEngineer',
};

export default function ProviderLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center">
          <Link href="/provider/dashboard" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>Provider Portal</span>
          </Link>
          <nav className="ml-auto flex gap-4">
            <Link href="/provider/dashboard" className="flex items-center gap-2 text-sm font-medium">
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </Link>
            <Link href="/provider/claim" className="flex items-center gap-2 text-sm font-medium">
              <Search className="h-4 w-4" />
              Claim Firm
            </Link>
            <Link href="/provider/profile" className="flex items-center gap-2 text-sm font-medium">
              <UserCircle className="h-4 w-4" />
              Profile
            </Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
