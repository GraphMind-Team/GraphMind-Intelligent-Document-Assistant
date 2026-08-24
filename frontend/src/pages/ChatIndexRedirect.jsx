import { useEffect, useRef } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useChatSessions } from '../context/ChatSessionsContext'

// `/chat` (no session id) always resolves to a real session and redirects
// -- there is no "no session selected" state in this app, mirroring how
// `/documents` (never `/documents/`) is the only bare landing route.
// `sessions` is already ordered most-recently-active-first
// (chat/sessions_repository.py::list_sessions_for_user), so the first
// entry is exactly the session a returning user would expect to land
// back on. An empty list (a brand-new account with zero chats yet)
// creates one instead of rendering an empty/dead-end page.
export default function ChatIndexRedirect() {
  const { t } = useTranslation()
  const location = useLocation()
  const { sessions, isLoading, error, createSession } = useChatSessions()
  // Guards the create-on-empty call to exactly one attempt per mount --
  // `createSession` itself triggers a navigate away once it resolves, but
  // that navigation isn't synchronous, so without this a second render
  // with the same (still-empty) `sessions` array before the redirect
  // lands would fire a second, duplicate create.
  const hasRequestedCreateRef = useRef(false)

  useEffect(() => {
    if (isLoading || error || sessions.length > 0 || hasRequestedCreateRef.current) return
    hasRequestedCreateRef.current = true
    createSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, error, sessions.length])

  if (!isLoading && sessions.length > 0) {
    // Forward whatever navigation state got us to `/chat` in the first
    // place (e.g. DocumentDetailPage/DocumentCard/DocumentReadyToasts'
    // `{ presetDocumentId }`) -- `<Navigate>` doesn't carry it along on
    // its own, and without this the redirect silently drops it, landing
    // on the session with no document scope applied.
    return <Navigate to={`/chat/${sessions[0].id}`} state={location.state} replace />
  }

  return (
    <div className="flex min-h-[400px] items-center justify-center">
      {error ? (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      ) : (
        <p role="status" className="flex items-center gap-3 text-sm font-semibold text-text2">
          <span
            aria-hidden="true"
            className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          {t('chat.sessionsPanel.loading')}
        </p>
      )}
    </div>
  )
}
