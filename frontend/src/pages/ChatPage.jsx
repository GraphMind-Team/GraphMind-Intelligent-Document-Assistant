import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
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
export default function ChatPage() {
  const { authFetch } = useAuth()
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [isAsking, setIsAsking] = useState(false)
  // { kind: 'service' | 'other', message } -- a 503 (or client-side
  // timeout/abort) renders as a banner here, structurally separate from
  // `messages`, so it can never render as an answer or a refusal (AC12).
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || isAsking) return

    setMessages((previous) => [...previous, { role: 'user', text: trimmed }])
    setQuestion('')
    setIsAsking(true)
    setError(null)

    try {
      const result = await askQuestion(authFetch, trimmed)
      if (result.empty_reason) {
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
              below is removed once its request settles. */}
          <div
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
                  disabled={isAsking}
                  placeholder="Ask a question about your documents…"
                  className="min-w-0 flex-1 rounded-full border border-border px-3.5 py-2.5 text-[13.5px] disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={isAsking}
                  className="shrink-0 rounded-full border border-transparent bg-primary px-4.5 py-2.5 text-[13px] font-semibold text-on-primary disabled:opacity-60"
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
