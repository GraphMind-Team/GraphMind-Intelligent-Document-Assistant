import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ProtectedRoute from './components/ProtectedRoute'
import PublicOnlyRoute from './components/PublicOnlyRoute'
import Shell from './components/Shell'
import RegisterPage from './pages/RegisterPage'
import LoginPage from './pages/LoginPage'
import VerifyEmailPage from './pages/VerifyEmailPage'
import LandingPage from './pages/LandingPage'
import HealthPage from './pages/HealthPage'
import DocumentsPage from './pages/DocumentsPage'
import DocumentDetailPage from './pages/DocumentDetailPage'
import ChatPage from './pages/ChatPage'
import GraphPage from './pages/GraphPage'
import SettingsPage from './pages/SettingsPage'
import ThemeAccountSync from './components/ThemeAccountSync'
import LanguageAccountSync from './components/LanguageAccountSync'

// Catch-all for anything that isn't a real route.
function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <main className="app-aurora flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <p className="font-display text-[22px] font-bold text-text">{t('notFound.message')}</p>
      <Link to="/" className="btn-brand rounded-full px-6 py-3 text-sm font-semibold">
        {t('notFound.backHome')}
      </Link>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <ThemeAccountSync />
      <LanguageAccountSync />
      <Routes>
        <Route path="/health" element={<HealthPage />} />

        {/* The public front door. Deliberately *not* under
            PublicOnlyRoute: a landing page that bounces signed-in
            visitors makes the product's own logo a broken link for
            them. It adapts its calls to action instead. */}
        <Route path="/" element={<LandingPage />} />

        {/* Story 1.6: reached only by clicking an emailed verify link, so
            it sits outside both guards below -- PublicOnlyRoute would
            bounce a visitor who happens to still have a session, and
            ProtectedRoute would bounce the (normal) logged-out case. */}
        <Route path="/verify-email" element={<VerifyEmailPage />} />

        {/* Already-authenticated visitors get sent into the shell instead
            of seeing a register/login form they don't need. */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/register" element={<RegisterPage />} />
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
