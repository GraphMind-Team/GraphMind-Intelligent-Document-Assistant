import { createContext, useContext, useEffect, useState } from 'react'

const ThemeContext = createContext(undefined)

const STORAGE_KEY = 'theme'

// Reads only an explicit stored override. System prefers-color-scheme is
// intentionally ignored -- the app always defaults to light unless the
// user (or a prior session) has explicitly chosen dark.
function getStoredTheme() {
  if (typeof window === 'undefined') return 'light'
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    // Storage inaccessible (private mode, disabled, sandboxed iframe) --
    // fall back to the default rather than crashing ThemeProvider.
    return 'light'
  }
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(getStoredTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const setThemeExplicit = (next) => {
    setTheme(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Storage write failed (quota, private mode) -- theme still applies
      // for this session, it just won't persist across reloads.
    }
  }

  const toggleTheme = () => {
    setThemeExplicit(theme === 'dark' ? 'light' : 'dark')
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme: setThemeExplicit, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (ctx === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return ctx
}
