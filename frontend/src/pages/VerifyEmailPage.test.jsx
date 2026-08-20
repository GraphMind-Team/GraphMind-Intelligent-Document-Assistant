import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import VerifyEmailPage from './VerifyEmailPage'
import * as authClient from '../api/authClient'

function renderVerifyEmailPage(initialEntry) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('VerifyEmailPage', () => {
  it('shows a missing-token message when no ?token= is present', () => {
    renderVerifyEmailPage('/verify-email')

    expect(screen.getByText(/verification link missing/i)).toBeInTheDocument()
  })

  it('verifies the token from the URL and shows success', async () => {
    vi.spyOn(authClient, 'verifyEmail').mockResolvedValue({ detail: 'Email verified.' })

    renderVerifyEmailPage('/verify-email?token=abc123')

    expect(await screen.findByText(/^email verified$/i)).toBeInTheDocument()
    expect(authClient.verifyEmail).toHaveBeenCalledWith({ token: 'abc123' })
    expect(authClient.verifyEmail).toHaveBeenCalledTimes(1)
  })

  it('shows the failure message and a resend form when verification fails', async () => {
    vi.spyOn(authClient, 'verifyEmail').mockRejectedValue(
      new Error('This verification link is invalid or has expired.'),
    )
    vi.spyOn(authClient, 'resendVerification').mockResolvedValue({ detail: 'sent' })
    const user = userEvent.setup()

    renderVerifyEmailPage('/verify-email?token=expired')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This verification link is invalid or has expired.',
    )

    await user.type(screen.getByLabelText(/send me a new link/i), 'maria@example.com')
    await user.click(screen.getByRole('button', { name: /resend verification email/i }))

    expect(authClient.resendVerification).toHaveBeenCalledWith({ email: 'maria@example.com' })
    expect(
      await screen.findByText(/if that account exists and isn't verified yet/i),
    ).toBeInTheDocument()
  })
})
