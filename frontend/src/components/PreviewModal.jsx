import { useEffect, useRef, useState } from 'react'
import { getDocumentContent } from '../api/documentsClient'
import { useAuth } from '../context/AuthContext'

const HEADING_ID = 'preview-modal-heading'

// Same diagonal-hatched backdrop as UploadModal.jsx, per DESIGN.md's Modal
// spec -- shared visual language across every modal in the app, not
// redefined per component beyond this copy (no shared constants module
// exists yet for it).
const BACKDROP_STYLE = {
  backgroundColor: 'rgba(10, 20, 40, 0.5)',
  backgroundImage:
    'repeating-linear-gradient(45deg, rgba(255,255,255,0.06) 0px, rgba(255,255,255,0.06) 1px, transparent 1px, transparent 10px)',
}

// Diverges from UploadModal.jsx's otherwise-identical copy by including
// `iframe`: this is the only modal whose content lives in one. Without it
// the trap array was a single Close button -- first and last at once, so
// every Tab was preventDefault'd straight back to Close and a keyboard
// user could never reach, let alone scroll, the document being previewed.
// The scroll container carries `tabIndex={0}` for the same reason on the
// markdown path, where there's no iframe to land on, and is picked up here
// by the trailing `[tabindex]` clause.
const FOCUSABLE_SELECTOR =
  'a[href], iframe, button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Preview modal: fetches a document's raw bytes (via authFetch, since a
// plain <iframe src> can't carry the Authorization header the backend
// requires) and renders them per `fileType`. Dialog a11y mirrors
// UploadModal.jsx exactly (focus trap, initial-focus, return-focus,
// Escape-to-close) -- the only new modal since that one, so it follows the
// same established pattern rather than inventing another.
export default function PreviewModal({ documentId, filename, fileType, onClose }) {
  const { authFetch } = useAuth()
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [error, setError] = useState(null)
  const [objectUrl, setObjectUrl] = useState(null)
  const [textContent, setTextContent] = useState(null)
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)
  const previouslyFocusedRef = useRef(null)

  // Fetch once on mount. The created object URL is revoked on unmount (or
  // when a re-fetch would create a new one, which can't happen here since
  // documentId/fileType don't change during this modal's lifetime) -- an
  // un-revoked object URL leaks the blob for the tab's remaining life.
  useEffect(() => {
    let cancelled = false
    let createdUrl = null

    getDocumentContent(authFetch, documentId)
      .then((blob) => {
        if (cancelled) return
        // Markdown is shown as raw text (no renderer -- see
        // DocumentDetailPage.jsx's standing "no Markdown/HTML renderer in
        // the app's own DOM" constraint); PDF and HTML both need a real
        // URL to hand to an iframe.
        if (fileType === 'markdown') {
          // Returned, not fire-and-forget: an unreturned inner promise
          // rejects outside this chain, so a decode failure left `status`
          // on 'loading' forever with nothing rendered and nothing thrown.
          return blob.text().then((text) => {
            if (!cancelled) {
              setTextContent(text)
              setStatus('ready')
            }
          })
        }
        createdUrl = URL.createObjectURL(blob)
        setObjectUrl(createdUrl)
        setStatus('ready')
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message)
          setStatus('error')
        }
      })

    return () => {
      cancelled = true
      if (createdUrl) URL.revokeObjectURL(createdUrl)
    }
  }, [authFetch, documentId, fileType])

  // Initial focus + return focus.
  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement
    closeButtonRef.current?.focus()
    return () => {
      if (previouslyFocusedRef.current instanceof HTMLElement) {
        previouslyFocusedRef.current.focus()
      }
    }
  }, [])

  // Focus trap + Escape-to-close, identical shape to UploadModal.jsx.
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={BACKDROP_STYLE}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={HEADING_ID}
        className="anim-rise flex h-[80vh] w-full max-w-[900px] flex-col rounded-2xl border border-border bg-card-bg shadow-modal"
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-6 py-4">
          <h2 id={HEADING_ID} className="min-w-0 truncate text-lg font-bold text-text">
            {filename}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-full border border-border bg-surface2 px-5 py-2 text-sm font-semibold text-primary"
          >
            Close
          </button>
        </div>

        {/* tabIndex/aria-label: a scrollable region that isn't focusable
            can't be scrolled by keyboard at all. Load-bearing on the
            markdown path in particular, where the text sits directly in
            this container rather than in a focusable iframe. */}
        <div tabIndex={0} aria-label="Document preview" className="flex-1 overflow-auto p-4">
          {status === 'loading' && (
            <p role="status" className="text-sm text-text2">
              Loading preview...
            </p>
          )}

          {status === 'error' && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}

          {status === 'ready' && fileType === 'pdf' && (
            <iframe src={objectUrl} title={filename} className="h-full w-full rounded-md border-0" />
          )}

          {status === 'ready' && fileType === 'markdown' && (
            <pre className="h-full whitespace-pre-wrap break-words text-sm text-text">
              {textContent}
            </pre>
          )}

          {status === 'ready' && fileType === 'html' && (
            // `sandbox` with no `allow-scripts` renders the document's
            // markup/layout but blocks any embedded script from executing
            // -- an isolated, script-disabled render surface, not
            // `dangerouslySetInnerHTML` into the app's own DOM (the
            // constraint DocumentDetailPage.jsx documents is about the
            // latter).
            <iframe
              src={objectUrl}
              sandbox=""
              title={filename}
              className="h-full w-full rounded-md border-0 bg-white"
            />
          )}
        </div>
      </div>
    </div>
  )
}
