import Link from 'next/link';
import { Lock } from 'lucide-react';

export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-sm">
            <p className="text-sm font-semibold text-slate-800">ProMechDirectory</p>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              A service of <span className="font-medium text-slate-600">ProReadyEngineer LLC</span><br />
              5325 Deerfield Blvd #148, Mason, OH 45040, USA<br />
              <a href="mailto:info@promechdirectory.com" className="text-primary hover:underline">
                info@promechdirectory.com
              </a>
            </p>
            <p className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
              <Lock className="h-3 w-3 text-emerald-600" /> Secure payments via Stripe
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <Link href="/about" className="text-slate-500 hover:text-slate-900 transition-colors">About Us</Link>
            <Link href="/trust" className="text-slate-500 hover:text-slate-900 transition-colors">Trust &amp; Security</Link>
            <Link href="/software-providers" className="text-slate-500 hover:text-slate-900 transition-colors">Software Providers</Link>
            <Link href="/featured-firms" className="text-slate-500 hover:text-slate-900 transition-colors">Featured Firms</Link>
            <Link href="/contact" className="text-slate-500 hover:text-slate-900 transition-colors">Contact Us</Link>
            <Link href="/terms" className="text-slate-500 hover:text-slate-900 transition-colors">Terms</Link>
            <Link href="/privacy" className="text-slate-500 hover:text-slate-900 transition-colors">Privacy</Link>
          </nav>
        </div>
        <p className="text-xs text-slate-400 mt-8">&copy; {year} ProReadyEngineer LLC. All rights reserved.</p>
      </div>
    </footer>
  );
}
