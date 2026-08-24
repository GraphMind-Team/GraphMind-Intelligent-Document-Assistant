import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ChatIndexRedirect from './ChatIndexRedirect'
import { useChatSessions } from '../context/ChatSessionsContext'

vi.mock('../context/ChatSessionsContext', () => ({ useChatSessions: vi.fn() }))

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
