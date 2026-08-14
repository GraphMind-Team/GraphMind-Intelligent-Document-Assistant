import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
function ScopePanelStub() {
  const { toggleDocument } = useChatScope()
  return <button onClick={() => toggleDocument('doc-1')}>toggle doc-1</button>
}

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(body) {
  return { ok: true, json: async () => body }
}

describe('ChatPage document scope', () => {
  it('sends the toggled document id as the scope for the next question', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse({ segments: [], empty_reason: null }))
    useAuth.mockReturnValue({ authFetch })
    const user = userEvent.setup()
    render(<ChatPage />)

    await user.click(screen.getByRole('button', { name: 'toggle doc-1' }))
    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const [, options] = authFetch.mock.calls[0]
    expect(JSON.parse(options.body).document_ids).toEqual(['doc-1'])
  })

  it('defaults to an empty scope (ask everything) when nothing is toggled', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse({ segments: [], empty_reason: null }))
    useAuth.mockReturnValue({ authFetch })
    const user = userEvent.setup()
    render(<ChatPage />)

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const [, options] = authFetch.mock.calls[0]
    expect(JSON.parse(options.body).document_ids).toEqual([])
  })
})
