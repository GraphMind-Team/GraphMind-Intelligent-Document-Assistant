import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Shell from './Shell'
import { useAuth } from '../context/AuthContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

describe('Shell Log out handler', () => {
  it('logs out and navigates to /login when Log out is clicked', async () => {
    const logout = vi.fn()
    // authFetch is used for the identity block's own `/auth/me` fetch --
    // unresolved here since this test isn't exercising that display, just
    // the logout action.
    useAuth.mockReturnValue({ logout, authFetch: vi.fn().mockResolvedValue({ ok: false }) })
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/documents']}>
        <Routes>
          <Route path="/documents" element={<Shell />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /log out/i }))

    expect(logout).toHaveBeenCalledOnce()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })
})

describe('Shell identity block', () => {
  function renderShell() {
    return render(
      <MemoryRouter initialEntries={['/documents']}>
        <Routes>
          <Route path="/documents" element={<Shell />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('shows the account name/email from AuthContext, not a snapshot fetched once on mount', () => {
    // Regression guard: this used to be Shell's own local state, fetched
    // once on mount and never updated -- a name change saved on
    // Settings -> Profile stayed stale in the sidebar until a full
    // reload. accountFullName/accountEmail now live in AuthContext
    // (ProfileCard.jsx writes them on load and on save), so Shell just
    // has to read them reactively, which this proves by re-rendering with
    // a changed value the way an actual ProfileCard save would.
    useAuth.mockReturnValue({
      logout: vi.fn(),
      authFetch: vi.fn(),
      accountFullName: 'Priya Raman',
      accountEmail: 'priya@example.com',
      setAccountFullName: vi.fn(),
      setAccountEmail: vi.fn(),
    })
    const { rerender } = renderShell()

    expect(screen.getByText('Priya Raman')).toBeInTheDocument()
    expect(screen.getByText('priya@example.com')).toBeInTheDocument()

    useAuth.mockReturnValue({
      logout: vi.fn(),
      authFetch: vi.fn(),
      accountFullName: 'Priya Chen',
      accountEmail: 'priya@example.com',
      setAccountFullName: vi.fn(),
      setAccountEmail: vi.fn(),
    })
    rerender(
      <MemoryRouter initialEntries={['/documents']}>
        <Routes>
          <Route path="/documents" element={<Shell />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Priya Chen')).toBeInTheDocument()
    expect(screen.queryByText('Priya Raman')).not.toBeInTheDocument()
  })

  it('fetches /auth/me itself only when the name is not already known (e.g. right after a fresh login)', async () => {
    const authFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ full_name: 'Priya Raman', email: 'priya@example.com' }),
    })
    const setAccountFullName = vi.fn()
    const setAccountEmail = vi.fn()
    useAuth.mockReturnValue({
      logout: vi.fn(),
      authFetch,
      accountFullName: null,
      accountEmail: null,
      setAccountFullName,
      setAccountEmail,
    })

    renderShell()

    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/auth/me'))
    await waitFor(() => expect(setAccountFullName).toHaveBeenCalledWith('Priya Raman'))
    expect(setAccountEmail).toHaveBeenCalledWith('priya@example.com')
  })

  it('skips its own /auth/me fetch once the name is already known', () => {
    // Doesn't assert `authFetch` overall is untouched -- Shell also
    // mounts DocumentReadyToasts, which calls it independently for
    // /documents. This is specifically about the identity block's own
    // fetch, which the accountFullName-already-known guard should skip.
    const authFetch = vi.fn()
    useAuth.mockReturnValue({
      logout: vi.fn(),
      authFetch,
      accountFullName: 'Priya Raman',
      accountEmail: 'priya@example.com',
      setAccountFullName: vi.fn(),
      setAccountEmail: vi.fn(),
    })

    renderShell()

    expect(authFetch).not.toHaveBeenCalledWith('/auth/me')
  })
})
