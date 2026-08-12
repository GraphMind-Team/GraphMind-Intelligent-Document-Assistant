import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { API_BASE_URL, loginAccount } from '../api/authClient'

const AuthContext = createContext(undefined)

const STORAGE_KEY = 'access_token'

// Mirrors ThemeContext's storage-guard pattern -- private mode/disabled
// storage/sandboxed iframes shouldn't crash AuthProvider, just fall back
// to no persisted session.
function getStoredToken() {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function setStoredToken(token) {
  try {
    if (token) {
      window.localStorage.setItem(STORAGE_KEY, token)
    } else {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  } catch {
    // Storage write failed (quota, private mode) -- session still works
    // for this tab, it just won't persist across reloads.
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(getStoredToken)
  // Mirrors `token` for authFetch to read synchronously. Needed because a
  // caller that does `await login(...)` then `await authFetch(...)` in the
  // same handler (exactly what LoginPage does) would otherwise capture
  // `authFetch` from a render that predates the `setToken` update -- state
  // setters don't retroactively patch already-created closures, so
  // `authFetch` would still see the pre-login token. A ref, updated in the
  // same place `setToken` is called, sidesteps that entirely.
  const tokenRef = useRef(token)

  const setTokenEverywhere = useCallback((next) => {
    tokenRef.current = next
    setToken(next)
    setStoredToken(next)
  }, [])

  const login = useCallback(
    async ({ email, password }) => {
      const data = await loginAccount({ email, password })
      setTokenEverywhere(data.access_token)
      return data
    },
    [setTokenEverywhere],
  )

  const logout = useCallback(() => {
    setTokenEverywhere(null)
  }, [setTokenEverywhere])

  // Reusable by later stories (documents/chat/kg) for any authenticated
  // call: attaches the current token as `Authorization: Bearer <token>`
  // when present, and treats a 401 response as an expired/invalid session
  // -- logging out automatically so the UI doesn't keep looking "logged
  // in" with a token the server no longer accepts.
  const authFetch = useCallback(
    async (path, options = {}) => {
      const headers = { ...(options.headers || {}) }
      if (tokenRef.current) headers.Authorization = `Bearer ${tokenRef.current}`
      const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
      if (response.status === 401) logout()
      return response
    },
    [logout],
  )

  // A stored token only proves a string made it into localStorage, not
  // that the server still honors it -- until now, an expired/tampered
  // token left the user "logged in" into a shell with nothing to 401 (its
  // pages are all placeholders), with Exit as the only way out. One
  // `/auth/me` call at boot settles it: 401 -> authFetch's own handler
  // logs out, success -> nothing to do. `isInitializing` covers the gap
  // while that's in flight, so ProtectedRoute/PublicOnlyRoute don't act on
  // a token that hasn't been confirmed yet (a bad token would otherwise
  // flash shell content before the 401 evicts it; a good one could get
  // bounced by a stale unauthenticated read). A network error (as opposed
  // to a 401) leaves the session as-is -- a dropped request isn't proof
  // the token is invalid, so this doesn't sign the user out over that.
  const [isInitializing, setIsInitializing] = useState(() => getStoredToken() !== null)

  useEffect(() => {
    if (!tokenRef.current) {
      setIsInitializing(false)
      return
    }
    let cancelled = false
    authFetch('/auth/me')
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setIsInitializing(false)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch])

  const value = {
    token,
    isAuthenticated: Boolean(token),
    isInitializing,
    login,
    logout,
    authFetch,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (ctx === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
