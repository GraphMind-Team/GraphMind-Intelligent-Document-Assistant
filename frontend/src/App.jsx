import { BrowserRouter, Route, Routes } from 'react-router-dom'
import RegisterPage from './pages/RegisterPage'
import HealthPage from './pages/HealthPage'

// Placeholder for routes not built yet (Login ships in Story 1.4), so
// links pointing at them don't dead-end on a blank screen.
function NotBuiltYetPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--bg)] p-8">
      <p className="text-sm text-[var(--text2)]">This page isn't available yet.</p>
    </main>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RegisterPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/login" element={<NotBuiltYetPage />} />
        <Route path="*" element={<NotBuiltYetPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
