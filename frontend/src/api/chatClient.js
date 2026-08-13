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
export async function askQuestion(authFetch, question) {
  let response
  try {
    response = await authFetch('/chat/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(ASK_TIMEOUT_MS),
    })
  } catch {
    // A client-side abort/timeout or network failure is NOT the backend's
    // AD-6 503 -- it never reached (or never heard back from) the service
    // at all, so it must fall into the generic 'other' error path, never
    // the service banner (that's reserved for a real 503 response body).
    throw new Error('The request timed out or the network failed. Please try again.')
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
