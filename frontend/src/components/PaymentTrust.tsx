import Link from 'next/link';
import { Lock, ShieldCheck } from 'lucide-react';

/**
 * Trust reassurance shown next to a checkout button.
 * `refund` controls the (accurate) refund note:
 *  - "subscription": refundable within the window (cancel anytime)
 *  - "one-time": one-time fee for immediate access (non-refundable per Terms)
 *  - "none": no refund note
 */
export default function PaymentTrust({
  refund = 'none',
  className = '',
}: {
  refund?: 'subscription' | 'one-time' | 'none';
  className?: string;
}) {
  return (
    <div className={`flex flex-col items-center gap-1.5 text-center ${className}`}>
      <div className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600">
        <Lock className="h-3.5 w-3.5 text-emerald-600 flex-shrink-0" />
        <span>
          Secure checkout via <span className="font-semibold text-slate-700">Stripe</span> — your card
          details are never stored on our servers.
        </span>
      </div>
      {refund === 'subscription' && (
        <p className="text-[11px] text-slate-500">
          Cancel anytime. Refundable within 14 days (annual) or 5 days (monthly).
        </p>
      )}
      {refund === 'one-time' && (
        <p className="text-[11px] text-slate-500">
          One-time fee for immediate access. See our{' '}
          <Link href="/terms" className="text-primary hover:underline">refund policy</Link>.
        </p>
      )}
      <Link
        href="/trust"
        className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
      >
        <ShieldCheck className="h-3 w-3" /> How we keep your payments &amp; projects safe
      </Link>
    </div>
  );
}
