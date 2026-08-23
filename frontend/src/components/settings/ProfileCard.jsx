import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { updateProfile } from '../../api/settingsClient'
import SettingsSectionCard from './SettingsSectionCard'

// Story 5.1. Saves independently of the other cards (Change Password,
// Appearance, Delete Account) -- its own local state, its own request.
// Mirrors AppearanceCard's saving/error/aria-live pattern where it applies;
// unlike AppearanceCard there's no optimistic account-wide update to make
// (nothing else on screen reads full_name), so this only needs local
// saving/error/status state.
export default function ProfileCard() {
  const { t } = useTranslation()
  const { authFetch, setAccountFullName, setAccountEmail } = useAuth()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved'

  // This card fetches its own copy from /auth/me on mount, rather than
  // seeding the form from AuthContext's accountFullName/accountEmail --
  // those are null-until-known and Shell's own identity block may not
  // have populated them yet at the moment this card mounts, so this stays
  // an independent load exactly as before. What's new is pushing the
  // result back into AuthContext (both here and after a save, below) --
  // that's the single shared value Shell's sidebar reads, so without this
  // sync a saved name change would only show there after a full reload.
  // A failed load (network error, non-401 server error -- a 401 itself
  // triggers authFetch's own logout) is surfaced the same way a failed
  // save is (role="alert"), rather than silently leaving the form blank
  // with no indication why or how to retry.
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
        setAccountFullName(data.full_name)
        setAccountEmail(data.email)
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
  }, [authFetch, setAccountFullName, setAccountEmail])

  async function handleSubmit(event) {
    event.preventDefault()
    if (saving) return
    setSaving(true)
    setStatus('saving')
    setError(null)
    try {
      const data = await updateProfile(authFetch, { fullName })
      setFullName(data.full_name)
      setAccountFullName(data.full_name)
      setStatus('saved')
    } catch (err) {
      setError(err.message)
      setStatus(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <SettingsSectionCard
      title={t('settings.profile.title')}
      description={t('settings.profile.description')}
      icon={
        <>
          <circle cx="12" cy="8" r="3.4" />
          <path d="M5 20c.7-3.8 3.7-6 7-6s6.3 2.2 7 6" />
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-text2">{t('settings.profile.fullName')}</span>
          <input
            type="text"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            disabled={loading || saving}
            className="w-full rounded-xl border border-border bg-input-bg px-4 py-2.5 text-sm text-text disabled:opacity-60"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-text2">{t('settings.profile.email')}</span>
          {/* Read-only per the resolved email-editability question -- only
              full_name is editable in this story. */}
          <input
            type="email"
            value={email}
            disabled
            readOnly
            className="w-full rounded-xl border border-border bg-input-bg px-4 py-2.5 text-sm text-text opacity-60"
          />
        </label>
        <button
          type="submit"
          disabled={loading || saving || fullName.trim() === ''}
          className="btn-brand self-start rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {saving ? t('settings.profile.saving') : t('settings.profile.save')}
        </button>
      </form>
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? t('settings.profile.savingStatus') : status === 'saved' ? t('settings.profile.savedStatus') : ''}
      </p>
      {status === 'saved' && (
        <p className="mt-3 text-sm font-medium text-success">{t('settings.profile.saved')}</p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </SettingsSectionCard>
  )
}
