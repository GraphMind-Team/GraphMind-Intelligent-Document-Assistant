import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { resendVerification, verifyEmail } from '../api/authClient'

// Email verification landing page (Story 1.6). Reached only by clicking
// the link mailed on registration/resend -- deliberately outside both
// PublicOnlyRoute and ProtectedRoute in App.jsx, since whoever clicks it
// is logged out by definition and shouldn't be bounced by either guard.
// Mirrors RegisterPage.jsx/LoginPage.jsx's `.auth-wrap` card layout.
export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = useState(token ? 'verifying' : 'missing-token')
  const [error, setError] = useState(null)
  const [resendEmail, setResendEmail] = useState('')
  const [resendState, setResendState] = useState('idle') // idle | sending | sent

  // Guards against React StrictMode's dev-only double-invoked effect
  // firing this POST twice -- the backend already tolerates a repeat
  // verify (idempotent), but there's no reason to burn a second real
  // request over it.
  const requested = useRef(false)

  useEffect(() => {
    if (!token || requested.current) return
    requested.current = true

    verifyEmail({ token })
      .then(() => setStatus('verified'))
      .catch((err) => {
        setError(err.message)
        setStatus('failed')
      })
  }, [token])

  async function handleResend(event) {
    event.preventDefault()
    setResendState('sending')
    try {
      await resendVerification({ email: resendEmail })
      setResendState('sent')
    } catch {
      // resend-verification never reveals whether the email exists, so
      // there's nothing more specific to show here even on failure --
      // rate-limiting is the one real failure mode, and "sent" is still
      // an honest thing to say (the account isn't punished either way).
      setResendState('sent')
    }
  }

  return (
    <main className="app-aurora flex min-h-screen items-center justify-center p-8">
      <div className="anim-rise w-full max-w-[420px] rounded-2xl border border-border bg-card-bg p-9 shadow-modal">
        <Link to="/" aria-label="GraphMind home" className="mb-4 inline-flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="relative block h-11 w-11 rounded-[15px] bg-[image:var(--grad-brand)] shadow-[var(--glow)] after:absolute after:inset-[11px] after:rounded-full after:border-2 after:border-white after:content-['']"
          />
          <span className="font-display text-[16px] font-bold text-text">GraphMind</span>
        </Link>

        {status === 'missing-token' && (
          <>
            <h1 className="mb-1 text-auth-title text-text">Verification link missing</h1>
            <p className="text-sm text-text2">
              This page needs a verification link -- open the one from your email, or{' '}
              <Link to="/login" className="font-semibold text-link">log in</Link> to request a new one.
            </p>
          </>
        )}

        {status === 'verifying' && (
          <>
            <h1 className="mb-1 text-auth-title text-text">Verifying your email...</h1>
            <p className="text-sm text-text2">One moment.</p>
          </>
        )}

        {status === 'verified' && (
          <>
            <h1 className="mb-1 text-auth-title text-text">Email verified</h1>
            <p className="mb-6 text-sm text-text2">Your account is ready. You can log in now.</p>
            <Link to="/login" className="btn-brand block w-full rounded-full px-5 py-3 text-center text-sm font-semibold">
              Log In
            </Link>
          </>
        )}

        {status === 'failed' && (
          <>
            <h1 className="mb-1 text-auth-title text-text">Verification failed</h1>
            <p role="alert" className="mb-6 text-sm text-danger">{error}</p>

            {resendState === 'sent' ? (
              <p className="text-sm text-text">
                If that account exists and isn't verified yet, we've sent a new link.
              </p>
            ) : (
              <form onSubmit={handleResend} className="flex flex-col">
                <label htmlFor="verify-resend-email" className="mb-1.5 block text-sm font-semibold text-text2">
                  Send me a new link
                </label>
                <input
                  id="verify-resend-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={resendEmail}
                  onChange={(event) => setResendEmail(event.target.value)}
                  className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
                />
                <button
                  type="submit"
                  disabled={resendState === 'sending'}
                  className="btn-brand w-full rounded-full px-5 py-3 text-sm font-semibold disabled:opacity-60"
                >
                  Resend verification email
                </button>
              </form>
            )}
          </>
        )}

        <p className="mt-3 text-center text-sm text-text2">
          <Link to="/login" className="font-semibold text-link">Back to log in</Link>
        </p>
      </div>
    </main>
  )
}
