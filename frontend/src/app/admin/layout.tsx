import { Metadata } from 'next';
import Link from 'next/link';
import { DashboardNav } from '@/components/admin/DashboardNav';

export const metadata: Metadata = {
  title: 'Admin - ProReadyEngineer',
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <DashboardNav />
      <main className="flex-1 bg-background">
        {children}
      </main>
    </div>
  );
}
