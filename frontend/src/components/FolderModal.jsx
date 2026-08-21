import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { createFolder, updateFolder } from '../api/foldersClient'
import { FOLDER_COLORS, folderSwatchClass } from '../utils/folderFormat'

const HEADING_ID = 'folder-modal-heading'

// Same diagonal-hatched dimmed backdrop as UploadModal.jsx (DESIGN.md's
// Modal spec) -- duplicated rather than imported, mirroring how
// UploadModal itself keeps this as an unexported module-level constant.
const BACKDROP_STYLE = {
  backgroundColor: 'rgba(10, 20, 40, 0.5)',
  backgroundImage:
    'repeating-linear-gradient(45deg, rgba(255,255,255,0.06) 0px, rgba(255,255,255,0.06) 1px, transparent 1px, transparent 10px)',
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Single dialog reused for both create and edit (the spec's Code Map),
// built on UploadModal.jsx's dialog shape: backdrop, focus trap,
// escape-to-close, focus capture/return, aria-labelledby heading id.
// `folder` is `null` for create, or the existing `{id, name, color}` for
// edit. On success, calls `onSaved(folder)` with the server's response
// (the caller updates its own folders list) and then `onClose()`.
export default function FolderModal({ folder, onClose, onSaved }) {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const isEditing = folder != null
  const [name, setName] = useState(folder?.name ?? '')
  const [color, setColor] = useState(folder?.color ?? FOLDER_COLORS[0])
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState(null)

  const dialogRef = useRef(null)
  const nameInputRef = useRef(null)
  const previouslyFocusedRef = useRef(null)

  // Initial focus + return focus (UX-DR25), same as UploadModal.
  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement
    nameInputRef.current?.focus()
    return () => {
      if (previouslyFocusedRef.current instanceof HTMLElement) {
        previouslyFocusedRef.current.focus()
      }
    }
  }, [])

  // Focus trap + Escape-to-cancel, same as UploadModal.
  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const node = dialogRef.current
      if (!node) return
      const focusable = Array.from(node.querySelectorAll(FOCUSABLE_SELECTOR))
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    return () => document.removeEventListener('keydown', handleKeyDown, true)
  }, [onClose])

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const saved = isEditing
        ? await updateFolder(authFetch, folder.id, { name, color })
        : await createFolder(authFetch, { name, color })
      onSaved(saved)
      onClose()
    } catch (err) {
      // On failure: error shown inline, dialog stays open for retry --
      // mirrors DocumentCard's delete-confirm error handling.
      setError(err.message)
      setIsSaving(false)
    }
  }

  const trimmedName = name.trim()

  return (
    // stopPropagation here (Round 2): `DocumentCard.jsx` now portals this
    // dialog to `document.body` for its drag/menu-created-folder flow --
    // React still bubbles a portalled element's synthetic events through
    // the *component* tree, not the DOM tree, so without this a click
    // landing on the backdrop or any non-button/link area (the heading,
    // labels, the name input) would bubble past this component and reach
    // `DocumentCard`'s own card-click-navigates handler. Harmless for
    // `FolderGrid.jsx`'s own (non-portalled) usage, which has no ancestor
    // click handler to guard against.
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={BACKDROP_STYLE}
      onClick={(event) => event.stopPropagation()}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={HEADING_ID}
        className="anim-rise flex w-full max-w-[420px] flex-col rounded-2xl border border-border bg-card-bg shadow-modal"
      >
        <div className="border-b border-border px-6 py-4">
          <h2 id={HEADING_ID} className="text-lg font-bold text-text">
            {isEditing ? t('documents.folderGrid.editFolder') : t('documents.folderGrid.newFolder')}
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="folder-name" className="text-xs font-semibold text-text2">
              {t('documents.folderGrid.nameLabel')}
            </label>
            <input
              ref={nameInputRef}
              id="folder-name"
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={255}
              className="rounded-lg border border-border bg-input-bg px-3 py-2 text-sm text-text"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span id="folder-color-label" className="text-xs font-semibold text-text2">
              {t('documents.folderGrid.colorLabel')}
            </span>
            {/* One-row swatch picker (Design Notes) -- native radio
                semantics via role="radio" rather than a new picker
                primitive, since this is the one and only place a folder
                color is chosen. */}
            <div role="radiogroup" aria-labelledby="folder-color-label" className="flex flex-wrap gap-2.5">
              {FOLDER_COLORS.map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={color === option}
                  aria-label={option}
                  onClick={() => setColor(option)}
                  className={[
                    'h-8 w-8 rounded-full border-2',
                    folderSwatchClass(option),
                    color === option ? 'border-primary' : 'border-transparent',
                  ].join(' ')}
                />
              ))}
            </div>
          </div>

          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSaving}
              className="rounded-full border border-border bg-surface2 px-5 py-2.5 text-sm font-semibold text-primary"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={isSaving || trimmedName.length === 0}
              className="btn-brand rounded-full px-5 py-2.5 text-sm font-semibold"
            >
              {isSaving ? t('documents.folderGrid.saving') : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
