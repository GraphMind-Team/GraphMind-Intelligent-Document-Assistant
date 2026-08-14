import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ChatPage from './ChatPage'
import { useAuth } from '../context/AuthContext'
import * as chatClient from '../api/chatClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../components/chat/DocumentsScopePanel', () => ({
  default: () => <div>scope panel stub</div>,
}))

afterEach(() => {
  vi.restoreAllMocks()
})

function renderChatPage() {
  useAuth.mockReturnValue({ authFetch: vi.fn() })
  return render(<ChatPage />)
}

// Mirrors the real `AskResponse` shape, `chunk_indexes` included -- nothing
// on this page renders that field (the chip's format is fixed by UX-DR3),
// but a fixture that silently drifts from the API it stands in for stops
// being evidence of anything.
const ANSWER_RESULT = {
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
    expect(await screen.findByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()
  })

  it('submits via pressing Enter', async () => {
    vi.spyOn(chatClient, 'askQuestion').mockResolvedValue(ANSWER_RESULT)
    const user = userEvent.setup()
    renderChatPage()

    await user.type(screen.getByLabelText(/ask a question/i), 'What is the refund window?{Enter}')

    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
    expect(await screen.findByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()
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

    const chip = await screen.findByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')
    expect(chip.tagName).toBe('CITE')
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
