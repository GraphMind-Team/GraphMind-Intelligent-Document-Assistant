import { Navigate, Outlet, useLocation } from 'react-router-dom'
import LoadingScreen from './LoadingScreen'
import { useAuth } from '../context/AuthContext'

// Client-side gate for shell routes (Story 1.5). The server already
// enforces auth via 401 on every protected endpoint (1.4) -- this just
// keeps an unauthenticated visitor from ever seeing shell chrome/pages
// with no data behind them, redirecting to /login instead.
export default function ProtectedRoute() {
  const { isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()

  // Wait for AuthContext's boot-time `/auth/me` check before deciding --
  // otherwise a stored-but-expired token would flash shell content for
  // one render before the 401 response evicts it. Bounded by
  // AUTH_ME_CHECK_TIMEOUT_MS (AuthContext.jsx), so this isn't an
  // indefinite wait on a stalled request (e.g. Render cold start).
  if (isInitializing) return <LoadingScreen />

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}
