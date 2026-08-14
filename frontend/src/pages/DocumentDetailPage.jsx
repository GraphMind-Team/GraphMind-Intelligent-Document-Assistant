import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { deleteDocument, getDocument } from '../api/documentsClient'
import StatusPill from '../components/StatusPill'
import {
  DELETE_BOUNDARY_TEXT,
  formatFileSize,
  formatFileType,
  formatUploadedDate,
} from '../utils/documentFormat'

// Document Detail (Story 2.2), rendered at `/documents/:documentId`.
//
// A nested *route*, not in-page state on DocumentsPage: that's what makes
// the back button, deep links, and the logged-out-deep-link flow work with
// no code of their own -- ProtectedRoute already stashes `location.state
// .from` and LoginPage already redirects back to it (Story 1.5).
//
// Everything rendered here is document-derived text (`filename` is
// attacker-controlled, and `.md`/`.html` are ingestible formats) and is
// therefore emitted as plain React text children only. No
// `dangerouslySetInnerHTML`, no Markdown/HTML renderer -- a standing
// constraint in `deferred-work.md`, not a preference.
//
// Story 2.4 adds the one `Ready`-state branch below: chapter count,
// passages-indexed, and the chapter breakdown list all come from
// `doc.chapter_breakdown` (`dict[chapter_name] -> passage_count`,
// populated server-side only in the same commit that sets
// `status = "Ready"`).
//
// Story 2.5 splits the non-Ready fallback in two. UX-DR8's "Pending, never
// a fabricated 0" rule was written for a document still moving through the
// pipeline -- "Pending" carries an implicit promise that the real value is
// coming. That promise is false for a `Failed` document: ingestion is
// terminal (nothing retries it today), so telling the user the breakdown
// "appears once this document has been parsed and indexed" contradicts the
// failure reason rendered directly below it. `Failed` therefore gets its
// own terminal wording; every other non-Ready status keeps "Pending"
// exactly as before.
const PENDING = 'Pending'
const UNAVAILABLE = 'Unavailable'

function MetaItem({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2.5">
      <dt className="text-eyebrow uppercase text-text2">{label}</dt>
      <dd className="mt-0.5 text-sm text-text">{value}</dd>
    </div>
  )
}

export default function DocumentDetailPage() {
  const { documentId } = useParams()
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [doc, setDoc] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  // Story 2.7: same inline-confirm pattern as DocumentCard.jsx, local to
  // this page rather than shared -- there is no third place this same
  // state needs to live.
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const deleteButtonRef = useRef(null)
  const cancelDeleteButtonRef = useRef(null)
  const deleteBoundaryTextId = 'delete-document-boundary'

  useEffect(() => {
    if (isConfirmingDelete) cancelDeleteButtonRef.current?.focus()
  }, [isConfirmingDelete])

  function openDeleteConfirm() {
    setDeleteError(null)
    setIsConfirmingDelete(true)
  }

  function collapseDeleteConfirm() {
    if (isDeleting) return
    setIsConfirmingDelete(false)
    setDeleteError(null)
    deleteButtonRef.current?.focus()
  }

  function handleDeleteConfirmKeyDown(event) {
    if (event.key !== 'Escape') return
    collapseDeleteConfirm()
  }

  async function handleConfirmDelete() {
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await deleteDocument(authFetch, documentId)
      // Nothing left to show at this route once the document is gone --
      // navigate back to the library rather than leaving a dead detail
      // view. No focus-return here: the page itself is unmounting.
      navigate('/documents')
    } catch (err) {
      setDeleteError(err.message)
      setIsDeleting(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)
    setDoc(null)

    getDocument(authFetch, documentId)
      .then((data) => {
        if (!cancelled) setDoc(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [authFetch, documentId])

  return (
    <div className="mx-auto max-w-[640px]">
      <Link to="/documents" className="mb-4 inline-block text-sm text-link hover:underline">
        Back to documents
      </Link>

      {isLoading && <p className="text-sm text-text2">Loading document...</p>}

      {/* A document that belongs to another account returns the same 404
          -- and therefore the same message -- as one that doesn't exist.
          This view has no way to tell them apart, by design. */}
      {!isLoading && error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {!isLoading && !error && doc && (() => {
        // The one `Ready`-state branch (Story 2.4): real values only once
        // the backend has actually populated `chapter_breakdown` in the
        // same commit as `status = "Ready"`. Every other status (including
        // a `Ready` row from before this story, which can't exist, but
        // also a defensive fallback) keeps rendering "Pending" -- never a
        // fabricated 0/empty list (UX-DR8).
        const isReady = doc.status === 'Ready' && doc.chapter_breakdown != null
        const isFailed = doc.status === 'Failed'
        const chapterEntries = isReady ? Object.entries(doc.chapter_breakdown) : []
        const chapterCount = isReady ? chapterEntries.length : null
        const passagesIndexed = isReady
          ? chapterEntries.reduce((total, [, count]) => total + count, 0)
          : null
        // Terminal for `Failed`, still-coming for anything else non-Ready.
        const notReadyLabel = isFailed ? UNAVAILABLE : PENDING

        return (
          <div className="rounded-xl border border-border bg-card-bg p-[26px]">
            <div className="flex items-start justify-between gap-3">
              <h1 className="text-[18px] font-bold text-primary">{doc.filename}</h1>
              {/* Story 2.7: Document Detail's own entry point to the same
                  delete action DocumentCard.jsx's trash icon offers.
                  "Danger: same shape as secondary, danger-colored text"
                  (DESIGN.md) -- not a filled-red button until the
                  confirmation step below. */}
              <button
                ref={deleteButtonRef}
                type="button"
                aria-expanded={isConfirmingDelete}
                onClick={openDeleteConfirm}
                className="shrink-0 rounded-md border border-border bg-surface2 px-3 py-1.5 text-xs font-semibold text-danger"
              >
                Delete
              </button>
            </div>

            {isConfirmingDelete && (
              // Inline confirm (UX-DR14): no modal. `role="alert"`
              // announces its appearance, matching this app's existing
              // error-announcement pattern. `border-danger/30 bg-danger/5`
              // is a soft tint (DESIGN.md's danger-zone pattern), not a
              // full-saturation border -- and the Delete button below is
              // the same shape as Cancel, only its text is danger-colored,
              // same as the trigger button above ("Danger: same shape as
              // secondary, danger-colored text").
              <div
                role="alert"
                onKeyDown={handleDeleteConfirmKeyDown}
                className="mt-3 mb-3 flex flex-col gap-2 rounded-md border border-danger/30 bg-danger/5 p-3"
              >
                <p id={deleteBoundaryTextId} className="text-sm text-text">
                  Delete {doc.filename}? {DELETE_BOUNDARY_TEXT}
                </p>
                {deleteError && (
                  <p role="alert" className="text-sm text-danger">
                    {deleteError}
                  </p>
                )}
                <div className="flex justify-end gap-2">
                  <button
                    ref={cancelDeleteButtonRef}
                    type="button"
                    aria-describedby={deleteBoundaryTextId}
                    onClick={collapseDeleteConfirm}
                    disabled={isDeleting}
                    className="rounded-md border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-primary"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    aria-describedby={deleteBoundaryTextId}
                    onClick={handleConfirmDelete}
                    disabled={isDeleting}
                    className="rounded-md border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-danger"
                  >
                    {isDeleting ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            )}

            <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[13px] text-text2">
              <span>Uploaded {formatUploadedDate(doc.created_at)}</span>
              <StatusPill status={doc.status} />
            </p>

            <dl className="my-[18px] grid grid-cols-2 gap-3.5">
              <MetaItem label="Uploaded" value={formatUploadedDate(doc.created_at)} />
              <MetaItem
                label="File type"
                value={`${formatFileType(doc.file_type)} · ${formatFileSize(doc.file_size_bytes)}`}
              />
              {/* Never a fabricated 0 (UX-DR8): a 0 here would read as
                  "this document has no chapters", which is a different and
                  false claim from "nothing has parsed it yet". "Pending"
                  while still in flight, "Unavailable" once Failed -- see
                  the note above the constants. */}
              <MetaItem label="Chapters" value={isReady ? chapterCount : notReadyLabel} />
              <MetaItem
                label="Passages indexed"
                value={isReady ? passagesIndexed : notReadyLabel}
              />
            </dl>

            <section>
              <h2 className="text-eyebrow uppercase text-text2">Chapter breakdown</h2>
              {isReady ? (
                <ul className="mt-2 divide-y divide-border">
                  {/* Insertion order from the backend already matches
                      document reading order (`Counter` over the parsed
                      chunks, first-appearance order) -- no client-side
                      sort. Chapter names are document-derived text, so
                      they render as plain text children only, never
                      `dangerouslySetInnerHTML`. */}
                  {chapterEntries.map(([chapter, count]) => (
                    <li
                      key={chapter}
                      className="flex items-center justify-between gap-3 py-2 text-sm text-text"
                    >
                      <span>{chapter}</span>
                      <span className="text-text2">{count}</span>
                    </li>
                  ))}
                </ul>
              ) : isFailed ? (
                // No "appears once parsed and indexed" promise here: this
                // document's ingestion is over, and the reason it ended is
                // rendered in the section directly below.
                <p className="mt-2 text-sm text-text2">
                  Unavailable — this document failed to process.
                </p>
              ) : (
                <p className="mt-2 text-sm text-text2">
                  Pending — the chapter breakdown appears once this document has been parsed and
                  indexed.
                </p>
              )}
            </section>

            {/* Story 2.5: Detail-only, never inline in the Documents table
                row (human decision) -- a short, human-readable,
                stage-aware reason set server-side only in the same commit
                as `status = "Failed"`. Rendered only when `status ===
                'Failed'`; every other status renders nothing here. */}
            {doc.status === 'Failed' && (
              <section className="mt-[18px]">
                <h2 className="text-eyebrow uppercase text-text2">Reason</h2>
                {/* `break-words` (matching `DocumentCard.jsx`'s filename
                    rendering) -- the backend allows up to ~340 chars of
                    freeform text here. Falls back to a fixed string rather
                    than rendering blank when `failed_reason` is null (e.g.
                    a pre-migration row). */}
                <p className="mt-2 text-sm text-text break-words">
                  {doc.failed_reason || 'No further details available.'}
                </p>
              </section>
            )}
          </div>
        )
      })()}
    </div>
  )
}
