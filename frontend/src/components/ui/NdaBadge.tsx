'use client';

import React from 'react';

/**
 * Maps NDA status to a human-readable badge with appropriate color scheme.
 *
 * Statuses:
 * - not_required: no badge shown
 * - payment_pending: "NDA Pending Payment"  (amber)
 * - customer_signature_pending: "Customer Signing" (amber)
 * - provider_signature_pending: "Provider Signing"  (blue)
 * - fully_signed: "NDA Signed" (green)
 * - failed: "NDA Failed" (red)
 * - cancelled: "NDA Cancelled" (gray)
 */

interface NdaBadgeProps {
  ndaRequired?: boolean;
  ndaStatus?: string;
  /** compact = short label for list rows; full = longer label */
  variant?: 'compact' | 'full';
}

const CONFIG: Record<string, { label: string; shortLabel: string; bg: string; text: string; border: string }> = {
  payment_pending:              { label: 'NDA Pending Payment',   shortLabel: 'NDA Pending',     bg: 'bg-amber-100',   text: 'text-amber-700',   border: 'border-amber-200' },
  customer_signature_pending:   { label: 'Customer Signing',      shortLabel: 'Customer Signing', bg: 'bg-amber-100',   text: 'text-amber-700',   border: 'border-amber-200' },
  provider_signature_pending:   { label: 'Provider Signing',      shortLabel: 'Provider Signing', bg: 'bg-blue-100',    text: 'text-blue-700',    border: 'border-blue-200' },
  fully_signed:                 { label: 'NDA Signed',            shortLabel: 'NDA Signed',       bg: 'bg-green-100',   text: 'text-green-700',   border: 'border-green-200' },
  failed:                       { label: 'NDA Failed',            shortLabel: 'NDA Failed',       bg: 'bg-red-100',     text: 'text-red-700',     border: 'border-red-200' },
  cancelled:                    { label: 'NDA Cancelled',         shortLabel: 'NDA Cancelled',    bg: 'bg-gray-100',    text: 'text-gray-500',    border: 'border-gray-200' },
};

export default function NdaBadge({ ndaRequired, ndaStatus, variant = 'compact' }: NdaBadgeProps) {
  // If NDA is not required or status is explicitly not_required, render nothing
  if (!ndaRequired) return null;

  const status = ndaStatus || 'payment_pending';
  if (status === 'not_required') return null;

  const cfg = CONFIG[status];

  // Fallback for unknown status: default purple "NDA Required" badge
  if (!cfg) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 border border-purple-200">
        NDA Required
      </span>
    );
  }

  const label = variant === 'compact' ? cfg.shortLabel : cfg.label;

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${cfg.bg} ${cfg.text} border ${cfg.border}`}>
      {label}
    </span>
  );
}
