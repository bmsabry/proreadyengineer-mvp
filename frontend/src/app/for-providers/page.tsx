'use client'
import Link from 'next/link'
import { Target, FileSignature, HandCoins, Cpu, Check, X, Star } from 'lucide-react'

function Benefit({ icon: Icon, title, children }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
      <div className="w-11 h-11 rounded-xl bg-blue-50 flex items-center justify-center mb-4">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <h3 className="text-base font-semibold text-slate-900 mb-1.5">{title}</h3>
      <p className="text-sm text-slate-600 leading-relaxed">{children}</p>
    </div>
  )
}

function Line({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? <Check className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" /> : <X className="h-4 w-4 text-slate-300 shrink-0 mt-0.5" />}
      <span className={ok ? '' : 'text-slate-400'}>{children}</span>
    </li>
  )
}

export default function ForProvidersPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-16">
        <div className="text-center mb-12 max-w-2xl mx-auto">
          <h1 className="text-4xl font-bold text-slate-900 mb-4" style={{ letterSpacing: '-0.02em' }}>For engineering firms</h1>
          <p className="text-lg text-slate-600 leading-relaxed">
            Stop chasing leads. Customers post Requests for Quotation, our AI matches them to your
            capabilities, and the work comes to you &mdash; with the NDAs, paperwork, and busywork handled.
          </p>
        </div>

        {/* Why providers win */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
          <Benefit icon={Target} title="Qualified RFQs, not cold outreach">
            Customers come to you. Our AI matches their projects to your exact capabilities and sends you
            the ones worth pursuing &mdash; real demand, not cold calls.
          </Benefit>
          <Benefit icon={FileSignature} title="NDAs handled for you">
            Confidential projects use a one-click mutual e&#8209;signature (via SignWell), prepared and stored
            automatically. <strong>The customer pays the NDA fee</strong> &mdash; you just sign and read. No lawyers,
            no back&#8209;and&#8209;forth.
          </Benefit>
          <Benefit icon={HandCoins} title="Keep 100% of your project fees">
            We never take a percentage of the work you win. You bill the customer directly &mdash; we only charge
            clear, upfront platform fees.
          </Benefit>
          <Benefit icon={Cpu} title="An AI assistant that wins you work">
            Upload a brochure and it <strong>builds and optimizes your firm profile</strong>, drafts your Notable
            Projects, and can prepare quotes from your documents &mdash; so you match to more, and better, RFQs.
          </Benefit>
        </div>

        {/* How the math works */}
        <div className="bg-primary rounded-2xl p-8 mb-16 max-w-4xl mx-auto text-center">
          <p className="text-blue-100 text-sm font-semibold uppercase tracking-wide mb-2">How the math works</p>
          <h2 className="text-2xl font-bold text-white mb-3" style={{ letterSpacing: '-0.02em' }}>
            The Annual plan pays for itself after ~20 RFQs
          </h2>
          <p className="text-blue-100 leading-relaxed max-w-2xl mx-auto">
            Unlocking RFQs one at a time costs $50 each. The $1,000/year plan makes <strong>every</strong> unlock
            free after about 20 RFQs &mdash; and on top of that you get each customer&rsquo;s direct contact details to
            win the deal, the AI assistant keeping your profile sharp, and priority placement in search.
          </p>
        </div>

        {/* Transparent pricing */}
        <div className="mb-12">
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-slate-900" style={{ letterSpacing: '-0.02em' }}>Transparent pricing</h2>
            <p className="text-slate-500 mt-2 text-sm">No hidden fees. Listing your firm and receiving RFQ teasers is free.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start max-w-5xl mx-auto">
            {/* Pay Per RFQ */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pay Per RFQ</p>
              <div className="mt-2 mb-4 flex items-baseline gap-1">
                <span className="text-3xl font-bold text-slate-900 tabular-nums">$50</span>
                <span className="text-slate-500 text-sm">/ RFQ</span>
              </div>
              <ul className="space-y-2 text-sm text-slate-600 mb-6">
                <Line ok>Unlock any RFQ and submit a quote</Line>
                <Line ok>No commitment</Line>
                <Line ok={false}>Customer contact details</Line>
                <Line ok={false}>Profile editing</Line>
                <Line ok={false}>AI Assistant</Line>
              </ul>
              <Link href="/register?role=provider" className="block text-center bg-slate-100 text-slate-800 px-4 py-2.5 rounded-lg font-semibold text-sm hover:bg-slate-200 transition-colors">List your firm free</Link>
            </div>

            {/* Annual — featured */}
            <div className="bg-primary rounded-2xl p-6 shadow-md text-white relative md:-mt-2">
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 bg-amber-400 text-slate-900 text-[11px] font-bold uppercase tracking-wide px-3 py-1 rounded-full">
                <Star className="h-3 w-3" /> Best value
              </div>
              <p className="text-xs font-semibold uppercase tracking-wider text-blue-200">Annual Professional</p>
              <div className="mt-2 mb-4 flex items-baseline gap-1">
                <span className="text-3xl font-bold tabular-nums">$1,000</span>
                <span className="text-blue-200 text-sm">/ year</span>
              </div>
              <ul className="space-y-2 text-sm text-blue-100 mb-6">
                <li className="flex items-start gap-2"><Check className="h-4 w-4 text-emerald-300 shrink-0 mt-0.5" /><span className="font-semibold text-white">AI Assistant that builds &amp; optimizes your profile and drafts quotes</span></li>
                <li className="flex items-start gap-2"><Check className="h-4 w-4 text-emerald-300 shrink-0 mt-0.5" /><span>Unlimited RFQ unlocks &mdash; no $50 fee</span></li>
                <li className="flex items-start gap-2"><Check className="h-4 w-4 text-emerald-300 shrink-0 mt-0.5" /><span>See the customer&rsquo;s direct contact on every RFQ</span></li>
                <li className="flex items-start gap-2"><Check className="h-4 w-4 text-emerald-300 shrink-0 mt-0.5" /><span>Unlimited profile edits + priority listing</span></li>
              </ul>
              <Link href="/provider/upgrade" className="block text-center bg-white text-primary px-4 py-2.5 rounded-lg font-semibold text-sm hover:bg-blue-50 transition-colors">Go Annual &mdash; $1,000/yr</Link>
            </div>

            {/* Profile Edit */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Profile Edit &mdash; One Time</p>
              <div className="mt-2 mb-4 flex items-baseline gap-1">
                <span className="text-3xl font-bold text-slate-900 tabular-nums">$500</span>
                <span className="text-slate-500 text-sm">once</span>
              </div>
              <ul className="space-y-2 text-sm text-slate-600 mb-6">
                <Line ok>Edit all profile fields to improve matching</Line>
                <Line ok>Better search placement</Line>
                <Line ok={false}>RFQ access still $50 / unlock</Line>
                <Line ok={false}>AI Assistant</Line>
              </ul>
              <Link href="/provider/upgrade" className="block text-center bg-slate-100 text-slate-800 px-4 py-2.5 rounded-lg font-semibold text-sm hover:bg-slate-200 transition-colors">Unlock profile edit</Link>
            </div>
          </div>
        </div>

        <div className="text-center flex flex-col sm:flex-row gap-4 justify-center">
          <Link href="/register?role=provider" className="inline-flex items-center justify-center bg-primary text-white px-8 py-3 rounded-lg font-semibold hover:bg-primary/90 transition-colors">
            List your firm &mdash; free to start
          </Link>
          <Link href="/provider/dashboard" className="inline-flex items-center justify-center border border-slate-300 text-slate-700 px-8 py-3 rounded-lg font-semibold hover:bg-slate-50 transition-colors">
            Provider Dashboard
          </Link>
        </div>
      </div>
    </div>
  )
}
