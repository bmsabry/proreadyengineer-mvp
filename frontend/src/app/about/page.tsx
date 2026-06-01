'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import {
  ArrowLeft, CheckCircle2, Search, Upload, X, Loader2, Sparkles, ShieldCheck, Linkedin,
} from 'lucide-react';

// ── Content ──────────────────────────────────────────────────────────────────
const INTRO = [
  'ProMechDirectory helps companies find the right mechanical engineering provider for their project without wasting time on random searches, open-ended bidding, or poorly matched quotes.',
  'Our platform is built around one core idea: engineering projects should be matched to firms based on real capability, not just visibility, price, or who responds first.',
];

const SECTIONS: Array<{ heading: string; paragraphs: string[]; bullets?: string[] }> = [
  {
    heading: 'How It Works',
    paragraphs: [
      'A customer creates a structured RFQ through ProMechDirectory. The platform reviews the project requirements and matches the RFQ to providers based on relevant factors such as:',
    ],
    bullets: [
      'Engineering capabilities',
      'Tools and software used',
      'Industries served',
      'Location and service area',
      'Company description',
      'Relevant historical project experience',
    ],
  },
  {
    heading: '',
    paragraphs: [
      'The RFQ is then sent to selected matching providers so they can review the scope, ask questions, and submit a quote.',
      'Once the customer receives 5 quotes, RFQ dispatch stops. This keeps the process focused, manageable, and more useful for both customers and providers.',
    ],
  },
  {
    heading: 'Built for Better Project Fit',
    paragraphs: [
      'The matching process is the heart of ProMechDirectory.',
      'Providers can build a private AI matching profile that includes their capabilities, tools, industries, and historical project experience. This information helps the platform understand which projects are a strong fit for each provider.',
      'Historical project details are not shown to customers, other providers, or the public. They are used only to improve matching accuracy, so providers can benefit from their experience without exposing proprietary or confidential information.',
    ],
  },
  {
    heading: 'Tools That Support the Process',
    paragraphs: [
      'ProMechDirectory is designed to reduce friction during the RFQ process. The platform includes streamlined NDA handling, direct RFQ communication, and an on-site AI agent that can help answer questions, support workflow steps, and assist with RFQ sending, receiving, and follow-up.',
      'Providers with Professional access can also see the RFQ submitter’s contact information, allowing them to reach out directly, clarify scope details, and prepare a stronger quote.',
    ],
  },
  {
    heading: 'No Project Commission',
    paragraphs: [
      'Unlike platforms that take a percentage of the project value, ProMechDirectory does not charge commission on awarded work.',
      'Providers keep their project revenue. ProMechDirectory is supported through monthly or annual provider subscriptions, which can save thousands of dollars on mid-sized and larger engineering projects.',
    ],
  },
];

const FOUNDING_BENEFITS = [
  'RFQs matched to their capabilities',
  'A private AI matching profile',
  'The ability to add historical project experience for better matching',
  'Access to RFQ submitter contact information',
  'Streamlined NDA and RFQ workflow tools',
  'Use of the on-site AI agent for workflow support',
  'A listing in the ProMechDirectory provider directory',
  'No platform commission on project revenue',
];

const SIGNATURE_PS =
  "I\u2019m a mechanical engineer myself, so I\u2019m building this around how serious engineering " +
  "work actually moves: clear scope, relevant experience, protected project details, NDAs when " +
  "needed, and less wasted back-and-forth. You can find me easily online.";

// Client-side guards (mirror the server)
const WEBSITE_RE = /^(https?:\/\/)?(www\.)?([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}(\/[^\s]*)?$/i;
const URLISH_RE = /(https?:\/\/|www\.|@|\.[a-z]{2,}(\/|$))/i;

type Status = { limit: number; sent: number; remaining: number; closed: boolean };

export default function AboutPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const loadStatus = useCallback(() => {
    api.founding.getStatus().then((r) => setStatus(r.data)).catch(() => setStatus(null));
  }, []);
  useEffect(() => { loadStatus(); }, [loadStatus]);

  const closed = status?.closed ?? false;
  const remaining = status?.remaining ?? null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-12">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-6">
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>

        <h1 className="text-4xl font-bold text-slate-900 mb-6">About ProMechDirectory</h1>
        {INTRO.map((p, i) => (
          <p key={i} className="text-slate-600 leading-relaxed mb-4">{p}</p>
        ))}

        {SECTIONS.map((sec, i) => (
          <div key={i} className="mt-8">
            {sec.heading && <h2 className="text-2xl font-bold text-slate-900 mb-3">{sec.heading}</h2>}
            {sec.paragraphs.map((p, j) => (
              <p key={j} className="text-slate-600 leading-relaxed mb-4">{p}</p>
            ))}
            {sec.bullets && (
              <ul className="space-y-2 mb-2">
                {sec.bullets.map((b, k) => (
                  <li key={k} className="flex items-start gap-2 text-slate-700">
                    <CheckCircle2 className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}

        {/* Founder signature */}
        <div className="mt-10 border-t border-slate-200 pt-6">
          <p className="text-slate-800 font-semibold">— Bassam Abdelnabi</p>
          <p className="text-slate-500 text-sm">Founder, ProMechDirectory</p>
          <a
            href="https://www.linkedin.com/in/bassam-abdelnabi-4a055a20/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mt-1"
          >
            <Linkedin className="h-4 w-4" /> linkedin.com/in/bassam-abdelnabi
          </a>
          <p className="text-slate-600 leading-relaxed text-sm mt-4">
            <span className="font-semibold">P.S.</span> {SIGNATURE_PS}
          </p>
        </div>

        {/* Founding Provider Offer */}
        <div className="mt-12 rounded-2xl border border-blue-200 bg-gradient-to-b from-blue-50 to-white p-6 sm:p-8">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="h-6 w-6 text-blue-600" />
            <h2 className="text-2xl font-bold text-slate-900">Founding Provider Offer</h2>
          </div>
          <p className="text-slate-700 leading-relaxed mb-3">
            We are currently offering 50 free Professional subscriptions to mechanical engineering
            providers who join through the link below.
          </p>
          <p className="font-semibold text-slate-800 mb-2">Founding providers receive:</p>
          <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-2 mb-5">
            {FOUNDING_BENEFITS.map((b, i) => (
              <li key={i} className="flex items-start gap-2 text-slate-700 text-sm">
                <CheckCircle2 className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-slate-500 mb-5">
            This offer is available while the 50 founding provider spots remain.
          </p>

          {closed ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-center">
              <p className="font-semibold text-slate-700">The founding provider offer is now closed.</p>
              <p className="text-sm text-slate-500 mt-1">All 50 invitations have been claimed. Thank you for your interest.</p>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <button
                onClick={() => setModalOpen(true)}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 py-3 text-white font-semibold hover:bg-blue-700 transition shadow-sm"
              >
                <Sparkles className="h-4 w-4" /> Join ProMechDirectory as a Founding Provider
              </button>
              {remaining !== null && (
                <span className="text-sm font-medium text-blue-700">
                  {remaining} of {status?.limit ?? 50} invitations left
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {modalOpen && (
        <FoundingModal
          onClose={() => setModalOpen(false)}
          onApplied={(s) => { setStatus(s); }}
        />
      )}
    </div>
  );
}

// ── Modal ────────────────────────────────────────────────────────────────────
type Step = 'search' | 'form' | 'done';

function FoundingModal({ onClose, onApplied }: {
  onClose: () => void;
  onApplied: (s: Status) => void;
}) {
  const [step, setStep] = useState<Step>('search');

  // search step
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [results, setResults] = useState<Array<{ name: string; location: string | null }>>([]);
  const [alreadyListed, setAlreadyListed] = useState(false);

  // form step
  const [name, setName] = useState('');
  const [business, setBusiness] = useState('');
  const [website, setWebsite] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);

  const runSearch = async () => {
    if (query.trim().length < 2) return;
    setSearching(true);
    try {
      const r = await api.founding.search(query.trim());
      setResults(r.data.results || []);
      setSearched(true);
    } catch {
      setResults([]); setSearched(true);
    } finally { setSearching(false); }
  };

  const goToForm = (listed: boolean) => {
    setAlreadyListed(listed);
    setBusiness((prev) => prev || query.trim());
    setStep('form');
  };

  const validate = (): string | null => {
    const n = name.trim();
    if (n.length < 2 || !/[A-Za-z]/.test(n)) return 'Please enter your full name.';
    if (URLISH_RE.test(n)) return 'Name should be a person’s name, not a website or email.';
    const b = business.trim();
    if (b.length < 2) return 'Please enter your business name.';
    if (URLISH_RE.test(b)) return 'Business name should be a name, not a website or email.';
    const w = website.trim();
    if (!WEBSITE_RE.test(w)) return 'Please enter a valid website (e.g. example.com).';
    if (files.length === 0) return 'Please attach at least one business document (brochure, capability statement, etc.).';
    return null;
  };

  const submit = async () => {
    const v = validate();
    if (v) { setErr(v); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const res = await api.founding.apply({
        applicant_name: name.trim(),
        business_name: business.trim(),
        website: website.trim(),
        already_listed: alreadyListed,
        matched_firms: alreadyListed ? results.slice(0, 5).map((r) => r.name).join('; ') : '',
        files,
      });
      setRemaining(res.remaining);
      onApplied({ limit: 0, sent: 0, remaining: res.remaining, closed: res.closed });
      setStep('done');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Something went wrong. Please try again.');
    } finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => !submitting && onClose()}>
      <div className="bg-white rounded-2xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h3 className="font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-blue-600" /> Founding Provider Application
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-5 w-5" /></button>
        </div>

        <div className="px-6 py-5">
          {step === 'search' && (
            <div className="space-y-4">
              <p className="text-sm text-slate-600">First, let&apos;s check whether your firm is already in our directory.</p>
              <div className="flex gap-2">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
                  placeholder="Your business name"
                  className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button onClick={runSearch} disabled={searching || query.trim().length < 2}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50">
                  {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search
                </button>
              </div>

              {searched && (
                <div className="space-y-3">
                  {results.length > 0 ? (
                    <>
                      <p className="text-sm text-slate-600">We found these possible matches:</p>
                      <ul className="rounded-lg border border-slate-200 divide-y divide-slate-100 max-h-40 overflow-y-auto">
                        {results.map((r, i) => (
                          <li key={i} className="px-3 py-2 text-sm">
                            <span className="font-medium text-slate-800">{r.name}</span>
                            {r.location && <span className="text-slate-400"> — {r.location}</span>}
                          </li>
                        ))}
                      </ul>
                      <p className="text-xs text-slate-500">
                        If one of these is your firm, you can still apply — we&apos;ll note that it may already be listed.
                      </p>
                      <button onClick={() => goToForm(true)} className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700">
                        Continue — my firm may be one of these
                      </button>
                      <button onClick={() => goToForm(false)} className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
                        None of these — my firm isn&apos;t listed
                      </button>
                    </>
                  ) : (
                    <>
                      <p className="text-sm text-slate-600">No matching firm found. Let&apos;s get your application started.</p>
                      <button onClick={() => goToForm(false)} className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700">
                        Continue to application
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {step === 'form' && (
            <div className="space-y-4">
              {alreadyListed && (
                <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                  <ShieldCheck className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  We&apos;ll note in your application that your firm may already be listed.
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Your name <span className="text-red-500">*</span></label>
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Smith"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Business name <span className="text-red-500">*</span></label>
                <input value={business} onChange={(e) => setBusiness(e.target.value)} placeholder="Acme Engineering LLC"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Business website <span className="text-red-500">*</span></label>
                <input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="example.com"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Business documents <span className="text-red-500">*</span></label>
                <p className="text-xs text-slate-500 mb-2">Brochures, capability statements, or similar. Required. PDF, Word, PowerPoint, Excel, images (max 8 MB each).</p>
                <label className="flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 px-4 py-4 text-sm text-slate-500 cursor-pointer hover:border-blue-400 hover:bg-blue-50/30">
                  <Upload className="h-4 w-4" /> Choose files
                  <input type="file" multiple className="hidden"
                    accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.rtf,.odt"
                    onChange={(e) => setFiles(Array.from(e.target.files || []))} />
                </label>
                {files.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {files.map((f, i) => (
                      <li key={i} className="text-xs text-slate-600 flex items-center gap-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> {f.name}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {err && <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{err}</div>}

              <div className="flex gap-2 pt-1">
                <button onClick={() => setStep('search')} disabled={submitting}
                  className="px-4 py-2.5 text-sm font-medium text-slate-600 hover:text-slate-800 disabled:opacity-50">Back</button>
                <button onClick={submit} disabled={submitting}
                  className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                  {submitting ? <><Loader2 className="h-4 w-4 animate-spin" /> Submitting…</> : 'Submit application'}
                </button>
              </div>
            </div>
          )}

          {step === 'done' && (
            <div className="text-center py-6">
              <div className="mx-auto w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-3">
                <CheckCircle2 className="h-7 w-7 text-green-600" />
              </div>
              <h4 className="font-bold text-slate-900 mb-1">Application submitted</h4>
              <p className="text-sm text-slate-600">
                Thanks! We&apos;ve received your founding provider application and will be in touch by email.
              </p>
              {remaining !== null && (
                <p className="text-sm font-medium text-blue-700 mt-3">{remaining} founding invitations remaining</p>
              )}
              <button onClick={onClose} className="mt-5 rounded-lg bg-slate-800 px-5 py-2 text-sm font-medium text-white hover:bg-slate-900">Close</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
