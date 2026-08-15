import { useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

// No UI -- mounted once, always, regardless of route (Story 5.2). Bridges
// AuthContext and ThemeContext without either importing the other:
// ThemeContext stays usable stand-alone (pre-auth pages, tests), and
// AuthContext stays theme-agnostic.
//
// Keyed on [accountTheme] only, not [theme] -- syncing on every `theme`
// change would immediately re-apply the account's last-known value right
// after the user's own toggle in AppearanceCard, fighting their click.
// `theme`/`setTheme` are read through a ref (updated every render, not a
// dependency) rather than added to the effect's dependency array: adding
// them would either refire on every local toggle (theme) or on every
// ThemeProvider re-render (setTheme isn't memoized there) -- both wrong.
export default function ThemeAccountSync() {
  const { accountTheme } = useAuth()
  const themeCtx = useTheme()
  const latest = useRef(themeCtx)

  // Updates the ref post-commit, in an effect -- not a plain `latest.current
  // = themeCtx` assignment in the render body, which would be a write
  // during render (works today, but isn't the sanctioned "latest ref"
  // pattern React's stricter/concurrent-rendering rules expect). Runs on
  // every render (no dependency array), so it's always caught up before
  // the sync effect below reads it on the same commit.
  useEffect(() => {
    latest.current = themeCtx
  })

  useEffect(() => {
    const { theme, setTheme } = latest.current
    if (accountTheme && accountTheme !== theme) {
      setTheme(accountTheme)
    }
  }, [accountTheme])

  return null
}
