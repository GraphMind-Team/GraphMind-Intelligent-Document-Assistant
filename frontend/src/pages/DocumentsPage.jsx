import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { ALLOWED_EXTENSIONS, listDocuments } from '../api/documentsClient'
import { listFolders } from '../api/foldersClient'
import DocumentCard from '../components/DocumentCard'
import FolderGrid, { ALL_DOCUMENTS_FILTER, UNGROUPED_FILTER } from '../components/FolderGrid'
import { DOCUMENT_STATUSES } from '../components/StatusPill'
import UploadModal from '../components/UploadModal'
import { RobotFigure } from '../components/chat/RobotMascot'
import Icon from '../components/Icon'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'

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
  { value: 'recent', key: 'recent' },
  { value: 'title', key: 'title' },
  { value: 'status', key: 'status' },
]

const TYPE_FILTER_OPTIONS = [
  { value: 'all', key: 'all' },
  { value: 'pdf', key: 'pdf' },
  { value: 'markdown', key: 'markdown' },
  { value: 'html', key: 'html' },
  { value: 'docx', key: 'docx' },
  { value: 'pptx', key: 'pptx' },
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
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [documents, setDocuments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const isSlow = useSlowRequestHint(isLoading)
  const [sortBy, setSortBy] = useState('recent')
  const [typeFilter, setTypeFilter] = useState('all')
  // Client-side, same as sortBy/typeFilter -- there's no server-side
  // search param to reach for here any more than there is a sort one
  // (this file's own top-of-file note on that still applies). Matters
  // once a library grows past a screenful: sort and type-filter alone
  // don't help find one specific file by name.
  const [searchText, setSearchText] = useState('')
  const uploadButtonRef = useRef(null)

  // Folder-grouping feature: `folders` is fetched once (no polling -- only
  // ingestion status needs that), and `folderFilter` is either
  // ALL_DOCUMENTS_FILTER, UNGROUPED_FILTER, or a real folder's own id.
  // Client-side over `documents`, same as sortBy/typeFilter above.
  const [folders, setFolders] = useState([])
  const [folderFilter, setFolderFilter] = useState(ALL_DOCUMENTS_FILTER)
  // Its own error state, separate from the document list's `error` above
  // -- a folder-fetch failure must not also blank out the document grid
  // (`showGrid`/`showEmptyLibrary`/`showFilteredEmpty` all key off `error`
  // already meaning "the document list itself failed"). Rendered with the
  // same `role="alert"` banner convention this file already uses for
  // `error`, just its own paragraph, so the failure is visible rather than
  // silently indistinguishable from "you have zero folders".
  const [folderError, setFolderError] = useState(null)

  // The folders panel (folder-grouping feature): a persistent right-hand
  // panel, not a dropdown -- toggled open/closed by its own "Folders"
  // button, and otherwise only closed by an outside click. Selecting a
  // tile inside it does *not* close it, unlike DocumentCard.jsx's own "⋮"
  // menu -- the panel is meant to stay put so a document can be dragged
  // into it repeatedly.
  //
  // Listens on `click`, not `mousedown`: a native drag gesture starts with
  // a `mousedown` on its source card (which sits outside this panel), and
  // a `mousedown` listener would close the panel the instant that drag
  // began -- before the drop ever reached a folder tile, defeating the
  // whole "drag a document into the open panel" point of keeping it open.
  // A `click` never fires for that same gesture (the browser suppresses it
  // once the pointer has moved), so dragging in from outside the panel is
  // unaffected; only an actual click elsewhere closes it.
  //
  // A click inside `[role="dialog"]` is also excluded: FolderModal (opened
  // from this panel's own "+ New folder"/edit, or from a doc-onto-doc drop
  // that creates one) is portalled to `document.body`, outside this
  // panel's own DOM subtree, so without this its own Save/Cancel buttons
  // would otherwise read as an outside click and close the panel out from
  // under the dialog that's still open on top of it.
  const [isFoldersOpen, setIsFoldersOpen] = useState(false)
  const foldersTriggerRef = useRef(null)
  const foldersPanelRef = useRef(null)

  useEffect(() => {
    if (!isFoldersOpen) return undefined

    function handleClick(event) {
      if (foldersPanelRef.current?.contains(event.target)) return
      if (foldersTriggerRef.current?.contains(event.target)) return
      if (event.target.closest('[role="dialog"]')) return
      setIsFoldersOpen(false)
    }

    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [isFoldersOpen])

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

  // Folders are fetched once on mount -- no polling loop, unlike documents:
  // nothing about a folder transitions on its own in the background the
  // way ingestion status does. A failure here is surfaced via its own
  // `folderError` banner (see the state comment above) rather than
  // swallowed -- the document grid still renders normally either way, but
  // the user can now tell "zero folders" apart from "folders failed to
  // load".
  const fetchFolders = useCallback(async () => {
    setFolderError(null)
    try {
      const data = await listFolders(authFetch)
      setFolders(data)
    } catch (err) {
      setFolderError(err.message)
    }
  }, [authFetch])

  useEffect(() => {
    fetchFolders()
  }, [fetchFolders])

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
    let filtered =
      typeFilter === 'all' ? documents : documents.filter((doc) => doc.file_type === typeFilter)

    // Folder-grouping feature: narrows further by the selected folder
    // tile, same client-side derivation as the type filter above -- no
    // separate fetch, no server-side param.
    if (folderFilter === UNGROUPED_FILTER) {
      filtered = filtered.filter((doc) => !doc.folder_id)
    } else if (folderFilter !== ALL_DOCUMENTS_FILTER) {
      filtered = filtered.filter((doc) => doc.folder_id === folderFilter)
    }

    const needle = searchText.trim().toLowerCase()
    if (needle) {
      filtered = filtered.filter((doc) => doc.filename.toLowerCase().includes(needle))
    }

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
  }, [documents, sortBy, typeFilter, folderFilter, searchText])

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
  // Also covers the "⋮" menu button and its menu items (Round 2: they're
  // `<button>`s too, same as trash, so no separate selector is needed for
  // them). Native HTML5 drag-and-drop (also Round 2) dispatches neither a
  // `click` nor bubbles through this guard, so dragging a card needs no
  // entry here either.
  function handleCardClick(event, documentId) {
    if (event.target.closest('a, button')) return
    navigate(`/documents/${documentId}`)
  }

  // Folder-grouping feature: DocumentCard reports a successful assignment
  // change here rather than keeping its own copy of `folder_id` -- this is
  // the single source of truth `visibleDocuments`/`FolderGrid`'s counts
  // are both derived from.
  function handleDocumentFolderChanged(documentId, folderId) {
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === documentId ? { ...doc, folder_id: folderId } : doc)),
    )
  }

  function handleFolderCreated(folder) {
    setFolders((prev) => [...prev, folder])
  }

  function handleFolderUpdated(folder) {
    setFolders((prev) => prev.map((existing) => (existing.id === folder.id ? folder : existing)))
  }

  // Deleting a folder never deletes its documents (the spec's Boundaries)
  // -- the backend's `ON DELETE SET NULL` already unfiled them server-side,
  // so the local `documents` copy of `folder_id` is updated here too,
  // otherwise it would keep pointing at a folder id that no longer exists
  // until the next full refetch.
  function handleFolderDeleted(folderId) {
    setFolders((prev) => prev.filter((folder) => folder.id !== folderId))
    setDocuments((prev) =>
      prev.map((doc) => (doc.folder_id === folderId ? { ...doc, folder_id: null } : doc)),
    )
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
      {/* Bounds the page's own width, independent of `<main>`'s -- the top
          nav (Shell.jsx) hands this page the full viewport instead of
          losing a column to a left sidebar, and past roughly this width
          the toolbar/grid below start reading as sprawl rather than making
          good use of the room. Wide enough that laptop/desktop viewports
          (the common case) never hit it -- this only engages on genuinely
          ultrawide monitors. */}
      <div className="mx-auto w-full max-w-[1680px]">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <p className="text-eyebrow uppercase text-accent">{t('documents.eyebrow')}</p>
            <h1 className="text-page-title text-text">{t('documents.title')}</h1>
          </div>
          <button
            ref={uploadButtonRef}
            type="button"
            onClick={handleOpenModal}
            className="btn-brand rounded-full px-5 py-2.5 text-sm font-semibold"
          >
            {t('documents.upload')}
          </button>
        </div>

        {/* Its own banner, separate from the document-list `error` below --
            a folder-fetch failure must stay visible without hiding the
            document grid (which stays functional either way, just with
            zero folder tiles until a retry). */}
        {folderError && (
          <p role="alert" className="mb-4 text-sm text-danger">
            {folderError}
          </p>
        )}

        {/* Toolbar row, raised on its own card -- the new top nav gives
            this page the full viewport width, and a bare row of small pill
            controls spread across that width reads as loose/unfinished
            rather than spacious. The card gives the row a floor: the same
            `--surface2` treatment the empty-library state below already
            uses, so the toolbar reads as one grouped control strip instead
            of a few buttons drifting in open space.

            The "Folders" trigger (folder-grouping feature) sits beside
            Sort/Filter, sized to match -- a plain toggle button, not a
            dropdown. Pressing it mounts a persistent right-hand panel
            (below, next to the document grid) that stays open across tile
            selections; only an outside click or pressing this button again
            closes it (the effect above). Real <select> elements for
            Sort/Filter -- not custom listbox widgets -- so keyboard/
            screen-reader/mobile behavior is the platform's, not something
            re-implemented here. The visible option text carries the
            "Sort:"/"Filter:" prefix exactly as the mockup does, so the
            labels themselves are screen-reader-only rather than
            duplicating that prefix on screen.

            Search used to be a fixed 11rem box shoved to the row's far
            right edge via `ml-auto` -- harmless while this row sat in a
            ~700px sidebar-narrowed column, but at full page width that
            left a few hundred pixels of dead air between Filter and
            Search, reading as a layout bug rather than intentional space.
            It's `flex-1` now (bounded by a max-width so it doesn't balloon
            on an ultrawide monitor) and sits right after Filter in normal
            flow, so it absorbs whatever room the row actually has left
            instead of leaving it empty -- and doubles as the toolbar's
            most prominent control, which "find one document by name"
            deserves once a library grows past a screenful. */}
        <div className="mb-5 flex flex-wrap items-center gap-2.5 rounded-2xl border border-border bg-surface2 px-3.5 py-3">
          <button
            ref={foldersTriggerRef}
            type="button"
            aria-pressed={isFoldersOpen}
            onClick={() => setIsFoldersOpen((open) => !open)}
            className={[
              'w-full rounded-full border px-3.5 py-2 text-[13px] font-medium sm:w-auto sm:shrink-0',
              isFoldersOpen || folderFilter !== ALL_DOCUMENTS_FILTER
                ? 'border-accent text-accent'
                : 'border-border bg-input-bg text-text',
            ].join(' ')}
          >
            {t('documents.foldersHeading')}
          </button>

          <label className="sr-only" htmlFor="documents-sort">
            {t('documents.sort.label')}
          </label>
          <select
            id="documents-sort"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value)}
            className="w-full cursor-pointer rounded-full border border-border bg-input-bg px-3.5 py-2 text-[13px] text-text sm:w-auto sm:shrink-0"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(`documents.sort.${option.key}`)}
              </option>
            ))}
          </select>

          <label className="sr-only" htmlFor="documents-type-filter">
            {t('documents.filter.label')}
          </label>
          <select
            id="documents-type-filter"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="w-full cursor-pointer rounded-full border border-border bg-input-bg px-3.5 py-2 text-[13px] text-text sm:w-auto sm:shrink-0"
          >
            {TYPE_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {t(`documents.filter.${option.key}`)}
              </option>
            ))}
          </select>

          <div className="relative w-full min-w-0 sm:min-w-[180px] sm:max-w-[420px] sm:flex-1">
            <label className="sr-only" htmlFor="documents-search">
              {t('documents.search.label')}
            </label>
            <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text2">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </Icon>
            <input
              id="documents-search"
              type="text"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder={t('documents.search.placeholder')}
              className="w-full rounded-full border border-border bg-input-bg py-2 pl-9 pr-3.5 text-[13px] text-text"
            />
          </div>
        </div>

        {/* The folders panel (when open) sits to the right of the document
            grid as a real layout column, not an overlay -- this is what
            lets a document be dragged into it. The grid's own column
            min-width shrinks while the panel is open (below) so the same
            document count still lands close to its usual columns-per-row
            instead of silently dropping a column to the panel. */}
        <div className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            {/* Mirrors GraphPage.jsx's own error-banner shape (card, not a
                bare paragraph) plus the one thing it had that this didn't:
                a Retry button, so a failed load isn't a dead end that only
                a full page refresh can get past. */}
            {error && (
              <div
                role="alert"
                className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-5 py-4"
              >
                <p className="text-sm text-danger">{error}</p>
                <button
                  type="button"
                  onClick={() => fetchDocuments()}
                  className="btn-ghost shrink-0 rounded-full px-4 py-1.5 text-xs font-semibold"
                >
                  {t('common.retry')}
                </button>
              </div>
            )}

            {!error && isLoading && (
              <p className="text-sm text-text2">
                {t('documents.loading')}
                {isSlow && <span className="block text-xs">{t('common.slowServerHint')}</span>}
              </p>
            )}

            {/* A real front door for a brand-new account, not one gray
                sentence -- this is the first thing a just-registered user
                sees, and the old text-only state gave them nothing to do
                next. Reuses the mascot (already the app's own identity
                element, per LandingPage.jsx) and the upload button's own
                `handleOpenModal`, so "Upload a document" here opens the
                exact same modal as the toolbar's button above. */}
            {showEmptyLibrary && (
              <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border bg-surface2 px-6 py-16 text-center">
                <RobotFigure state="idle" className="w-20" />
                <div className="max-w-[46ch]">
                  <h2 className="font-display text-[18px] font-bold text-text">
                    {t('documents.emptyState.title')}
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-text2">{t('documents.emptyState.body')}</p>
                </div>
                <button
                  type="button"
                  onClick={handleOpenModal}
                  className="btn-brand rounded-full px-6 py-3 text-sm font-semibold"
                >
                  {t('documents.emptyState.cta')}
                </button>
                <p className="text-xs text-text2">
                  {t('documents.uploadModal.supported', { extensions: ALLOWED_EXTENSIONS.join(', ') })}
                </p>
              </div>
            )}

            {showFilteredEmpty && <p className="text-sm text-text2">{t('documents.emptyFiltered')}</p>}

            {/* Card grid rather than the mockup's `.doclist` table -- a
                human-requested design change, recorded in the spec's
                Change Log. A <ul> because this is a list of things, not a
                grid of layout boxes -- screen readers announce the count.

                Fixed breakpoint column counts (not `auto-fill`/`minmax`,
                which sized columns off the grid's own container width):
                opening the folders panel shrinks that container without
                changing the viewport, so a container-width-driven grid
                silently dropped a column and stranded one card alone on
                its own row -- human-reported. Keying off the viewport via
                Tailwind's breakpoints instead means the column count only
                ever changes when the *window* is resized, never when the
                folders panel is toggled. */}
            {showGrid && (
              <ul
                aria-label={t('documents.title')}
                className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              >
                {visibleDocuments.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    document={doc}
                    onCardClick={handleCardClick}
                    onDeleted={handleDeleted}
                    folders={folders}
                    onFolderChanged={handleDocumentFolderChanged}
                    onFolderCreated={handleFolderCreated}
                  />
                ))}
              </ul>
            )}
          </div>

          {isFoldersOpen && (
            <div ref={foldersPanelRef}>
              <FolderGrid
                folders={folders}
                documents={documents}
                activeFilter={folderFilter}
                onSelectFilter={setFolderFilter}
                onFolderCreated={handleFolderCreated}
                onFolderUpdated={handleFolderUpdated}
                onFolderDeleted={handleFolderDeleted}
                onDocumentFolderChanged={handleDocumentFolderChanged}
              />
            </div>
          )}
        </div>
      </div>

      {isModalOpen && <UploadModal onClose={handleCloseModal} />}
    </>
  )
}
