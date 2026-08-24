import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useChatSessions } from '../../context/ChatSessionsContext'

// One row: click selects the session; a hover-revealed pencil swaps the
// label for an inline rename input (no modal -- a session only has one
// field, unlike FolderModal's name+color, so a full dialog would be
// heavier than this 260px-wide sidebar needs); a hover-revealed trash
// opens an inline danger-confirm box structurally copied from
// FolderGrid.jsx's FolderTile `isConfirming` branch -- this project's one
// established delete-confirm pattern (role="alert", danger-tinted,
// Cancel/Delete buttons, focus-to-Cancel on open, Escape to collapse),
// reused rather than reinvented.
function ChatSessionRow({ session, isActive, onSelect, onRename, onDelete }) {
  const { t } = useTranslation()
  const [isRenaming, setIsRenaming] = useState(false)
  const [titleDraft, setTitleDraft] = useState(session.title ?? '')
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)
  const cancelButtonRef = useRef(null)
  const deleteButtonRef = useRef(null)
  // Enter commits, then blurs the input -- without this guard, the
  // resulting blur would fire a second, overlapping commitRename call.
  const isSavingRef = useRef(false)

  const displayTitle = session.title ?? t('chat.sessionsPanel.untitled')

  useEffect(() => {
    if (isRenaming) inputRef.current?.focus()
  }, [isRenaming])

  useEffect(() => {
    if (isConfirmingDelete) cancelButtonRef.current?.focus()
  }, [isConfirmingDelete])

  function openRename(event) {
    event.stopPropagation()
    setTitleDraft(session.title ?? '')
    setError(null)
    setIsRenaming(true)
  }

  async function commitRename() {
    if (isSavingRef.current) return
    const trimmed = titleDraft.trim()
    if (!trimmed || trimmed === session.title) {
      setIsRenaming(false)
      return
    }
    isSavingRef.current = true
    try {
      await onRename(session.id, trimmed)
      setIsRenaming(false)
    } catch (err) {
      setError(err.message)
    } finally {
      isSavingRef.current = false
    }
  }

  function handleRenameKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      commitRename()
    } else if (event.key === 'Escape') {
      event.stopPropagation()
      setIsRenaming(false)
      setError(null)
    }
  }

  function openConfirmDelete(event) {
    event.stopPropagation()
    setError(null)
    setIsConfirmingDelete(true)
  }

  function collapseConfirm() {
    if (isDeleting) return
    setIsConfirmingDelete(false)
    setError(null)
    deleteButtonRef.current?.focus()
  }

  function handleConfirmBoxKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    collapseConfirm()
  }

  async function handleConfirmDelete(event) {
    event.stopPropagation()
    setIsDeleting(true)
    setError(null)
    try {
      await onDelete(session.id)
    } catch (err) {
      setError(err.message)
      setIsDeleting(false)
    }
  }

  if (isConfirmingDelete) {
    return (
      <li
        role="alert"
        onKeyDown={handleConfirmBoxKeyDown}
        className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger/5 p-2.5"
      >
        <p className="text-xs text-text">{t('chat.sessionsPanel.deleteConfirm', { title: displayTitle })}</p>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={collapseConfirm}
            disabled={isDeleting}
            className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-primary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirmDelete}
            disabled={isDeleting}
            className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-danger"
          >
            {isDeleting ? t('chat.sessionsPanel.deleting') : t('common.delete')}
          </button>
        </div>
      </li>
    )
  }

  return (
    <li
      className={[
        'flex items-center gap-1.5 rounded-xl border px-3 py-2.5 text-[12.5px]',
        isActive ? 'border-accent/40 bg-accent/10 font-semibold text-accent' : 'border-border bg-surface2 text-text',
      ].join(' ')}
    >
      {isRenaming ? (
        <>
          <label htmlFor={`chat-session-rename-${session.id}`} className="sr-only">
            {t('chat.sessionsPanel.renameLabel')}
          </label>
          <input
            id={`chat-session-rename-${session.id}`}
            ref={inputRef}
            type="text"
            value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
            onKeyDown={handleRenameKeyDown}
            onBlur={commitRename}
            onClick={(event) => event.stopPropagation()}
            placeholder={t('chat.sessionsPanel.renamePlaceholder')}
            maxLength={255}
            className="min-w-0 flex-1 rounded-full border border-border bg-card-bg px-2.5 py-1 text-[12.5px] text-text"
          />
        </>
      ) : (
        <button type="button" onClick={() => onSelect(session.id)} className="min-w-0 flex-1 truncate text-left">
          {displayTitle}
        </button>
      )}
      {!isRenaming && (
        // Always visible, not hover-revealed -- mirrors FolderGrid.jsx's
        // FolderTile edit/delete icons (that project convention), and
        // unlike a hover-only reveal, works on touch devices, which have
        // no hover state at all.
        <div className="flex shrink-0 gap-0.5">
          <button
            type="button"
            aria-label={t('chat.sessionsPanel.editAria', { title: displayTitle })}
            onClick={openRename}
            className="rounded-lg p-1 text-current hover:bg-black/10"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
            </svg>
          </button>
          <button
            ref={deleteButtonRef}
            type="button"
            aria-label={t('chat.sessionsPanel.deleteAria', { title: displayTitle })}
            aria-expanded={isConfirmingDelete}
            onClick={openConfirmDelete}
            className="rounded-lg p-1 text-current hover:bg-black/10"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3 w-3">
              <path d="M3 6h18" />
              <path d="M8 6V4h8v2" />
              <path d="M6 6l1 14h10l1-14" />
            </svg>
          </button>
        </div>
      )}
      {error && <p role="alert" className="w-full text-[11px] text-danger">{error}</p>}
    </li>
  )
}

// Left "chats" panel (multi-session chat): create, list, switch, rename,
// delete -- styled with the same tokens as DocumentsScopePanel's shell
// for a consistent look. Owns no fetch of its own; all list state and
// CRUD actions come from ChatSessionsContext, shared with ChatPage (which
// needs the active session id to key its own message-fetch effect) and
// ChatIndexRedirect (which needs the list to pick a landing session).
export default function ChatSessionsPanel() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { sessionId: activeSessionId } = useParams()
  const { sessions, isLoading, error, createSession, renameSession, deleteSession } = useChatSessions()
  const [createError, setCreateError] = useState(null)

  async function handleCreate() {
    setCreateError(null)
    try {
      await createSession()
    } catch (err) {
      setCreateError(err.message)
    }
  }

  return (
    <aside className="flex w-full shrink-0 flex-col self-start rounded-2xl border border-border bg-card-bg p-5 shadow-card min-[901px]:w-[260px]">
      <h2 className="mb-2.5 text-[13px] font-bold text-primary">{t('chat.sessionsPanel.title')}</h2>

      <button
        type="button"
        onClick={handleCreate}
        className="mb-3 flex w-full items-center justify-center gap-1.5 rounded-full border border-border bg-surface2 px-3.5 py-2 text-[12.5px] font-semibold text-text hover:border-accent hover:text-accent"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
          <path d="M12 5v14M5 12h14" />
        </svg>
        {t('chat.sessionsPanel.newChat')}
      </button>

      {createError && (
        <p role="alert" className="mb-2 text-xs text-danger">
          {createError}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {isLoading && <p className="text-xs text-text2">{t('chat.sessionsPanel.loading')}</p>}
      {!isLoading && !error && sessions.length === 0 && (
        <p className="text-xs text-text2">{t('chat.sessionsPanel.empty')}</p>
      )}

      <ul className="list-none space-y-1.5 p-0">
        {sessions.map((session) => (
          <ChatSessionRow
            key={session.id}
            session={session}
            isActive={session.id === activeSessionId}
            onSelect={(id) => navigate(`/chat/${id}`)}
            onRename={renameSession}
            onDelete={deleteSession}
          />
        ))}
      </ul>
    </aside>
  )
}
