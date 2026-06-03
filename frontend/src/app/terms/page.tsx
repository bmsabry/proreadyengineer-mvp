import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Terms of Service | ProMechDirectory',
  description: 'Terms of Service for ProMechDirectory engineering services marketplace.',
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-2xl font-semibold mb-4 pb-2 border-b">{title}</h2>
      <div className="space-y-3 text-muted-foreground">{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-blue-600">ProMechDirectory</Link>
          <nav className="flex gap-4 text-sm text-muted-foreground">
            <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
          </nav>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-12">
        <div className="mb-10">
          <h1 className="text-4xl font-bold text-foreground mb-3">Terms of Service</h1>
          <p className="text-sm text-muted-foreground">Last updated: March 1, 2025</p>
          <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800">
              Please read these Terms carefully before using ProMechDirectory. By accessing
              or using our platform, you agree to be bound by these terms.
            </p>
          </div>
        </div>

        <div className="space-y-10">

          <Section title="1. Acceptance of Terms">
            <p className="leading-relaxed">
              By accessing or using ProMechDirectory (the &ldquo;Platform&rdquo;), operated by
              ProMechDirectory LLC, you agree to be legally bound by these Terms of Service.
              If you do not agree, you may not use the Platform.
            </p>
            <p className="leading-relaxed">
              We reserve the right to modify these Terms at any time. Continued use after
              changes constitutes acceptance of the updated Terms.
            </p>
          </Section>

          <Section title="Payments, Subscriptions, and Refunds">
            <p className="leading-relaxed">
              Paid plans are billed through Stripe. <strong>Annual</strong> subscriptions are refundable within <strong>14 days</strong> of the payment date; after 14 days they are non-refundable and your subscription remains active until the end of the paid annual period. <strong>Monthly</strong> subscriptions are refundable within <strong>5 days</strong> of the payment date; after 5 days they are non-refundable and your subscription remains active until the end of the paid monthly period.
            </p>
            <p className="leading-relaxed">
              One-time fees — including RFQ unlock fees, NDA handling fees, and the provider profile-edit unlock — are <strong>non-refundable</strong> once paid, as they pay for a service delivered immediately.
            </p>
            <p className="leading-relaxed">
              You may cancel a subscription at any time to stop future renewals; outside the refund windows above, your access continues until the end of the period you have already paid for. By completing a payment you acknowledge and agree to this refund policy.
            </p>
          </Section>

          <Section title="2. Description of Services">
            <p className="leading-relaxed">
              ProMechDirectory is a B2B engineering services marketplace connecting customers
              with qualified engineering service providers. Services include:
            </p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>AI-powered search and provider matching across 5,000+ firms</li>
              <li>Request for Quotation (RFQ) submission and management</li>
              <li>Provider directory with detailed capability profiles</li>
              <li>Secure document handling including NDA management</li>
              <li>Quote submission and side-by-side comparison tools</li>
              <li>Subscription services for providers and advertisers</li>
            </ul>
            <p className="leading-relaxed">
              ProMechDirectory acts solely as an intermediary marketplace and is not a party
              to any service agreements between customers and providers.
            </p>
          </Section>

          <Section title="3. User Accounts">
            <p className="leading-relaxed">To access certain features you must create an account. You agree to:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Provide accurate, current, and complete registration information</li>
              <li>Maintain the security of your account credentials</li>
              <li>Promptly notify us of any unauthorized account access</li>
              <li>Accept responsibility for all activities under your account</li>
              <li>Not share your account credentials with third parties</li>
            </ul>
            <p className="leading-relaxed">
              We reserve the right to suspend or terminate accounts that violate these Terms
              or engage in fraudulent, abusive, or illegal activity.
            </p>
          </Section>

          <Section title="4. Provider Listings">
            <p className="leading-relaxed">Engineering service providers listed on the Platform agree to:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Provide accurate and truthful information about capabilities and services</li>
              <li>Only claim provider records for firms they are authorized to represent</li>
              <li>Not misrepresent certifications, capabilities, or project experience</li>
              <li>Respond to RFQ inquiries professionally and in good faith</li>
              <li>Maintain current and up-to-date profile information</li>
            </ul>
            <p className="leading-relaxed">
              We reserve the right to remove listings with inaccurate content. Tier ratings
              are assigned at our sole discretion based on provider history and capabilities.
            </p>
          </Section>

          <Section title="5. RFQ Process">
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>All quotes are non-binding, rough order-of-magnitude estimates only</li>
              <li>ProMechDirectory does not guarantee accuracy of any submitted quote</li>
              <li>Customers may receive up to five (5) quotes per RFQ submission</li>
              <li>Providers must pay an unlock fee to access full RFQ details</li>
              <li>NDA requirements must be satisfied before accessing protected materials</li>
              <li>Quote acceptance initiates direct engagement outside the Platform</li>
              <li>Customer contact details are only revealed after quote acceptance</li>
            </ul>
            <p className="leading-relaxed">
              ProMechDirectory is not responsible for outcomes of engagements initiated
              through the Platform. Final contract terms are solely between customer and provider.
            </p>
          </Section>

          <Section title="6. Payment Terms">
            <p className="leading-relaxed">The following fees apply to Platform services:</p>
            <div className="bg-muted rounded-lg p-4 text-sm divide-y divide-border">
              <div className="flex justify-between py-2"><span>RFQ Unlock Fee (per RFQ)</span><span className="font-semibold">$50.00</span></div>
              <div className="flex justify-between py-2"><span>NDA Document Handling Fee</span><span className="font-semibold">$10.00</span></div>
              <div className="flex justify-between py-2"><span>Provider Profile Subscription</span><span className="font-semibold">$10.00/mo</span></div>
              <div className="flex justify-between py-2"><span>Search Subscription &mdash; 100 searches/mo</span><span className="font-semibold">$50.00/mo or $500.00/yr</span></div>
              <div className="flex justify-between py-2"><span>Ad Slot Subscription</span><span className="font-semibold">$50.00/mo</span></div>
            </div>
            <p className="leading-relaxed">
              All payments processed via Stripe. Subscriptions renew monthly until
              cancelled. RFQ unlock fees are non-refundable once accessed. Refunds handled
              on a case-by-case basis at our discretion.
            </p>
          </Section>

          <Section title="7. Limitation of Liability">
            <p className="leading-relaxed font-medium">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, PROMECHDIRECTORY LLC AND ITS OFFICERS,
              DIRECTORS, AND EMPLOYEES SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL,
              SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING LOSS OF PROFITS OR DATA.
            </p>
            <p className="leading-relaxed">
              OUR TOTAL LIABILITY SHALL NOT EXCEED THE GREATER OF (A) TOTAL FEES PAID BY YOU
              IN THE PRIOR TWELVE MONTHS OR (B) ONE HUNDRED DOLLARS ($100.00).
            </p>
          </Section>

          <Section title="8. Intellectual Property">
            <p className="leading-relaxed">
              The Platform is owned by ProMechDirectory LLC and protected by copyright,
              trademark, and intellectual property laws. You may not copy, modify, or
              distribute Platform content without our express written permission.
            </p>
            <p className="leading-relaxed">
              By submitting content to the Platform you grant ProMechDirectory LLC a
              non-exclusive, royalty-free license to use and display that content for
              Platform operations.
            </p>
          </Section>

          <Section title="9. Privacy">
            <p className="leading-relaxed">
              Your use of the Platform is governed by our{' '}
              <Link href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</Link>,
              incorporated herein by reference. By using the Platform you consent to the
              collection and use of information as described therein.
            </p>
          </Section>

          <Section title="10. Termination">
            <p className="leading-relaxed">We may suspend or terminate your access at any time for:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Violation of these Terms</li>
              <li>Fraudulent, abusive, or illegal activity</li>
              <li>Non-payment of fees</li>
              <li>Providing false or misleading information</li>
            </ul>
            <p className="leading-relaxed">
              Upon termination your right to use the Platform immediately ceases. Payment
              obligations, intellectual property rights, and limitation of liability
              provisions survive termination.
            </p>
          </Section>

          <Section title="11. Governing Law (Ohio)">
            <p className="leading-relaxed">
              These Terms are governed by the laws of the State of Ohio, United States,
              without regard to conflict of law principles. Disputes shall be subject to
              the exclusive jurisdiction of state and federal courts located in Ohio.
            </p>
          </Section>

          <Section title="12. Contact">
            <p className="leading-relaxed">For questions about these Terms, contact us:</p>
            <div className="bg-muted rounded-lg p-4 text-sm space-y-1">
              <p className="font-semibold">ProMechDirectory LLC</p>
              <p>Email: <a href="mailto:legal@promechdirectory.com" className="text-blue-600 hover:underline">legal@promechdirectory.com</a></p>
              <p>Website: <a href="https://www.promechdirectory.com" className="text-blue-600 hover:underline">www.promechdirectory.com</a></p>
            </div>
          </Section>

        </div>
      </main>

      <footer className="border-t mt-16 py-8 bg-muted/30">
        <div className="max-w-4xl mx-auto px-4 flex flex-col sm:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} ProMechDirectory LLC. All rights reserved.</p>
          <div className="flex gap-6">
            <Link href="/terms" className="font-medium text-foreground">Terms of Service</Link>
            <Link href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link>
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
