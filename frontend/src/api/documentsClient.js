import { API_BASE_URL, formatDetail } from './authClient'

// Client-side allowlist, mirrored from `backend/app/documents/service.py`'s
// `_EXTENSION_TO_FILE_TYPE`/`MAX_FILE_SIZE_BYTES` -- kept in sync by hand
// (no shared codegen between the two languages here) so an obviously-bad
// file is rejected before any request is sent, per the story's Boundaries
// ("Validate before any DB write, not after" -- the client-side half of
// that is never sending the request at all).
export const ALLOWED_EXTENSIONS = ['.pdf', '.md', '.markdown', '.html', '.htm']
export const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

function getExtension(filename) {
  const index = filename.lastIndexOf('.')
  return index === -1 ? '' : filename.slice(index).toLowerCase()
}

// Returns a plain-language rejection reason (UX-DR19), or null when the
// file is acceptable to upload.
export function validateFile(file) {
  const extension = getExtension(file.name)
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Unsupported file format. Supported formats: ${ALLOWED_EXTENSIONS.join(', ')}.`
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return 'File exceeds the 20MB size limit.'
  }
  return null
}

// XHR, not fetch: fetch has no upload-progress event, and real per-file
// progress (not synthetic) is a hard requirement of this story. One XHR
// per call -- UploadModal.jsx fires one per queued file, concurrently, so
// a slow file's XHR never blocks another file's XHR.
//
// Resolves with the parsed `DocumentResponse` body on 2xx, rejects with an
// `Error` whose message is the backend's `detail` (mirrors authClient.js's
// pattern) on any non-2xx status or transport failure.
export function uploadDocument(token, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/documents`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.addEventListener('progress', (event) => {
      if (!onProgress) return
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    })

    xhr.addEventListener('load', () => {
      let data = null
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        data = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data)
      } else {
        const message = formatDetail(data?.detail)
        reject(new Error(message || `Upload failed (${xhr.status}).`))
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('Upload failed. Check your connection and try again.'))
    })

    const formData = new FormData()
    formData.append('file', file)
    xhr.send(formData)
  })
}

// `authFetch` (from AuthContext) is passed in rather than imported --
// this module has no access to the auth token/logout-on-401 behavior
// authFetch already provides, and duplicating that here would drift from
// AuthContext.jsx's single implementation.
export async function listDocuments(authFetch) {
  const response = await authFetch('/documents')
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load documents (${response.status}).`)
  }

  // A 2xx response should always be a JSON array; a null/malformed body
  // here means something's genuinely wrong (not a normal empty-list case
  // -- that's `[]`, which parses fine) -- fail loudly rather than handing
  // the caller `null` to `.map`/`.length` over.
  if (!Array.isArray(data)) {
    throw new Error('Failed to load documents: unexpected response.')
  }

  return data
}

// One document by id, behind Document Detail (Story 2.2). A document that
// isn't yours comes back as a 404 (the backend deliberately never answers
// 403 here -- that would confirm the id exists), so the caller renders the
// backend's own "Document not found." for both cases and doesn't try to
// distinguish them.
export async function getDocument(authFetch, documentId) {
  const response = await authFetch(`/documents/${encodeURIComponent(documentId)}`)
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load document (${response.status}).`)
  }

  // Mirrors listDocuments' shape guard: fail loudly rather than handing
  // the caller a null to read fields off.
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('Failed to load document: unexpected response.')
  }

  return data
}

// One document's raw bytes, for the preview modal. `authFetch` (not a bare
// `<iframe src>`) because the endpoint requires the same Authorization
// header every other document route does -- an iframe/img src can't carry
// one, so the caller fetches the bytes itself and turns them into an
// object URL. Same 404-for-not-yours-or-missing shape as getDocument.
export async function getDocumentContent(authFetch, documentId) {
  const response = await authFetch(`/documents/${encodeURIComponent(documentId)}/content`)

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load document content (${response.status}).`)
  }

  return response.blob()
}

// Deletes one document by id (Story 2.7): its Weaviate passages and its
// row are both gone on success, through the same backend call that
// applies AD-2's tenancy scoping -- another account's document id (or a
// nonexistent one) comes back as the same 404 `getDocument` already
// handles, so this mirrors that error-handling shape rather than
// inventing a new one.
//
// The success response is 204 with no body, unlike getDocument/
// listDocuments -- so this never calls `response.json()` on the happy
// path, only on a non-2xx response where the backend's `{"detail": ...}`
// envelope (AD-3) is expected.
// Assigns/unassigns one document's folder (folder-grouping feature).
// `folderId` may be `null` to unassign (back to "Ungrouped"). Same error
// shape as every other client in this module -- a cross-tenant or
// nonexistent document id, or a `folderId` belonging to another account,
// both come back as the backend's own 404 (different messages: "Document
// not found." vs "Folder not found." -- see documents/service.py).
export async function updateDocumentFolder(authFetch, documentId, folderId) {
  const response = await authFetch(`/documents/${encodeURIComponent(documentId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to update document folder (${response.status}).`)
  }

  return data
}

export async function deleteDocument(authFetch, documentId) {
  const response = await authFetch(`/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to delete document (${response.status}).`)
  }
}
