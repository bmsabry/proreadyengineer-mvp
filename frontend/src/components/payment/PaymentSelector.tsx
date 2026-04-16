"use client";

import { useState } from "react";
import { CreditCard, Loader2 } from "lucide-react";

interface StripeConfig {
  onStripeCheckout: () => void | Promise<void>;
  stripeLabel?: string;
  stripeLoading?: boolean;
  stripeDisabled?: boolean;
}

export interface PaymentSelectorProps {
  /** one-time order or recurring subscription */
  type: "order" | "subscription";
  label?: string;
  stripe: StripeConfig;
  onSuccess?: (method: "stripe", data: Record<string, unknown>) => void;
  onError?: (method: "stripe", error: string) => void;
  className?: string;
}

export default function PaymentSelector({
  label = "Pay securely",
  stripe,
  className = "",
}: PaymentSelectorProps) {
  const [stripeProcessing, setStripeProcessing] = useState(false);

  const handleStripeClick = async () => {
    setStripeProcessing(true);
    try {
      await stripe.onStripeCheckout();
    } finally {
      setStripeProcessing(false);
    }
  };

  const isDisabled = stripe.stripeDisabled || stripeProcessing || stripe.stripeLoading;

  return (
    <div className={`space-y-3 ${className}`}>
      {label && <p className="text-sm font-medium text-gray-700">{label}</p>}

      <button
        type="button"
        onClick={handleStripeClick}
        disabled={isDisabled}
        className="w-full flex items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {(stripeProcessing || stripe.stripeLoading) ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Redirecting to Stripe...
          </>
        ) : (
          <>
            <CreditCard className="h-4 w-4" />
            {stripe.stripeLabel ?? "Pay with Card"}
          </>
        )}
      </button>

      <p className="text-center text-xs text-gray-400">
        Powered by Stripe &mdash; all major cards accepted
      </p>
    </div>
  );
}
