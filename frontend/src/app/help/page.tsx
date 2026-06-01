'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { helpApi, type HelpStatus } from '@/lib/api';
import { ArrowLeft, Sparkles, Lock } from 'lucide-react';

// Lightweight markdown renderer — we do not have a Markdown lib in the bundle,
// and we trust the source (our own repo), but we still escape HTML defensively.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderMarkdown(md: string): string {
  const lines = md.split(/\r?\n/);
  const out: string[] = [];
  let inList = false;
  let inBlockquote = false;
  let inCode = false;

  const close = () => {
    if (inList) { out.push('</ul>'); inList = false; }
    if (inBlockquote) { out.push('</blockquote>'); inBlockquote = false; }
  };

  const inlineMd = (s: string) =>
    escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code class="bg-slate-100 px-1 py-0.5 rounded text-xs">$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a class="text-[#0F2B54] underline" href="$2">$1</a>');

  for (const raw of lines) {
    const line = raw;
    if (line.trim().startsWith('```')) { inCode = !inCode; out.push(inCode ? '<pre class="bg-slate-900 text-slate-100 p-3 rounded-md overflow-x-auto text-xs my-3">' : '</pre>'); continue; }
    if (inCode) { out.push(escapeHtml(line) + '\n'); continue; }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { close(); const lvl = h[1].length; out.push(`<h${lvl} class="font-semibold text-slate-900 mt-6 mb-2 ${lvl === 1 ? 'text-2xl' : lvl === 2 ? 'text-xl' : 'text-lg'}">${inlineMd(h[2])}</h${lvl}>`); continue; }

    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { close(); out.push('<ul class="list-disc pl-6 space-y-1 text-slate-700 my-2">'); inList = true; }
      out.push(`<li>${inlineMd(line.replace(/^\s*[-*]\s+/, ''))}</li>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      // we'll treat numbered as a sequence of <p> with a small prefix
      close();
      out.push(`<p class="text-slate-700 ml-4 my-1">${inlineMd(line.trim())}</p>`);
      continue;
    }

    if (/^>\s+/.test(line)) {
      if (!inBlockquote) { close(); out.push('<blockquote class="border-l-4 border-slate-300 pl-3 text-slate-600 italic my-3">'); inBlockquote = true; }
      out.push(`<p>${inlineMd(line.replace(/^>\s+/, ''))}</p>`);
      continue;
    }

    if (line.trim() === '---') { close(); out.push('<hr class="my-6 border-slate-200" />'); continue; }

    if (line.trim() === '') { close(); out.push(''); continue; }

    close();
    out.push(`<p class="text-slate-700 my-2 leading-relaxed">${inlineMd(line)}</p>`);
  }
  close();
  if (inCode) out.push('</pre>');
  return out.join('\n');
}

export default function HelpPage() {
  const [markdown, setMarkdown] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<HelpStatus | null>(null);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    Promise.all([helpApi.manual(), helpApi.status().catch(() => null)])
      .then(([m, s]) => {
        if (cancel) return;
        setMarkdown(m.markdown || '');
        setStatus(s);
      })
      .catch(() => { if (!cancel) setMarkdown('Could not load the help manual. Please try again later.'); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, []);

  const html = renderMarkdown(markdown);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="inline-flex items-center gap-2 text-sm text-slate-700 hover:text-slate-900">
            <ArrowLeft className="h-4 w-4" /> Back to home
          </Link>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Sparkles className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">ProMechDirectory Help</span>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {/* Chatbot CTA */}
        {status && !status.has_access && (
          <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start gap-3">
            <Lock className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-amber-900">
              <div className="font-semibold mb-1">Want instant answers?</div>
              <div className="text-amber-800">
                Our AI Help Assistant answers any question about the platform. It's included with any paid subscription (Customer Search subscription or Provider Profile/Annual).{' '}
                <Link href={status.authenticated ? '/customer/dashboard' : '/register'} className="underline font-medium">
                  {status.authenticated ? 'View plans' : 'Sign up'}
                </Link>{' '}
                to unlock it.
              </div>
            </div>
          </div>
        )}
        {status && status.has_access && (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3">
            <Sparkles className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-emerald-900">
              <span className="font-semibold">AI Help Assistant is active.</span>{' '}
              Click the chat bubble in the lower-right to ask anything.
            </div>
          </div>
        )}

        {loading && <div className="text-sm text-slate-500">Loading manual...</div>}
        {!loading && (
          <article
            className="prose prose-slate max-w-none bg-white border border-slate-200 rounded-xl p-6"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
      </main>
    </div>
  );
}
