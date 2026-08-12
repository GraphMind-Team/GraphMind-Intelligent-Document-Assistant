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
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <div className="w-full max-w-[400px] rounded-[14px] border border-[var(--border)] bg-[var(--card-bg)] p-9 shadow-[var(--card-shadow)]">
        <span
          aria-hidden="true"
          className="relative mb-3.5 block h-[38px] w-[38px] rounded-[9px] bg-[linear-gradient(135deg,var(--primary),var(--accent))] after:absolute after:inset-[10px] after:rounded-full after:border-2 after:border-[var(--bg)] after:content-['']"
        />
        <h1 className="mb-1 text-xl font-bold text-[var(--primary)]">Create your account</h1>
        <p className="mb-6 text-sm text-[var(--text2)]">
          Start asking grounded questions of your documents.
        </p>

        {registered ? (
          <p className="text-sm text-[var(--text)]">Account created for {email}.</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col">
            <label htmlFor="register-fullname" className="mb-1.5 block text-sm font-semibold text-[var(--text2)]">Full name</label>
            <input
              id="register-fullname"
              type="text"
              required
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="mb-4 w-full rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text)]"
            />

            <label htmlFor="register-email" className="mb-1.5 block text-sm font-semibold text-[var(--text2)]">Email</label>
            <input
              id="register-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mb-4 w-full rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text)]"
            />

            <label htmlFor="register-password" className="mb-1.5 block text-sm font-semibold text-[var(--text2)]">Password</label>
            <input
              id="register-password"
              type="password"
              required
              minLength={8}
              maxLength={128}
              autoComplete="new-password"
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
              Create Account
            </button>
          </form>
        )}

        <p className="mt-3 text-center text-sm text-[var(--text2)]">
          Already have an account? <Link to="/login" className="font-semibold text-[var(--link)]">Log in</Link>
        </p>
      </div>
    </main>
  )
}
