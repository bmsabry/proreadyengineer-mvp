"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Admin section error:", error.message, error.stack);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8">
      <div className="max-w-2xl w-full bg-red-50 border border-red-200 rounded-lg p-6 space-y-4">
        <h2 className="text-xl font-bold text-red-800">Admin Page Error</h2>
        <div className="bg-white border border-red-100 rounded p-3">
          <p className="text-red-700 text-sm font-mono font-bold">{error.message}</p>
        </div>
        {error.digest && (
          <p className="text-xs text-red-500">Digest: {error.digest}</p>
        )}
        {error.stack && (
          <div className="bg-gray-900 rounded p-3 overflow-x-auto">
            <pre className="text-xs text-green-400 whitespace-pre-wrap">{error.stack}</pre>
          </div>
        )}
        <Button onClick={reset} variant="outline" className="w-full">
          Try Again
        </Button>
      </div>
    </div>
  );
}
