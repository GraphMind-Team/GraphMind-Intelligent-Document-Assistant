import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatIndexRedirect from './ChatIndexRedirect'
import { useChatSessions } from '../context/ChatSessionsContext'

vi.mock('../context/ChatSessionsContext', () => ({ useChatSessions: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

// Probe standing in for ChatPage at the redirect's target route -- reports
// whatever `location.state` it actually received, so these tests can tell
// a forwarded state apart from a dropped one without depending on
// ChatPage's own (much heavier) rendering.
function LocationStateProbe() {
  const { state } = useLocation()
  return <div>Landed with state: {JSON.stringify(state ?? null)}</div>
}

function renderAtChatIndex(initialState) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/chat', state: initialState }]}>
      <Routes>
        <Route path="/chat" element={<ChatIndexRedirect />} />
        <Route path="/chat/:sessionId" element={<LocationStateProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatIndexRedirect', () => {
  it('creates a session for a brand-new account and redirects to it', async () => {
    const createSession = vi.fn().mockResolvedValue({ id: 'new-session' })
    useChatSessions.mockReturnValue({ sessions: [], isLoading: false, error: null, createSession })

    renderAtChatIndex(undefined)

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

    renderAtChatIndex(undefined)

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

    renderAtChatIndex(undefined)

    expect(await screen.findByText(/Landed with state/)).toBeInTheDocument()
    expect(createSession).not.toHaveBeenCalled()
  })

  it('forwards the incoming location state (e.g. presetDocumentId) to the session it redirects to', async () => {
    useChatSessions.mockReturnValue({
      sessions: [{ id: 'session-1' }],
      isLoading: false,
      error: null,
      createSession: vi.fn(),
    })

    renderAtChatIndex({ presetDocumentId: 'doc-9' })

    expect(await screen.findByText('Landed with state: {"presetDocumentId":"doc-9"}')).toBeInTheDocument()
  })

  it('redirects with no state when none was passed in', async () => {
    useChatSessions.mockReturnValue({
      sessions: [{ id: 'session-1' }],
      isLoading: false,
      error: null,
      createSession: vi.fn(),
    })

    renderAtChatIndex(undefined)

    expect(await screen.findByText('Landed with state: null')).toBeInTheDocument()
  })
})
