import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import StatusPill from './StatusPill'
import FolderModal from './FolderModal'
import { useAuth } from '../context/AuthContext'
import { deleteDocument, updateDocumentFolder } from '../api/documentsClient'
import { formatFileTypeShort, formatUploadedDate } from '../utils/documentFormat'

// The MIME type `onDragStart` below writes the dragged document's id
// under, and every other card's `onDrop` reads it back from (Round 2:
// native HTML5 drag-and-drop only, per the spec's Boundaries -- no new
// dependency).
const DRAG_DOCUMENT_ID_TYPE = 'text/plain'

// Captured at module scope, before the component below exists -- every
// `DocumentCard` instance takes a document *record* as its own `document`
// prop, which shadows the global `window.document` for this entire
// component's body (every `document.id`/`document.filename`/etc. below is
// that prop, not the DOM). This is how the component still reaches the
// real DOM `document`, for portalling the create-folder modal out of this
// card's `.card-lift` (see the portal's own comment below) and for the
// "⋮" menu's outside-click listener.
const ownerDocument = document

// One document as a card in the library grid (Story 2.2, human-requested
// design change from the mockup's `.doclist` table -- see the spec's
// Change Log).
//
// Carries exactly the same five facts the table columns did: file type
// (the icon tile), title, status, uploaded date, and the trash action.
//
// The file-icon tile carries the brand gradient (`--grad-brand`) in
// design system v2 -- the same fill as the logo mark, the primary button
// and the mascot, rather than the v1 `--citation` tint. That keeps the
// citation token strictly for citations (v2 narrowed it to that single
// purpose) and makes the grid's densest repeated element the place the
// brand actually shows up. White-on-gradient clears AA at this weight;
// the two-letter label is also never the only carrier of file type --
// the filename beneath it always is.
// `folders` defaults to `[]`, `onFolderChanged`/`onFolderCreated` to
// no-ops, so every existing caller/test that predates the folder-grouping
// feature (built before these props existed) keeps rendering unchanged.
export default function DocumentCard({
  document,
  onCardClick,
  onDeleted,
  folders = [],
  onFolderChanged = () => {},
  onFolderCreated = () => {},
}) {
  const { t } = useTranslation()
  const detailHref = `/documents/${document.id}`
  const { authFetch } = useAuth()

  // Local, not lifted to DocumentsPage: each card's confirm state is its
  // own -- the only thing the parent needs is the single `onDeleted(id)`
  // callback below, not shared confirm-open state (Design Notes).
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState(null)

  // Folder assignment (folder-grouping feature) -- its own small local
  // state, same "own it locally, notify the parent on success" shape as
  // the delete confirm above: the parent (`DocumentsPage`) owns the
  // `documents` array this card's `folder_id` is a snapshot of, so a
  // successful change is reported up via `onFolderChanged` rather than
  // this component keeping its own copy of the assignment.
  const [folderError, setFolderError] = useState(null)

  // Round 2 (Spec Change Log): the native `<select>` is gone, replaced by
  // a "⋮" menu -- `isMenuOpen` toggles it, `isDragOver` is drag-and-drop
  // visual feedback only. `createFolderState` covers both places this
  // card can open the shared `FolderModal` in create mode: the menu's own
  // "Create new folder" item (assigns just this document), and a
  // doc-onto-doc drop where the target (this card) is Ungrouped (assigns
  // both the dragged document and this one) -- `null | 'menu' | { draggedId }`.
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)
  const [createFolderState, setCreateFolderState] = useState(null)

  const menuButtonRef = useRef(null)
  const menuRef = useRef(null)

  // Assigns `documentId` to `folderId` (or `null` to unassign) and reports
  // success up via `onFolderChanged` -- shared by the menu's own items and
  // both drag-and-drop branches, since a drop can assign a document other
  // than this card's own (the dragged one).
  async function assignFolder(documentId, folderId) {
    try {
      await updateDocumentFolder(authFetch, documentId, folderId)
      onFolderChanged(documentId, folderId)
    } catch (err) {
      setFolderError(err.message)
    }
  }

  function closeMenu() {
    setIsMenuOpen(false)
  }

  function toggleMenu(event) {
    event.stopPropagation()
    setFolderError(null)
    setIsMenuOpen((open) => !open)
  }

  async function handleMoveToFolder(event, folderId) {
    event.stopPropagation()
    closeMenu()
    setFolderError(null)
    await assignFolder(document.id, folderId)
  }

  function handleCreateNewFolder(event) {
    event.stopPropagation()
    closeMenu()
    setFolderError(null)
    setCreateFolderState('menu')
  }

  // Focus moves into the menu on open, to its first item -- the same
  // "focus moves into the transient surface" convention the delete
  // confirm box below and `FolderModal` both already follow. This is also
  // what lets Escape close it via a plain `onKeyDown` on the menu itself
  // (bubbling up from whichever item has focus), the same local pattern
  // the confirm box's own `handleConfirmBoxKeyDown` uses, rather than a
  // second global listener.
  useEffect(() => {
    if (isMenuOpen) menuRef.current?.querySelector('[role="menuitem"]')?.focus()
  }, [isMenuOpen])

  // Outside-click still needs a document-level listener -- there's no
  // local event that fires for "a click landed outside this element".
  // Scoped to only run while the menu is actually open, mirroring the
  // delete confirm box's own `useEffect(..., [isConfirming])` gating.
  useEffect(() => {
    if (!isMenuOpen) return undefined

    function handlePointerDown(event) {
      if (menuRef.current?.contains(event.target)) return
      if (menuButtonRef.current?.contains(event.target)) return
      setIsMenuOpen(false)
    }

    ownerDocument.addEventListener('mousedown', handlePointerDown)
    return () => ownerDocument.removeEventListener('mousedown', handlePointerDown)
  }, [isMenuOpen])

  function handleMenuKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    setIsMenuOpen(false)
    menuButtonRef.current?.focus()
  }

  // Round 2: native HTML5 drag-and-drop (the spec's Boundaries -- no new
  // dependency). `onDragStart` marks this card as the one being dragged;
  // every *other* card's `onDragOver`/`onDrop` is the target side below.
  function handleDragStart(event) {
    event.dataTransfer.setData(DRAG_DOCUMENT_ID_TYPE, document.id)
    event.dataTransfer.effectAllowed = 'move'
  }

  // `preventDefault` here is the native HTML5 requirement for `onDrop` to
  // fire at all -- without it, the browser rejects the drop unconditionally.
  function handleDragOver(event) {
    event.preventDefault()
  }

  function handleDragEnter(event) {
    event.preventDefault()
    setIsDragOver(true)
  }

  function handleDragLeave() {
    setIsDragOver(false)
  }

  // Doc-onto-doc drop (the spec's I/O matrix): dragging onto itself, or a
  // drop with no dragged-document data, is a no-op -- no request sent.
  // Otherwise: if *this* card (the drop target) already belongs to a
  // folder, the dragged document joins that folder directly, no dialog.
  // If this card is Ungrouped, the create-folder dialog opens instead,
  // and confirming it assigns *both* documents to the new folder.
  function handleDrop(event) {
    event.preventDefault()
    setIsDragOver(false)
    const draggedId = event.dataTransfer.getData(DRAG_DOCUMENT_ID_TYPE)
    if (!draggedId || draggedId === document.id) return

    setFolderError(null)
    if (document.folder_id) {
      assignFolder(draggedId, document.folder_id)
    } else {
      setCreateFolderState({ draggedId })
    }
  }

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
    //
    // Round 2: `draggable` + the drag handlers turn the whole card into
    // both a drag source (`onDragStart`) and a drop target for every
    // *other* card (`onDragOver`/`onDrop`) -- native HTML5 DnD dispatches
    // neither a `click` nor a `dragstart` from the other, so this needs no
    // extra guard in `DocumentsPage.jsx`'s own click-vs-navigate handler.
    <li
      draggable
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={(event) => onCardClick(event, document.id)}
      className={[
        'card-lift flex cursor-pointer flex-col gap-3.5 rounded-2xl border bg-card-bg p-5 shadow-card hover:border-accent',
        isDragOver ? 'border-accent bg-surface2' : 'border-border',
      ].join(' ')}
    >
        <div className="flex items-start justify-between gap-2">
          <span
            aria-hidden="true"
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[image:var(--grad-brand)] text-[11px] font-extrabold tracking-[0.02em] text-white shadow-[var(--glow)]"
          >
            {formatFileTypeShort(document.file_type)}
          </span>

          <div className="flex shrink-0 items-start gap-0.5">
            {/* Round 2: replaces the native <select> folder-assignment
                control -- the one new menu/popover primitive this project
                now has (the original "no new dropdown/menu" boundary is
                explicitly struck, see the spec's Spec Change Log). Kept
                minimal: a plain absolutely-positioned list, role="menu"
                /role="menuitem", Escape + outside-click to close (the
                effect above), matching this file's own confirm-box focus
                conventions rather than introducing a new pattern. */}
            <div className="relative">
              <button
                ref={menuButtonRef}
                type="button"
                aria-haspopup="menu"
                aria-expanded={isMenuOpen}
                aria-label={t('documents.folderMenu.moveAria', { filename: document.filename })}
                onClick={toggleMenu}
                className="-mt-1 rounded-lg p-1.5 text-text2 hover:bg-accent/10 hover:text-accent"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4">
                  <circle cx="12" cy="5" r="1.7" />
                  <circle cx="12" cy="12" r="1.7" />
                  <circle cx="12" cy="19" r="1.7" />
                </svg>
              </button>

              {isMenuOpen && (
                <div
                  ref={menuRef}
                  role="menu"
                  aria-label={t('documents.folderMenu.moveToFolder')}
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={handleMenuKeyDown}
                  className="absolute right-0 top-full z-10 mt-1 w-48 rounded-lg border border-border bg-card-bg py-1 shadow-modal"
                >
                  <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.02em] text-text2">
                    {t('documents.folderMenu.moveToFolder')}
                  </p>
                  {document.folder_id && (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={(event) => handleMoveToFolder(event, null)}
                      className="block w-full px-3 py-1.5 text-left text-[13px] text-text hover:bg-surface2"
                    >
                      {t('documents.folderMenu.ungrouped')}
                    </button>
                  )}
                  {folders.map((folder) => (
                    <button
                      key={folder.id}
                      type="button"
                      role="menuitem"
                      onClick={(event) => handleMoveToFolder(event, folder.id)}
                      className="block w-full px-3 py-1.5 text-left text-[13px] text-text hover:bg-surface2"
                    >
                      {folder.name}
                    </button>
                  ))}
                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleCreateNewFolder}
                    className="block w-full border-t border-border px-3 py-1.5 text-left text-[13px] font-semibold text-primary hover:bg-surface2"
                  >
                    {t('documents.folderMenu.createNewFolder')}
                  </button>
                </div>
              )}
            </div>

            {/* stopPropagation is belt-and-braces alongside the card
                handler's own `closest('a, button')` guard; either alone
                would keep this from navigating. Stays rendered and focusable
                whether resting or confirming -- never disabled -- so Tab
                order never shifts underneath a keyboard user. */}
            <button
              ref={trashButtonRef}
              type="button"
              aria-label={t('documents.deleteAria', { filename: document.filename })}
              aria-expanded={isConfirming}
              onClick={openConfirm}
              className="-mt-1 shrink-0 rounded-lg p-1.5 text-text2 hover:bg-danger/10 hover:text-danger"
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
        </div>

        {/* `break-words` rather than truncate: filenames are the one thing
            a user scans this grid for, and a silently clipped name is
            worse than a taller card. `line-clamp-2` bounds it so one
            pathological name can't stretch its whole grid row. */}
        {/* `draggable={false}`: an <a href> is natively draggable by
            default, and starting a drag from directly over the filename
            would otherwise let the browser take over with its own
            link-drag ghost (filename + full URL in a gray chip) instead of
            this card's own `onDragStart` above -- stepping on the "Move to
            {folder}" tooltip FolderGrid.jsx shows during that same drag. */}
        <Link
          to={detailHref}
          draggable={false}
          className="line-clamp-2 text-[14.5px] font-semibold break-words text-text hover:text-primary hover:underline"
        >
          {document.filename}
        </Link>

        {folderError && (
          <p role="alert" className="-mt-2 text-xs text-danger">
            {folderError}
          </p>
        )}

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
            className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger/5 p-3"
          >
            <p id={boundaryTextId} className="text-xs text-text">
              {t('documents.deleteConfirmPrefix', { filename: document.filename })} {t('documents.deleteBoundaryText')}
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
                className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-primary"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                aria-describedby={boundaryTextId}
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-danger"
              >
                {isDeleting ? t('documents.deleting') : t('common.delete')}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
            <StatusPill status={document.status} />
            <span className="text-xs text-text2">{formatUploadedDate(document.created_at)}</span>
          </div>
        )}

        {/* Portalled to `document.body`, not rendered inline here: this
            `<li>` carries `.card-lift`, which sets a CSS `transform` on
            hover, and any transformed ancestor becomes the containing
            block for a `position: fixed` descendant -- inline, the modal
            backdrop would stop covering the full viewport the moment the
            card is hovered. A portal sidesteps that entirely, the same
            reason dialogs are conventionally portalled out of scrolling/
            transformed list items in general. */}
        {createFolderState &&
          createPortal(
            <FolderModal
              folder={null}
              onClose={() => setCreateFolderState(null)}
              onSaved={(saved) => {
                onFolderCreated(saved)
                if (createFolderState !== 'menu') {
                  assignFolder(createFolderState.draggedId, saved.id)
                }
                assignFolder(document.id, saved.id)
              }}
            />,
            ownerDocument.body,
          )}
    </li>
  )
}
