"use client";

import { useEffect, useRef, useState } from "react";

export interface PayPalButtonProps {
  /** one-time order or recurring subscription */
  type: "order" | "subscription";
  purpose: string;
  amountUsd?: number;
  relatedEntityType?: string;
  relatedEntityId?: string;
  subscriptionType?: string;
  onSuccess?: (data: Record<string, unknown>) => void;
  onError?: (err: unknown) => void;
  className?: string;
}

interface PayPalConfig {
  client_id: string;
  mode: string;
  enabled: boolean;
}

// Minimal PayPal SDK type declarations
declare global {
  interface Window {
    paypal?: {
      Buttons: (
        config: Record<string, unknown>
      ) => { render: (selector: string) => Promise<void> };
    };
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function PayPalButton({
  type,
  purpose,
  amountUsd,
  relatedEntityType,
  relatedEntityId,
  subscriptionType,
  onSuccess,
  onError,
  className = "",
}: PayPalButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [sdkError, setSdkError] = useState<string | null>(null);
  const [sdkReady, setSdkReady] = useState(false);

  const isSubscription = type === "subscription" || Boolean(subscriptionType);

  useEffect(() => {
    let cancelled = false;

    async function initPayPal() {
      try {
        const res = await fetch(`${API_BASE}/payments/paypal/config`, {
          credentials: "include",
        });
        if (!res.ok) throw new Error("Failed to load PayPal config");
        const config: PayPalConfig = await res.json();
        if (!config.client_id || !config.enabled) throw new Error("PayPal not configured");

        if (window.paypal) {
          if (!cancelled) { setSdkReady(true); setLoading(false); }
          return;
        }

        const src = isSubscription
          ? `https://www.paypal.com/sdk/js?client-id=${config.client_id}&currency=USD&vault=true&intent=subscription`
          : `https://www.paypal.com/sdk/js?client-id=${config.client_id}&currency=USD&intent=capture`;

        const script = document.createElement("script");
        script.src = src;
        script.async = true;
        script.onload = () => {
          if (!cancelled) { setSdkReady(true); setLoading(false); }
        };
        script.onerror = () => {
          if (!cancelled) { setSdkError("Failed to load PayPal SDK"); setLoading(false); }
        };
        document.body.appendChild(script);
      } catch (err) {
        if (!cancelled) {
          setSdkError(err instanceof Error ? err.message : "PayPal unavailable");
          setLoading(false);
        }
      }
    }

    initPayPal();
    return () => { cancelled = true; };
  }, [isSubscription]);

  useEffect(() => {
    if (!sdkReady || !containerRef.current || !window.paypal) return;
    const container = containerRef.current;
    container.innerHTML = "";
    const id = `pp-btn-${Math.random().toString(36).slice(2)}`;
    container.id = id;

    const cfg: Record<string, unknown> = {
      style: { layout: "vertical", color: "gold", shape: "rect",
               label: isSubscription ? "subscribe" : "pay" },
      onError: (err: unknown) => { console.error("PayPal error", err); onError?.(err); },
      onCancel: () => console.log("PayPal cancelled"),
      ...(isSubscription ? {
        createSubscription: async () => {
          const r = await fetch(`${API_BASE}/payments/paypal/create-subscription`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ subscription_type: subscriptionType }),
          });
          if (!r.ok) throw new Error("Failed to create subscription");
          const { subscription_id } = await r.json();
          return subscription_id;
        },
        onApprove: (data: Record<string, unknown>) => { onSuccess?.(data); },
      } : {
        createOrder: async () => {
          const r = await fetch(`${API_BASE}/payments/paypal/create-order`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({
              purpose,
              amount_usd: amountUsd,
              related_entity_type: relatedEntityType,
              related_entity_id: relatedEntityId,
            }),
          });
          if (!r.ok) throw new Error("Failed to create order");
          const { order_id } = await r.json();
          return order_id;
        },
        onApprove: async (data: Record<string, unknown>) => {
          const r = await fetch(`${API_BASE}/payments/paypal/capture-order`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ order_id: data.orderID }),
          });
          if (!r.ok) throw new Error("Capture failed");
          const result = await r.json();
          onSuccess?.(result);
        },
      }),
    };

    window.paypal.Buttons(cfg).render(`#${id}`).catch(console.error);
  }, [sdkReady, isSubscription, purpose, amountUsd, relatedEntityType, relatedEntityId,
      subscriptionType, onSuccess, onError]);

  if (loading) return (
    <div className={`flex items-center justify-center p-4 ${className}`}>
      <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-500" />
      <span className="ml-2 text-sm text-gray-500">Loading PayPal...</span>
    </div>
  );

  if (sdkError) return (
    <div className={`p-3 text-sm text-red-600 bg-red-50 rounded ${className}`}>
      {sdkError}
    </div>
  );

  return <div ref={containerRef} className={className} />;
}

export default PayPalButton;
