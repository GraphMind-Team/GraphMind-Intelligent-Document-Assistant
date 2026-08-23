import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import * as authClient from '../api/authClient'

function Consumer() {
  const { isAuthenticated, isInitializing, accountTheme, accountFullName, accountEmail } = useAuth()
  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="initializing">{String(isInitializing)}</span>
      <span data-testid="account-theme">{String(accountTheme)}</span>
      <span data-testid="account-full-name">{String(accountFullName)}</span>
      <span data-testid="account-email">{String(accountEmail)}</span>
    </div>
  )
}

function LoginButton() {
  const { login } = useAuth()
  return (
    <button onClick={() => login({ email: 'maria@example.com', password: 'x' }).catch(() => {})}>
      login
    </button>
  )
}

function LogoutButton() {
  const { logout } = useAuth()
  return <button onClick={logout}>logout</button>
}

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AuthContext boot-time token validation', () => {
  it('is not authenticated and not initializing when there is no stored token', () => {
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(screen.getByTestId('initializing')).toHaveTextContent('false')
  })

  it('logs out a stored token the server rejects (expired/deleted account), instead of stranding the user "authenticated"', async () => {
    window.localStorage.setItem('access_token', 'a-stale-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    // Boot-time /auth/me check is in flight -- ProtectedRoute/PublicOnlyRoute
    // must not act on the stale token while this is still pending.
    expect(screen.getByTestId('initializing')).toHaveTextContent('true')

    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'))

    expect(screen.getByTestId('authenticated')).toHaveTextContent('false')
    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/me'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer a-stale-token' }) }),
    )
  })

  it('keeps a stored token authenticated once the server confirms it', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }))

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'))

    expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
    expect(window.localStorage.getItem('access_token')).toBe('a-valid-token')
  })

  it('does not sign the user out on a network error validating the token (not proof the token is invalid)', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    vi.spyOn(global, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'))

    expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
  })

  it(
    'gives up on a stalled /auth/me request instead of hanging forever (e.g. a Render cold start)',
    async () => {
      window.localStorage.setItem('access_token', 'a-valid-token')
      // A fetch that never settles on its own -- exactly what a genuinely
      // stalled request looks like -- but does reject once its AbortSignal
      // fires, same as real fetch. If AuthContext ever stops passing a
      // signal, this promise (and the test) would hang until Vitest's own
      // timeout, rather than resolving via the assertions below.
      vi.spyOn(global, 'fetch').mockImplementation(
        (_url, options) =>
          new Promise((_resolve, reject) => {
            options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
          }),
      )

      render(
        <AuthProvider>
          <Consumer />
        </AuthProvider>,
      )

      expect(screen.getByTestId('initializing')).toHaveTextContent('true')
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/me'),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      )

      await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'), { timeout: 7000 })

      // Timed out, not confirmed invalid -- same "don't know" treatment as
      // a network error, not a forced logout.
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true')
    },
    10000,
  )
})

describe('AuthContext isAuthenticated coercion', () => {
  it('stays unauthenticated if login resolves without an access_token, instead of treating undefined as a session', async () => {
    vi.spyOn(authClient, 'loginAccount').mockResolvedValue({ token_type: 'bearer' })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginButton />
        <Consumer />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('false'))
  })

  it('becomes authenticated once login resolves with a real access_token', async () => {
    vi.spyOn(authClient, 'loginAccount').mockResolvedValue({ access_token: 'real-token', token_type: 'bearer' })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginButton />
        <Consumer />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'))
  })
})

describe('AuthContext accountTheme (Story 5.2)', () => {
  it('sets accountTheme from a successful boot /auth/me response', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ theme: 'dark' }), { status: 200 }),
    )

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('account-theme')).toHaveTextContent('dark'))
  })

  it('leaves accountTheme null when the boot /auth/me check comes back non-ok, instead of parsing an error body as theme data', async () => {
    window.localStorage.setItem('access_token', 'a-stale-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'))

    expect(screen.getByTestId('account-theme')).toHaveTextContent('null')
  })

  it('does not let a boot /auth/me response that resolves after logout repopulate accountTheme', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    let resolveFetch
    vi.spyOn(global, 'fetch').mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LogoutButton />
        <Consumer />
      </AuthProvider>,
    )

    // Log out while the boot check is still in flight -- AuthProvider
    // itself never unmounts here, so the effect's own `cancelled` flag
    // stays false; only tokenRef going null (via logout) should stop the
    // stale response from landing.
    await user.click(screen.getByRole('button', { name: 'logout' }))
    expect(screen.getByTestId('account-theme')).toHaveTextContent('null')

    resolveFetch(new Response(JSON.stringify({ theme: 'dark' }), { status: 200 }))

    await waitFor(() => expect(screen.getByTestId('initializing')).toHaveTextContent('false'))
    expect(screen.getByTestId('account-theme')).toHaveTextContent('null')
  })

  it('sets accountTheme directly from the login response, without a second request', async () => {
    vi.spyOn(authClient, 'loginAccount').mockResolvedValue({
      access_token: 'real-token',
      token_type: 'bearer',
      theme: 'dark',
    })
    vi.spyOn(global, 'fetch')
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginButton />
        <Consumer />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByTestId('account-theme')).toHaveTextContent('dark'))
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('resets accountTheme to null on logout, so it does not leak into the next session', async () => {
    vi.spyOn(authClient, 'loginAccount').mockResolvedValue({
      access_token: 'real-token',
      token_type: 'bearer',
      theme: 'dark',
    })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginButton />
        <LogoutButton />
        <Consumer />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'login' }))
    await waitFor(() => expect(screen.getByTestId('account-theme')).toHaveTextContent('dark'))

    await user.click(screen.getByRole('button', { name: 'logout' }))

    expect(screen.getByTestId('account-theme')).toHaveTextContent('null')
  })
})

describe('AuthContext accountFullName/accountEmail', () => {
  it('sets accountFullName/accountEmail from a successful boot /auth/me response', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ theme: 'dark', full_name: 'Priya Raman', email: 'priya@example.com' }), {
        status: 200,
      }),
    )

    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('account-full-name')).toHaveTextContent('Priya Raman'))
    expect(screen.getByTestId('account-email')).toHaveTextContent('priya@example.com')
  })

  it('stays null after login -- LoginResponse carries no full_name/email to seed it from', async () => {
    // Unlike accountTheme/accountLanguage: this is Shell.jsx's own reason
    // for still running its own `/auth/me` fetch after a fresh login.
    vi.spyOn(authClient, 'loginAccount').mockResolvedValue({
      access_token: 'real-token',
      token_type: 'bearer',
      theme: 'dark',
    })
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LoginButton />
        <Consumer />
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'login' }))

    await waitFor(() => expect(screen.getByTestId('account-theme')).toHaveTextContent('dark'))
    expect(screen.getByTestId('account-full-name')).toHaveTextContent('null')
  })

  it('resets accountFullName/accountEmail to null on logout', async () => {
    window.localStorage.setItem('access_token', 'a-valid-token')
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ theme: 'dark', full_name: 'Priya Raman', email: 'priya@example.com' }), {
        status: 200,
      }),
    )
    const user = userEvent.setup()

    render(
      <AuthProvider>
        <LogoutButton />
        <Consumer />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('account-full-name')).toHaveTextContent('Priya Raman'))

    await user.click(screen.getByRole('button', { name: 'logout' }))

    expect(screen.getByTestId('account-full-name')).toHaveTextContent('null')
    expect(screen.getByTestId('account-email')).toHaveTextContent('null')
  })
})
