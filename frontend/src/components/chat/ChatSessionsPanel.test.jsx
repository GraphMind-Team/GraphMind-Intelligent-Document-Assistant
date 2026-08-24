import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Outlet, Route, Routes, useParams } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatSessionsPanel from './ChatSessionsPanel'
import { useAuth } from '../../context/AuthContext'
import { ChatSessionsProvider } from '../../context/ChatSessionsContext'
import * as chatSessionsClient from '../../api/chatSessionsClient'

vi.mock('../../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

const SESSION_A = {
  id: 'session-a',
  title: 'Refund policy',
  created_at: '2026-08-19T00:00:00Z',
  updated_at: '2026-08-19T00:00:00Z',
}
const SESSION_B = {
  id: 'session-b',
  title: null,
  created_at: '2026-08-18T00:00:00Z',
  updated_at: '2026-08-18T00:00:00Z',
}

// Shows the active route's own `sessionId` param -- lets tests assert
// ChatSessionsContext actually navigated, not just that it called the API.
function CurrentSessionMarker() {
  const { sessionId } = useParams()
  return <p data-testid="current-session">{sessionId}</p>
}

function renderPanel({ initialSessionId = SESSION_A.id } = {}) {
  useAuth.mockReturnValue({ authFetch: vi.fn() })
  return render(
    <MemoryRouter initialEntries={[`/chat/${initialSessionId}`]}>
      <Routes>
        <Route
          element={
            <ChatSessionsProvider>
              <Outlet />
            </ChatSessionsProvider>
          }
        >
          <Route
            path="/chat/:sessionId"
            element={
              <>
                <ChatSessionsPanel />
                <CurrentSessionMarker />
              </>
            }
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('ChatSessionsPanel: list', () => {
  it('renders each session by title, falling back to "New chat" for a titleless one', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    renderPanel()

    expect(await screen.findByText('Refund policy')).toBeInTheDocument()
    // Scoped to the list itself: the "+ New chat" create button above it
    // has the identical accessible name "New chat", which a page-wide
    // query would also match.
    expect(within(screen.getByRole('list')).getByText('New chat')).toBeInTheDocument()
  })

  it('shows the empty-state message when the account has no chats', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([])
    renderPanel()

    expect(await screen.findByText('No chats yet.')).toBeInTheDocument()
  })

  it('surfaces a load error', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockRejectedValue(new Error('Failed to load chats.'))
    renderPanel()

    expect(await screen.findByText('Failed to load chats.')).toBeInTheDocument()
  })
})

describe('ChatSessionsPanel: create', () => {
  it('clicking "New chat" creates a session and navigates to it', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const created = { id: 'session-new', title: null, created_at: 'now', updated_at: 'now' }
    const createSpy = vi.spyOn(chatSessionsClient, 'createChatSession').mockResolvedValue(created)
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'New chat' }))

    await waitFor(() => expect(createSpy).toHaveBeenCalled())
    expect(await screen.findByTestId('current-session')).toHaveTextContent('session-new')
  })
})

describe('ChatSessionsPanel: rename', () => {
  it('swaps the label for an input, and Enter commits the new title', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const renameSpy = vi
      .spyOn(chatSessionsClient, 'renameChatSession')
      .mockResolvedValue({ ...SESSION_A, title: 'Renamed chat' })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Rename Refund policy' }))
    const input = screen.getByLabelText('Rename chat')
    await user.clear(input)
    await user.type(input, 'Renamed chat{Enter}')

    await waitFor(() => expect(renameSpy).toHaveBeenCalledWith(expect.anything(), 'session-a', 'Renamed chat'))
    expect(await screen.findByText('Renamed chat')).toBeInTheDocument()
  })

  it('Escape cancels the rename without calling the API', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const renameSpy = vi.spyOn(chatSessionsClient, 'renameChatSession')
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Rename Refund policy' }))
    await user.type(screen.getByLabelText('Rename chat'), ' more text{Escape}')

    expect(screen.queryByLabelText('Rename chat')).not.toBeInTheDocument()
    expect(screen.getByText('Refund policy')).toBeInTheDocument()
    expect(renameSpy).not.toHaveBeenCalled()
  })
})

describe('ChatSessionsPanel: delete', () => {
  it('shows an inline confirm box on the delete icon, without deleting anything yet', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const deleteSpy = vi.spyOn(chatSessionsClient, 'deleteChatSession')
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Delete Refund policy' }))

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('Cancel collapses the confirm box without deleting', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    const deleteSpy = vi.spyOn(chatSessionsClient, 'deleteChatSession')
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Delete Refund policy' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('Confirm calls deleteChatSession and removes the row', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    const deleteSpy = vi.spyOn(chatSessionsClient, 'deleteChatSession').mockResolvedValue(undefined)
    const user = userEvent.setup()
    // Session B (titleless -- "New chat") is the active one here, session
    // A is the one being deleted, so no fallback navigation is triggered
    // and the delete's own row-removal is what's under test in isolation.
    renderPanel({ initialSessionId: SESSION_B.id })
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Delete Refund policy' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith(expect.anything(), 'session-a'))
    await waitFor(() => expect(screen.queryByText('Refund policy')).not.toBeInTheDocument())
  })

  it('deleting the currently active session navigates to the next one in the list', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A, SESSION_B])
    vi.spyOn(chatSessionsClient, 'deleteChatSession').mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPanel({ initialSessionId: SESSION_A.id })
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Delete Refund policy' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(screen.getByTestId('current-session')).toHaveTextContent('session-b'))
  })

  it('on failure, shows the error inline and keeps the confirm box for retry', async () => {
    vi.spyOn(chatSessionsClient, 'listChatSessions').mockResolvedValue([SESSION_A])
    vi.spyOn(chatSessionsClient, 'deleteChatSession').mockRejectedValue(new Error('Chat session not found.'))
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Refund policy')

    await user.click(screen.getByRole('button', { name: 'Delete Refund policy' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Chat session not found.')).toBeInTheDocument()
    // Still in the confirm view (not reverted to the normal row) --
    // the same session's title is still named in its own confirm sentence.
    expect(screen.getByText('Delete "Refund policy"? This can\'t be undone.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })
})
