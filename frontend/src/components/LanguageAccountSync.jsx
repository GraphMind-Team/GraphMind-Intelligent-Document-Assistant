import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'

// No UI -- mounted once, always, regardless of route, mirroring
// ThemeAccountSync.jsx exactly (a separate file rather than folded into
// that one: each sync bridge stays keyed on exactly one dependency via the
// ref-latest pattern below, so it can't fight the user's own change in
// LanguageCard/AppearanceCard -- merging the two would either duplicate
// that narrowness pointlessly or make one effect handle two unrelated
// fields).
export default function LanguageAccountSync() {
  const { accountLanguage } = useAuth()
  const { i18n } = useTranslation()
  const latest = useRef(i18n)

  useEffect(() => {
    latest.current = i18n
  })

  useEffect(() => {
    const currentI18n = latest.current
    if (accountLanguage && accountLanguage !== currentI18n.resolvedLanguage) {
      currentI18n.changeLanguage(accountLanguage)
    }
  }, [accountLanguage])

  return null
}
