'use client'
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html>
      <body>
        <div style={{padding:'2rem', fontFamily:'sans-serif'}}>
          <h2 style={{color:'red'}}>Critical Error</h2>
          <p>{error.message}</p>
          <pre style={{background:'#f5f5f5',padding:'1rem',fontSize:'12px',overflow:'auto'}}>{error.stack}</pre>
          <button onClick={reset} style={{marginTop:'1rem',padding:'0.5rem 1rem',background:'blue',color:'white',border:'none',borderRadius:'4px',cursor:'pointer'}}>Reload</button>
        </div>
      </body>
    </html>
  )
}
