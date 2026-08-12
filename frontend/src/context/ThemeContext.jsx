// Minimal theme detection (Story 1.3).
//
// Detects the OS/browser color-scheme preference on mount and sets
// `data-theme` on <html> so CSS variables in index.css pick the right
// palette. No toggle, no persistence, no setter -- runtime switching via
// this Context, the full token set, and a Settings toggle UI are Story
// 1.2's job. This exists only so Registration (and every later page) is
// never built against hardcoded/unstyled colors (AD-5, UX-DR2).

import { createContext, useEffect, useState } from 'react'

export const ThemeContext = createContext('light')

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  )

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event) => setTheme(event.matches ? 'dark' : 'light')
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>
}
