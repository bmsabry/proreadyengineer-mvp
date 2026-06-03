'use client'
import Link from 'next/link'

export default function ForProvidersPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">For Providers</h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            List your engineering firm and connect with customers actively looking for your expertise.
            Receive qualified RFQs matched to your capabilities.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">📌</div>
            <h3 className="text-lg font-semibold mb-2">Claim Your Profile</h3>
            <p className="text-gray-600 text-sm">Search for your firm in our pre-seeded directory of 5,000+ engineering providers and claim ownership of your listing.</p>
          </div>
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">📬</div>
            <h3 className="text-lg font-semibold mb-2">Receive RFQ Teasers</h3>
            <p className="text-gray-600 text-sm">Get teaser notifications when your firm matches a customer RFQ. Unlock the full RFQ details for a small fee.</p>
          </div>
          <div className="bg-white rounded-lg p-6 shadow-sm border">
            <div className="text-3xl mb-4">⭐</div>
            <h3 className="text-lg font-semibold mb-2">Build Your Reputation</h3>
            <p className="text-gray-600 text-sm">Subscribe to edit your profile, showcase capabilities, and request tier upgrades based on your track record.</p>
          </div>
          <div className="bg-white rounded-lg p-6 shadow-sm border-2 border-primary/30 ring-1 ring-primary/10">
            <div className="text-3xl mb-4">🤖</div>
            <h3 className="text-lg font-semibold mb-2">AI Assistant <span className="text-[10px] font-bold uppercase tracking-wide text-primary align-middle bg-blue-50 px-1.5 py-0.5 rounded">Subscribers</span></h3>
            <p className="text-gray-600 text-sm">An AI agent that <strong>does the work</strong>: it builds and optimizes your firm profile from a brochure or a few details, and drafts your Notable Projects — so you get matched to more, and better, RFQs.</p>
          </div>
        </div>

        <div className="text-center space-x-4">
          <Link
            href="/provider/dashboard"
            className="inline-block bg-green-600 text-white px-8 py-3 rounded-lg font-semibold hover:bg-green-700 transition-colors"
          >
            Provider Dashboard
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
