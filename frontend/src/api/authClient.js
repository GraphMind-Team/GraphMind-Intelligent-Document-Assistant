const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Throws an Error whose message is the backend's `{"detail": ...}` string
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
    const detail = data?.detail
    throw new Error(typeof detail === 'string' ? detail : `Registration failed (${response.status}).`)
  }

  return data
}
