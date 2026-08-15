import { useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { changePassword } from '../../api/settingsClient'

// Story 5.1. Independent of ProfileCard -- its own current/new password
// fields, its own saving/error state, its own request. Clears its own
// fields on success only; never touches Profile's state.
export default function ChangePasswordCard() {
  const { authFetch } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved'

  const canSubmit = currentPassword.length > 0 && newPassword.length >= 8

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
    <div className="rounded-lg border border-border bg-card-bg p-[22px]">
      <h2 className="text-base font-bold text-text">Change Password</h2>
      <form className="mt-4 flex flex-col gap-3" onSubmit={handleSubmit}>
        <label className="flex flex-col gap-1 text-sm text-text">
          Current password
          <input
            type="password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            disabled={saving}
            autoComplete="current-password"
            className="rounded-md border border-border bg-transparent px-3 py-2 text-sm text-text"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-text">
          New password
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            disabled={saving}
            autoComplete="new-password"
            minLength={8}
            className="rounded-md border border-border bg-transparent px-3 py-2 text-sm text-text"
          />
        </label>
        <button
          type="submit"
          disabled={saving || !canSubmit}
          className="self-start rounded-md border border-border px-3 py-1.5 text-sm text-text disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Change Password'}
        </button>
      </form>
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? 'Changing password...' : status === 'saved' ? 'Password changed.' : ''}
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
