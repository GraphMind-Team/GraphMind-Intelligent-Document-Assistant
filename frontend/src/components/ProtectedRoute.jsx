import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Client-side gate for shell routes (Story 1.5). The server already
// enforces auth via 401 on every protected endpoint (1.4) -- this just
// keeps an unauthenticated visitor from ever seeing shell chrome/pages
// with no data behind them, redirecting to /login instead.
export default function ProtectedRoute() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}
