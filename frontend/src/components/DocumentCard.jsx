import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import StatusPill from './StatusPill'
import { useAuth } from '../context/AuthContext'
import { deleteDocument } from '../api/documentsClient'
import { DELETE_BOUNDARY_TEXT, formatFileTypeShort, formatUploadedDate } from '../utils/documentFormat'

// One document as a card in the library grid (Story 2.2, human-requested
// design change from the mockup's `.doclist` table -- see the spec's
// Change Log).
//
// Carries exactly the same five facts the table columns did: file type
// (the icon tile), title, status, uploaded date, and the trash action.
//
// The file-icon tile reuses DESIGN.md's `.file-icon` treatment
// (`--citation` fill, `--primary` text) rather than inventing a colour:
// that is the one use of the citation token DESIGN.md sanctions outside a
// literal citation chip ("the file-type icon tile in upload rows"), so the
// grid stays inside the existing palette instead of adding to it.
export default function DocumentCard({ document, onCardClick, onDeleted }) {
  const detailHref = `/documents/${document.id}`
  const { authFetch } = useAuth()

  // Local, not lifted to DocumentsPage: each card's confirm state is its
  // own -- the only thing the parent needs is the single `onDeleted(id)`
  // callback below, not shared confirm-open state (Design Notes).
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState(null)

  const trashButtonRef = useRef(null)
  const cancelButtonRef = useRef(null)

  const boundaryTextId = `delete-boundary-${document.id}`

  // Focus moves into the box on open, to Cancel -- the safer default for
  // a destructive action (Design Notes, UX-DR26).
  useEffect(() => {
    if (isConfirming) cancelButtonRef.current?.focus()
  }, [isConfirming])

  function openConfirm(event) {
    event.stopPropagation()
    setError(null)
    setIsConfirming(true)
  }

  // Escape and Cancel both collapse back to the resting state and return
  // focus to the control that opened the box (UX-DR26) -- but only on a
  // non-deleting close; a delete already in flight isn't interrupted by
  // either.
  function collapseConfirm() {
    if (isDeleting) return
    setIsConfirming(false)
    setError(null)
    trashButtonRef.current?.focus()
  }

  function handleConfirmBoxKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    collapseConfirm()
  }

  function handleCancel(event) {
    event.stopPropagation()
    collapseConfirm()
  }

  async function handleConfirmDelete(event) {
    event.stopPropagation()
    setIsDeleting(true)
    setError(null)
    try {
      await deleteDocument(authFetch, document.id)
      onDeleted(document.id)
    } catch (err) {
      // On failure: error shown, row stays, confirm box stays open for
      // retry (I/O matrix) -- focus is left where it is rather than
      // forced anywhere, since the user may want to retry immediately.
      setError(err.message)
      setIsDeleting(false)
    }
  }

  return (
    // Click-anywhere is a mouse-convenience layer over the real <Link>
    // below -- the same split the table row used. The card is not itself a
    // link/button because the trash control lives inside it, and a
    // <button> nested in an <a> is invalid HTML that breaks keyboard and
    // screen-reader behavior. Keyboard users reach the document through
    // the title link and the trash through its own button, which is why
    // this carries no tabIndex or role.
    //
    // The handler sits on the <li> itself rather than an inner wrapper so
    // the clickable region is exactly the visible card -- with a wrapper,
    // a click landing on the <li>'s own box (outside the child) would do
    // nothing, since events bubble up rather than down.
    <li
      onClick={(event) => onCardClick(event, document.id)}
      className="flex cursor-pointer flex-col gap-3 rounded-lg border border-border bg-card-bg p-4 hover:border-accent"
    >
        <div className="flex items-start justify-between gap-2">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-citation text-[11px] font-extrabold tracking-[0.02em] text-primary"
          >
            {formatFileTypeShort(document.file_type)}
          </span>

          {/* stopPropagation is belt-and-braces alongside the card
              handler's own `closest('a, button')` guard; either alone
              would keep this from navigating. Stays rendered and focusable
              whether resting or confirming -- never disabled -- so Tab
              order never shifts underneath a keyboard user. */}
          <button
            ref={trashButtonRef}
            type="button"
            aria-label={`Delete ${document.filename}`}
            aria-expanded={isConfirming}
            onClick={openConfirm}
            className="-mr-1 -mt-1 shrink-0 rounded-sm p-1 text-text2 hover:bg-surface2 hover:text-danger"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-4 w-4"
            >
              <path d="M3 6h18" />
              <path d="M8 6V4h8v2" />
              <path d="M6 6l1 14h10l1-14" />
              <path d="M10 11v6M14 11v6" />
            </svg>
          </button>
        </div>

        {/* `break-words` rather than truncate: filenames are the one thing
            a user scans this grid for, and a silently clipped name is
            worse than a taller card. `line-clamp-2` bounds it so one
            pathological name can't stretch its whole grid row. */}
        <Link
          to={detailHref}
          className="line-clamp-2 text-sm font-semibold break-words text-text hover:underline"
        >
          {document.filename}
        </Link>

        {isConfirming ? (
          // Inline confirm box (UX-DR14): no modal, built from scratch.
          // `role="alert"` on the box itself announces its appearance the
          // same way this app's existing error text does (UploadModal.jsx,
          // DocumentsPage.jsx). onClick stopPropagation keeps a click
          // landing on the box's own text (not a button) from bubbling up
          // to the card's navigate-on-click handler mid-confirm.
          //
          // `border-danger/30 bg-danger/5` -- a soft tint, not a
          // full-saturation red border -- per DESIGN.md's danger-zone
          // pattern (the Delete Account card's "danger-tinted
          // border/background"). The Delete button below is the same
          // shape as Cancel (`border-border`), only its text is
          // danger-colored -- DESIGN.md: "Danger: same shape as
          // secondary, danger-colored text ... not a filled-red button
          // until a confirmation step." A solid red border on both the
          // box and the button was two loud reds stacked on each other.
          <div
            role="alert"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={handleConfirmBoxKeyDown}
            className="flex flex-col gap-2 rounded-md border border-danger/30 bg-danger/5 p-2.5"
          >
            <p id={boundaryTextId} className="text-xs text-text">
              Delete {document.filename}? {DELETE_BOUNDARY_TEXT}
            </p>
            {error && (
              <p role="alert" className="text-xs text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                ref={cancelButtonRef}
                type="button"
                aria-describedby={boundaryTextId}
                onClick={handleCancel}
                disabled={isDeleting}
                className="rounded-md border border-border bg-card-bg px-2.5 py-1 text-xs font-semibold text-primary"
              >
                Cancel
              </button>
              <button
                type="button"
                aria-describedby={boundaryTextId}
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="rounded-md border border-border bg-card-bg px-2.5 py-1 text-xs font-semibold text-danger"
              >
                {isDeleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
            <StatusPill status={document.status} />
            <span className="text-xs text-text2">{formatUploadedDate(document.created_at)}</span>
          </div>
        )}
    </li>
  )
}
