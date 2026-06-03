import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Toaster } from '@/components/ui/toaster';
import { AuthProvider } from '@/contexts/AuthContext';
import { ConfigProvider } from '@/contexts/ConfigContext';
import { SetupWrapper } from '@/components/setup/SetupWrapper';
import HelpChatWidget from '@/components/help/HelpChatWidget';
import SiteHeader from '@/components/SiteHeader';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  icons: {
    icon: '/favicon.svg',
    shortcut: '/favicon.svg',
  },
  title: 'ProMechDirectory - Engineering Services Marketplace',
  description: 'Find and hire top engineering service providers',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ConfigProvider>
          <AuthProvider>
            <SiteHeader />
            {children}
            <SetupWrapper />
            <HelpChatWidget />
            <Toaster />
          </AuthProvider>
        </ConfigProvider>
      </body>
    </html>
  );
}
