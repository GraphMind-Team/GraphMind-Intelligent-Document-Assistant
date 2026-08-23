import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { updateLanguage } from '../../api/settingsClient'
import { SUPPORTED_LANGUAGES } from '../../i18n'
import SettingsSectionCard from './SettingsSectionCard'

// Language names are deliberately hardcoded, not translated -- every
// app's language picker shows each language's own name in its own
// script, regardless of the currently active UI language.
const LANGUAGE_LABELS = { en: 'English', bg: 'Български', de: 'Deutsch' }
const LABEL_ID = 'language-select-label'

// Mirrors AppearanceCard.jsx's optimistic-update + PATCH + account-sync
// pattern exactly, but a <select> (3 options) instead of a binary
// ToggleSwitch.
export default function LanguageCard() {
  const { t, i18n } = useTranslation()
  const { authFetch, setAccountLanguage } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved' -- sr-only announcement text

  async function handleChange(next) {
    if (saving || next === i18n.resolvedLanguage) return
    i18n.changeLanguage(next) // applies immediately, kept even if the save below fails
    setSaving(true)
    setStatus('saving')
    setError(null)
    try {
      await updateLanguage(authFetch, next)
      // Keeps AuthContext's copy in sync with what was just persisted --
      // otherwise accountLanguage sits at its pre-change value until the
      // next login/boot check re-fetches it.
      setAccountLanguage(next)
      setStatus('saved')
    } catch (err) {
      setError(t('settings.language.saveError', { message: err.message }))
      setStatus(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <SettingsSectionCard
      title={t('settings.language.title')}
      description={t('settings.language.description')}
      icon={
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3c2.5 2.7 4 6.2 4 9s-1.5 6.3-4 9c-2.5-2.7-4-6.2-4-9s1.5-6.3 4-9Z" />
        </>
      }
    >
      <div className="flex items-center justify-between">
        <span id={LABEL_ID} className="text-sm font-medium text-text">
          {t('settings.language.title')}
        </span>
        <select
          aria-labelledby={LABEL_ID}
          value={i18n.resolvedLanguage}
          disabled={saving}
          onChange={(event) => handleChange(event.target.value)}
          className="cursor-pointer rounded-full border border-border bg-input-bg px-4 py-2 text-sm text-text disabled:opacity-60"
        >
          {SUPPORTED_LANGUAGES.map((code) => (
            <option key={code} value={code}>
              {LANGUAGE_LABELS[code]}
            </option>
          ))}
        </select>
      </div>
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? t('settings.language.savingStatus') : status === 'saved' ? t('settings.language.savedStatus') : ''}
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </SettingsSectionCard>
  )
}
