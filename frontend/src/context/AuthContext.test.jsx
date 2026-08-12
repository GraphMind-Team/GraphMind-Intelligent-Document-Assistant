import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import * as authClient from '../api/authClient'

function Consumer() {
  const { isAuthenticated, isInitializing } = useAuth()
  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="initializing">{String(isInitializing)}</span>
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
