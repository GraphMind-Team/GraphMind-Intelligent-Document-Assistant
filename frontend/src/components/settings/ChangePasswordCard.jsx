import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { changePassword } from '../../api/settingsClient'
import SettingsSectionCard from './SettingsSectionCard'

// Story 5.1. Independent of ProfileCard -- its own current/new password
// fields, its own saving/error state, its own request. Clears its own
// fields on success only; never touches Profile's state.
export default function ChangePasswordCard() {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved'

  const canSubmit = currentPassword.length > 0 && newPassword.length >= 8

  // Visible "Saved!" confirmation clears itself after a few seconds --
  // same pattern as ProfileCard's own save confirmation.
  useEffect(() => {
    if (status !== 'saved') return
    const timer = setTimeout(() => setStatus(null), 3000)
    return () => clearTimeout(timer)
  }, [status])

  async function handleSubmit(event) {
    event.preventDefault()
    if (saving || !canSubmit) return
    setSaving(true)
    setStatus('saving')
    setError(null)
    try {
      await changePassword(authFetch, { currentPassword, newPassword })
      // Cleared on success only -- a failed attempt (e.g. wrong current
      // password) keeps both fields so the user doesn't have to retype
      // the new password they'd already chosen.
      setCurrentPassword('')
      setNewPassword('')
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
      title={t('settings.changePassword.title')}
      description={t('settings.changePassword.description')}
      icon={
        <>
          <rect x="5" y="10.5" width="14" height="9" rx="2.2" />
          <path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7" />
        </>
      }
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-text2">
            {t('settings.changePassword.currentPassword')}
          </span>
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            disabled={saving}
            autoComplete="current-password"
            className="w-full rounded-xl border border-border bg-input-bg px-4 py-2.5 text-sm text-text disabled:opacity-60"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-semibold text-text2">
            {t('settings.changePassword.newPassword')}
          </span>
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            disabled={saving}
            autoComplete="new-password"
            minLength={8}
            className="w-full rounded-xl border border-border bg-input-bg px-4 py-2.5 text-sm text-text disabled:opacity-60"
          />
        </label>
        <button
          type="submit"
          disabled={saving || !canSubmit}
          className="btn-brand self-start rounded-full px-5 py-2.5 text-sm font-semibold disabled:opacity-60"
        >
          {saving ? t('settings.changePassword.saving') : t('settings.changePassword.submit')}
        </button>
      </form>
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? t('settings.changePassword.savingStatus') : status === 'saved' ? t('settings.changePassword.savedStatus') : ''}
      </p>
      {status === 'saved' && (
        <p className="mt-3 text-sm font-medium text-success">{t('settings.changePassword.saved')}</p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </SettingsSectionCard>
  )
}
