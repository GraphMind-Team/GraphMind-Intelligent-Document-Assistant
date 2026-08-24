import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatPage from './ChatPage'
import { useAuth } from '../context/AuthContext'
import * as chatClient from '../api/chatClient'

const SESSION_ID = 'session-1'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../components/chat/DocumentsScopePanel', () => ({
  default: () => <div>scope panel stub</div>,
}))
// ChatSessionsPanel reads ChatSessionsContext -- out of scope for this
// file (its own create/rename/delete flows are covered by
// ChatSessionsPanel.test.jsx), and this file has no ChatSessionsProvider
// ancestor to satisfy it.
vi.mock('../components/chat/ChatSessionsPanel', () => ({
  default: () => <div>sessions panel stub</div>,
}))
// ChatPage itself now also calls useChatSessions() directly (to refresh
// the sessions list once the first turn's auto-title lands) -- same
// "no ChatSessionsProvider ancestor here" reason as the panel mock above.
vi.mock('../context/ChatSessionsContext', () => ({ useChatSessions: () => ({ refresh: vi.fn() }) }))

afterEach(() => {
  vi.restoreAllMocks()
})

// Renders at a real, matched `/chat/:sessionId` route (mirrors how
// App.jsx actually mounts ChatPage) so `useParams()` resolves a real
// `sessionId` instead of `undefined` -- every mocked `askQuestion`/
// `getChatHistory` call below expects that as their second argument.
function renderAtChatRoute(ui, { initialEntries = [`/chat/${SESSION_ID}`] } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/chat/:sessionId" element={ui} />
      </Routes>
    </MemoryRouter>,
  )
}

// Story 3.4: every render now fires an initial `GET /chat/history` fetch
// on mount -- defaults to an empty page here (mirrors a brand-new
// account) so every pre-3.4 test's "starts with an empty thread"
// assumption keeps holding without each one having to mock this itself.
// Pass `historyPage` to control what that initial fetch resolves to for
// a test that specifically exercises history loading.
function renderChatPage({ historyPage } = {}) {
  useAuth.mockReturnValue({ authFetch: vi.fn() })
  vi.spyOn(chatClient, 'getChatHistory').mockResolvedValue(
    historyPage ?? { messages: [], next_cursor: null, has_more: false },
  )
  return renderAtChatRoute(<ChatPage />)
}

// Mirrors the real `AskResponse` shape, `chunk_indexes` included -- nothing
// on this page renders that field (the chip's format is fixed by UX-DR3),
// but a fixture that silently drifts from the API it stands in for stops
// being evidence of anything.
const ANSWER_RESULT = {
  message_id: 'assistant-msg-1',
  segments: [
    {
      text: "TechCorp's refund window is 30 days.",
      citations: [
        {
          chapter: 'Chapter 4',
          document_filename: 'Vendor_Agreement_2026.pdf',
          chunk_indexes: [0, 3],
        },
      ],
    },
  ],
  empty_reason: null,
}

describe('ChatPage', () => {
  it('submits via clicking Ask', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the refund window?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
    // Citations now sit behind a single collapsed "N source(s)" pill
    // (CitationSummary) instead of rendering inline -- open it before
    // asserting the citation text underneath.
    await user.click(await screen.findByRole('button', { name: '1 source' }))
    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()
  })

  it('submits via pressing Enter', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the refund window?{Enter}')

    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: '1 source' }))
    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()
  })

  it('renders the user message before the assistant reply arrives', async () => {
    let resolveAsk
    vi.spyOn(chatClient, 'askQuestion').mockReturnValue(
      new Promise((resolve) => {
        resolveAsk = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'A question{Enter}')

    expect(screen.getByText('A question')).toBeInTheDocument()
    expect(screen.queryByText(/Ch\./)).not.toBeInTheDocument()

    resolveAsk({ segments: [], empty_reason: null })
  })

  it('renders a real <cite> chip with the exact citation text on success', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    await user.click(await screen.findByRole('button', { name: '1 source' }))
    const chip = screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')
    expect(chip.tagName).toBe('CITE')
  })

  it('renders the model-suggested follow-up questions as clickable chips and sends one immediately on click', async () => {
    const askSpy = vi.spyOn(chatClient, 'askQuestion').mockResolvedValueOnce({
      ...ANSWER_RESULT,
      followup_questions: ['Who else is connected to this project?', 'What is the renewal date?'],
    })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const followupChip = await screen.findByRole('button', { name: 'Who else is connected to this project?' })
    expect(screen.getByRole('button', { name: 'What is the renewal date?' })).toBeInTheDocument()

    askSpy.mockResolvedValueOnce({ ...ANSWER_RESULT, message_id: 'assistant-msg-2', followup_questions: [] })
    await user.click(followupChip)

    // Sent immediately -- same "click sends, doesn't just fill the input"
    // behavior the empty-thread welcome's own sample-question chips use.
    expect(askSpy).toHaveBeenLastCalledWith(
      expect.anything(),
      SESSION_ID,
      'Who else is connected to this project?',
      [],
    )
    // Two matches now: the still-visible chip on the first answer (a
    // message's own follow-ups don't disappear once a later turn is
    // asked) plus the new turn's own user bubble echoing the same text.
    await waitFor(() =>
      expect(screen.getAllByText('Who else is connected to this project?')).toHaveLength(2),
    )
  })

  it('renders no follow-up section when the response has none', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue({ ...ANSWER_RESULT, followup_questions: [] })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    await screen.findByRole('button', { name: '1 source' })
    expect(screen.queryByText('Ask more:')).not.toBeInTheDocument()
  })

  it('renders a distinct service banner for a 503, never as an assistant message', async () => {
    const error = new Error('Answer generation is temporarily unavailable. Please try again.')
    error.isServiceError = true
    vi.spyOn(chatClient, 'askQuestion').mockRejectedValue(error)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong generating an answer. Please try again.',
    )
    // Never appended to the message thread as an assistant bubble.
    expect(screen.queryByText('Answer generation is temporarily unavailable. Please try again.')).not.toBeInTheDocument()
  })

  it('renders the generic error path for a non-503 failure', async () => {
    const error = new Error('The request timed out or the network failed. Please try again.')
    vi.spyOn(chatClient, 'askQuestion').mockRejectedValue(error)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The request timed out or the network failed. Please try again.',
    )
  })

  it('renders distinct plain notices for "no_documents" vs "no_answer", neither as a bubble', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValueOnce({ segments: [], empty_reason: 'no_documents' })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q1{Enter}')
    const noDocumentsNotice = await screen.findByText('No documents are available to search yet.')
    expect(noDocumentsNotice.tagName).toBe('P')
    expect(noDocumentsNotice).not.toHaveClass('bg-surface')

    vi.spyOn(chatClient, 'askQuestion').mockResolvedValueOnce({ segments: [], empty_reason: 'no_answer' })
    await user.type(screen.getByLabelText(/ask a question/i), 'q2{Enter}')
    const noAnswerNotice = await screen.findByText('GraphMind could not generate an answer for this question.')
    expect(noAnswerNotice.tagName).toBe('P')
    expect(noAnswerNotice).not.toHaveClass('bg-surface')

    // The two notices are distinguishable from each other...
    expect(noDocumentsNotice.textContent).not.toBe(noAnswerNotice.textContent)
    // ...and the earlier notice is still present (persists in the thread).
    expect(screen.getByText('No documents are available to search yet.')).toBeInTheDocument()
  })

  it('renders the refusal as a real bubble, distinct from the plain empty-state notices', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue({ segments: [], empty_reason: 'refusal' })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const refusalText = await screen.findByText(
      'No supporting evidence found in your documents for this question.',
    )
    // A real bubble (DIV with the dedicated refusal fill), unlike the
    // no_documents/no_answer notices above which are bare <p> elements.
    expect(refusalText.closest('div')).toHaveClass('bg-refusal-bg')
    // Announced distinctly to screen readers, not merely styled
    // differently -- its own sr-only prefix, never "GraphMind:".
    expect(refusalText.closest('div')).toHaveTextContent(/^Refusal:/)
  })

  it('carries aria-live="polite" on the message list', () => {
    renderChatPage()

    const liveRegion = document.querySelector('[aria-live="polite"]')
    expect(liveRegion).toBeInTheDocument()
    expect(liveRegion).toHaveAttribute('aria-atomic', 'false')
  })

  it('makes the message list keyboard-focusable via role="log"', () => {
    renderChatPage()

    // Chrome 127+ makes an overflow scroller focusable on its own, but
    // Firefox/Safari don't -- role="log" + tabIndex are what let a
    // keyboard-only user scroll back through a long thread in every
    // browser, not just Chrome.
    const log = screen.getByRole('log', { name: /conversation/i })
    expect(log).toHaveAttribute('tabindex', '0')
  })

  it('gives each message bubble a screen-reader-only sender cue', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the refund window?{Enter}')

    // Sighted users get the sender cue from alignment/fill/corner shape
    // (UX-DR5) alone -- a screen reader gets none of that without an
    // explicit prefix, so the two turns would otherwise read as one
    // undifferentiated stream.
    const userBubble = screen.getByText('What is the refund window?').closest('div')
    expect(userBubble).toHaveTextContent(/^You:/)

    const assistantText = await screen.findByText("TechCorp's refund window is 30 days.", {
      exact: false,
    })
    expect(assistantText.closest('div')).toHaveTextContent(/^GraphMind:/)
  })

  it('caps the question input at 2000 characters via maxLength', () => {
    renderChatPage()

    expect(screen.getByLabelText(/ask a question/i)).toHaveAttribute('maxlength', '2000')
  })

  it('renders the empty_scope notice distinctly from no_documents/no_answer', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue({ segments: [], empty_reason: 'empty_scope' })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    const notice = await screen.findByText('No content found in the documents you selected.')
    expect(notice.tagName).toBe('P')
  })

  it('falls back to generic notice copy for an unrecognized empty_reason', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue({
      segments: [],
      empty_reason: 'some_future_reason',
    })
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    expect(
      await screen.findByText('GraphMind has nothing to show for this question.'),
    ).toBeInTheDocument()
  })

  it('scrolls the message list to the newest content when a message is appended', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    // jsdom never actually lays anything out, so scrollHeight/scrollTop
    // stay 0 unless stubbed -- this asserts the effect's own logic
    // (scrollTop set to match scrollHeight), not real browser scrolling.
    const liveRegion = document.querySelector('[aria-live="polite"]')
    Object.defineProperty(liveRegion, 'scrollHeight', { value: 900, configurable: true })

    await user.type(screen.getByLabelText(/ask a question/i), 'q{Enter}')

    expect(liveRegion.scrollTop).toBe(900)
  })

  it('keeps focus on the question input through a pending request instead of dropping it to <body>', async () => {
    let resolveAsk
    vi.spyOn(chatClient, 'askQuestion').mockReturnValue(
      new Promise((resolve) => {
        resolveAsk = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatPage()

    const input = screen.getByLabelText(/ask a question/i)
    await user.type(input, 'q{Enter}')

    // readOnly (not disabled) while isAsking -- a disabled input would
    // have kicked focus to <body> here, with no reliable moment to
    // restore it once the request settles.
    expect(input).toHaveAttribute('readonly')
    expect(document.activeElement).toBe(input)

    resolveAsk({ segments: [], empty_reason: null })
  })

  it('keeps focus on the Ask button through a pending request instead of dropping it to <body>', async () => {
    let resolveAsk
    vi.spyOn(chatClient, 'askQuestion').mockReturnValue(
      new Promise((resolve) => {
        resolveAsk = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q')
    const button = screen.getByRole('button', { name: /ask/i })
    await user.click(button)

    // aria-disabled, not disabled -- a disabled button that currently
    // holds focus (a keyboard/mouse user who activated Ask directly,
    // rather than Enter from the input) would drop focus to <body> with
    // no reliable moment to restore it, same reasoning as the input's
    // readOnly case above.
    expect(button).toHaveAttribute('aria-disabled', 'true')
    expect(button).not.toBeDisabled()
    expect(document.activeElement).toBe(button)

    resolveAsk({ segments: [], empty_reason: null })
  })

  it('does not submit a second time when Ask is clicked again while a request is already pending', async () => {
    let resolveAsk
    const askSpy = vi.spyOn(chatClient, 'askQuestion').mockReturnValue(
      new Promise((resolve) => {
        resolveAsk = resolve
      }),
    )
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'q')
    const button = screen.getByRole('button', { name: /ask/i })
    await user.click(button)
    // Button is only aria-disabled (see above), so a second click still
    // reaches handleSubmit -- must be blocked there by the isAsking guard,
    // not by the browser refusing to dispatch the click at all.
    await user.click(button)

    expect(askSpy).toHaveBeenCalledTimes(1)

    resolveAsk({ segments: [], empty_reason: null })
  })
})

// Story 3.4/FR-17: initial history load, scroll-up pagination, and the
// aria-live exclusion for revealed (as opposed to genuinely new) content.
describe('ChatPage conversation history (Story 3.4)', () => {
  it('requests exactly the 10 most recent messages on initial load (UX-DR29)', async () => {
    const historySpy = vi.spyOn(chatClient, 'getChatHistory').mockResolvedValue({
      messages: [],
      next_cursor: null,
      has_more: false,
    })
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)

    await waitFor(() => expect(historySpy).toHaveBeenCalled())
    const [, sessionArg, options] = historySpy.mock.calls[0]
    expect(sessionArg).toBe(SESSION_ID)
    expect(options).toEqual({ limit: 10 })
  })

  it('renders messages loaded from history in chronological (oldest-first) order', async () => {
    renderChatPage({
      historyPage: {
        // The backend returns newest-first -- the page must reverse this
        // back to chronological order before rendering.
        messages: [
          {
            id: 'm2',
            role: 'assistant',
            question: null,
            segments: [{ text: 'TechCorp is the vendor.', citations: [] }],
            empty_reason: null,
            created_at: '2026-01-01T00:00:02',
          },
          {
            id: 'm1',
            role: 'user',
            question: 'Who is the vendor?',
            segments: null,
            empty_reason: null,
            created_at: '2026-01-01T00:00:01',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })

    expect(await screen.findByText('Who is the vendor?')).toBeInTheDocument()
    expect(await screen.findByText('TechCorp is the vendor.', { exact: false })).toBeInTheDocument()
  })

  it('renders a persisted refusal from history as the same dedicated bubble a live refusal uses', async () => {
    renderChatPage({
      historyPage: {
        messages: [
          {
            id: 'm2',
            role: 'assistant',
            question: null,
            segments: [],
            empty_reason: 'refusal',
            created_at: '2026-01-01T00:00:02',
          },
          {
            id: 'm1',
            role: 'user',
            question: 'Something unrelated?',
            segments: null,
            empty_reason: null,
            created_at: '2026-01-01T00:00:01',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })

    const refusalText = await screen.findByText(
      'No supporting evidence found in your documents for this question.',
    )
    expect(refusalText.closest('div')).toHaveClass('bg-refusal-bg')
  })

  it('loads a further page at limit=10 when the message list is scrolled to the top', async () => {
    const historySpy = vi.spyOn(chatClient, 'getChatHistory')
    historySpy.mockResolvedValueOnce({
      messages: [
        {
          id: 'm2',
          role: 'user',
          question: 'Recent question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:02',
        },
      ],
      next_cursor: 'cursor-1',
      has_more: true,
    })
    historySpy.mockResolvedValueOnce({
      messages: [
        {
          id: 'm1',
          role: 'user',
          question: 'Older question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:01',
        },
      ],
      next_cursor: null,
      has_more: false,
    })
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)

    expect(await screen.findByText('Recent question?')).toBeInTheDocument()
    expect(screen.queryByText('Older question?')).not.toBeInTheDocument()

    const log = screen.getByRole('log', { name: /conversation/i })
    fireEvent.scroll(log, { target: { scrollTop: 0 } })

    expect(await screen.findByText('Older question?')).toBeInTheDocument()
    const [, , secondCallOptions] = historySpy.mock.calls[1]
    expect(secondCallOptions).toEqual({ cursor: 'cursor-1', limit: 10 })
  })

  it('pulls older pages in on its own until the thread is tall enough to scroll', async () => {
    // Regression (the "Load earlier messages" button's own reason for
    // existing, after that button was removed): scroll is the only trigger
    // for the next page, and a scroll event can only fire on a scroller
    // that actually overflows. A returning user whose 3-message initial
    // page doesn't fill the container therefore had nothing to scroll and
    // no way at all to reach their own history -- it simply wasn't there.
    //
    // jsdom has no layout, so both measurements are 0 and the component's
    // own `clientHeight > 0` guard would skip the auto-fill entirely.
    // These stubs stand in for the layout jsdom doesn't do: a fixed 500px
    // viewport, and a content height that grows 200px per message -- so
    // the thread starts un-overflowed (1 message = 200px < 500px) and
    // crosses the threshold only once a third message has been pulled in.
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      get() {
        return this.getAttribute('role') === 'log' ? 500 : 0
      },
    })
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get() {
        return this.getAttribute('role') === 'log' ? this.childElementCount * 200 : 0
      },
    })

    const historySpy = vi.spyOn(chatClient, 'getChatHistory')
    const page = (id, question, cursor, hasMore) => ({
      messages: [
        {
          id,
          role: 'user',
          question,
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:01',
        },
      ],
      next_cursor: cursor,
      has_more: hasMore,
    })
    historySpy.mockResolvedValueOnce(page('m3', 'Newest question?', 'cursor-1', true))
    historySpy.mockResolvedValueOnce(page('m2', 'Middle question?', 'cursor-2', true))
    historySpy.mockResolvedValueOnce(page('m1', 'Oldest question?', null, false))
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)

    // No scroll gesture anywhere in this test: the thread fills itself.
    expect(await screen.findByText('Oldest question?')).toBeInTheDocument()
    expect(screen.getByText('Middle question?')).toBeInTheDocument()
    expect(screen.getByText('Newest question?')).toBeInTheDocument()

    // And it stops there rather than draining the whole conversation:
    // 3 messages x 200px now exceeds the 500px viewport, so the scroller
    // overflows and `handleMessageListScroll` is the trigger again.
    expect(historySpy).toHaveBeenCalledTimes(3)

    delete HTMLElement.prototype.clientHeight
    delete HTMLElement.prototype.scrollHeight
  })

  it('does not request a further page when scrolling up once has_more is false', async () => {
    const historySpy = vi.spyOn(chatClient, 'getChatHistory').mockResolvedValue({
      messages: [
        {
          id: 'm1',
          role: 'user',
          question: 'Only question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:01',
        },
      ],
      next_cursor: null,
      has_more: false,
    })
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)
    await screen.findByText('Only question?')

    const log = screen.getByRole('log', { name: /conversation/i })
    fireEvent.scroll(log, { target: { scrollTop: 0 } })

    // Only the initial mount call -- has_more: false means there is
    // nothing further to fetch.
    expect(historySpy).toHaveBeenCalledTimes(1)
  })

  it('does not re-trigger the aria-live region for history revealed on the initial load', async () => {
    renderChatPage({
      historyPage: {
        messages: [
          {
            id: 'm1',
            role: 'user',
            question: 'Old question?',
            segments: null,
            empty_reason: null,
            created_at: '2026-01-01T00:00:01',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })

    await screen.findByText('Old question?')

    const log = screen.getByRole('log', { name: /conversation/i })
    expect(log).toHaveAttribute('aria-live', 'off')
  })

  it('does not re-trigger the aria-live region for history revealed by scrolling up', async () => {
    const historySpy = vi.spyOn(chatClient, 'getChatHistory')
    historySpy.mockResolvedValueOnce({
      messages: [
        {
          id: 'm2',
          role: 'user',
          question: 'Recent question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:02',
        },
      ],
      next_cursor: 'cursor-1',
      has_more: true,
    })
    historySpy.mockResolvedValueOnce({
      messages: [
        {
          id: 'm1',
          role: 'user',
          question: 'Older question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:01',
        },
      ],
      next_cursor: null,
      has_more: false,
    })
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)
    await screen.findByText('Recent question?')

    const log = screen.getByRole('log', { name: /conversation/i })
    // Already "off" from the initial-load reveal (its own dedicated test
    // above covers that in isolation) -- the assertion this test actually
    // exists for is that it *stays* off after the scroll-triggered reveal
    // too, not merely after the first one.
    expect(log).toHaveAttribute('aria-live', 'off')

    fireEvent.scroll(log, { target: { scrollTop: 0 } })
    await screen.findByText('Older question?')

    expect(log).toHaveAttribute('aria-live', 'off')
  })

  it('re-enables aria-live once a new question is actually asked after a history reveal', async () => {
    renderChatPage({
      historyPage: {
        messages: [
          {
            id: 'm1',
            role: 'user',
            question: 'Old question?',
            segments: null,
            empty_reason: null,
            created_at: '2026-01-01T00:00:01',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })
    await screen.findByText('Old question?')
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue({ segments: [], empty_reason: null })
    const user = userEvent.setup()

    await user.type(screen.getByLabelText(/ask a question/i), 'A brand new question{Enter}')

    const log = screen.getByRole('log', { name: /conversation/i })
    expect(log).toHaveAttribute('aria-live', 'polite')
  })

  it('renders a persisted "no_documents"/"empty_scope" history row as its own reason-specific notice, not a blank bubble', async () => {
    // `toUiMessage`'s notice-branch mapping (empty_reason set, but not
    // "refusal") is only ever exercised on the live-ask path elsewhere in
    // this file -- this pins it for a *history-loaded* row too, for both
    // reasons distinct copy exists for.
    renderChatPage({
      historyPage: {
        messages: [
          {
            id: 'm2',
            role: 'assistant',
            question: null,
            segments: [],
            empty_reason: 'empty_scope',
            created_at: '2026-01-01T00:00:02',
          },
          {
            id: 'm1',
            role: 'user',
            question: 'Anything in scope?',
            segments: null,
            empty_reason: null,
            created_at: '2026-01-01T00:00:01',
          },
        ],
        next_cursor: null,
        has_more: false,
      },
    })

    const notice = await screen.findByText('No content found in the documents you selected.')
    // A bare <p>, not a bubble -- same shape the live-ask "empty_scope"
    // notice renders as (ChatMessage.jsx's own role="notice" branch),
    // never a generic/blank assistant bubble.
    expect(notice.tagName).toBe('P')
    expect(notice).not.toHaveClass('bg-surface')
  })

  // --- Review fixes: the three ways history could become unreachable. ---
  // The "Load earlier messages" button that used to cover the
  // no-overflow/no-keyboard-path gap here was removed at the user's
  // request -- pagination is scroll-only again, already covered by "loads
  // a further page at limit=10 when the message list is scrolled to the
  // top" above.

  it('keeps history reachable when the initial fetch resolves after a live question', async () => {
    // Regression: the initial fetch used to bail out entirely once a live
    // question had been submitted, which also skipped recording
    // `next_cursor`/`has_more` -- leaving pagination dead for the rest of
    // the session for exactly the users who had history to page through.
    let resolveHistory
    const historySpy = vi.spyOn(chatClient, 'getChatHistory').mockImplementation(
      () => new Promise((resolve) => { resolveHistory = resolve }),
    )
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the refund window?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText("TechCorp's refund window is 30 days.")).toBeInTheDocument()

    resolveHistory({
      messages: [
        {
          id: 'm1',
          role: 'user',
          question: 'An earlier question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:01',
        },
      ],
      next_cursor: 'cursor-1',
      has_more: true,
    })

    // The stale page is prepended above the live turn rather than
    // replacing it -- neither is lost.
    expect(await screen.findByText('An earlier question?')).toBeInTheDocument()
    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
    expect(screen.getByText("TechCorp's refund window is 30 days.")).toBeInTheDocument()

    // And the pagination anchor survived, so older pages stay reachable via
    // scroll -- the second call proves `historyCursor`/`hasMoreHistory`
    // weren't dropped by the live-question bail-out this test guards.
    historySpy.mockResolvedValueOnce({ messages: [], next_cursor: null, has_more: false })
    fireEvent.scroll(screen.getByRole('log', { name: /conversation/i }), { target: { scrollTop: 0 } })
    await waitFor(() => expect(historySpy).toHaveBeenCalledTimes(2))
    const [, , secondCallOptions] = historySpy.mock.calls[1]
    expect(secondCallOptions).toEqual({ cursor: 'cursor-1', limit: 10 })
  })

  it('renders the loading indicator outside the scrollable log', async () => {
    // The prepend scroll-restore measures the scroller's `scrollHeight`
    // before the update and reapplies it after. Anything that mounts or
    // unmounts *inside* the scroller between those two moments -- as the
    // indicator used to -- makes the restored position short by its own
    // height, the exact visible jump that effect exists to prevent.
    const historySpy = vi.spyOn(chatClient, 'getChatHistory')
    historySpy.mockResolvedValueOnce({
      messages: [
        {
          id: 'm2',
          role: 'user',
          question: 'Recent question?',
          segments: null,
          empty_reason: null,
          created_at: '2026-01-01T00:00:02',
        },
      ],
      next_cursor: 'cursor-1',
      has_more: true,
    })
    let resolveSecond
    historySpy.mockImplementationOnce(
      () => new Promise((resolve) => { resolveSecond = resolve }),
    )
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderAtChatRoute(<ChatPage />)

    await screen.findByText('Recent question?')
    const log = screen.getByRole('log', { name: /conversation/i })
    fireEvent.scroll(log, { target: { scrollTop: 0 } })

    const indicator = await screen.findByText('Loading earlier messages…')
    expect(log).toHaveAttribute('aria-busy', 'true')
    expect(log.contains(indicator)).toBe(false)

    resolveSecond({ messages: [], next_cursor: null, has_more: false })
    await waitFor(() => expect(log).toHaveAttribute('aria-busy', 'false'))
  })
})
