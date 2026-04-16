"use client"

import { useEffect, useState } from "react"

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    console.error("App error:", error);
  }, [error]);

  const handleRetry = () => {
    if (retryCount < 2) {
      setRetryCount(prev => prev + 1);
      reset();
    } else {
      if (typeof window !== "undefined") {
        window.location.href = "/";
      }
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white border border-red-200 rounded-lg p-6 shadow">
        <h2 className="text-xl font-bold text-red-700 mb-2">Something went wrong</h2>
        <p className="text-gray-600 mb-2 text-sm">{error?.message || "An unexpected error occurred"}</p>
        {error?.digest && <p className="text-xs text-gray-400 mb-4">Error ID: {error.digest}</p>}
        <div className="flex gap-2">
          <button onClick={handleRetry} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700">
            {retryCount < 2 ? "Try Again" : "Go Home"}
          </button>
          <button onClick={() => { if (typeof window !== "undefined") window.location.reload(); }} className="bg-gray-100 text-gray-700 px-4 py-2 rounded text-sm border hover:bg-gray-200">
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
}
