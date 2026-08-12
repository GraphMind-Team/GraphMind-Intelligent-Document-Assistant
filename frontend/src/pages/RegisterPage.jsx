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
      <div className="w-full max-w-[400px] rounded-[14px] border border-[var(--border)] bg-[var(--surface)] p-9 shadow-sm">
        <h1 className="mb-1 text-xl font-bold text-[var(--primary)]">Create your account</h1>
        <p className="mb-6 text-sm text-[var(--text2)]">
          Start asking grounded questions of your documents.
        </p>

        {registered ? (
          <p className="text-sm text-[var(--text)]">Account created for {email}.</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm text-[var(--text)]">
              Full name
              <input
                type="text"
                required
                autoComplete="name"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className="rounded-md border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[var(--text)]"
              />
            </label>

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
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
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
              Create Account
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-[var(--text2)]">
          Already have an account? <Link to="/login" className="text-[var(--accent)]">Log in</Link>
        </p>
      </div>
    </main>
  )
}
