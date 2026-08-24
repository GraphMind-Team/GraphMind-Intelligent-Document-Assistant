import { formatDetail } from './authClient'

// Client for the chat_sessions module (multi-session chat). Mirrors
// `foldersClient.js`'s `authFetch`-first-param pattern and
// `formatDetail(data?.detail)` error shape throughout -- see that file's
// own header comment for why `authFetch` is passed in rather than
// imported here.

export async function listChatSessions(authFetch) {
  const response = await authFetch('/chat/sessions')
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load chats (${response.status}).`)
  }

  if (!Array.isArray(data)) {
    throw new Error('Failed to load chats: unexpected response.')
  }

  return data
}

// No body -- a session always starts titleless (auto-titled from its
// first question, backend-side).
export async function createChatSession(authFetch) {
  const response = await authFetch('/chat/sessions', { method: 'POST' })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to create a new chat (${response.status}).`)
  }

  return data
}

export async function renameChatSession(authFetch, sessionId, title) {
  const response = await authFetch(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to rename chat (${response.status}).`)
  }

  return data
}

// 204 with no body on success, same shape as foldersClient.js's
// deleteFolder -- a cross-tenant or nonexistent session id comes back as
// the backend's own 404 "Chat session not found.".
export async function deleteChatSession(authFetch, sessionId) {
  const response = await authFetch(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to delete chat (${response.status}).`)
  }
}
