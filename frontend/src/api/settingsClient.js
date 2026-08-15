import { formatDetail } from './authClient'

// `authFetch` passed in rather than imported -- mirrors documentsClient.js's
// convention (this module has no access to the token/logout-on-401
// behavior AuthContext already provides).
export async function updateTheme(authFetch, theme) {
  const response = await authFetch('/auth/theme', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to save theme (${response.status}).`)
  }

  return data
}
