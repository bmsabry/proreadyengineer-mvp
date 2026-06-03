import Link from 'next/link';
import { Building2, Lock, ShieldCheck, FileSignature, HandCoins, BadgeCheck, LifeBuoy } from 'lucide-react';
import SiteFooter from '@/components/SiteFooter';

export const metadata = {
  title: 'Trust & Security — ProMechDirectory',
  description: 'How ProMechDirectory keeps your payments secure and your engineering projects confidential.',
};

function Item({ icon: Icon, title, children }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <h2 className="font-semibold text-slate-900 text-lg">{title}</h2>
      </div>
      <div className="text-sm text-slate-600 leading-relaxed space-y-2">{children}</div>
    </div>
  );
}

export default function TrustPage() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
              <Building2 className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-lg text-slate-900 tracking-tight">ProMechDirectory</span>
          </Link>
          <Link href="/" className="text-sm text-slate-600 hover:text-slate-900 font-medium">Back to home</Link>
        </div>
      </header>

      <main className="flex-1">
        <section className="bg-gradient-to-br from-slate-50 via-white to-blue-50/40 border-b border-slate-100">
          <div className="max-w-3xl mx-auto px-6 py-16 text-center">
            <div className="inline-flex items-center gap-2 bg-emerald-50 border border-emerald-100 rounded-full px-4 py-1.5 mb-6">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <span className="text-xs font-semibold text-emerald-700 tracking-wide uppercase">Trust &amp; Security</span>
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold text-slate-900 leading-tight mb-4" style={{ letterSpacing: '-0.02em' }}>
              Built for serious engineering work
            </h1>
            <p className="text-lg text-slate-600 leading-relaxed">
              Your payment details and your project information are handled with the same rigor you
              bring to your own work. Here is exactly how.
            </p>
          </div>
        </section>

        <section className="max-w-5xl mx-auto px-6 py-14">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Item icon={Lock} title="Your payments are secure">
              <p>
                All payments run through <span className="font-semibold text-slate-700">Stripe</span>, a
                globally trusted, PCI-DSS Level 1 payment processor. You enter your card on Stripe&rsquo;s
                own hosted checkout — <strong>your card details never touch our servers and are never
                stored by us.</strong>
              </p>
              <p>Every page and payment is encrypted in transit (TLS/HTTPS), and receipts are issued by Stripe.</p>
            </Item>

            <Item icon={FileSignature} title="Your projects stay confidential">
              <p>
                For confidential RFQs we use a <strong>provider-first, mutual NDA</strong>: a provider must
                sign the NDA <em>before</em> they can see your full project description or files. The
                agreement is e-signed through SignWell, and full details unlock only after both parties sign.
              </p>
              <p>A provider&rsquo;s project history is used only for matching and is never shown publicly.</p>
            </Item>

            <Item icon={HandCoins} title="We don&rsquo;t take a cut of your project">
              <p>
                ProMechDirectory does <strong>not</strong> escrow or take a percentage of the fees you pay a
                provider for the engineering work. Payment for the project happens directly between you and
                the firm. We earn only from clearly stated platform fees and subscriptions.
              </p>
            </Item>

            <Item icon={Building2} title="A real, registered company">
              <p>
                ProMechDirectory is operated by <strong>ProReadyEngineer LLC</strong>, a registered company
                at 5325 Deerfield Blvd #148, Mason, OH 45040, USA. You can reach a real person at{' '}
                <a href="mailto:info@promechdirectory.com" className="text-primary hover:underline">info@promechdirectory.com</a>.
              </p>
              <p>It&rsquo;s built by a practicing mechanical engineer — <Link href="/about" className="text-primary hover:underline">read the founder&rsquo;s story</Link>.</p>
            </Item>

            <Item icon={BadgeCheck} title="Clear, honest refund policy">
              <p>
                <strong>Subscriptions</strong> are refundable within <strong>14 days</strong> (annual) or{' '}
                <strong>5 days</strong> (monthly) of payment, and you can cancel anytime to stop renewals.
              </p>
              <p>
                <strong>One-time fees</strong> (RFQ unlock, NDA handling) are non-refundable once paid, because
                they pay for a service delivered immediately. The full policy is on our{' '}
                <Link href="/terms" className="text-primary hover:underline">Terms</Link> page, shown again at checkout.
              </p>
            </Item>

            <Item icon={LifeBuoy} title="Help when you need it">
              <p>
                Questions before you pay? Use <Link href="/contact" className="text-primary hover:underline">Contact</Link>{' '}
                or the in-app assistant. We respond to billing questions with your account email and the payment date.
              </p>
            </Item>
          </div>

          <div className="mt-10 text-center">
            <Link href="/register" className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary/90 transition-colors">
              Get started
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
