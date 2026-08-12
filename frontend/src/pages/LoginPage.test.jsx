import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'
import { useAuth } from '../context/AuthContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

function renderLoginPage(initialEntry) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/documents" element={<div>Documents page</div>} />
        <Route path="/chat" element={<div>Chat page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function submitLoginForm(user) {
  await user.type(screen.getByLabelText(/email/i), 'maria@example.com')
  await user.type(screen.getByLabelText(/password/i), 'correct horse battery staple')
  await user.click(screen.getByRole('button', { name: /log in/i }))
}

describe('LoginPage redirect-target logic', () => {
  it('navigates to /documents (the default) when there is no location.state.from', async () => {
    useAuth.mockReturnValue({ login: vi.fn().mockResolvedValue({}) })
    const user = userEvent.setup()

    renderLoginPage('/login')
    await submitLoginForm(user)

    expect(await screen.findByText('Documents page')).toBeInTheDocument()
  })

  it('navigates back to location.state.from when ProtectedRoute redirected the user here', async () => {
    useAuth.mockReturnValue({ login: vi.fn().mockResolvedValue({}) })
    const user = userEvent.setup()

    renderLoginPage({ pathname: '/login', state: { from: { pathname: '/chat', search: '', hash: '' } } })
    await submitLoginForm(user)

    expect(await screen.findByText('Chat page')).toBeInTheDocument()
  })

  it('shows the error and stays on the page when login rejects', async () => {
    useAuth.mockReturnValue({ login: vi.fn().mockRejectedValue(new Error('Invalid email or password.')) })
    const user = userEvent.setup()

    renderLoginPage('/login')
    await submitLoginForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
    expect(screen.queryByText('Documents page')).not.toBeInTheDocument()
  })
})
