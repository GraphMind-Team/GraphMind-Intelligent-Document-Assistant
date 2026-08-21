import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { updateProfile } from '../../api/settingsClient'

// Story 5.1. Saves independently of the other cards (Change Password,
// Appearance, Delete Account) -- its own local state, its own request.
// Mirrors AppearanceCard's saving/error/aria-live pattern where it applies;
// unlike AppearanceCard there's no optimistic account-wide update to make
// (nothing else on screen reads full_name), so this only needs local
// saving/error/status state.
export default function ProfileCard() {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved'

  // AuthContext only tracks the token and account theme (Story 5.2) -- it
  // has no full_name/email fields, so this card fetches its own copy from
  // /auth/me on mount rather than guessing at a shape AuthContext doesn't
  // expose. A failed load (network error, non-401 server error -- a 401
  // itself triggers authFetch's own logout) is surfaced the same way a
  // failed save is (role="alert"), rather than silently leaving the form
  // blank with no indication why or how to retry.
  // Visible "Saved!" confirmation clears itself after a few seconds --
  // long enough to notice, not glued to the form forever the way the
  // sr-only announcement below effectively is (it only fires once per
  // save, but has no reason to time out since it's silent).
  useEffect(() => {
    if (status !== 'saved') return
    const timer = setTimeout(() => setStatus(null), 3000)
    return () => clearTimeout(timer)
  }, [status])

  useEffect(() => {
    let cancelled = false
    authFetch('/auth/me')
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`Failed to load profile (${response.status}).`))))
      .then((data) => {
        if (cancelled) return
        setFullName(data.full_name)
        setEmail(data.email)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message || t('settings.profile.loadError'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch])

  async function handleSubmit(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setStatus('saving')
    setError(null)
    try {
      const data = await updateProfile(authFetch, { fullName })
      setFullName(data.full_name)
      setStatus('saved')
    } catch (err) {
      setError(err.message)
      setStatus(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card-bg p-[22px]">
      <h2 className="text-base font-bold text-text">{t('settings.profile.title')}</h2>
      <form className="mt-4 flex flex-col gap-3" onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1 text-sm text-text">
          {t('settings.profile.fullName')}
          <input
            type="text"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            disabled={loading || saving}
            className="rounded-md border border-border bg-transparent px-3 py-2 text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-text">
          {t('settings.profile.email')}
          {/* Read-only per the resolved email-editability question -- only
              full_name is editable in this story. */}
          <input
            type="email"
            value={email}
            disabled
            readOnly
            className="rounded-md border border-border bg-transparent px-3 py-2 text-sm text-text opacity-60"
          />
        </label>
        <button
          type="submit"
          disabled={loading || saving || fullName.trim() === ''}
          className="self-start rounded-md border border-border px-3 py-1.5 text-sm text-text transition-colors hover:border-primary hover:bg-primary/10 hover:text-primary disabled:opacity-50 disabled:hover:border-border disabled:hover:bg-transparent disabled:hover:text-text"
        >
          {saving ? t('settings.profile.saving') : t('settings.profile.save')}
        </button>
      </form>
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? t('settings.profile.savingStatus') : status === 'saved' ? t('settings.profile.savedStatus') : ''}
      </p>
      {status === 'saved' && (
        <p className="mt-3 text-sm text-success">{t('settings.profile.saved')}</p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
