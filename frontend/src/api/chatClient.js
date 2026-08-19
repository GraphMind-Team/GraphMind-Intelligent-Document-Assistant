import { formatDetail } from './authClient'

// Comfortably above the backend's own ~120s worst case (45s per attempt +
// up to 30s of a 429's own Retry-After + 45s retry, see
// shared/llm_client's _CHAT_TIMEOUT_SECONDS/_CHAT_MAX_ATTEMPTS) -- without
// this, the request could hang indefinitely, or get cut off early by a
// dev-proxy/reverse-proxy's own shorter default timeout, producing a
// confusing raw network error before the backend ever gets to respond.
const ASK_TIMEOUT_MS = 130_000

// `authFetch` (from AuthContext) is passed in rather than imported --
// mirrors documentsClient.js's convention.
//
// `documentIds` (Story 3.3/FR-11): defaults to `[]`, meaning "search all of
// the user's documents" -- the same default the backend's `AskRequest`
// applies, so an omitted third argument here and an explicit empty array
// are indistinguishable to the server on purpose.
export async function askQuestion(authFetch, question, documentIds = []) {
  let response
  try {
    response = await authFetch('/chat/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, document_ids: documentIds }),
      signal: AbortSignal.timeout(ASK_TIMEOUT_MS),
    })
  } catch (err) {
    // Only relabel the two failure shapes this fetch call can actually
    // produce on its own: AbortSignal.timeout expiring (DOMException
    // "TimeoutError"), and the browser's own network-failure signature
    // (fetch rejects with a plain TypeError for DNS/connection/offline
    // failures -- never for an HTTP error status, which is handled below
    // via response.ok instead). Anything else -- e.g. a future authFetch
    // change that throws for an expired-session/token-refresh failure --
    // must not be swallowed and relabeled as "network failed"; rethrow it
    // as-is so its real message reaches the user instead of a misleading
    // network-error banner.
    if (err.name === 'TimeoutError' || err.name === 'AbortError') {
      throw new Error('The request timed out. Please try again.')
    }
    if (err instanceof TypeError) {
      throw new Error('The network failed. Please check your connection and try again.')
    }
    throw err
  }

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    const error = new Error(message || `Failed to get an answer (${response.status}).`)
    // AC12: distinguishes the LLM-wrapper's 503 from every other failure --
    // ChatPage renders this as a distinct service-unavailable banner, never
    // as an assistant message and never as a refusal.
    error.isServiceError = response.status === 503
    throw error
  }

  if (!data || !Array.isArray(data.segments)) {
    throw new Error('Failed to get an answer: unexpected response.')
  }

  return data
}

// Story 3.4/AD-10: `GET /chat/history`, cursor-paginated -- `cursor` is
// `undefined`/omitted on the initial load (the backend's own "start from
// the newest message" default), or a prior response's own `next_cursor`
// to fetch the next-older page. `limit` mirrors UX-DR29's two call sites
// in ChatPage.jsx: 3 on initial load, 10 per scroll-up page.
//
// `(authFetch, ...) => Promise` shape, same convention as `askQuestion`
// above.
export async function getChatHistory(authFetch, { cursor, limit } = {}) {
  const params = new URLSearchParams()
  if (cursor) params.set('cursor', cursor)
  if (limit != null) params.set('limit', String(limit))
  const query = params.toString()

  const response = await authFetch(`/chat/history${query ? `?${query}` : ''}`)
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load conversation history (${response.status}).`)
  }

  if (!data || !Array.isArray(data.messages) || typeof data.has_more !== 'boolean') {
    throw new Error('Failed to load conversation history: unexpected response.')
  }

  return data
}
