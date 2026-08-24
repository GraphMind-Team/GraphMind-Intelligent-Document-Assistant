import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatSessionsProvider, useChatSessions } from './ChatSessionsContext'
import { useAuth } from './AuthContext'
import * as chatSessionsClient from '../api/chatSessionsClient'

vi.mock('./AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

const SESSION_A = { id: 'session-a', title: 'A', created_at: 't1', updated_at: 't1' }
const SESSION_B = { id: 'session-b', title: 'B', created_at: 't2', updated_at: 't2' }

// A minimal consumer exposing the context's own state/actions as buttons
// and text, so these tests exercise the context's contract directly
// rather than through ChatSessionsPanel's UI (that's
// ChatSessionsPanel.test.jsx's job).
function Consumer() {
  const { sessions, activeSessionId, isLoading, createSession, renameSession, deleteSession } = useChatSessions()
  return (
    <div>
      <p data-testid="loading">{String(isLoading)}</p>
      <p data-testid="active">{activeSessionId}</p>
      <ul>
        {sessions.map((session) => (
          <li key={session.id}>{session.title}</li>
        ))}
      </ul>
      <button onClick={() => createSession()}>create</button>
      <button onClick={() => renameSession('session-a', 'A renamed')}>rename a</button>
      <button onClick={() => deleteSession('session-a')}>delete a</button>
      <button onClick={() => deleteSession('session-b')}>delete b</button>
    </div>
  )
}

function CurrentSessionMarker() {
  const { sessionId } = useParams()
  return <p data-testid="route-session">{sessionId}</p>
}

function renderConsumer({ initialSessionId = SESSION_A.id } = {}) {
  useAuth.mockReturnValue({ authFetch: vi.fn() })
  return render(
    <MemoryRouter initialEntries={[`/chat/${initialSessionId}`]}>
      <Routes>
        <Route
          path="/chat/:sessionId"
          element={
            <ChatSessionsProvider>
              <Consumer />
              <CurrentSessionMarker />
            </ChatSessionsProvider>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatSessionsContext', () => {
  it('fetches the list on mount and exposes the URL sessionId as activeSessionId', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    renderConsumer()

    expect(screen.getByTestId('loading')).toHaveTextContent('true')
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('active')).toHaveTextContent('session-a')
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('createSession prepends the new session and navigates to it', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const created = { id: 'session-new', title: null, created_at: 't3', updated_at: 't3' }
    vi.spyOn(chatSessionsClient, 'createChatSession').mockResolvedValue(created)
    const user = userEvent.setup()
    renderConsumer()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await user.click(screen.getByText('create'))

    await waitFor(() => expect(screen.getByTestId('route-session')).toHaveTextContent('session-new'))
  })

  it('renameSession updates the list in place, without reordering', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    vi.spyOn(chatSessionsClient, 'renameChatSession').mockResolvedValue({ ...SESSION_A, title: 'A renamed' })
    const user = userEvent.setup()
    renderConsumer()
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await user.click(screen.getByText('rename a'))

    expect(await screen.findByText('A renamed')).toBeInTheDocument()
    const items = screen.getAllByRole('listitem').map((el) => el.textContent)
    expect(items).toEqual(['A renamed', 'B'])
  })

  it('deleteSession on a non-active session removes it without navigating', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    vi.spyOn(chatSessionsClient, 'deleteChatSession').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderConsumer({ initialSessionId: SESSION_A.id })
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await user.click(screen.getByText('delete b'))

    await waitFor(() => expect(screen.queryByText('B')).not.toBeInTheDocument())
    expect(screen.getByTestId('route-session')).toHaveTextContent('session-a')
  })

  it('deleteSession on the active session falls back to the next session in the list', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    vi.spyOn(chatSessionsClient, 'deleteChatSession').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderConsumer({ initialSessionId: SESSION_A.id })
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await user.click(screen.getByText('delete a'))

    await waitFor(() => expect(screen.getByTestId('route-session')).toHaveTextContent('session-b'))
  })

  it('deleting the last remaining session creates a fresh one instead of leaving an empty list', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    vi.spyOn(chatSessionsClient, 'deleteChatSession').mockResolvedValue(undefined)
    const created = { id: 'session-fresh', title: null, created_at: 't3', updated_at: 't3' }
    vi.spyOn(chatSessionsClient, 'createChatSession').mockResolvedValue(created)
    const user = userEvent.setup()
    renderConsumer({ initialSessionId: SESSION_A.id })
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))

    await user.click(screen.getByText('delete a'))

    await waitFor(() => expect(screen.getByTestId('route-session')).toHaveTextContent('session-fresh'))
  })
})
