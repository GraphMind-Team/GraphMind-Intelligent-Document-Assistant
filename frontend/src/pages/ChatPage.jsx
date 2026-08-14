import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { ChatScopeProvider, useChatScope } from '../context/ChatScopeContext'
import { askQuestion } from '../api/chatClient'
import ChatMessage from '../components/chat/ChatMessage'
import RobotMascot from '../components/chat/RobotMascot'
import DocumentsScopePanel from '../components/chat/DocumentsScopePanel'

// Chat page (Story 3.1): a two-column grid -- flexible chat window (1fr) +
// fixed 260px documents-in-scope panel, 20px gutter (UX-DR9). Collapses to
// a single column below 900px so the fixed-width columns (this page's
// panel plus Shell's 220px sidebar) can't force horizontal scroll/clipping
// at 200% browser zoom on a typical laptop viewport (AC2, WCAG 1.4.4,
// UX-DR28) -- the scope panel already sits second in DOM order, so no CSS
// `order`/`row-reverse` is needed to make it flow below the chat column
// (mirrors Shell.jsx's own UX-DR18 convention).
//
// Split into this thin wrapper + ChatPageContent (Story 3.3) because
// ChatPageContent needs `useChatScope()`, which reads the context this
// component renders -- a single component can't call a hook that reads a
// provider it renders itself, that provider isn't mounted yet at the
// point its own render function runs.
export default function ChatPage() {
  return (
    <ChatScopeProvider>
      <ChatPageContent />
    </ChatScopeProvider>
  )
}

function ChatPageContent() {
  const { authFetch } = useAuth()
  const { selectedDocumentIds } = useChatScope()
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  // { kind: 'service' | 'other', message } -- a 503 (or client-side
  // timeout/abort) renders as a banner here, structurally separate from
  // `messages`, so it can never render as an answer or a refusal (AC12).
  const [error, setError] = useState(null)
  const messageListRef = useRef(null)

  // Keeps the newest message (or the transient "Thinking…" bubble) in
  // view without requiring the user to scroll manually -- a real question
  // during review: a 20-40s wait is already disorienting, and without
  // this the answer (or even "Thinking…" itself) can land below the fold
  // and look like nothing happened.
  useEffect(() => {
    const el = messageListRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, isAsking])

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || isAsking) return

    setMessages((previous) => [...previous, { role: 'user', text: trimmed }])
    setQuestion('')
    setIsAsking(true)
    setError(null)

    try {
      const result = await askQuestion(authFetch, trimmed, selectedDocumentIds)
      if (result.empty_reason === 'refusal') {
        // FR-10/UX-DR15: a designed refusal, not an empty-state notice --
        // its own message role so ChatMessage renders a real bubble,
        // never the plain notice paragraph the other two reasons use.
        setMessages((previous) => [...previous, { role: 'refusal' }])
      } else if (result.empty_reason) {
        setMessages((previous) => [...previous, { role: 'notice', reason: result.empty_reason }])
      } else {
        setMessages((previous) => [...previous, { role: 'assistant', segments: result.segments }])
      }
    } catch (err) {
      setError({ kind: err.isServiceError ? 'service' : 'other', message: err.message })
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <>
      <h1 className="text-xl font-bold text-text">Chat</h1>

      <div className="mt-4 grid grid-cols-[1fr_260px] gap-[20px] max-[900px]:grid-cols-1">
        <div
          className="flex min-w-0 flex-col rounded-xl border border-border bg-card-bg"
          style={{ minHeight: '480px', maxHeight: '70vh' }}
        >
          {/* aria-atomic="false": only the newly-appended message is
              announced, not a full re-read of the thread every turn
              (UX-DR24). Notice messages persist in the thread after a
              later question is asked -- an honest record of the
              conversation, same as a user message or a real answer never
              being removed either; only the transient "Thinking…" bubble
              below is removed once its request settles.
              role="log" + tabIndex={0}: Chrome 127+ makes an overflow
              scroller keyboard-focusable on its own, but Firefox/Safari
              don't -- without this, a keyboard-only user on a long thread
              can't scroll back up at all. role="log" also documents the
              live-region semantics already implied by aria-live above. */}
          <div
            ref={messageListRef}
            role="log"
            tabIndex={0}
            aria-label="Conversation"
            aria-live="polite"
            aria-atomic="false"
            className="flex flex-1 flex-col gap-3 overflow-y-auto p-5"
          >
            {messages.map((message, index) => (
              <ChatMessage key={index} message={message} />
            ))}
            {isAsking && <ChatMessage message={{ role: 'thinking' }} />}
          </div>

          {error && (
            <p role="alert" className="mx-5 mb-2 text-xs text-danger">
              {error.kind === 'service'
                ? 'Something went wrong generating an answer. Please try again.'
                : error.message}
            </p>
          )}

          <form onSubmit={handleSubmit} className="border-t border-border p-3.5">
            <div className="relative mt-6 w-full">
              <RobotMascot />
              <div className="flex w-full items-stretch gap-2">
                <label htmlFor="chat-question" className="sr-only">
                  Ask a question about your documents
                </label>
                <input
                  id="chat-question"
                  type="text"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  // Mirrors AskRequest.max_length (chat/schemas.py) -- without
                  // this a pasted over-length question sails past the browser
                  // and only fails as a raw Pydantic 422 message, not the
                  // notice-style copy UX-DR19 expects for user-facing errors.
                  maxLength={2000}
                  // readOnly, not disabled: a disabled input drops keyboard
                  // focus to <body> and there's no reliable moment to
                  // restore it once re-enabled. readOnly keeps focus in
                  // place through the wait, still blocks editing, and
                  // still lets Enter re-submit -- but that re-submit is a
                  // no-op, since handleSubmit's own `isAsking` guard above
                  // already covers double-submit protection regardless of
                  // which of the two attributes is used here.
                  readOnly={isAsking}
                  placeholder="Ask a question about your documents…"
                  className={`min-w-0 flex-1 rounded-full border border-border px-3.5 py-2.5 text-[13.5px] ${isAsking ? 'opacity-60' : ''}`}
                />
                <button
                  type="submit"
                  // aria-disabled, not disabled: same reasoning as the
                  // input's readOnly above -- a disabled button that
                  // currently holds focus (a keyboard user who activated
                  // Ask, rather than pressing Enter from the input) drops
                  // focus to <body> with no reliable moment to restore it.
                  // Still functionally blocked: handleSubmit's own
                  // `isAsking` guard makes a click/Enter/Space while
                  // asking a no-op, exactly as it already does for the
                  // input's readOnly re-submit case.
                  aria-disabled={isAsking}
                  className={`shrink-0 rounded-full border border-transparent bg-primary px-4.5 py-2.5 text-[13px] font-semibold text-on-primary ${isAsking ? 'cursor-not-allowed opacity-60' : ''}`}
                >
                  Ask
                </button>
              </div>
            </div>
          </form>
        </div>

        <DocumentsScopePanel authFetch={authFetch} />
      </div>
    </>
  )
}
