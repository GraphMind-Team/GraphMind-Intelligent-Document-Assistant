import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'
import { useAuth } from '../context/AuthContext'
import * as authClient from '../api/authClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

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

describe('LoginPage email-verification gate (Story 1.6)', () => {
  it('offers a resend action when login rejects with a 403', async () => {
    const rejection = new Error(
      'Please verify your email address before logging in. We sent a link when you registered.',
    )
    rejection.status = 403
    useAuth.mockReturnValue({ login: vi.fn().mockRejectedValue(rejection) })
    const user = userEvent.setup()

    renderLoginPage('/login')
    await submitLoginForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/verify your email/i)
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeInTheDocument()
  })

  it('does not offer a resend action on a plain 401', async () => {
    const rejection = new Error('Invalid email or password.')
    rejection.status = 401
    useAuth.mockReturnValue({ login: vi.fn().mockRejectedValue(rejection) })
    const user = userEvent.setup()

    renderLoginPage('/login')
    await submitLoginForm(user)

    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /resend verification email/i })).not.toBeInTheDocument()
  })

  it('confirms inline once the resend action is used', async () => {
    const rejection = new Error('Please verify your email address before logging in.')
    rejection.status = 403
    useAuth.mockReturnValue({ login: vi.fn().mockRejectedValue(rejection) })
    vi.spyOn(authClient, 'resendVerification').mockResolvedValue({ detail: 'sent' })
    const user = userEvent.setup()

    renderLoginPage('/login')
    await submitLoginForm(user)
    await user.click(await screen.findByRole('button', { name: /resend verification email/i }))

    expect(authClient.resendVerification).toHaveBeenCalledWith({ email: 'maria@example.com' })
    expect(
      await screen.findByText(/if that account exists and isn't verified yet/i),
    ).toBeInTheDocument()
  })
})
