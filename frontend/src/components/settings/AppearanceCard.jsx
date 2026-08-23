import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { updateTheme } from '../../api/settingsClient'
import ToggleSwitch from '../ToggleSwitch'
import SettingsSectionCard from './SettingsSectionCard'

const LABEL_ID = 'appearance-dark-mode-label'

// Story 5.2. The PATCH call lives here, not in ThemeContext -- mirrors how
// DocumentCard/DocumentDetailPage call deleteDocument(authFetch, id)
// directly rather than routing mutations through a context.
export default function AppearanceCard() {
  const { t } = useTranslation()
  const { authFetch, setAccountTheme } = useAuth()
  const { theme, setTheme } = useTheme()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState(null) // null | 'saving' | 'saved' -- sr-only announcement text

  const checked = theme === 'dark'

  // `disabled={saving}` on the switch below serializes clicks -- without
  // it, two rapid toggles fire two PATCHes that can resolve out of order
  // and leave the account one flip behind what's on screen.
  async function handleToggle(nextChecked) {
    const next = nextChecked ? 'dark' : 'light'
    setTheme(next) // applies immediately (UX-DR13), kept even if the save below fails
    setSaving(true)
    setStatus('saving')
    setError(null)
    try {
      await updateTheme(authFetch, next)
      // Keeps AuthContext's copy in sync with what was just persisted --
      // otherwise accountTheme sits at its pre-toggle value until the next
      // login/boot check re-fetches it.
      setAccountTheme(next)
      setStatus('saved')
    } catch (err) {
      // Explicit about *what* failed (UX-DR19) -- the theme is still
      // applied here, it just isn't saved to the account yet.
      setError(t('settings.appearance.saveError', { message: err.message }))
      setStatus(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <SettingsSectionCard
      title={t('settings.appearance.title')}
      description={t('settings.appearance.description')}
      icon={
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
        </>
      }
    >
      <div className="flex items-center justify-between">
        {/* Clickable, and the switch's aria-labelledby points here -- one
            source of truth for the wording instead of a duplicated
            aria-label, and clicking the text toggles too (as clicking a
            <label> next to a native control would). */}
        <span id={LABEL_ID} className="cursor-pointer text-sm font-medium text-text" onClick={() => !saving && handleToggle(!checked)}>
          {t('settings.appearance.darkMode')}
        </span>
        <ToggleSwitch checked={checked} onChange={handleToggle} disabled={saving} busy={saving} labelledBy={LABEL_ID} />
      </div>
      {/* Visually hidden -- announces save progress/success to screen
          readers, who otherwise get nothing but the visual dimming while
          saving and no confirmation at all on success (only failure has an
          announced role="alert"). */}
      <p className="sr-only" aria-live="polite">
        {status === 'saving' ? t('settings.appearance.savingStatus') : status === 'saved' ? t('settings.appearance.savedStatus') : ''}
      </p>
      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}
    </SettingsSectionCard>
  )
}
