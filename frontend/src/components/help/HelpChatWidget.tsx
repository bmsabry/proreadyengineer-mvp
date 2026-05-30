'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { helpApi } from '@/lib/api';
import type { HelpChatTurn, HelpStatus } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { MessageCircle, X, Send, Lock, Sparkles } from 'lucide-react';

// Routes where we do NOT show the chat bubble (to keep login/legal pages clean).
const HIDDEN_PREFIXES = [
  '/login',
  '/register',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
  '/check-email',
  '/privacy',
  '/terms',
  '/nda',
];

type Msg = { role: 'user' | 'assistant'; content: string };

export default function HelpChatWidget() {
  const pathname = usePathname() || '';
  const router = useRouter();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<HelpStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const hidden = HIDDEN_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'));

  useEffect(() => {
    if (!open) return;
    let cancel = false;
    setLoadingStatus(true);
    helpApi
      .status()
      .then((s) => { if (!cancel) setStatus(s); })
      .catch(() => { if (!cancel) setStatus(null); })
      .finally(() => { if (!cancel) setLoadingStatus(false); });
    return () => { cancel = true; };
  }, [open, user]);

  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [messages, open]);

  const onSubscribeClick = () => {
    setOpen(false);
    if (!user) {
      router.push('/register');
      return;
    }
    const roles = user.roles || [];
    if (roles.includes('provider')) {
      router.push('/provider/upgrade');
    } else {
      router.push('/customer/dashboard');
    }
  };

  const onSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setError(null);
    setInput('');
    const nextMsgs: Msg[] = [...messages, { role: 'user', content: text }];
    setMessages(nextMsgs);
    setSending(true);
    try {
      const history: HelpChatTurn[] = nextMsgs.slice(-10);
      const page = typeof window !== 'undefined' ? window.location.pathname : undefined;
      const resp = await helpApi.chat(text, history, page);
      setMessages((prev) => [...prev, { role: 'assistant', content: resp.reply }]);
      if (status && typeof resp.remaining_today === 'number') {
        setStatus({ ...status, remaining_today: resp.remaining_today });
      }
    } catch (e) {
      const err = e as Error & { code?: number; message?: string };
      if (err.code === 402) {
        setStatus((s) => (s ? { ...s, has_access: false, reason: 'no_active_subscription' } : s));
      } else if (err.code === 429) {
        setError("You've reached the daily limit. Try again tomorrow.");
      } else {
        // Surface the underlying message so non-obvious failures (422, 500, etc.)
        // are diagnosable instead of always reading 'Something went wrong'.
        const msg = (err?.message || '').trim();
        setError(msg ? `Couldn't reach the assistant: ${msg}` : 'Something went wrong. Please try again.');
      }
    } finally {
      setSending(false);
    }
  };

  if (hidden) return null;

  return (
    <>
      {/* Floating bubble */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-[#0F2B54] text-white px-4 py-3 shadow-lg hover:shadow-xl hover:bg-[#143a6f] transition-all"
          aria-label="Open AI Help Assistant"
        >
          <MessageCircle className="h-5 w-5" />
          <span className="text-sm font-medium hidden sm:inline">AI Help</span>
        </button>
      )}

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 w-[92vw] max-w-md h-[70vh] max-h-[640px] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-[#0F2B54] text-white">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              <div>
                <div className="text-sm font-semibold leading-tight">AI Help Assistant</div>
                <div className="text-[11px] text-white/70 leading-tight">
                  {status?.has_access
                    ? 'Included with your subscription'
                    : 'Subscriber-only feature'}
                </div>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded hover:bg-white/10"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Body */}
          <div ref={scrollerRef} className="flex-1 overflow-y-auto px-4 py-3 bg-slate-50">
            {loadingStatus && (
              <div className="text-center text-xs text-slate-500 py-6">Loading...</div>
            )}
            {!loadingStatus && status && !status.has_access && (
              <PaywallView status={status} onSubscribe={onSubscribeClick} />
            )}
            {!loadingStatus && status && status.has_access && (
              <>
                {messages.length === 0 && (
                  <div className="text-xs text-slate-600 bg-white border border-slate-200 rounded-lg p-3 mb-3">
                    <div className="font-semibold text-slate-800 mb-1">Ask me about ProMechDirectory.</div>
                    <ul className="list-disc pl-5 space-y-0.5 text-slate-600">
                      <li>How do I submit an RFQ?</li>
                      <li>How do unlock fees work?</li>
                      <li>How do I cancel my subscription?</li>
                      <li>What is a tollgate (TG0-TG6)?</li>
                    </ul>
                    {typeof status.remaining_today === 'number' && (
                      <div className="mt-2 text-[11px] text-slate-500">
                        {status.remaining_today} of {status.daily_limit} messages left today
                      </div>
                    )}
                  </div>
                )}
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`mb-2 flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                        m.role === 'user'
                          ? 'bg-[#0F2B54] text-white'
                          : 'bg-white border border-slate-200 text-slate-800'
                      }`}
                    >
                      {m.content}
                    </div>
                  </div>
                ))}
                {sending && (
                  <div className="flex justify-start mb-2">
                    <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 text-sm text-slate-500">
                      thinking...
                    </div>
                  </div>
                )}
                {error && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-2 mb-2">
                    {error}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Input / footer */}
          {status?.has_access ? (
            <div className="border-t border-slate-200 p-2 bg-white">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      onSend();
                    }
                  }}
                  placeholder="Ask a question..."
                  className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#0F2B54]/30"
                  disabled={sending}
                  maxLength={2000}
                />
                <button
                  onClick={onSend}
                  disabled={sending || !input.trim()}
                  className="p-2 rounded-lg bg-[#0F2B54] text-white hover:bg-[#143a6f] disabled:opacity-50"
                  aria-label="Send"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
              <div className="text-[10px] text-slate-400 mt-1 px-1">
                Grounded on the platform manual. Not legal or engineering advice.
              </div>
            </div>
          ) : (
            <div className="border-t border-slate-200 p-3 bg-white">
              <button
                onClick={onSubscribeClick}
                className="w-full py-2 rounded-lg bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#143a6f]"
              >
                {status?.authenticated ? 'View subscription plans' : 'Sign up / Log in'}
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

function PaywallView({ status, onSubscribe }: { status: HelpStatus; onSubscribe: () => void }) {
  const authenticated = status.authenticated;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 text-slate-700">
      <div className="flex items-center gap-2 mb-2">
        <Lock className="h-4 w-4 text-amber-600" />
        <div className="font-semibold text-slate-900 text-sm">Subscribers only</div>
      </div>
      <p className="text-sm text-slate-600 mb-3">
        The AI Help Assistant answers any question about how ProMechDirectory works - RFQs, quotes,
        unlocks, NDAs, billing, and more. It's included with any paid subscription.
      </p>
      <div className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 mb-3 border border-slate-100">
        <div className="font-medium text-slate-800 mb-1">Included with:</div>
        <ul className="list-disc pl-4 space-y-0.5">
          <li>Customer Search subscription (monthly)</li>
          <li>Provider Profile monthly or Provider Annual</li>
        </ul>
      </div>
      {!authenticated && (
        <p className="text-xs text-slate-500 mb-2">Log in first, then pick a plan.</p>
      )}
      <button
        onClick={onSubscribe}
        className="w-full py-2 rounded-lg bg-[#0F2B54] text-white text-sm font-medium hover:bg-[#143a6f]"
      >
        {authenticated ? 'View subscription plans' : 'Sign up / Log in'}
      </button>
    </div>
  );
}
