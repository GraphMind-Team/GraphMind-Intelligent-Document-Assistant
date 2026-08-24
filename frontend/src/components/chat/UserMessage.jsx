import { forwardRef, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import highlightMatches from './highlightMatches'

// Mirrors MessageActions.jsx's own COPY_CONFIRM_MS.
const COPY_CONFIRM_MS = 1500

// A user's own message: the existing right-aligned bubble (Story 3.1,
// UX-DR5), plus -- ChatMessage.jsx's "actions live below the bubble, not
// inside it" convention, established for the assistant side -- a copy/edit
// action row underneath. Editing swaps the bubble for an editable
// textarea in place; committing hands the edited text up to `onEditMessage`,
// which is what actually discards this question and everything after it
// and re-asks (ChatPage.jsx::handleEditMessage) -- this component only
// owns the editing UI itself, never that truncate/re-ask decision.
//
// The edit button is withheld entirely while `id == null` (a live turn
// whose response hasn't come back yet -- see ChatPage.jsx::submitQuestion's
// own comment on why the id arrives late), mirroring MessageActions'
// identical guard for feedback: there is nothing server-side to edit until
// this question has actually been persisted. Copy has no such gate --
// the text sitting in the bubble is always copyable, id or not.
const UserMessage = forwardRef(function UserMessage(
  { id, text, highlight = '', isActiveMatch = false, onEditMessage },
  ref,
) {
  const { t } = useTranslation()
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(text)
  const [isCopied, setIsCopied] = useState(false)
  const textareaRef = useRef(null)
  const copyTimerRef = useRef(null)
  const activeMatchClass = isActiveMatch ? ' outline outline-2 outline-accent outline-offset-2' : ''

  useEffect(() => () => clearTimeout(copyTimerRef.current), [])

  // Focus moves into the textarea on entering edit mode, caret at the end
  // -- the same "focus moves into the transient surface" convention
  // ChatSessionsPanel.jsx's rename input already follows.
  useEffect(() => {
    if (!isEditing) return
    const el = textareaRef.current
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, [isEditing])

  async function handleCopy() {
    // Same swallow-and-stay-unconfirmed treatment as MessageActions
    // .handleCopy's own comment -- a denied Clipboard API write must not
    // become an unhandled rejection.
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      return
    }
    setIsCopied(true)
    clearTimeout(copyTimerRef.current)
    copyTimerRef.current = setTimeout(() => setIsCopied(false), COPY_CONFIRM_MS)
  }

  function openEdit() {
    setDraft(text)
    setIsEditing(true)
  }

  function cancelEdit() {
    setIsEditing(false)
  }

  function commitEdit() {
    const trimmed = draft.trim()
    if (!trimmed) return
    setIsEditing(false)
    onEditMessage(id, trimmed)
  }

  // Enter commits (mirrors the main composer's own Enter-to-send), Shift
  // +Enter inserts a newline for a genuinely multi-line edit, Escape
  // cancels without saving -- same as ChatSessionsPanel.jsx's rename
  // input. Deliberately no commit-on-blur: unlike a rename, committing an
  // edit discards every later turn in the conversation, so an accidental
  // click-away must never trigger it -- only an explicit Enter/Save does.
  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      commitEdit()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      cancelEdit()
    }
  }

  if (isEditing) {
    return (
      <div ref={ref} className="anim-rise ml-auto flex max-w-[70%] flex-col items-end gap-1.5 self-end">
        <label htmlFor="edit-user-message" className="sr-only">
          {t('chat.userMessage.editLabel')}
        </label>
        <textarea
          id="edit-user-message"
          ref={textareaRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={Math.min(6, Math.max(2, draft.split('\n').length))}
          className="w-full resize-none rounded-[20px_20px_6px_20px] border border-accent bg-surface px-4 py-2.5 text-[14px] leading-[1.6] text-text shadow-[var(--glow)] focus:outline-none"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={cancelEdit}
            className="rounded-full border border-border bg-card-bg px-3.5 py-1.5 text-[12.5px] font-semibold text-primary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={commitEdit}
            disabled={!draft.trim()}
            className="btn-brand rounded-full px-3.5 py-1.5 text-[12.5px] font-semibold"
          >
            {t('chat.userMessage.save')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div ref={ref} className="anim-rise ml-auto flex max-w-[70%] flex-col items-end gap-1.5 self-end">
      <div
        className={`rounded-[20px_20px_6px_20px] bg-[image:var(--grad-brand)] px-4 py-2.5 text-[14px] text-white shadow-[var(--glow)]${activeMatchClass}`}
      >
        {/* Sighted users get the sender cue from alignment/fill/corner
            (UX-DR5) alone; a screen reader gets none of that, so without
            this prefix two turns read as one undifferentiated stream. */}
        <span className="sr-only">{t('chat.message.youPrefix')} </span>
        {highlightMatches(text, highlight)}
      </div>
      <div className="flex items-center gap-1 px-1">
        <button
          type="button"
          aria-label={isCopied ? t('chat.actions.copied') : t('chat.userMessage.copy')}
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

        {id != null && (
          <button
            type="button"
            aria-label={t('chat.userMessage.edit')}
            onClick={openEdit}
            className="rounded-lg p-1.5 text-text2 hover:bg-accent/10 hover:text-accent"
          >
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
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
})

export default UserMessage
