'use client'
import Link from 'next/link'

export default function ForCustomersPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">For Customers</h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Find the right engineering service provider for your project. Describe your needs,
            upload your documents, and receive matched quotes from pre-vetted engineering firms.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 mb-12">
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">🔍</div>
            <h3 className="text-lg font-semibold mb-2">Smart Search</h3>
            <p className="text-gray-600 text-sm">Describe your engineering needs in plain language and get AI-matched providers from our database of 5,000+ firms.</p>
          </div>
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">📋</div>
            <h3 className="text-lg font-semibold mb-2">Submit RFQs</h3>
            <p className="text-gray-600 text-sm">Send your Request for Quote to multiple engineering providers simultaneously and compare rough estimates side by side.</p>
          </div>
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">🔒</div>
            <h3 className="text-lg font-semibold mb-2">NDA Protection</h3>
            <p className="text-gray-600 text-sm">Protect your IP with built-in NDA handling. Providers sign before accessing your project documents.</p>
          </div>
        </div>

        {/* Pricing Section */}
        <div className="mb-12">
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-8">Simple, Transparent Pricing</h2>
          <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
            {/* Free Tier */}
            <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200">
              <div className="mb-4">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">Free</span>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-bold text-gray-900">$0</span>
                  <span className="text-gray-500">/month</span>
                </div>
              </div>
              <ul className="space-y-2 text-sm text-gray-600 mb-6">
                <li className="flex items-center gap-2">✓ 5 searches / month</li>
                <li className="flex items-center gap-2">✓ Submit unlimited RFQs</li>
                <li className="flex items-center gap-2">✓ Receive up to 5 quotes per RFQ</li>
                <li className="flex items-center gap-2">✓ Registration required to search</li>
              </ul>
              <Link
                href="/register"
                className="block text-center bg-gray-100 text-gray-800 px-4 py-2.5 rounded-lg font-semibold text-sm hover:bg-gray-200 transition-colors"
              >
                Get Started Free
              </Link>
            </div>
            {/* Search Plan */}
            <div className="bg-primary rounded-xl p-6 shadow-md border border-primary text-white">
              <div className="mb-4">
                <span className="text-xs font-semibold uppercase tracking-wider text-blue-200">Search Plan</span>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-bold">$50</span>
                  <span className="text-blue-200">/mo · $500/yr</span>
                </div>
              </div>
              <ul className="space-y-2 text-sm text-blue-100 mb-6">
                <li className="flex items-center gap-2">&#10003; 100 searches / month</li>
                <li className="flex items-center gap-2">&#10003; 5 free NDAs / month <span className="text-xs text-emerald-600 font-semibold ml-1">($50 value)</span></li>
                <li className="flex items-center gap-2">✓ Submit unlimited RFQs</li>
                <li className="flex items-center gap-2">✓ Receive up to 5 quotes per RFQ</li>
                <li className="flex items-center gap-2">✓ Priority support</li>
              </ul>
              <Link
                href="/billing"
                className="block text-center bg-white text-primary px-4 py-2.5 rounded-lg font-semibold text-sm hover:bg-blue-50 transition-colors"
              >
                Upgrade — $50/mo or $500/yr
              </Link>
            </div>
          </div>
          {/* Fee notes */}
          <div className="mt-6 max-w-2xl mx-auto grid md:grid-cols-2 gap-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
              <strong>NDA Handling Fee:</strong> $10 one-time fee per RFQ when NDA protection is required. <strong>Subscribers get 5 free NDAs/month</strong> ($50 value) — fee waived until credits are used.
            </div>
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
              <strong>Provider RFQ Unlock:</strong> Engineering firms pay $50 to access your full RFQ details and submit a quote.
            </div>
          </div>
        </div>

        <div className="text-center flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/search"
            className="inline-block bg-primary text-white px-8 py-3 rounded-lg font-semibold hover:bg-primary/90 transition-colors"
          >
            Start Searching
          </Link>
          <Link
            href="/"
            className="inline-block border border-gray-300 text-gray-700 px-8 py-3 rounded-lg font-semibold hover:bg-gray-50 transition-colors"
          >
            Back to Home
          </Link>
        </div>
      </div>
    </div>
  )
}
