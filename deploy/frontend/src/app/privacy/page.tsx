import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Privacy Policy | ProMechDirectory',
  description: 'Privacy Policy for ProMechDirectory engineering services marketplace.',
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-2xl font-semibold mb-4 pb-2 border-b">{title}</h2>
      <div className="space-y-3 text-muted-foreground">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-blue-600">ProMechDirectory</Link>
          <nav className="flex gap-4 text-sm text-muted-foreground">
            <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
          </nav>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-12">
        <div className="mb-10">
          <h1 className="text-4xl font-bold text-foreground mb-3">Privacy Policy</h1>
          <p className="text-sm text-muted-foreground">Last updated: March 1, 2025</p>
          <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800">
              ProMechDirectory is committed to protecting your privacy. This Policy explains how
              we collect, use, and safeguard your information when you use our platform.
            </p>
          </div>
        </div>
        <div className="space-y-10">

          <Section title="1. Information We Collect">
            <p className="font-medium text-foreground">Information you provide directly:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Account registration data: name, email address, password (hashed)</li>
              <li>Business information: company name, address, phone, website</li>
              <li>RFQ content: project descriptions, uploaded documents, contact details</li>
              <li>Quote submissions: pricing estimates, scope notes, assumptions</li>
              <li>Payment information: processed by Stripe or PayPal (we do not store card data)</li>
              <li>Profile data: capabilities, certifications, software tools, project history</li>
            </ul>
            <p className="font-medium text-foreground mt-2">Information collected automatically:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>IP address and approximate geographic location</li>
              <li>Browser type, operating system, and device information</li>
              <li>Pages visited, search queries, and usage patterns</li>
              <li>Session identifiers and authentication tokens</li>
              <li>Log data including access times and referring URLs</li>
            </ul>
          </Section>

          <Section title="2. How We Use Your Information">
            <p className="leading-relaxed">We use collected information to:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Operate, maintain, and improve the Platform</li>
              <li>Match customers with qualified engineering service providers</li>
              <li>Process RFQ submissions and dispatch to matched providers</li>
              <li>Facilitate payment processing and subscription management</li>
              <li>Send transactional emails (RFQ notifications, quote alerts, receipts)</li>
              <li>Generate AI-powered embeddings for provider search and matching</li>
              <li>Enforce rate limits and prevent abuse</li>
              <li>Comply with legal obligations and resolve disputes</li>
              <li>Analyze usage patterns to improve search quality and user experience</li>
            </ul>
            <p className="leading-relaxed">
              We do not sell your personal information to third parties. We do not use your
              data for advertising targeting outside the Platform.
            </p>
          </Section>

          <Section title="3. Data Sharing">
            <p className="leading-relaxed">We share information only in these circumstances:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li><strong>With matched providers:</strong> Teaser RFQ details (no contact info until acceptance)</li>
              <li><strong>With selected providers:</strong> Customer contact info only after quote acceptance</li>
              <li><strong>With payment processors:</strong> Stripe and PayPal handle payment data per their privacy policies</li>
              <li><strong>With document signing services:</strong> Signwell receives NDA documents for electronic signing</li>
              <li><strong>With cloud storage:</strong> AWS S3 stores uploaded documents and signed NDAs</li>
              <li><strong>With AI providers:</strong> OpenAI or Anthropic process queries for intent extraction (no PII sent)</li>
              <li><strong>Legal requirements:</strong> When required by law, court order, or to protect our rights</li>
            </ul>
          </Section>

          <Section title="4. Cookies and Tracking">
            <p className="leading-relaxed">We use the following cookies and storage mechanisms:</p>
            <div className="bg-muted rounded-lg p-4 text-sm divide-y divide-border">
              <div className="py-2"><span className="font-semibold">Authentication cookies</span> — secure, httpOnly JWT tokens for session management</div>
              <div className="py-2"><span className="font-semibold">Refresh tokens</span> — secure, httpOnly long-lived tokens stored server-side (hashed)</div>
              <div className="py-2"><span className="font-semibold">localStorage</span> — non-sensitive UI preferences (e.g., search duration estimates)</div>
              <div className="py-2"><span className="font-semibold">Session tracking</span> — anonymous search quota enforcement by IP address</div>
            </div>
            <p className="leading-relaxed">
              We do not use third-party advertising cookies. We do not use cross-site tracking pixels.
              Essential authentication cookies cannot be disabled while using the Platform.
            </p>
          </Section>

          <Section title="5. Data Security">
            <p className="leading-relaxed">We implement industry-standard security measures including:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Passwords hashed with bcrypt (never stored in plaintext)</li>
              <li>JWT tokens with short expiration (15 minutes) and secure rotation</li>
              <li>HTTPS/TLS encryption for all data in transit</li>
              <li>AWS S3 server-side encryption for files at rest</li>
              <li>Database encrypted at rest on Render managed PostgreSQL</li>
              <li>Rate limiting and abuse prevention on all API endpoints</li>
              <li>Webhook signature verification for all payment and signing events</li>
            </ul>
            <p className="leading-relaxed">
              No system is perfectly secure. In the event of a data breach affecting your
              personal information, we will notify you as required by applicable law.
            </p>
          </Section>

          <Section title="6. Data Retention">
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li>Account data retained while your account is active</li>
              <li>RFQ and quote data retained for 3 years for dispute resolution</li>
              <li>Payment records retained for 7 years per financial regulations</li>
              <li>Signed NDAs and audit trails retained for 7 years</li>
              <li>Search logs retained for 90 days for abuse prevention</li>
              <li>Inactive accounts may be deleted after 2 years of inactivity with notice</li>
            </ul>
          </Section>

          <Section title="7. Your Rights">
            <p className="leading-relaxed">You have the right to:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-4">
              <li><strong>Access:</strong> Request a copy of your personal data we hold</li>
              <li><strong>Correction:</strong> Update inaccurate or incomplete information via your profile</li>
              <li><strong>Deletion:</strong> Request deletion of your account and associated data (subject to retention requirements)</li>
              <li><strong>Portability:</strong> Request export of your data in a machine-readable format</li>
              <li><strong>Opt-out:</strong> Unsubscribe from non-transactional communications at any time</li>
            </ul>
            <p className="leading-relaxed">
              To exercise these rights, contact us at privacy@promechdirectory.com. We will
              respond within 30 days. Some requests may be subject to legal retention obligations.
            </p>
          </Section>

          <Section title="8. Third-Party Services">
            <p className="leading-relaxed">Our Platform integrates with these third-party services, each governed by their own privacy policies:</p>
            <div className="bg-muted rounded-lg p-4 text-sm divide-y divide-border">
              <div className="py-2.5">
                <p className="font-semibold">Stripe</p>
                <p className="text-xs mt-0.5">Payment processing for cards and ACH. <a href="https://stripe.com/privacy" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">stripe.com/privacy</a></p>
              </div>
              <div className="py-2.5">
                <p className="font-semibold">PayPal / Braintree</p>
                <p className="text-xs mt-0.5">PayPal and Venmo payment processing. <a href="https://www.paypal.com/privacy" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">paypal.com/privacy</a></p>
              </div>
              <div className="py-2.5">
                <p className="font-semibold">AWS S3</p>
                <p className="text-xs mt-0.5">Document and file storage. <a href="https://aws.amazon.com/privacy/" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">aws.amazon.com/privacy</a></p>
              </div>
              <div className="py-2.5">
                <p className="font-semibold">Signwell</p>
                <p className="text-xs mt-0.5">Electronic NDA document signing. <a href="https://www.signwell.com/privacy/" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">signwell.com/privacy</a></p>
              </div>
              <div className="py-2.5">
                <p className="font-semibold">Resend / SendGrid</p>
                <p className="text-xs mt-0.5">Transactional email delivery.</p>
              </div>
              <div className="py-2.5">
                <p className="font-semibold">Sentry</p>
                <p className="text-xs mt-0.5">Error monitoring. May capture anonymized stack traces. <a href="https://sentry.io/privacy/" className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">sentry.io/privacy</a></p>
              </div>
            </div>
          </Section>

          <Section title="9. Contact">
            <p className="leading-relaxed">For privacy questions or data requests, contact our Privacy Team:</p>
            <div className="bg-muted rounded-lg p-4 text-sm space-y-1">
              <p className="font-semibold">ProMechDirectory LLC — Privacy Team</p>
              <p>Email: <a href="mailto:privacy@promechdirectory.com" className="text-blue-600 hover:underline">privacy@promechdirectory.com</a></p>
              <p>Website: <a href="https://www.promechdirectory.com" className="text-blue-600 hover:underline">www.promechdirectory.com</a></p>
            </div>
            <p className="leading-relaxed text-sm">
              This Privacy Policy applies to ProMechDirectory services. By using the Platform
              you acknowledge you have read and understood this policy.
            </p>
          </Section>

        </div>
      </main>

      <footer className="border-t mt-16 py-8 bg-muted/30">
        <div className="max-w-4xl mx-auto px-4 flex flex-col sm:flex-row justify-between items-center gap-4 text-sm text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} ProMechDirectory LLC. All rights reserved.</p>
          <div className="flex gap-6">
            <Link href="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link>
            <Link href="/privacy" className="font-medium text-foreground">Privacy Policy</Link>
            <Link href="/" className="hover:text-foreground transition-colors">Home</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
