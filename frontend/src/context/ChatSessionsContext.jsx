import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from './AuthContext'
import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  renameChatSession,
} from '../api/chatSessionsClient'

// Chat sessions list state (multi-session chat): shared between
// ChatSessionsPanel (which renders the list and its create/rename/delete
// affordances) and ChatIndexRedirect (which needs the list to pick a
// session to land on). Mirrors ChatScopeContext.jsx's provider/hook shape
// -- context-owned state, never prop-drilled.
//
// Deliberately does NOT own "the active session id" as state of its own --
// that lives in the URL (`/chat/:sessionId`, decision #1 of this
// feature's plan), read here via `useParams()` so it's always exactly
// what the address bar says, never a second source of truth that could
// drift from it after a browser back/forward or a shared link.
const ChatSessionsContext = createContext(undefined)

export function ChatSessionsProvider({ children }) {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const { sessionId: activeSessionId } = useParams()
  const [sessions, setSessions] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(() => {
    setIsLoading(true)
    setError(null)
    return listChatSessions(authFetch)
      .then((data) => {
        setSessions(data)
        return data
      })
      .catch((err) => {
        setError(err.message)
        return []
      })
      .finally(() => setIsLoading(false))
  }, [authFetch])

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authFetch])

  const createSession = useCallback(async () => {
    const created = await createChatSession(authFetch)
    // Newest-active-first, same order the backend's own `updated_at desc`
    // list already returns -- a freshly created session is always the
    // most recent, so prepending here matches a refetch without one.
    setSessions((previous) => [created, ...previous])
    navigate(`/chat/${created.id}`)
    return created
  }, [authFetch, navigate])

  const renameSession = useCallback(
    async (id, title) => {
      const updated = await renameChatSession(authFetch, id, title)
      // In place, no resort: a rename alone never bumps `updated_at`
      // (chat/sessions_repository.py::touch_session only does that for a
      // live turn), so the list's existing order stays valid.
      setSessions((previous) => previous.map((session) => (session.id === id ? updated : session)))
      return updated
    },
    [authFetch],
  )

  const deleteSession = useCallback(
    async (id) => {
      await deleteChatSession(authFetch, id)
      const remaining = sessions.filter((session) => session.id !== id)
      setSessions(remaining)
      // Mirrors FolderGrid.jsx::handleFolderDeleted's "fall back" pattern:
      // deleting the session currently open must not leave the chat
      // window pointed at an id that no longer exists. Falls back to
      // whichever session is now first (most recently active); if that
      // was the last one, starts a fresh session instead of landing on
      // an empty list.
      if (id === activeSessionId) {
        if (remaining.length > 0) {
          navigate(`/chat/${remaining[0].id}`)
        } else {
          await createSession()
        }
      }
    },
    [authFetch, sessions, activeSessionId, navigate, createSession],
  )

  const value = {
    sessions,
    activeSessionId,
    isLoading,
    error,
    refresh,
    createSession,
    renameSession,
    deleteSession,
  }
  return <ChatSessionsContext.Provider value={value}>{children}</ChatSessionsContext.Provider>
}

export function useChatSessions() {
  const ctx = useContext(ChatSessionsContext)
  if (ctx === undefined) {
    throw new Error('useChatSessions must be used within a ChatSessionsProvider')
  }
  return ctx
}
