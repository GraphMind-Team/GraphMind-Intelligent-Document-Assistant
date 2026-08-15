// Presentation helpers shared by the Documents table, the Document Detail
// panel, and the upload modal's file rows (Story 2.2). Extracted rather
// than repeated per page so the same document renders the same size/type/
// date string wherever it appears.

// Story 2.7 (updated by Story 2.8, OD-4): the declarative boundary text an
// inline delete-confirm box states before any deletion happens (UX-DR19) --
// shared by DocumentCard.jsx's trash-icon confirm and
// DocumentDetailPage.jsx's Delete-button confirm so the same
// reference-counted-pruning wording can't drift between the two entry
// points to the identical action. No longer an unconditional "entities
// remain" -- Story 2.8 reverses that: entities/relationships unique to this
// document are pruned from the graph, and only ones a surviving document
// still contributes to are kept.
export const DELETE_BOUNDARY_TEXT =
  'Removes its passages, and any entities/relationships not shared with another document.'

// The stored `file_type` values are the normalized ones the backend writes
// (`backend/app/documents/service.py`'s `_EXTENSION_TO_FILE_TYPE`); this
// maps them to the display labels the reference mockup uses.
export const FILE_TYPE_LABELS = {
  pdf: 'PDF',
  markdown: 'Markdown',
  html: 'HTML',
}

// Falls back to the raw stored value rather than hiding it: a `file_type`
// this map doesn't know about is a backend/frontend drift worth seeing,
// not worth silently blanking. Rendered as plain React text either way.
export function formatFileType(fileType) {
  return FILE_TYPE_LABELS[fileType] ?? fileType
}

// Short badge labels for the card grid's file-icon tile, where "Markdown"
// is too wide for a 44px square. Same drift-visible fallback as above,
// upper-cased and clipped so an unknown value still reads as *something*
// rather than overflowing the tile.
const SHORT_FILE_TYPE_LABELS = {
  pdf: 'PDF',
  markdown: 'MD',
  html: 'HTML',
}

export function formatFileTypeShort(fileType) {
  return SHORT_FILE_TYPE_LABELS[fileType] ?? String(fileType ?? '?').slice(0, 4).toUpperCase()
}

export function formatFileSize(bytes) {
  if (typeof bytes !== 'number' || Number.isNaN(bytes)) return 'Unknown'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// "Aug 10, 2026" per the mockup -- date only, no time: the table column is
// "Uploaded", and a wall-clock time adds width without adding meaning at
// this granularity. An unparseable timestamp renders an em dash rather
// than "Invalid Date".
export function formatUploadedDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
