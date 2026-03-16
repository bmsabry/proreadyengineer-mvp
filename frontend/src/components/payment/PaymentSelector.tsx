"use client";

import { useState } from "react";
import { CreditCard } from "lucide-react";
import PayPalButton, { PayPalButtonProps } from "./PayPalButton";

type PaymentMethod = "stripe" | "paypal";

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
  paypal: Omit<PayPalButtonProps, "type">;
  onSuccess?: (method: PaymentMethod, data: Record<string, unknown>) => void;
  onError?: (method: PaymentMethod, error: string) => void;
  className?: string;
}

export default function PaymentSelector({
  type,
  label = "Select payment method",
  stripe,
  paypal,
  onSuccess,
  onError,
  className = "",
}: PaymentSelectorProps) {
  const [selected, setSelected] = useState<PaymentMethod>("stripe");
  const [stripeProcessing, setStripeProcessing] = useState(false);

  const handleStripeClick = async () => {
    setStripeProcessing(true);
    try {
      await stripe.onStripeCheckout();
    } finally {
      setStripeProcessing(false);
    }
  };

  return (
    <div className={`space-y-4 ${className}`}>
      {label && <p className="text-sm font-medium text-gray-700">{label}</p>}

      {/* Method selector */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setSelected("stripe")}
          className={`flex items-center justify-center gap-2 rounded-md border px-4 py-3 text-sm font-medium transition-colors ${
            selected === "stripe"
              ? "border-blue-600 bg-blue-50 text-blue-700"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50"
          }`}
        >
          <CreditCard className="h-4 w-4" />
          Card / Stripe
        </button>

        <button
          type="button"
          onClick={() => setSelected("paypal")}
          className={`flex items-center justify-center gap-2 rounded-md border px-4 py-3 text-sm font-medium transition-colors ${
            selected === "paypal"
              ? "border-blue-600 bg-blue-50 text-blue-700"
              : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50"
          }`}
        >
          {/* PayPal logo text */}
          <span className="font-bold">
            <span className="text-blue-800">Pay</span>
            <span className="text-blue-500">Pal</span>
          </span>
        </button>
      </div>

      {/* Stripe panel */}
      {selected === "stripe" && (
        <div className="space-y-3">
          <button
            type="button"
            onClick={handleStripeClick}
            disabled={stripe.stripeDisabled || stripeProcessing}
            className="w-full rounded-md bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {stripeProcessing
              ? "Redirecting to Stripe..."
              : stripe.stripeLabel ?? "Pay with Card"}
          </button>
          <p className="text-center text-xs text-gray-400">
            Powered by Stripe &mdash; all major cards accepted
          </p>
        </div>
      )}

      {/* PayPal panel */}
      {selected === "paypal" && (
        <div className="space-y-3">
          <PayPalButton
            {...paypal}
            type={type}
            onSuccess={(data) => onSuccess?.("paypal", data)}
            onError={(err) => onError?.("paypal", err instanceof Error ? err.message : String(err))}
          />
          <p className="text-center text-xs text-gray-400">
            You will be redirected to PayPal to complete payment
          </p>
        </div>
      )}
    </div>
  );
}
