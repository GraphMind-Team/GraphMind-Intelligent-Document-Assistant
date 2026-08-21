import { formatDetail } from './authClient'

// Client for the folders module (folder-grouping feature). Mirrors
// `documentsClient.js`'s `authFetch`-first-param pattern and
// `formatDetail(data?.detail)` error shape throughout -- see that file's
// own header comment for why `authFetch` is passed in rather than
// imported here.

export async function listFolders(authFetch) {
  const response = await authFetch('/folders')
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load folders (${response.status}).`)
  }

  if (!Array.isArray(data)) {
    throw new Error('Failed to load folders: unexpected response.')
  }

  return data
}

export async function createFolder(authFetch, { name, color }) {
  const response = await authFetch('/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to create folder (${response.status}).`)
  }

  return data
}

export async function updateFolder(authFetch, folderId, { name, color } = {}) {
  const body = {}
  if (name !== undefined) body.name = name
  if (color !== undefined) body.color = color

  const response = await authFetch(`/folders/${encodeURIComponent(folderId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to update folder (${response.status}).`)
  }

  return data
}

// 204 with no body on success, same shape as documentsClient.js's
// deleteDocument -- a cross-tenant or nonexistent folder id comes back as
// the backend's own 404 "Folder not found.".
export async function deleteFolder(authFetch, folderId) {
  const response = await authFetch(`/folders/${encodeURIComponent(folderId)}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to delete folder (${response.status}).`)
  }
}
