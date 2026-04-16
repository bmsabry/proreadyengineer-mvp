"use client";

// PayPal has been removed from customer-facing flows.
// This stub exists to prevent import errors from any remaining references.

export interface PayPalButtonProps {
  type: "order" | "subscription";
  purpose?: string;
  amountUsd?: number;
  relatedEntityType?: string;
  relatedEntityId?: string;
  subscriptionType?: string;
  onSuccess?: (data: Record<string, unknown>) => void;
  onError?: (err: unknown) => void;
  className?: string;
}

export function PayPalButton(_props: PayPalButtonProps) {
  return null;
}

export default PayPalButton;
