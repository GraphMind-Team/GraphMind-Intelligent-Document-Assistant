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

// Story 5.1. Mirrors updateTheme's shape exactly: authFetch first, JSON
// body, formatDetail for the error message.
export async function updateProfile(authFetch, { fullName }) {
  const response = await authFetch('/auth/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ full_name: fullName }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to save profile (${response.status}).`)
  }

  return data
}

export async function changePassword(authFetch, { currentPassword, newPassword }) {
  const response = await authFetch('/auth/me/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to change password (${response.status}).`)
  }

  return data
}
