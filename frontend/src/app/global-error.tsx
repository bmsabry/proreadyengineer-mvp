"use client"

import { useEffect, useState } from "react"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    // Log error for debugging
    console.error("Global error caught:", error);
  }, [error]);

  const handleRetry = () => {
    if (retryCount < 2) {
      setRetryCount(prev => prev + 1);
      reset();
    } else {
      // After 2 failed retries, do a full page reload to break any loops
      if (typeof window !== "undefined") {
        window.location.href = "/";
      }
    }
  };

  return (
    <html>
      <body>
        <div style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#fafafa"
        }}>
          <div style={{
            maxWidth: "500px",
            width: "100%",
            background: "white",
            borderRadius: "12px",
            padding: "2rem",
            boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
            border: "1px solid #e5e7eb"
          }}>
            <h2 style={{ color: "#dc2626", margin: "0 0 1rem 0", fontSize: "1.25rem" }}>
              Something went wrong
            </h2>
            <p style={{ color: "#6b7280", margin: "0 0 1rem 0", fontSize: "0.875rem" }}>
              {error?.message || "An unexpected error occurred"}
            </p>
            {error?.digest && (
              <p style={{ color: "#9ca3af", margin: "0 0 1rem 0", fontSize: "0.75rem" }}>
                Error ID: {error.digest}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                onClick={handleRetry}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#2563eb",
                  color: "white",
                  border: "none",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.875rem"
                }}
              >
                {retryCount < 2 ? "Try Again" : "Go Home"}
              </button>
              <button
                onClick={() => { if (typeof window !== "undefined") window.location.href = "/"; }}
                style={{
                  padding: "0.5rem 1rem",
                  background: "#f3f4f6",
                  color: "#374151",
                  border: "1px solid #d1d5db",
                  borderRadius: "6px",
                  cursor: "pointer",
                  fontSize: "0.875rem"
                }}
              >
                Reload Page
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
