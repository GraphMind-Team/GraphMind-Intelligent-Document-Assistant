import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Proves frontend/backend integration end-to-end (Story 1.1): calls the
// backend's neutral /health endpoint and renders whatever it returns. If
// the backend is unreachable, this shows a visible error instead of a
// silent blank screen.
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
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center">
      <h1 className="text-3xl font-semibold text-slate-900">GraphMind</h1>
      <p className="text-slate-500">Backend health check</p>

      {status === 'loading' && (
        <p className="text-slate-600">Checking backend at {API_BASE_URL}...</p>
      )}

      {status === 'ok' && (
        <pre className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-800 shadow-sm">
          {JSON.stringify(health, null, 2)}
        </pre>
      )}

      {status === 'error' && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-red-700">
          Could not reach the backend at {API_BASE_URL}: {error}
        </p>
      )}
    </main>
  )
}
