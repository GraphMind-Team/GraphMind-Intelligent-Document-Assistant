import { BrowserRouter, Route, Routes } from 'react-router-dom'
import RegisterPage from './pages/RegisterPage'
import LoginPage from './pages/LoginPage'
import HealthPage from './pages/HealthPage'

// Catch-all for anything that isn't a real route.
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
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
