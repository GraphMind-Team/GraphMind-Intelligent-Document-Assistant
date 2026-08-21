import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import en from './locales/en.json'
import bg from './locales/bg.json'
import de from './locales/de.json'

const SUPPORTED_LANGUAGES = ['en', 'bg', 'de']
// Mirrors ThemeContext's localStorage key pattern ('theme').
const STORAGE_KEY = 'language'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      bg: { translation: bg },
      de: { translation: de },
    },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGUAGES,
    // Lets a browser locale like 'de-DE' or 'bg-BG' resolve to the plain
    // 'de'/'bg' resource instead of falling through to English -- the
    // detector reports the full tag, this collapses it to the supported
    // base language before fallbackLng ever needs to apply.
    nonExplicitSupportedLngs: true,
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: STORAGE_KEY,
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false, // React already escapes interpolated values
    },
  })

export default i18n
export { SUPPORTED_LANGUAGES, STORAGE_KEY }
