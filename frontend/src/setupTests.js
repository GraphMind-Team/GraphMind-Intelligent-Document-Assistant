import '@testing-library/jest-dom/vitest'
// Initializes the global i18next singleton once for every test file --
// components call useTranslation() without a wrapping <I18nextProvider>
// in tests (mirroring how main.jsx's implicit-instance registration works
// in the real app), so without this import t() would have no resources
// loaded and fall back to returning raw keys.
import './i18n'
