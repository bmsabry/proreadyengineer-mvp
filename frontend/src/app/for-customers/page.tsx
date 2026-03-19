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
            <p className="text-gray-600 text-sm">Describe your engineering needs in plain language and get AI-matched providers from our database of 6,000+ firms.</p>
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

        <div className="text-center space-x-4">
          <Link
            href="/search"
            className="inline-block bg-blue-600 text-white px-8 py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
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
