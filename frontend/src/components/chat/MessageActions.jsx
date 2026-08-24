import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { setMessageFeedback } from '../../api/chatClient'

// How long the copy button shows its "copied" checkmark before reverting
// to the plain copy icon -- long enough to register as confirmation,
// short enough that a second copy soon after isn't stuck mid-confirmation.
const COPY_CONFIRM_MS = 1500

// Answer action row: thumbs up/down + copy, sitting next to
// CitationSummary below an assistant message's text. Gives the answer a
// feedback loop (the system visibly "learns" from a rating) and a quick
// way to lift the answer out for pasting elsewhere.
//
// Feedback is optimistic: a click flips the pressed thumb immediately,
// then confirms against the backend; a failed save rolls the thumb back
// and surfaces a small inline error rather than leaving the UI silently
// out of sync with what was actually persisted. Clicking an
// already-active thumb clears it (`rating: null`) instead of only ever
// toggling to the opposite one, so retracting a rating doesn't require
// clicking through the other thumb first.
export default function MessageActions({ authFetch, messageId, initialFeedback, answerText }) {
  const { t } = useTranslation()
  const [feedback, setFeedback] = useState(initialFeedback ?? null)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState(null)
  const [isCopied, setIsCopied] = useState(false)
  const copyTimerRef = useRef(null)

  useEffect(() => () => clearTimeout(copyTimerRef.current), [])

  async function handleRate(rating) {
    // No id (shouldn't happen -- every persisted turn gets one, see
    // chat/service.py::_finish) means there's nothing to attach feedback
    // to server-side; silently no-op rather than fire a request that can
    // only 404.
    if (isSaving || messageId == null) return
    const nextRating = feedback === rating ? null : rating
    const previousFeedback = feedback
    setFeedback(nextRating)
    setError(null)
    setIsSaving(true)
    try {
      await setMessageFeedback(authFetch, messageId, nextRating)
    } catch (err) {
      setFeedback(previousFeedback)
      setError(err.message)
    } finally {
      setIsSaving(false)
    }
  }

  async function handleCopy() {
    // The Clipboard API rejects (e.g. `NotAllowedError`) when the document
    // lacks focus/permission -- browsers don't surface that as a thrown
    // error the user sees, so swallow it here too rather than leaving an
    // unhandled rejection; the button just stays unconfirmed, same as if
    // the click never happened.
    try {
      await navigator.clipboard.writeText(answerText)
    } catch {
      return
    }
    setIsCopied(true)
    clearTimeout(copyTimerRef.current)
    copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_CONFIRM_MS)
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      <button
        type="button"
        aria-label={isCopied ? t('chat.actions.copied') : t('chat.actions.copy')}
        onClick={handleCopy}
        className="rounded-lg p-1.5 text-text2 hover:bg-accent/10 hover:text-accent"
      >
        {isCopied ? (
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-3.5 w-3.5"
          >
            <path d="M20 6 9 17l-5-5" />
          </svg>
        ) : (
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-3.5 w-3.5"
          >
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
        )}
      </button>

      <button
        type="button"
        aria-pressed={feedback === 'up'}
        aria-label={feedback === 'up' ? t('chat.actions.thumbsUpActive') : t('chat.actions.thumbsUp')}
        onClick={() => handleRate('up')}
        disabled={isSaving}
        className={`rounded-lg p-1.5 hover:bg-accent/10 ${feedback === 'up' ? 'text-accent' : 'text-text2 hover:text-accent'}`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill={feedback === 'up' ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-3.5 w-3.5"
        >
          <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
        </svg>
      </button>

      <button
        type="button"
        aria-pressed={feedback === 'down'}
        aria-label={feedback === 'down' ? t('chat.actions.thumbsDownActive') : t('chat.actions.thumbsDown')}
        onClick={() => handleRate('down')}
        disabled={isSaving}
        className={`rounded-lg p-1.5 hover:bg-accent/10 ${feedback === 'down' ? 'text-accent' : 'text-text2 hover:text-accent'}`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill={feedback === 'down' ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-3.5 w-3.5"
        >
          <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
        </svg>
      </button>

      {error && (
        <p role="alert" className="w-full text-[11px] text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
