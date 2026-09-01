import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { listDocuments } from '../api/documentsClient'
import { getGraph } from '../api/graphClient'
import Icon from './Icon'

const POLLABLE_STATUSES = ['Uploaded', 'Extracting', 'Graphing']
const POLL_INTERVAL_MS = 4000

// Mounted once in Shell.jsx -- deliberately session-scoped, not
// page-scoped.
//
// This used to live inside DocumentsPage, tracking each document's
// last-seen status in a ref local to that page. That meant navigating
// away from Documents (to Chat, to a document's own detail page,
// anywhere) before a document finished processing silently dropped the
// watch: DocumentsPage would unmount, its ref would be discarded, and
// coming back later found the document already Ready with no prior
// status on record -- indistinguishable, by the transition check below,
// from "was already Ready before this page ever loaded" (the one case a
// toast must *not* fire for, so a plain reload of an established library
// doesn't flood the user with toasts for documents finished days ago).
// Mounting this in Shell instead means the watch runs for the whole
// authenticated session, independent of whichever page happens to be on
// screen, so a document that finishes while the user is off in Chat
// still gets its toast the moment it turns Ready.
//
// The poll here runs unconditionally, for as long as Shell stays mounted
// -- an earlier version only kept polling while `documents` (as of the
// *last* check) already contained something mid-pipeline, and stopped
// otherwise. That broke the single most common case: log in with nothing
// currently processing, upload a document a minute later -- the interval
// had already torn itself down at mount (nothing was pollable yet) and
// nothing ever restarted it, so the toast could never fire. A session
// isn't a document-detail page the polling budget in DocumentsPage.jsx
// exists to bound (the risk there was a runaway loop on one page the user
// is actively looking at); this just checks in the background the whole
// time the user is signed in, which is the point of it living here.
export default function DocumentReadyToasts() {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [readyToasts, setReadyToasts] = useState([])
  // id -> status as of the last check, so the next one can tell "just
  // turned Ready" apart from "was already Ready" or "never observed in
  // flight". Ref, not state -- read-then-write every check, no render
  // needed in between.
  const previousStatusesRef = useRef(new Map())

  const checkDocuments = useCallback(async () => {
    try {
      const data = await listDocuments(authFetch)
      const previousStatuses = previousStatusesRef.current
      const newlyReady = data.filter((doc) => {
        const previousStatus = previousStatuses.get(doc.id)
        return doc.status === 'Ready' && POLLABLE_STATUSES.includes(previousStatus)
      })
      previousStatusesRef.current = new Map(data.map((doc) => [doc.id, doc.status]))
      if (newlyReady.length > 0) {
        // One `/kg/graph` call per newly-ready document, scoped to just
        // that document's id, so the toast can say how much its own
        // extraction produced -- not the account's running total, which
        // would misreport a document that turned up nothing new. Failure
        // is swallowed the same way the outer `checkDocuments` catch does:
        // the entity count is a bonus on the toast, not something worth
        // blocking or erroring the "it's ready" news over.
        const newToasts = await Promise.all(
          newlyReady.map(async (doc) => {
            let entityCount = null
            try {
              const graph = await getGraph(authFetch, [doc.id])
              entityCount = graph.total_node_count
            } catch {
              // Count stays null -- the toast still renders, just without
              // the "N entities found" line.
            }
            return {
              toastId: `${doc.id}-${Date.now()}`,
              documentId: doc.id,
              filename: doc.filename,
              entityCount,
            }
          }),
        )
        setReadyToasts((prev) => [...prev, ...newToasts])
      }
    } catch {
      // A background watcher, not a page with its own error banner -- a
      // failed check just tries again on the next tick.
    }
  }, [authFetch])

  useEffect(() => {
    checkDocuments()
    const intervalId = setInterval(checkDocuments, POLL_INTERVAL_MS)
    return () => clearInterval(intervalId)
  }, [checkDocuments])

  function dismissReadyToast(toastId) {
    setReadyToasts((prev) => prev.filter((toast) => toast.toastId !== toastId))
  }

  // The CTA both navigates and clears its own toast -- once the user has
  // acted on it, it's done its job; leaving it sitting in the corner of
  // /chat afterward would just be clutter on top of the answer it's now
  // impossible to close needs.
  function openChatForToast(toast) {
    dismissReadyToast(toast.toastId)
    navigate('/chat', { state: { presetDocumentId: toast.documentId } })
  }

  // Mirrors openChatForToast above -- same preset-and-dismiss shape, just
  // pointed at Graph instead of Chat. GraphPage reads this the same way
  // ChatPage reads its own `presetDocumentId`: scope to just this one
  // document, no scope panel had to be opened by hand first.
  function openGraphForToast(toast) {
    dismissReadyToast(toast.toastId)
    navigate('/graph', { state: { presetDocumentId: toast.documentId } })
  }

  if (readyToasts.length === 0) return null

  return (
    // `aria-live="polite"` on the stack (not `role="alert"`) -- this is
    // good news, not an error, so it shouldn't interrupt like one. Fixed
    // bottom-right, stacking upward (`flex-col-reverse`) so the newest
    // toast lands next to the pointer instead of pushing older ones down
    // past it. No auto-dismiss -- a toast stays until the user closes it
    // with the X, on purpose (not everyone is watching the corner of the
    // screen the moment it appears).
    <div
      aria-live="polite"
      className="fixed bottom-24 right-5 z-20 flex w-[min(340px,calc(100vw-2.5rem))] flex-col-reverse gap-3 sm:bottom-5"
    >
      {readyToasts.map((toast) => (
        <div
          key={toast.toastId}
          className="anim-rise flex items-start gap-3 rounded-2xl border border-border bg-card-bg p-4 shadow-modal"
        >
          {/* A small success badge, not just text -- gives the toast an
              identity at a glance (the same brand-gradient treatment the
              logo mark and the mascot use), rather than reading as a
              plain gray notice. */}
          <span
            aria-hidden="true"
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[image:var(--grad-brand)] text-white"
          >
            <Icon className="h-4 w-4" strokeWidth="2.4">
              <path d="M5 13l4 4L19 7" />
            </Icon>
          </span>
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 break-words text-[14.5px] font-semibold leading-snug text-text" title={toast.filename}>
              {t('documents.readyToast.title', { filename: toast.filename })}
            </p>
            {/* `entityCount` is null when its own `/kg/graph` call failed
                (see checkDocuments) -- omit the line entirely rather than
                claiming "0 entities", which would read as a real result
                instead of a fetch that just didn't happen. */}
            {typeof toast.entityCount === 'number' && (
              <p className="mt-0.5 text-[13px] text-text2">
                {t('documents.readyToast.entitiesFound', { count: toast.entityCount })}
              </p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
              <button
                type="button"
                onClick={() => openChatForToast(toast)}
                className="flex items-center gap-1.5 text-[13px] font-semibold text-accent hover:underline"
              >
                <Icon className="h-[15px] w-[15px]">
                  <path d="M20 14a3 3 0 0 1-3 3H8l-4 3V7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3Z" />
                  <path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01" />
                </Icon>
                {t('documents.readyToast.cta')}
              </button>
              <button
                type="button"
                onClick={() => openGraphForToast(toast)}
                className="flex items-center gap-1.5 text-[13px] font-semibold text-accent hover:underline"
              >
                <Icon className="h-[15px] w-[15px]">
                  <circle cx="6" cy="7" r="2.4" />
                  <circle cx="18" cy="9" r="2.4" />
                  <circle cx="11" cy="18" r="2.4" />
                  <path d="M8.2 8.2 15.7 9M7.2 9.2 10 15.7M16.6 11.1 12.6 16.4" />
                </Icon>
                {t('documents.readyToast.viewGraphCta')}
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={() => dismissReadyToast(toast.toastId)}
            aria-label={t('documents.readyToast.dismissAria')}
            className="-m-1 shrink-0 rounded-md p-1 text-text2 hover:bg-surface2 hover:text-text"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  )
}
