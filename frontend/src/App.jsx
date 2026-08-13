import { BrowserRouter, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import PublicOnlyRoute from './components/PublicOnlyRoute'
import Shell from './components/Shell'
import RegisterPage from './pages/RegisterPage'
import LoginPage from './pages/LoginPage'
import HealthPage from './pages/HealthPage'
import DocumentsPage from './pages/DocumentsPage'
import DocumentDetailPage from './pages/DocumentDetailPage'
import ChatPage from './pages/ChatPage'
import GraphPage from './pages/GraphPage'
import SettingsPage from './pages/SettingsPage'

// Catch-all for anything that isn't a real route.
function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-bg p-8">
      <p className="text-sm text-text2">Page not found.</p>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/health" element={<HealthPage />} />

        {/* Already-authenticated visitors get sent into the shell instead
            of seeing a register/login form they don't need. */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/" element={<RegisterPage />} />
          <Route path="/login" element={<LoginPage />} />
        </Route>

        {/* Shell routes (Story 1.5): gated on isAuthenticated, wrapped in
            the fixed-sidebar shell. /documents is the default post-login
            landing route. */}
        <Route element={<ProtectedRoute />}>
          <Route element={<Shell />}>
            <Route path="/documents" element={<DocumentsPage />} />
            {/* Document Detail as a nested route rather than in-page state
                (Story 2.2): back button and deep links come for free, and
                the sidebar's `/documents` NavLink stays the single active
                item on this URL too (UX-DR1), since NavLink matches
                descendant paths by default. */}
            <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/graph" element={<GraphPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
