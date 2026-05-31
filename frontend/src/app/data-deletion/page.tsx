"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function DataDeletionPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 mb-8">
          <ArrowLeft className="h-4 w-4" />
          Back to home
        </Link>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Data Deletion Request</h1>
        <p className="text-sm text-slate-500 mb-8">Last updated: May 31, 2026</p>

        <div className="prose prose-slate max-w-none space-y-6 text-slate-700 text-sm leading-relaxed">
          <section>
            <p>You have the right to request deletion of your account and the personal information associated with it. ProReadyEngineer LLC (d/b/a ProMechDirectory) will honor verified deletion requests as described below.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-900">How to request deletion</h2>
            <p>To request deletion of your data, email us from the email address associated with your account at <a href="mailto:info@promechdirectory.com?subject=Data%20Deletion%20Request" className="text-blue-600 hover:underline">info@promechdirectory.com</a> with the subject line &ldquo;Data Deletion Request.&rdquo; Please include your account name so we can locate and verify your account.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-900">What happens next</h2>
            <ul className="list-disc pl-6 space-y-1">
              <li>We may ask you to verify your identity to protect your account from unauthorized deletion.</li>
              <li>Once verified, we will delete or de-identify your personal information and close your account, typically within 30 days.</li>
              <li>We may retain limited information where required for legal, accounting, fraud-prevention, or dispute-resolution purposes, and content that has already been shared with other users (for example, an RFQ sent to a provider) may persist in their records.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-slate-900">Related information</h2>
            <p>For more detail on how we handle your information and your privacy rights, see our <Link href="/privacy" className="text-blue-600 hover:underline">Privacy Policy</Link>. For general questions, please <Link href="/contact" className="text-blue-600 hover:underline">contact us</Link>.</p>
          </section>
        </div>
      </div>
    </div>
  );
}
