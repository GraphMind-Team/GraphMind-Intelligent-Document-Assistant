import { useState } from 'react'
import { Link } from 'react-router-dom'
import { registerAccount } from '../api/authClient'

// Registration page (Story 1.3). Sits outside the authenticated shell but
// still themes correctly via the CSS variable tokens in index.css
// (UX-DR2). Layout follows the reference mockup's `.auth-wrap` card.
export default function RegisterPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [registered, setRegistered] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await registerAccount({ fullName, email, password })
      setRegistered(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
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
        <h1 className="mb-1 text-auth-title text-text">Create your account</h1>
        <p className="mb-6 text-sm text-text2">
          Start asking grounded questions of your documents.
        </p>

        {registered ? (
          <p className="text-sm text-text">Account created for {email}.</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col">
            <label htmlFor="register-fullname" className="mb-1.5 block text-sm font-semibold text-text2">Full name</label>
            <input
              id="register-fullname"
              type="text"
              required
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
            />

            <label htmlFor="register-email" className="mb-1.5 block text-sm font-semibold text-text2">Email</label>
            <input
              id="register-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
            />

            <label htmlFor="register-password" className="mb-1.5 block text-sm font-semibold text-text2">Password</label>
            <input
              id="register-password"
              type="password"
              required
              minLength={8}
              maxLength={128}
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
            />

            {error && (
              <p role="alert" className="mb-4 text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="btn-brand w-full rounded-full px-5 py-3 text-sm font-semibold disabled:opacity-60"
            >
              Create Account
            </button>
          </form>
        )}

        <p className="mt-3 text-center text-sm text-text2">
          Already have an account? <Link to="/login" className="font-semibold text-link">Log in</Link>
        </p>
      </div>
    </main>
  )
}
