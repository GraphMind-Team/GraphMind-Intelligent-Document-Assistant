import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatIndexRedirect from './ChatIndexRedirect'
import { useChatSessions } from '../context/ChatSessionsContext'

vi.mock('../context/ChatSessionsContext', () => ({ useChatSessions: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <Routes>
        <Route path="/chat" element={<ChatIndexRedirect />} />
        <Route path="/chat/:sessionId" element={<p>landed on a session</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatIndexRedirect', () => {
  it('creates a session for a brand-new account and redirects to it', async () => {
    const createSession = vi.fn().mockResolvedValue({ id: 'new-session' })
    useChatSessions.mockReturnValue({ sessions: [], isLoading: false, error: null, createSession })

    renderPage()

    await waitFor(() => expect(createSession).toHaveBeenCalled())
  })

  it('shows an error instead of spinning forever when the create fails', async () => {
    // A rejected createSession must not be an unhandled rejection, and
    // there is no second attempt -- ChatIndexRedirect.jsx's own
    // `hasRequestedCreateRef` guard is one-shot per mount, so leaving the
    // failure unhandled would strand the user on the loading spinner
    // indefinitely.
    const createSession = vi.fn().mockRejectedValue(new Error('Could not start a new chat.'))
    useChatSessions.mockReturnValue({ sessions: [], isLoading: false, error: null, createSession })

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not start a new chat.')
  })

  it('redirects to the first (most-recently-active) session without creating a new one', async () => {
    const createSession = vi.fn()
    useChatSessions.mockReturnValue({
      sessions: [{ id: 'session-a' }, { id: 'session-b' }],
      isLoading: false,
      error: null,
      createSession,
    })

    renderPage()

    expect(await screen.findByText('landed on a session')).toBeInTheDocument()
    expect(createSession).not.toHaveBeenCalled()
  })
})
