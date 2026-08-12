export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// FastAPI's `detail` is a plain string for HTTPException errors (e.g. the
// 409 duplicate-email case) but a list of {msg, loc, type} objects for
// Pydantic validation errors (422s). Handle both so the user always sees
// the real reason, not a status-code dump.
function formatDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item.msg === 'string' ? item.msg : null))
      .filter(Boolean)
    if (messages.length > 0) return messages.join(' ')
  }
  return null
}

// Throws an Error whose message is the backend's `{"detail": ...}` content
// (AD-3) so callers can render it directly -- plain and declarative,
// per UX-DR19, not a generic "something went wrong".
export async function registerAccount({ fullName, email, password }) {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ full_name: fullName, email, password }),
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Registration failed (${response.status}).`)
  }

  return data
}

export async function loginAccount({ email, password }) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Login failed (${response.status}).`)
  }

  return data
}
