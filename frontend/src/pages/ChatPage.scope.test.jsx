import { useEffect } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatPage from './ChatPage'
import { useAuth } from '../context/AuthContext'
import { useChatScope } from '../context/ChatScopeContext'

// A separate file from ChatPage.test.jsx: `vi.mock` factories are hoisted
// per-file, so this file's DocumentsScopePanel mock (which calls the real,
// unmocked useChatScope to prove ChatPage actually threads the selected
// scope into askQuestion) cannot coexist with ChatPage.test.jsx's own
// `<div>scope panel stub</div>` mock in the same file.
vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../components/chat/DocumentsScopePanel', () => ({ default: ScopePanelStub }))

// A `function` declaration, not a `const` arrow -- fully hoisted, so it's
// safe to reference from the (also-hoisted) `vi.mock` factory above despite
// appearing later in source order. Named + capitalized so lint's
// rules-of-hooks recognizes it as a component allowed to call useChatScope.
//
// Also reports a fixed one-document list up via `onDocumentsLoaded`,
// mirroring the real DocumentsScopePanel's own contract -- this is what
// lets the preset-scope tests below exercise ChatPage's handling of a
// `presetDocumentId` without a real fetch. Harmless for the two
// pre-existing tests in this file: they never set `presetDocumentId`, so
// ChatPage's own preset effect is a no-op regardless of what this reports.
function ScopePanelStub({ onDocumentsLoaded }) {
  const { toggleDocument } = useChatScope()
  useEffect(() => {
    onDocumentsLoaded?.([{ id: 'doc-9', filename: 'preset.pdf', status: 'Ready' }])
  }, [onDocumentsLoaded])
  return <button onClick={() => toggleDocument('doc-1')}>toggle doc-1</button>
}

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(body) {
  return { ok: true, json: async () => body }
}

// Story 3.4: ChatPage now also fires an initial `GET /chat/history` on
// mount, through this same shared `authFetch` mock -- so the `/chat/ask`
// call is no longer reliably `authFetch.mock.calls[0]`. Finding it by its
// own URL keeps these two tests correct regardless of what else `authFetch`
// gets called with (the history mock resolving as an ask-shaped body
// rather than a history-shaped one causes `getChatHistory` to reject,
// caught silently by ChatPage's own mount effect -- doesn't affect these
// scope assertions either way).
function findAskCall(authFetch) {
  return authFetch.mock.calls.find(([url]) => url === '/chat/ask')
}

describe('ChatPage document scope', () => {
  it('sends the toggled document id as the scope for the next question', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse({ segments: [], empty_reason: null }))
    useAuth.mockReturnValue({ authFetch })
    const user = userEvent.setup()
    render(<ChatPage />, { wrapper: MemoryRouter })

    await user.click(screen.getByRole('button', { name: 'toggle doc-1' }))
    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const [, options] = findAskCall(authFetch)
    expect(JSON.parse(options.body).document_ids).toEqual(['doc-1'])
  })

  it('defaults to an empty scope (ask everything) when nothing is toggled', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse({ segments: [], empty_reason: null }))
    useAuth.mockReturnValue({ authFetch })
    const user = userEvent.setup()
    render(<ChatPage />, { wrapper: MemoryRouter })

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const [, options] = findAskCall(authFetch)
    expect(JSON.parse(options.body).document_ids).toEqual([])
  })

  it('preselects the document handed off from DocumentDetailPage\'s "Ask about this document" link', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse({ segments: [], empty_reason: null }))
    useAuth.mockReturnValue({ authFetch })
    const user = userEvent.setup()
    render(<ChatPage />, {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={[{ pathname: '/chat', state: { presetDocumentId: 'doc-9' } }]}>
          {children}
        </MemoryRouter>
      ),
    })

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const [, options] = findAskCall(authFetch)
    expect(JSON.parse(options.body).document_ids).toEqual(['doc-9'])
  })
})

describe('ChatPage scope chip', () => {
  it('shows no chip when the scope is empty (asking everything)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    render(<ChatPage />, { wrapper: MemoryRouter })

    expect(screen.queryByText(/Asking in/)).not.toBeInTheDocument()
  })

  it('shows a chip once a document is toggled, and clears the scope when its × is clicked', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()
    render(<ChatPage />, { wrapper: MemoryRouter })

    await user.click(screen.getByRole('button', { name: 'toggle doc-1' }))

    expect(screen.getByText('Asking in 1 document')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Ask across all documents instead' }))

    expect(screen.queryByText(/Asking in/)).not.toBeInTheDocument()
  })
})
