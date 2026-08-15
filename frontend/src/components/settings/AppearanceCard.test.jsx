import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppearanceCard from './AppearanceCard'
import { useAuth } from '../../context/AuthContext'
import { useTheme } from '../../context/ThemeContext'
import { updateTheme } from '../../api/settingsClient'

vi.mock('../../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../context/ThemeContext', () => ({ useTheme: vi.fn() }))
vi.mock('../../api/settingsClient', () => ({ updateTheme: vi.fn() }))

const authFetch = vi.fn()
const setAccountTheme = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue({ authFetch, setAccountTheme })
})

describe('AppearanceCard', () => {
  it('reflects the current theme as the switch state', () => {
    useTheme.mockReturnValue({ theme: 'dark', setTheme: vi.fn() })

    render(<AppearanceCard />)

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('applies the new theme immediately, saves it to the account, and syncs AuthContext', async () => {
    const setTheme = vi.fn()
    useTheme.mockReturnValue({ theme: 'light', setTheme })
    updateTheme.mockResolvedValue({ theme: 'dark' })
    const user = userEvent.setup()

    render(<AppearanceCard />)
    await user.click(screen.getByRole('switch'))

    expect(setTheme).toHaveBeenCalledWith('dark')
    await waitFor(() => expect(updateTheme).toHaveBeenCalledWith(authFetch, 'dark'))
    // Keeps AuthContext.accountTheme from going stale relative to what was
    // just persisted -- otherwise it sits at the pre-toggle value.
    await waitFor(() => expect(setAccountTheme).toHaveBeenCalledWith('dark'))
  })

  it("shows an inline error naming the account-save failure but keeps the optimistic local theme (doesn't revert)", async () => {
    const setTheme = vi.fn()
    useTheme.mockReturnValue({ theme: 'light', setTheme })
    updateTheme.mockRejectedValue(new Error('Network error.'))
    const user = userEvent.setup()

    render(<AppearanceCard />)
    await user.click(screen.getByRole('switch'))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/didn't save to your account/i))
    expect(setTheme).toHaveBeenCalledWith('dark')
    expect(setTheme).not.toHaveBeenCalledWith('light')
    expect(setAccountTheme).not.toHaveBeenCalled()
  })

  it('disables the toggle while a save is in flight, so a second rapid click cannot fire a second request', async () => {
    useTheme.mockReturnValue({ theme: 'light', setTheme: vi.fn() })
    let resolveUpdate
    updateTheme.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve
      }),
    )
    const user = userEvent.setup()

    render(<AppearanceCard />)
    const toggle = screen.getByRole('switch')

    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-disabled', 'true')
    expect(toggle).toHaveAttribute('aria-busy', 'true')

    // Second click while the first PATCH is still in flight -- this is the
    // race the `saving` guard exists to prevent.
    await user.click(toggle)
    expect(updateTheme).toHaveBeenCalledTimes(1)

    resolveUpdate({ theme: 'dark' })
    await waitFor(() => expect(toggle).toHaveAttribute('aria-disabled', 'false'))
    expect(toggle).toHaveAttribute('aria-busy', 'false')
  })

  it('associates the visible "Dark mode" text with the switch via aria-labelledby, and clicking the text toggles too', async () => {
    const setTheme = vi.fn()
    useTheme.mockReturnValue({ theme: 'light', setTheme })
    updateTheme.mockResolvedValue({ theme: 'dark' })
    const user = userEvent.setup()

    render(<AppearanceCard />)
    const toggle = screen.getByRole('switch')
    const label = screen.getByText('Dark mode')

    expect(toggle).toHaveAttribute('aria-labelledby', label.id)

    await user.click(label)

    expect(setTheme).toHaveBeenCalledWith('dark')
  })

  it('announces save progress and success through a polite live region', async () => {
    useTheme.mockReturnValue({ theme: 'light', setTheme: vi.fn() })
    let resolveUpdate
    updateTheme.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve
      }),
    )
    const user = userEvent.setup()

    render(<AppearanceCard />)
    await user.click(screen.getByRole('switch'))

    expect(screen.getByText('Saving appearance...')).toBeInTheDocument()

    resolveUpdate({ theme: 'dark' })

    await waitFor(() => expect(screen.getByText('Appearance saved.')).toBeInTheDocument())
  })
})
