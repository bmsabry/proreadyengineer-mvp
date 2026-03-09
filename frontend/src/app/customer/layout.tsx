import { Metadata } from 'next';
import Link from 'next/link';
import { Building2, LayoutDashboard, PlusCircle, FileText } from 'lucide-react';

export const metadata: Metadata = {
  title: 'Customer Portal - ProReadyEngineer',
};

export default function CustomerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
        <div className="container flex h-14 items-center">
          <Link href="/customer/dashboard" className="flex items-center gap-2 font-bold text-xl">
            <Building2 className="h-6 w-6" />
            <span>Customer Portal</span>
          </Link>
          <nav className="ml-auto flex gap-4">
            <Link href="/customer/dashboard" className="flex items-center gap-2 text-sm font-medium">
              <LayoutDashboard className="h-4 w-4" />
              Dashboard
            </Link>
            <Link href="/customer/rfq/new" className="flex items-center gap-2 text-sm font-medium">
              <PlusCircle className="h-4 w-4" />
              New RFQ
            </Link>
            <Link href="/customer/quotes" className="flex items-center gap-2 text-sm font-medium">
              <FileText className="h-4 w-4" />
              Quotes
            </Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
