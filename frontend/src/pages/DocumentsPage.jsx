import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { listDocuments } from '../api/documentsClient'
import DocumentCard from '../components/DocumentCard'
import { DOCUMENT_STATUSES } from '../components/StatusPill'
import UploadModal from '../components/UploadModal'

// Documents library (Story 2.2): a card grid (file-type tile, title,
// status pill, uploaded date, trash icon per card), a toolbar above it,
// and card click-through to `/documents/:documentId`. The grid replaces
// the reference mockup's `.doclist` table at the human's request -- see
// the spec's Change Log; the same five facts are carried per card.
//
// Sort and filter are applied **client-side** over the already-fetched
// list, deliberately: sending a client-chosen sort field to the server is
// the classic path to an `order_by` injection, and there is no server-side
// sort/filter parameter to reach for here precisely because this story
// doesn't add one. Changing either control re-derives the rows from state
// -- it never refetches.
const SORT_OPTIONS = [
  { value: 'recent', label: 'Sort: Most recent' },
  { value: 'title', label: 'Sort: Title A–Z' },
  { value: 'status', label: 'Sort: Status' },
]

const TYPE_FILTER_OPTIONS = [
  { value: 'all', label: 'Filter: All types' },
  { value: 'pdf', label: 'PDF' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
]

function byMostRecent(a, b) {
  return new Date(b.created_at) - new Date(a.created_at)
}

// Position in the FR-4 pipeline vocabulary, so "Sort: Status" groups by
// where a document actually is in ingestion rather than by the alphabet.
// A status outside the vocabulary sorts last instead of first (which is
// what a raw `indexOf` returning -1 would do).
function statusRank(status) {
  const index = DOCUMENT_STATUSES.indexOf(status)
  return index === -1 ? DOCUMENT_STATUSES.length : index
}

// Nothing refetches after mount/modal-close, so every asynchronous status
// transition made by the background ingestion task would otherwise be
// invisible until a manual reload.
//
// Story 2.3 polled `Uploaded` only, deliberately: back then a parsed
// document parked at `Extracting` forever, so polling those statuses would
// have meant every account with any document polling forever. Story 2.4
// completes the pipeline (`Extracting` -> `Graphing` -> `Ready`/`Failed`),
// which retires that reasoning entirely -- polling only `Uploaded` now
// means the grid stops watching a few seconds in and never shows a
// document actually reaching `Ready`. Every non-terminal status is
// pollable; `Ready`/`Failed` are terminal and are what stops the loop.
//
// The attempt budget has to cover the *whole* pipeline, not one
// transition: the key below is the set of pollable document ids, which
// doesn't change as a document moves Uploaded -> Extracting -> Graphing
// (it stays pollable throughout), so the effect never restarts and the
// budget never resets mid-ingestion. Sized against the slow path rather
// than the typical one -- a cold `fastembed` model download (~44s, see
// deferred-work.md) plus the LLM extraction's own 2x30s timeout budget can
// legitimately put a document minutes away from `Ready`, and a budget that
// expired first would strand the UI exactly where this story's payoff
// becomes visible.
const POLLABLE_STATUSES = ['Uploaded', 'Extracting', 'Graphing']
const POLL_INTERVAL_MS = 4000
const MAX_POLL_ATTEMPTS = 45

export default function DocumentsPage() {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [sortBy, setSortBy] = useState('recent')
  const [typeFilter, setTypeFilter] = useState('all')
  const uploadButtonRef = useRef(null)

  // `silent` skips the loading/error UI churn -- used by the polling
  // effect below so a background re-check every few seconds doesn't blank
  // out the already-rendered grid on every tick.
  const fetchDocuments = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) {
        setIsLoading(true)
        setError(null)
      }
      try {
        const data = await listDocuments(authFetch)
        setDocuments(data)
      } catch (err) {
        if (!silent) setError(err.message)
      } finally {
        if (!silent) setIsLoading(false)
      }
    },
    [authFetch],
  )

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // A key identifying *which* documents are currently pollable, not just
  // whether any are -- a plain boolean would mean a document stuck at
  // `Uploaded` forever (e.g. the process restarted between upload and its
  // background task ever running) permanently exhausts MAX_POLL_ATTEMPTS
  // and then never polls again for the rest of the session, silently
  // eating every later upload's polling too, since the effect below only
  // restarts on a *change* to its dependency and "stuck document present"
  // never changes. Keying on the sorted id list instead means a fresh
  // upload landing at `Uploaded` changes the key even while the stuck one
  // remains, so the effect restarts and the budget resets for it.
  const pollableDocumentIdsKey = useMemo(
    () =>
      documents
        .filter((doc) => POLLABLE_STATUSES.includes(doc.status))
        .map((doc) => doc.id)
        .sort()
        .join(','),
    [documents],
  )

  // Gated on the derived key, not `documents` itself -- depending on the
  // array would tear down and rebuild the interval on every single poll
  // tick (each fetch produces a new array reference), degrading a true
  // periodic timer into something closer to a setTimeout chain.
  const pollAttemptsRef = useRef(0)
  useEffect(() => {
    pollAttemptsRef.current = 0
    if (!pollableDocumentIdsKey) return undefined

    const intervalId = setInterval(() => {
      // Checked *before* incrementing/fetching, so exactly
      // MAX_POLL_ATTEMPTS fetches happen -- checking after incrementing
      // would skip the fetch on the very tick the cap exists to still
      // allow (an off-by-one that quietly shrinks the budget by one).
      if (pollAttemptsRef.current >= MAX_POLL_ATTEMPTS) {
        clearInterval(intervalId)
        return
      }
      pollAttemptsRef.current += 1
      fetchDocuments({ silent: true })
    }, POLL_INTERVAL_MS)

    return () => clearInterval(intervalId)
  }, [pollableDocumentIdsKey, fetchDocuments])

  const visibleDocuments = useMemo(() => {
    const filtered =
      typeFilter === 'all' ? documents : documents.filter((doc) => doc.file_type === typeFilter)

    // Copy before sorting -- `documents` is state, and Array#sort mutates.
    const sorted = [...filtered]
    if (sortBy === 'title') {
      sorted.sort((a, b) => a.filename.localeCompare(b.filename))
    } else if (sortBy === 'status') {
      sorted.sort((a, b) => statusRank(a.status) - statusRank(b.status) || byMostRecent(a, b))
    } else {
      sorted.sort(byMostRecent)
    }
    return sorted
  }, [documents, sortBy, typeFilter])

  // Single boolean gate, one <UploadModal/> ever rendered -- structurally
  // no second modal can open on top of it (Story 2.1 AC1).
  function handleOpenModal() {
    setIsModalOpen(true)
  }

  function handleCloseModal() {
    setIsModalOpen(false)
    // Return focus to the Upload button (UX-DR25) also happens inside
    // UploadModal's own unmount cleanup, via the activeElement it
    // captured on open -- this is the trigger it captured.
    fetchDocuments()
  }

  // Card click-through (UX-DR7). The trash icon and the title link are
  // separate hit targets inside the same card, so a click that originated
  // on either is skipped here rather than double-handled: without this
  // guard, activating the trash button (mouse *or* Enter/Space, since
  // button activation dispatches a bubbling click) would navigate, and
  // clicking the title link would push two identical history entries.
  function handleCardClick(event, documentId) {
    if (event.target.closest('a, button')) return
    navigate(`/documents/${documentId}`)
  }

  // Story 2.7: on a successful delete, the row is removed from local
  // state directly -- no refetch -- matching Story 2.2's existing
  // client-side sort/filter-only pattern (`visibleDocuments` above is
  // derived from `documents`, so this alone is enough to drop the card
  // from the grid).
  //
  // Focus restoration (Spec Change Log): the card that unmounts held
  // focus (the confirm box's own Delete button), so without this a
  // keyboard/screen-reader user's focus silently falls back to
  // `document.body` right after the one action in this story that most
  // needed to stay legible. The Upload button is the simplest always-
  // present, stable landing spot -- reuses the existing ref rather than
  // introducing a new ownership path for it.
  function handleDeleted(documentId) {
    setDocuments((prev) => prev.filter((doc) => doc.id !== documentId))
    uploadButtonRef.current?.focus()
  }

  const hasDocuments = documents.length > 0
  const showGrid = !error && !isLoading && visibleDocuments.length > 0
  // Two genuinely different situations, so two different sentences: an
  // account with nothing in it vs. a filter that happens to exclude
  // everything. Same copy for both would tell the user the wrong thing.
  const showEmptyLibrary = !error && !isLoading && !hasDocuments
  const showFilteredEmpty = !error && !isLoading && hasDocuments && visibleDocuments.length === 0

  return (
    <>
      <div className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="text-eyebrow uppercase text-accent">Your library</p>
          <h1 className="text-page-title text-text">Documents</h1>
        </div>
        <button
          ref={uploadButtonRef}
          type="button"
          onClick={handleOpenModal}
          className="btn-brand rounded-full px-5 py-2.5 text-sm font-semibold"
        >
          Upload
        </button>
      </div>

      {/* Real <select> elements with real labels -- not custom listbox
          widgets -- so keyboard/screen-reader/mobile behavior is the
          platform's, not something re-implemented here. The visible
          option text carries the "Sort:"/"Filter:" prefix exactly as the
          mockup does, so the labels themselves are screen-reader-only
          rather than duplicating that prefix on screen. */}
      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <label className="sr-only" htmlFor="documents-sort">
          Sort documents
        </label>
        <select
          id="documents-sort"
          value={sortBy}
          onChange={(event) => setSortBy(event.target.value)}
          className="rounded-full border border-border bg-input-bg px-3.5 py-2 text-[13px] text-text"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <label className="sr-only" htmlFor="documents-type-filter">
          Filter documents by type
        </label>
        <select
          id="documents-type-filter"
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
          className="rounded-full border border-border bg-input-bg px-3.5 py-2 text-[13px] text-text"
        >
          {TYPE_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {error}
        </p>
      )}

      {!error && isLoading && <p className="text-sm text-text2">Loading documents...</p>}

      {showEmptyLibrary && <p className="text-sm text-text2">No documents yet.</p>}

      {showFilteredEmpty && <p className="text-sm text-text2">No documents match this filter.</p>}

      {/* Card grid rather than the mockup's `.doclist` table -- a
          human-requested design change, recorded in the spec's Change Log.
          `auto-fill` + `minmax` reflows by itself as the content area
          narrows (including at 200% zoom), which is also what retires the
          table's clipping problem structurally rather than by patching an
          overflow rule: there is no fixed min-content width to clip.
          A <ul> because this is a list of things, not a grid of layout
          boxes -- screen readers announce the count. */}
      {showGrid && (
        <ul className="grid list-none grid-cols-[repeat(auto-fill,minmax(14rem,1fr))] gap-4 p-0">
          {visibleDocuments.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onCardClick={handleCardClick}
              onDeleted={handleDeleted}
            />
          ))}
        </ul>
      )}

      {isModalOpen && <UploadModal onClose={handleCloseModal} />}
    </>
  )
}
