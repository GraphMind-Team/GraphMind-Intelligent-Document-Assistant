import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { registerAccount, resendVerification } from '../api/authClient'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'

// Registration page (Story 1.3). Sits outside the authenticated shell but
// still themes correctly via the CSS variable tokens in index.css
// (UX-DR2). Layout follows the reference mockup's `.auth-wrap` card.
export default function RegisterPage() {
  const { t } = useTranslation()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [registered, setRegistered] = useState(false)
  // Story 1.6: lets the "check your inbox" panel offer a resend without
  // making the visitor retype their address.
  const [resendState, setResendState] = useState('idle') // idle | sending | sent
  // Registration is often the very first request the app makes -- see
  // LoginPage.jsx's own comment on `useSlowRequestHint`.
  const isSlow = useSlowRequestHint(submitting)

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

  async function handleResend() {
    setResendState('sending')
    try {
      await resendVerification({ email })
      setResendState('sent')
    } catch {
      // resend-verification always answers the same way regardless of
      // outcome (it never reveals account existence) -- "sent" is the
      // honest thing to show either way, mirroring VerifyEmailPage. Must
      // be a catch, not a finally that lets the rejection keep propagating
      // (e.g. a 429 from the rate limiter) -- that would both show "sent"
      // *and* leave an unhandled promise rejection behind.
      setResendState('sent')
    }
  }

  return (
    <main className="app-aurora flex min-h-screen items-center justify-center p-8">
      <div className="anim-rise w-full max-w-[420px] rounded-2xl border border-border bg-card-bg p-9 shadow-modal">
        {/* The brand mark doubles as the way back to the public page --
            an auth form with no exit is a dead end for anyone who
            arrived by mistake. */}
        <Link to="/" aria-label={t('auth.brandHome')} className="mb-4 inline-flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="relative block h-11 w-11 rounded-[15px] bg-[image:var(--grad-brand)] shadow-[var(--glow)] after:absolute after:inset-[11px] after:rounded-full after:border-2 after:border-white after:content-['']"
          />
          <span className="font-display text-[16px] font-bold text-text">GraphMind</span>
        </Link>
        <h1 className="mb-1 text-auth-title text-text">{t('auth.register.title')}</h1>
        <p className="mb-6 text-sm text-text2">
          {t('auth.register.subtitle')}
        </p>

        {registered ? (
          <div>
            <p className="mb-4 text-sm text-text">
              {t('auth.register.checkInboxPrefix')} <strong>{email}</strong> {t('auth.register.checkInboxSuffix')}
            </p>
            {resendState === 'sent' ? (
              <p className="text-sm text-text2">
                {t('auth.register.resendSent')}
              </p>
            ) : (
              <button
                type="button"
                onClick={handleResend}
                disabled={resendState === 'sending'}
                className="text-sm font-semibold text-link disabled:opacity-60"
              >
                {t('auth.register.resendVerification')}
              </button>
            )}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col">
            <label htmlFor="register-fullname" className="mb-1.5 block text-sm font-semibold text-text2">{t('auth.register.fullName')}</label>
            <input
              id="register-fullname"
              type="text"
              required
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
            />

            <label htmlFor="register-email" className="mb-1.5 block text-sm font-semibold text-text2">{t('auth.register.email')}</label>
            <input
              id="register-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mb-4 w-full rounded-xl border border-border bg-input-bg px-4 py-3 text-sm text-text"
            />

            <label htmlFor="register-password" className="mb-1.5 block text-sm font-semibold text-text2">{t('auth.register.password')}</label>
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
              {t('auth.register.submit')}
            </button>

            {isSlow && (
              <p role="status" className="mt-3 text-center text-xs text-text2">
                {t('common.slowServerHint')}
              </p>
            )}
          </form>
        )}

        <p className="mt-3 text-center text-sm text-text2">
          {t('auth.register.haveAccount')} <Link to="/login" className="font-semibold text-link">{t('auth.register.loginLink')}</Link>
        </p>
      </div>
    </main>
  )
}
