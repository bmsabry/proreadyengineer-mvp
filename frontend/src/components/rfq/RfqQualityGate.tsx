'use client';

import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';

/** Structured payload returned in `error.response.data.detail` (HTTP 422) by the
 *  RFQ completeness gate, or in a successful response's `quality_warning`. */
export type QualityGate = {
  ok?: boolean;
  reason?: 'rfq_incomplete' | 'rfq_terminally_blocked' | 'rfq_support_escalated';
  terminal?: boolean;
  message?: string;
  missing?: string[];
  suggestions?: string[];
  summary?: string;
  score?: number;
  attempts_used?: number;
  attempts_max?: number;
  ai_help?: boolean;
};

/** Pull a gate payload out of an Axios error, or return null if it's an ordinary error. */
export function extractQualityGate(err: unknown): QualityGate | null {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === 'object') {
    const d = detail as QualityGate;
    if (typeof d.reason === 'string' && d.reason.startsWith('rfq_')) return d;
  }
  return null;
}

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-sm font-semibold text-slate-700">{title}</p>
      <ul className="mt-1 list-disc pl-5 space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-sm text-slate-600">{it}</li>
        ))}
      </ul>
    </div>
  );
}

/** Modal panel that explains why an RFQ was held back and offers the right next step. */
export default function RfqQualityGate({
  gate,
  onClose,
}: {
  gate: QualityGate;
  onClose: () => void;
}) {
  const router = useRouter();
  const reason = gate.reason;

  const heading =
    reason === 'rfq_terminally_blocked'
      ? "This RFQ can't be submitted"
      : reason === 'rfq_support_escalated'
        ? "We're bringing in our team to help"
        : 'Your RFQ needs a few more details';

  const isIncomplete = reason === 'rfq_incomplete';

  const openAssistant = () => {
    onClose();
    const seed =
      'Please help me complete this RFQ so it meets industry standards. ' +
      (gate.missing && gate.missing.length
        ? 'It is currently missing: ' + gate.missing.join(', ') + '.'
        : '');
    window.dispatchEvent(new CustomEvent('promech:open-help', { detail: { seed } }));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-white shadow-xl border border-slate-200 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-[#0F2B54]">{heading}</h2>

        {gate.summary && isIncomplete && (
          <p className="mt-2 text-sm text-slate-600">{gate.summary}</p>
        )}
        {gate.message && !isIncomplete && (
          <p className="mt-2 text-sm text-slate-600">{gate.message}</p>
        )}

        {isIncomplete && (
          <>
            <p className="mt-2 text-sm text-slate-600">
              Providers pay to unlock each RFQ, so we hold back ones that aren&apos;t complete
              enough to quote accurately. Add the items below and resubmit.
            </p>
            <List title="Missing or unclear" items={gate.missing} />
            <List title="Suggestions" items={gate.suggestions} />
            {typeof gate.attempts_used === 'number' && typeof gate.attempts_max === 'number' && (
              <p className="mt-3 text-xs text-slate-500 tabular-nums">
                Attempt {gate.attempts_used} of {gate.attempts_max}
              </p>
            )}
          </>
        )}

        <div className="mt-6 flex flex-wrap gap-3 justify-end">
          {isIncomplete && gate.ai_help && (
            <Button onClick={openAssistant} className="bg-[#0F2B54] hover:bg-[#0a1f3e] text-white">
              Let the AI assistant complete this
            </Button>
          )}
          {isIncomplete && !gate.ai_help && (
            <Button
              onClick={() => {
                onClose();
                router.push('/billing');
              }}
              className="bg-[#0F2B54] hover:bg-[#0a1f3e] text-white"
            >
              Unlock the AI assistant
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            {isIncomplete ? 'Edit it myself' : 'Got it'}
          </Button>
        </div>

        {isIncomplete && !gate.ai_help && (
          <p className="mt-3 text-xs text-slate-500">
            A Search subscription unlocks an AI assistant that completes RFQs for you from a
            spec sheet or a few details.
          </p>
        )}
      </div>
    </div>
  );
}
