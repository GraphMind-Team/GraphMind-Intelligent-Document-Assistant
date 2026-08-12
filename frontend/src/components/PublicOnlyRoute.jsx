import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getRedirectTarget } from '../utils/authRedirect'

// Mirror of ProtectedRoute.jsx, gating the opposite direction: an already
// authenticated visitor hitting Register (/) or Login (/login) gets sent
// straight into the shell instead of seeing an auth form they don't need.
//
// Reads the same location.state.from LoginPage does (set by
// ProtectedRoute's redirect), via the same getRedirectTarget helper,
// rather than hardcoding /documents: the instant login() flips
// isAuthenticated true, this component re-renders *while LoginPage is
// still mounted inside it* and its <Navigate> can win the race against
// LoginPage's own post-login navigate() call. Since both now resolve to
// the same target, whichever wins the race lands the user in the same
// place -- a deep-linked visitor (e.g. redirected from /chat) no longer
// sometimes gets dropped on /documents instead.
export default function PublicOnlyRoute() {
  const { isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()

  // Same wait as ProtectedRoute -- a stored token that's about to fail
  // AuthContext's boot-time `/auth/me` check shouldn't get routed as
  // "authenticated" into the shell for one render first.
  if (isInitializing) return null

  if (isAuthenticated) {
    return <Navigate to={getRedirectTarget(location)} replace />
  }

  return <Outlet />
}
