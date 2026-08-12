import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Login page (Story 1.4). Mirrors RegisterPage.jsx's structure/styling.
// On success, calls authFetch('/auth/me') as concrete end-to-end proof
// the JWT works -- there's no authenticated shell to redirect into yet
// (that arrives in Story 1.5).
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [profile, setProfile] = useState(null)
  const { login, authFetch } = useAuth()

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login({ email, password })
      const response = await authFetch('/auth/me')
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error('Logged in, but could not load your profile.')
      setProfile(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <div className="w-full max-w-[400px] rounded-[14px] border border-[var(--border)] bg-[var(--surface)] p-9 shadow-sm">
        <h1 className="mb-1 text-xl font-bold text-[var(--primary)]">Log in</h1>
        <p className="mb-6 text-sm text-[var(--text2)]">Welcome back.</p>

        {profile ? (
          <p className="text-sm text-[var(--text)]">Logged in as {profile.email}.</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm text-[var(--text)]">
              Email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="rounded-md border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[var(--text)]"
              />
            </label>

            <label className="flex flex-col gap-1 text-sm text-[var(--text)]">
              Password
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="rounded-md border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[var(--text)]"
              />
            </label>

            {error && (
              <p role="alert" className="text-sm text-[var(--danger)]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="mt-2 rounded-md bg-[var(--primary)] px-4 py-2 font-semibold text-[var(--on-primary)] disabled:opacity-60"
            >
              Log In
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-[var(--text2)]">
          Don't have an account? <Link to="/" className="text-[var(--accent)]">Register</Link>
        </p>
      </div>
    </main>
  )
}
