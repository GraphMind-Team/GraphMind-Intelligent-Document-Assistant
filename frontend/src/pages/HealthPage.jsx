import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Proves frontend/backend integration end-to-end (Story 1.1): calls the
// backend's neutral /health endpoint and renders whatever it returns. If
// the backend is unreachable, this shows a visible error instead of a
// silent blank screen.
//
// Story 1.2: retrofitted to token-based classes (no hardcoded slate/red).
// Its temporary dev-only theme toggle was removed in Story 5.2, which
// shipped the real Settings appearance toggle it stood in for.
export default function HealthPage() {
  const [status, setStatus] = useState('loading')
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE_URL}/health`)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Backend responded with status ${res.status}`)
        }
        return res.json()
      })
      .then((data) => {
        if (cancelled) return
        setHealth(data)
        setStatus('ok')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg p-8 text-center">
      <h1 className="text-page-title font-bold text-primary">GraphMind</h1>
      <p className="text-body text-text2">Backend health check</p>

      {status === 'loading' && (
        <p className="text-body text-text2">Checking backend at {API_BASE_URL}...</p>
      )}

      {status === 'ok' && (
        <pre className="rounded-lg border border-border bg-bg px-4 py-3 text-left text-body text-text shadow-sm">
          {JSON.stringify(health, null, 2)}
        </pre>
      )}

      {status === 'error' && (
        <p className="rounded-lg border border-border bg-status-failed-bg px-4 py-3 text-body text-status-failed-text">
          Could not reach the backend at {API_BASE_URL}: {error}
        </p>
      )}

      {/* Decorative token demo, not real product content -- hidden from AT. */}
      <div aria-hidden="true" className="mt-4 flex flex-wrap items-center justify-center gap-2">
        <span className="rounded-full bg-status-ready-bg px-3 py-1 text-eyebrow font-bold uppercase text-status-ready-text">
          Ready
        </span>
        <span className="rounded-full bg-status-uploaded-bg px-3 py-1 text-eyebrow font-bold uppercase text-status-uploaded-text">
          Uploaded
        </span>
        <span className="rounded-full bg-status-extracting-bg px-3 py-1 text-eyebrow font-bold uppercase text-status-extracting-text">
          Extracting
        </span>
        <span className="rounded-full bg-status-graphing-bg px-3 py-1 text-eyebrow font-bold uppercase text-status-graphing-text">
          Graphing
        </span>
        <span className="rounded-full bg-status-failed-bg px-3 py-1 text-eyebrow font-bold uppercase text-status-failed-text">
          Failed
        </span>
      </div>
    </main>
  )
}
