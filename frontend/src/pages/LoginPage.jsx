import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getRedirectTarget } from '../utils/authRedirect'

// Login page (Story 1.4). Mirrors RegisterPage.jsx's structure/styling.
// On success, navigates into the authenticated shell -- back to wherever
// ProtectedRoute redirected the user *from* (location.state.from, set by
// ProtectedRoute.jsx) if there was one, otherwise /documents, Story 1.5's
// default post-login landing route.
export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login({ email, password })
      navigate(getRedirectTarget(location), { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <div className="w-full max-w-[400px] rounded-[14px] border border-[var(--border)] bg-[var(--card-bg)] p-9 shadow-[var(--card-shadow)]">
        <span
          aria-hidden="true"
          className="relative mb-3.5 block h-[38px] w-[38px] rounded-[9px] bg-[linear-gradient(135deg,var(--primary),var(--accent))] after:absolute after:inset-[10px] after:rounded-full after:border-2 after:border-[var(--bg)] after:content-['']"
        />
        <h1 className="mb-1 text-xl font-bold text-[var(--primary)]">Welcome back</h1>
        <p className="mb-6 text-sm text-[var(--text2)]">Log in to your GraphMind workspace.</p>

        <form onSubmit={handleSubmit} className="flex flex-col">
          <label htmlFor="login-email" className="mb-1.5 block text-sm font-semibold text-[var(--text2)]">Email</label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mb-4 w-full rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text)]"
          />

          <label htmlFor="login-password" className="mb-1.5 block text-sm font-semibold text-[var(--text2)]">Password</label>
          <input
            id="login-password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mb-4 w-full rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text)]"
          />

          {error && (
            <p role="alert" className="mb-4 text-sm text-[var(--danger)]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-[var(--primary)] px-5 py-2.5 text-sm font-semibold text-[var(--on-primary)] disabled:opacity-60"
          >
            Log In
          </button>
        </form>

        <p className="mt-3 text-center text-sm text-[var(--text2)]">
          Don't have an account? <Link to="/" className="font-semibold text-[var(--accent)]">Register</Link>
        </p>
      </div>
    </main>
  )
}
