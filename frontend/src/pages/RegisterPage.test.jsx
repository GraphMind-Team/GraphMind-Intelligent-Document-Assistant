import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RegisterPage from './RegisterPage'
import * as authClient from '../api/authClient'

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <RegisterPage />
    </MemoryRouter>,
  )
}

async function submitRegisterForm(user) {
  await user.type(screen.getByLabelText(/full name/i), 'Maria Ivanova')
  await user.type(screen.getByLabelText(/^email$/i), 'maria@example.com')
  await user.type(screen.getByLabelText(/password/i), 'correct horse battery staple')
  await user.click(screen.getByRole('button', { name: /create account/i }))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RegisterPage (Story 1.6: check-your-inbox state)', () => {
  it('shows a check-your-inbox panel naming the address after a successful registration', async () => {
    vi.spyOn(authClient, 'registerAccount').mockResolvedValue({ id: '1', email: 'maria@example.com' })
    const user = userEvent.setup()

    renderRegisterPage()
    await submitRegisterForm(user)

    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument()
    expect(screen.getByText('maria@example.com')).toBeInTheDocument()
  })

  it('lets the visitor resend the verification email from the check-your-inbox panel', async () => {
    vi.spyOn(authClient, 'registerAccount').mockResolvedValue({ id: '1', email: 'maria@example.com' })
    vi.spyOn(authClient, 'resendVerification').mockResolvedValue({ detail: 'sent' })
    const user = userEvent.setup()

    renderRegisterPage()
    await submitRegisterForm(user)
    await user.click(await screen.findByRole('button', { name: /resend verification email/i }))

    expect(authClient.resendVerification).toHaveBeenCalledWith({ email: 'maria@example.com' })
    expect(
      await screen.findByText(/if that account exists and isn't verified yet/i),
    ).toBeInTheDocument()
  })

  it('still confirms "sent" when the resend request itself fails (e.g. rate-limited)', async () => {
    // Regression test: handleResend used to setResendState('sent') in a
    // `finally` block, which let the rejection keep propagating as an
    // unhandled promise rejection after already showing "sent". This
    // pins the fixed behavior -- a rejected resend (a 429 from the rate
    // limiter is a real, reachable case since the button stays clickable)
    // must resolve cleanly to the same "sent" confirmation, not leak an
    // unhandled rejection.
    vi.spyOn(authClient, 'registerAccount').mockResolvedValue({ id: '1', email: 'maria@example.com' })
    vi.spyOn(authClient, 'resendVerification').mockRejectedValue(
      new Error('Too many verification email requests. Try again later.'),
    )
    const user = userEvent.setup()

    renderRegisterPage()
    await submitRegisterForm(user)
    await user.click(await screen.findByRole('button', { name: /resend verification email/i }))

    expect(
      await screen.findByText(/if that account exists and isn't verified yet/i),
    ).toBeInTheDocument()
  })

  it('shows the error and stays on the form when registration fails', async () => {
    vi.spyOn(authClient, 'registerAccount').mockRejectedValue(
      new Error('An account with this email already exists.'),
    )
    const user = userEvent.setup()

    renderRegisterPage()
    await submitRegisterForm(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('An account with this email already exists.')
    expect(screen.queryByText(/check your inbox/i)).not.toBeInTheDocument()
  })
})
