import { BrowserRouter, Route, Routes } from 'react-router-dom'
import RegisterPage from './pages/RegisterPage'
import HealthPage from './pages/HealthPage'

// Login ships in Story 1.4 -- a known, upcoming route, not a wrong URL.
function LoginNotBuiltYetPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <p className="text-sm text-[var(--text2)]">This page isn't available yet.</p>
    </main>
  )
}

// Catch-all for anything that isn't a real route -- an honest "not found"
// rather than reusing the Login placeholder's wording, which would imply
// the URL is a recognized future page.
function NotFoundPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <p className="text-sm text-[var(--text2)]">Page not found.</p>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RegisterPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/login" element={<LoginNotBuiltYetPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
