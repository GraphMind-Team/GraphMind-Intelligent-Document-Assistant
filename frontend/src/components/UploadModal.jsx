import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { ALLOWED_EXTENSIONS, uploadDocument, validateFile } from '../api/documentsClient'
import { formatFileSize } from '../utils/documentFormat'

const HEADING_ID = 'upload-modal-heading'

// Diagonal-hatched dimmed backdrop per DESIGN.md's Modal spec ("dimmed
// diagonal-hatched backdrop, not a flat scrim") -- a plain rgba scrim plus
// a repeating 45deg stripe pattern. Same in both themes (it's an overlay
// atop everything, not a themed surface), so this stays a plain style
// object rather than a CSS custom property.
const BACKDROP_STYLE = {
  backgroundColor: 'rgba(10, 20, 40, 0.5)',
  backgroundImage:
    'repeating-linear-gradient(45deg, rgba(255,255,255,0.06) 0px, rgba(255,255,255,0.06) 1px, transparent 1px, transparent 10px)',
}

function isSettled(status) {
  return status === 'success' || status === 'error' || status === 'duplicate'
}

function makeRowId(file) {
  return `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2)}`
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Upload modal (Story 2.1): dialog a11y (trap/labelledby/initial-focus/
// return-focus per UX-DR25), single dropzone accepting both drag-and-drop
// and click-to-browse, independent per-file progress rows via one
// `XMLHttpRequest` per file fired concurrently (not a sequential queue --
// that's what makes "a slow file never blocks the others" literally true).
//
// `onClose` is called both on explicit Cancel and once every queued file
// has resolved (success or error) -- either way the caller (DocumentsPage)
// refetches the documents list. Closing never cancels an in-flight
// `XMLHttpRequest`: this component simply stops rendering, but nothing
// calls `xhr.abort()`.
export default function UploadModal({ onClose }) {
  const { t } = useTranslation()
  const { token } = useAuth()
  const [files, setFiles] = useState([])
  const [isDragActive, setIsDragActive] = useState(false)
  const dialogRef = useRef(null)
  const dropzoneRef = useRef(null)
  const fileInputRef = useRef(null)
  const previouslyFocusedRef = useRef(null)
  const isMountedRef = useRef(true)

  // Tracks whether this component is still mounted, so an upload that
  // outlives the modal skips its state update on the way back.
  //
  // Deliberately NOT an `xhr.abort()`: UX-DR6 requires that closing the
  // modal never cancels an upload already in flight, so the request must
  // be allowed to finish and write its row. Only the React state update
  // is skipped; the request itself is untouched.
  //
  // Worth being honest about the scope: React 18 removed the
  // "state update on an unmounted component" warning and treats such an
  // update as a silent no-op, so on React 19 this guard prevents no bug
  // and silences no warning. It's kept as intent documentation -- the
  // fire-and-forget upload outliving its modal is deliberate, not an
  // oversight -- and to avoid the pointless map over stale rows. The
  // load-bearing protection for UX-DR6 is the test asserting the upload
  // is never aborted, not this ref.
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Initial focus + return focus (UX-DR25). Runs once on mount/unmount.
  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement
    dropzoneRef.current?.focus()
    return () => {
      if (previouslyFocusedRef.current instanceof HTMLElement) {
        previouslyFocusedRef.current.focus()
      }
    }
  }, [])

  // Auto-close once every queued file has resolved (success or error) --
  // per the story's Boundaries -- but only if at least one actually
  // succeeded. Without the success guard, a batch that's 100% rejected by
  // client-side validation (e.g. one bad file dropped alone) would
  // auto-close the instant it's added -- before the user has any chance
  // to read why. An all-rejected batch now waits for explicit Cancel/
  // Escape instead, same as if nothing had been added.
  //
  // `'duplicate'` deliberately does NOT count as a reason to auto-close
  // (Story 2.6, corrected after a real duplicate upload closed the modal
  // before the "Already uploaded" message or its link were ever visible):
  // a duplicate result is exactly the kind of thing this gate exists to
  // protect -- informational, not a "nothing more to do here" signal, so
  // it's treated the same as an error for this purpose even though it's
  // still a *settled* row for the every-row-resolved check above.
  useEffect(() => {
    if (
      files.length > 0 &&
      files.every((row) => isSettled(row.status)) &&
      files.some((row) => row.status === 'success')
    ) {
      onClose()
    }
  }, [files, onClose])

  // Focus trap + Escape-to-cancel. Escape behaves exactly like Cancel:
  // closes without touching any in-flight upload.
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

  // Every state update below can land after the modal is gone (an upload
  // outliving its modal is expected here, per UX-DR6 -- see isMountedRef).
  // Dropping the update rather than applying it to a dead component is the
  // whole point; the upload itself still completes and still writes a row,
  // which the parent picks up on its post-close refetch.
  function updateRowIfMounted(rowId, patch) {
    if (!isMountedRef.current) return
    setFiles((prev) => prev.map((item) => (item.id === rowId ? { ...item, ...patch } : item)))
  }

  function startUpload(row) {
    updateRowIfMounted(row.id, { status: 'uploading', progress: 0 })

    uploadDocument(token, row.file, (progress) => {
      updateRowIfMounted(row.id, { progress })
    })
      .then((body) => {
        // Story 2.6: `uploadDocument`'s 2xx-resolves contract is unchanged
        // (200 for a duplicate already resolves same as 201) -- this is
        // the branch that turns the resolved body's `is_duplicate` flag
        // into its own terminal row status, distinct from a fresh
        // 'success', so the row can render "Already uploaded" and link to
        // the existing document (OD-7) instead of a generic success state.
        if (body?.is_duplicate) {
          updateRowIfMounted(row.id, { status: 'duplicate', progress: 100, documentId: body.id })
        } else {
          updateRowIfMounted(row.id, { status: 'success', progress: 100, documentId: body?.id })
        }
      })
      .catch((err) => {
        updateRowIfMounted(row.id, { status: 'error', error: err.message })
      })
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList)
    if (incoming.length === 0) return

    const rows = incoming.map((file) => {
      const reason = validateFile(file)
      return {
        id: makeRowId(file),
        file,
        name: file.name,
        size: file.size,
        status: reason ? 'error' : 'queued',
        progress: 0,
        error: reason,
      }
    })

    setFiles((prev) => [...prev, ...rows])

    // Every accepted file starts uploading immediately and independently
    // -- no sequential queue, so a slow file never blocks the others.
    rows.filter((row) => row.status === 'queued').forEach((row) => startUpload(row))
  }

  function handleInputChange(event) {
    addFiles(event.target.files)
    event.target.value = ''
  }

  function handleDrop(event) {
    event.preventDefault()
    setIsDragActive(false)
    addFiles(event.dataTransfer.files)
  }

  function handleDragOver(event) {
    event.preventDefault()
    setIsDragActive(true)
  }

  function handleDragLeave(event) {
    event.preventDefault()
    setIsDragActive(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={BACKDROP_STYLE}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={HEADING_ID}
        className="anim-rise flex w-full max-w-[520px] flex-col rounded-2xl border border-border bg-card-bg shadow-modal"
      >
        <div className="border-b border-border px-6 py-4">
          <h2 id={HEADING_ID} className="text-lg font-bold text-text">
            {t('documents.uploadModal.heading')}
          </h2>
        </div>

        <div className="flex flex-col gap-4 px-6 py-5">
          <div
            ref={dropzoneRef}
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                fileInputRef.current?.click()
              }
            }}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className={[
              'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center',
              isDragActive ? 'border-accent bg-surface2' : 'border-border bg-surface',
            ].join(' ')}
          >
            <p className="text-sm text-text2">
              {t('documents.uploadModal.dropzonePrefix')}{' '}
              <span className="font-semibold text-accent">{t('documents.uploadModal.browse')}</span>
            </p>
            <p className="mt-1 text-xs text-text2">
              {t('documents.uploadModal.supported', { extensions: ALLOWED_EXTENSIONS.join(', ') })}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ALLOWED_EXTENSIONS.join(',')}
              onChange={handleInputChange}
              className="sr-only"
              aria-label={t('documents.uploadModal.chooseFiles')}
            />
          </div>

          {files.length > 0 && (
            <ul className="flex flex-col gap-2.5">
              {files.map((row) => (
                <li
                  key={row.id}
                  className="rounded-xl border border-border bg-surface2 px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="min-w-0 flex-1 truncate text-sm text-text">{row.name}</span>
                    <span className="shrink-0 text-xs text-text2">
                      {row.status === 'queued' ? t('documents.uploadModal.queued') : formatFileSize(row.size)}
                    </span>
                  </div>

                  {row.status === 'error' ? (
                    <p role="alert" className="mt-1.5 text-xs text-danger">
                      {row.error}
                    </p>
                  ) : row.status === 'duplicate' ? (
                    // Story 2.6 / OD-7: a content-hash match surfaces the
                    // existing document rather than just saying "skipped"
                    // -- explicit "already uploaded" message, linking to
                    // `/documents/{id}`. `role="status"` (not "alert" --
                    // that's reserved for errors/urgent) so screen readers
                    // get a polite announcement when a row settles here,
                    // mirroring the error branch's live-region treatment.
                    <p role="status" className="mt-1.5 text-xs text-text2">
                      {t('documents.uploadModal.alreadyUploaded')}
                      {row.documentId ? (
                        <>
                          {' -- '}
                          <Link
                            to={`/documents/${row.documentId}`}
                            className="font-semibold text-accent"
                          >
                            {t('documents.uploadModal.viewDocument')}
                          </Link>
                        </>
                      ) : null}
                    </p>
                  ) : (
                    <div
                      role="progressbar"
                      aria-valuenow={row.progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Upload progress for ${row.name}`}
                      className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface2"
                    >
                      <div
                        className={[
                          'h-full rounded-full transition-[width]',
                          row.status === 'success' ? 'bg-success' : 'bg-primary',
                        ].join(' ')}
                        style={{ width: `${row.progress}%` }}
                      />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex justify-end gap-2.5 border-t border-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-border bg-surface2 px-5 py-2.5 text-sm font-semibold text-primary"
          >
            {t('common.cancel')}
          </button>
        </div>
      </div>
    </div>
  )
}
