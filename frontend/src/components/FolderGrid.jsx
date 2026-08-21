import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { deleteFolder } from '../api/foldersClient'
import { updateDocumentFolder } from '../api/documentsClient'
import { folderSwatchClass } from '../utils/folderFormat'
import FolderModal from './FolderModal'

// Filter values `DocumentsPage.jsx` compares `visibleDocuments` derivation
// against, alongside a real folder's own `id`. Exported so the page never
// hand-rolls these strings itself. "Ungrouped" (Spec Change Log Round 2,
// was "Unfiled") -- renamed at the human's request; the sentinel value
// itself changes too since nothing persists it across a session.
export const ALL_DOCUMENTS_FILTER = 'all'
export const UNGROUPED_FILTER = 'ungrouped'

// The MIME type `DocumentCard.jsx`'s `onDragStart` writes the dragged
// document's id under (Round 2: native HTML5 drag-and-drop, no new
// dependency per the spec's Boundaries).
const DRAG_DOCUMENT_ID_TYPE = 'text/plain'

function FolderTile({ folder, count, isActive, onSelect, onEdit, onDeleted, onDropDocument }) {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState(null)
  // Round 2: drag-and-drop visual feedback only -- purely presentational,
  // toggled by the native dragenter/dragleave pair below.
  const [isDragOver, setIsDragOver] = useState(false)

  const deleteButtonRef = useRef(null)
  const cancelButtonRef = useRef(null)

  // Focus moves to Cancel on open, the safer default for a destructive
  // action -- mirrors DocumentCard.jsx's own delete confirm (UX-DR26).
  useEffect(() => {
    if (isConfirming) cancelButtonRef.current?.focus()
  }, [isConfirming])

  function openConfirm(event) {
    event.stopPropagation()
    setError(null)
    setIsConfirming(true)
  }

  function collapseConfirm() {
    if (isDeleting) return
    setIsConfirming(false)
    setError(null)
    deleteButtonRef.current?.focus()
  }

  function handleConfirmBoxKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    collapseConfirm()
  }

  async function handleConfirmDelete(event) {
    event.stopPropagation()
    setIsDeleting(true)
    setError(null)
    try {
      await deleteFolder(authFetch, folder.id)
      onDeleted(folder.id)
    } catch (err) {
      setError(err.message)
      setIsDeleting(false)
    }
  }

  // Round 2: this tile is a drop target for "drag doc onto a folder tile"
  // (the spec's I/O matrix) -- dropping assigns the dragged document to
  // *this* folder directly, no dialog (unlike doc-onto-doc, which can open
  // one). `preventDefault` in `onDragOver` is the native HTML5 requirement
  // for `onDrop` to fire at all.
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

  function handleDrop(event) {
    event.preventDefault()
    setIsDragOver(false)
    const draggedId = event.dataTransfer.getData(DRAG_DOCUMENT_ID_TYPE)
    if (!draggedId) return
    onDropDocument(draggedId, folder.id)
  }

  if (isConfirming) {
    // Inline confirm box (UX-DR14), same shape as DocumentCard.jsx's own
    // delete confirm -- no modal, built from scratch, danger-tinted per
    // DESIGN.md's danger-zone pattern.
    return (
      <div
        role="alert"
        onKeyDown={handleConfirmBoxKeyDown}
        className="flex flex-col gap-2 rounded-xl border border-danger/30 bg-danger/5 p-3"
      >
        <p className="text-xs text-text">
          {t('documents.folderGrid.deleteConfirm', { name: folder.name })}
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
            onClick={collapseConfirm}
            disabled={isDeleting}
            className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-primary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={handleConfirmDelete}
            disabled={isDeleting}
            className="rounded-lg border border-border bg-card-bg px-3 py-1.5 text-xs font-semibold text-danger"
          >
            {isDeleting ? t('documents.deleting') : t('common.delete')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={[
        'card-lift relative flex flex-col gap-1.5 rounded-xl border p-3.5',
        isActive || isDragOver ? 'border-accent bg-surface2' : 'border-border bg-card-bg',
      ].join(' ')}
    >
      <button
        type="button"
        aria-pressed={isActive}
        aria-label={t('documents.folderGrid.tileAria', { name: folder.name, count })}
        onClick={() => onSelect(folder.id)}
        className="flex flex-col items-start gap-1.5 pr-10 text-left"
      >
        <span
          aria-hidden="true"
          className={['h-3.5 w-3.5 shrink-0 rounded-full', folderSwatchClass(folder.color)].join(' ')}
        />
        <span className="line-clamp-2 text-[13.5px] font-semibold break-words text-text">
          {folder.name}
        </span>
        <span className="text-xs text-text2">
          {t('documents.folderGrid.documentCount', { count })}
        </span>
      </button>

      <div className="absolute right-2 top-2 flex gap-0.5">
        <button
          type="button"
          aria-label={t('documents.folderGrid.editAria', { name: folder.name })}
          onClick={(event) => {
            event.stopPropagation()
            onEdit(folder)
          }}
          className="rounded-lg p-1 text-text2 hover:bg-accent/10 hover:text-accent"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
        </button>
        <button
          ref={deleteButtonRef}
          type="button"
          aria-label={t('documents.folderGrid.deleteFolderAria', { name: folder.name })}
          aria-expanded={isConfirming}
          onClick={openConfirm}
          className="rounded-lg p-1 text-text2 hover:bg-danger/10 hover:text-danger"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
            <path d="M3 6h18" />
            <path d="M8 6V4h8v2" />
            <path d="M6 6l1 14h10l1-14" />
          </svg>
        </button>
      </div>
    </div>
  )
}

function FixedTile({ label, count, isActive, onSelect }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      aria-pressed={isActive}
      aria-label={t('documents.folderGrid.tileAria', { name: label, count })}
      onClick={onSelect}
      className={[
        'card-lift flex flex-col items-start gap-1.5 rounded-xl border p-3.5 text-left',
        isActive ? 'border-accent bg-surface2' : 'border-border bg-card-bg',
      ].join(' ')}
    >
      <span className="text-[13.5px] font-semibold text-text">{label}</span>
      <span className="text-xs text-text2">
        {t('documents.folderGrid.documentCount', { count })}
      </span>
    </button>
  )
}

// Folder tile grid sitting above the document grid (folder-grouping
// feature). Selecting a tile filters `DocumentsPage.jsx`'s grid
// client-side over the already-fetched `documents` list -- no server
// round trip, matching the page's existing sort/filter convention. Folder
// membership counts are likewise derived client-side here, from
// `documents`, not from a separate endpoint.
//
// `onDocumentFolderChanged(documentId, folderId)` (Round 2) is the same
// callback shape `DocumentCard.jsx` reports its own assignment changes
// through -- `DocumentsPage.jsx` wires both to the identical handler, so
// a folder-tile drop and a card-menu move both update the one
// `documents` array the same way.
export default function FolderGrid({
  folders,
  documents,
  activeFilter,
  onSelectFilter,
  onFolderCreated,
  onFolderUpdated,
  onFolderDeleted,
  onDocumentFolderChanged,
}) {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const [modalState, setModalState] = useState(null) // null | 'create' | <folder>
  const [dropError, setDropError] = useState(null)

  const { allCount, ungroupedCount, countsByFolderId } = useMemo(() => {
    const counts = new Map()
    let ungrouped = 0
    for (const doc of documents) {
      if (doc.folder_id) {
        counts.set(doc.folder_id, (counts.get(doc.folder_id) ?? 0) + 1)
      } else {
        ungrouped += 1
      }
    }
    return { allCount: documents.length, ungroupedCount: ungrouped, countsByFolderId: counts }
  }, [documents])

  function handleFolderDeleted(folderId) {
    onFolderDeleted(folderId)
    // The tile just disappeared -- if it was the active filter, fall back
    // to "All documents" rather than leaving the grid filtered on a folder
    // that no longer exists.
    if (activeFilter === folderId) {
      onSelectFilter(ALL_DOCUMENTS_FILTER)
    }
  }

  // Round 2: "drag doc onto a folder tile" -- assigns the dragged document
  // to `folderId` directly, no dialog (the spec's I/O matrix). Dropping a
  // document onto the folder it's already in is a harmless no-op PATCH,
  // not specially guarded against.
  async function handleDropDocument(documentId, folderId) {
    setDropError(null)
    try {
      await updateDocumentFolder(authFetch, documentId, folderId)
      onDocumentFolderChanged(documentId, folderId)
    } catch (err) {
      setDropError(err.message)
    }
  }

  return (
    <div className="mb-5">
      {dropError && (
        <p role="alert" className="mb-2 text-xs text-danger">
          {dropError}
        </p>
      )}
      <ul
        aria-label={t('documents.foldersHeading')}
        className="grid list-none grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-3 p-0"
      >
        <li>
          <FixedTile
            label={t('documents.folderGrid.allDocuments')}
            count={allCount}
            isActive={activeFilter === ALL_DOCUMENTS_FILTER}
            onSelect={() => onSelectFilter(ALL_DOCUMENTS_FILTER)}
          />
        </li>
        <li>
          <FixedTile
            label={t('documents.folderMenu.ungrouped')}
            count={ungroupedCount}
            isActive={activeFilter === UNGROUPED_FILTER}
            onSelect={() => onSelectFilter(UNGROUPED_FILTER)}
          />
        </li>
        {folders.map((folder) => (
          <li key={folder.id}>
            <FolderTile
              folder={folder}
              count={countsByFolderId.get(folder.id) ?? 0}
              isActive={activeFilter === folder.id}
              onSelect={onSelectFilter}
              onEdit={(target) => setModalState(target)}
              onDeleted={handleFolderDeleted}
              onDropDocument={handleDropDocument}
            />
          </li>
        ))}
        <li>
          <button
            type="button"
            onClick={() => setModalState('create')}
            className="flex h-full min-h-[4.75rem] w-full flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-border p-3.5 text-text2 hover:border-accent hover:text-accent"
          >
            <span aria-hidden="true" className="text-lg leading-none">+</span>
            <span className="text-xs font-semibold">{t('documents.folderGrid.newFolder')}</span>
          </button>
        </li>
      </ul>

      {modalState && (
        <FolderModal
          folder={modalState === 'create' ? null : modalState}
          onClose={() => setModalState(null)}
          onSaved={(saved) => {
            if (modalState === 'create') {
              onFolderCreated(saved)
            } else {
              onFolderUpdated(saved)
            }
          }}
        />
      )}
    </div>
  )
}
