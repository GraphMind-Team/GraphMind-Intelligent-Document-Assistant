import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { resendVerification } from '../api/authClient'
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
  // Story 1.6: set alongside `error` only when the login rejection was the
  // "verify your email" 403 -- distinguishes that case from a plain wrong-
  // password 401 so the resend action only ever shows where it's relevant.
  const [needsVerification, setNeedsVerification] = useState(false)
  const [resendState, setResendState] = useState('idle') // idle | sending | sent
  const [submitting, setSubmitting] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setNeedsVerification(false)
    setResendState('idle')
    setSubmitting(true)
    try {
      await login({ email, password })
      navigate(getRedirectTarget(location), { replace: true })
    } catch (err) {
      setError(err.message)
      setNeedsVerification(err.status === 403)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleResend() {
    setResendState('sending')
    try {
      await resendVerification({ email })
      setResendState('sent')
    } catch {
      // resend-verification always answers the same way regardless of
      // outcome -- see RegisterPage.jsx's handleResend for why this must
      // be a catch (showing "sent" without leaving the rejection, e.g. a
      // 429, as an unhandled promise rejection).
      setResendState('sent')
    }
  }

  return (
    <main className="app-aurora flex min-h-screen items-center justify-center p-8">
      <div className="anim-rise w-full max-w-[420px] rounded-2xl border border-border bg-card-bg p-9 shadow-modal">
        {/* The brand mark doubles as the way back to the public page --
            an auth form with no exit is a dead end for anyone who
            arrived by mistake. */}
        <Link to="/" aria-label="GraphMind home" className="mb-4 inline-flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="relative block h-11 w-11 rounded-[15px] bg-[image:var(--grad-brand)] shadow-[var(--glow)] after:absolute after:inset-[11px] after:rounded-full after:border-2 after:border-white after:content-['']"
          />
          <span className="font-display text-[16px] font-bold text-text">GraphMind</span>
        </Link>
        <h1 className="mb-1 text-auth-title text-text">Welcome back</h1>
        <p className="mb-6 text-sm text-text2">Log in to your GraphMind workspace.</p>

        <form onSubmit={handleSubmit} className="flex flex-col">
          <label htmlFor="login-email" className="mb-1.5 block text-sm font-semibold text-text2">Email</label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
          />

          <label htmlFor="login-password" className="mb-1.5 block text-sm font-semibold text-text2">Password</label>
          <input
            id="login-password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
          />

          {error && (
            <p role="alert" className={`text-sm text-danger ${needsVerification ? 'mb-2' : 'mb-4'}`}>
              {error}
            </p>
          )}

          {needsVerification && (
            <div className="mb-4">
              {resendState === 'sent' ? (
                <p className="text-sm text-text2">
                  If that account exists and isn't verified yet, we've sent a new link.
                </p>
              ) : (
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resendState === 'sending'}
                  className="text-sm font-semibold text-link disabled:opacity-60"
                >
                  Resend verification email
                </button>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="btn-brand w-full rounded-full px-5 py-3 text-sm font-semibold disabled:opacity-60"
          >
            Log In
          </button>
        </form>

        <p className="mt-3 text-center text-sm text-text2">
          Don't have an account? <Link to="/register" className="font-semibold text-link">Register</Link>
        </p>
      </div>
    </main>
  )
}
