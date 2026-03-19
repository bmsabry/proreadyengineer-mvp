'use client'
import { useEffect } from 'react'
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('App Error:', error)
  }, [error])
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white border border-red-200 rounded-lg p-6 shadow">
        <h2 className="text-xl font-bold text-red-700 mb-2">Something went wrong</h2>
        <p className="text-gray-600 mb-2 text-sm">{error.message}</p>
        {error.digest && <p className="text-xs text-gray-400 mb-4">Error ID: {error.digest}</p>}
        <pre className="bg-gray-50 text-xs p-3 rounded overflow-auto max-h-40 mb-4 text-red-800">{error.stack}</pre>
        <button onClick={reset} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700">Try again</button>
      </div>
    </div>
  )
}
