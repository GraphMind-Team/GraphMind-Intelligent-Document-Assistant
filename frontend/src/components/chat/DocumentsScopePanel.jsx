import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listDocuments } from '../../api/documentsClient'
import { useChatScope } from '../../context/ChatScopeContext'
import StatusPill from '../StatusPill'

// Documents-in-scope panel (Story 3.1 built the static shell; Story 3.3
// adds the interactivity FR-11 needs): per-document checkboxes, a
// "Select all" for every Ready document, and a client-side filter over
// this panel's own list only (OD-5 -- never a library-wide search).
// Selected ids live in ChatScopeContext, shared with ChatPage's submit
// handler.
export default function DocumentsScopePanel({ authFetch, onDocumentsLoaded }) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState(null)
  const [filterText, setFilterText] = useState('')
  const { selectedDocumentIds, toggleDocument, selectAll, retainOnly } = useChatScope()

  useEffect(() => {
    let cancelled = false
    listDocuments(authFetch)
      .then((data) => {
        if (cancelled) return
        setDocuments(data)
        // Safety net, not a fix for a live bug today -- see
        // ChatScopeContext.jsx's retainOnly comment. A no-op on this
        // first load since the selection starts empty.
        retainOnly(data.filter((doc) => doc.status === 'Ready').map((doc) => doc.id))
        // ChatPage's empty-thread welcome placeholder (document count) and
        // its preset-scope handoff from DocumentDetailPage (needs each
        // document's own `status`) both read off this -- this panel
        // already owns the fetch, so it reports the full list up rather
        // than ChatPage duplicating the request.
        onDocumentsLoaded?.(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch, retainOnly, onDocumentsLoaded])

  const readyDocumentIds = useMemo(
    () => documents.filter((doc) => doc.status === 'Ready').map((doc) => doc.id),
    [documents],
  )

  const visibleDocuments = useMemo(() => {
    const needle = filterText.trim().toLowerCase()
    if (!needle) return documents
    return documents.filter((doc) => doc.filename.toLowerCase().includes(needle))
  }, [documents, filterText])

  return (
    // Full width below 900px (the same breakpoint ChatPage.jsx collapses
    // the grid to a single column at) -- a fixed 260px here regardless of
    // breakpoint would leave the panel as a narrow left-aligned block
    // under the chat column instead of spanning the stacked layout's
    // full width.
    <aside className="flex w-full shrink-0 flex-col self-start rounded-2xl border border-border bg-card-bg p-5 shadow-card min-[901px]:w-[260px]">
      <h2 className="mb-2.5 text-[13px] font-bold text-primary">{t('chat.scopePanel.title')}</h2>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {!error && documents.length === 0 && <p className="text-xs text-text2">{t('chat.scopePanel.noDocuments')}</p>}

      {documents.length > 0 && (
        <>
          {/* OD-6: an all-unchecked panel must read as "asking across
              everything," not "nothing selected" -- FR-11's default. */}
          <p className="mb-2 text-[11px] text-text2">
            {selectedDocumentIds.length === 0
              ? t('chat.scopePanel.askingAcrossAll', { count: documents.length })
              : t('chat.scopePanel.selected', { selected: selectedDocumentIds.length, total: documents.length })}
          </p>

          <div className="mb-2 flex items-center gap-2">
            <label htmlFor="scope-filter" className="sr-only">
              {t('chat.scopePanel.filterLabel')}
            </label>
            <input
              id="scope-filter"
              type="text"
              value={filterText}
              onChange={(event) => setFilterText(event.target.value)}
              placeholder={t('chat.scopePanel.filterPlaceholder')}
              className="min-w-0 flex-1 rounded-full border border-border px-3.5 py-2 text-[12px]"
            />
            <button
              type="button"
              // Always the full list's Ready ids, not the filtered view's --
              // UX-DR10's "every Ready document" is unqualified by the
              // filter.
              onClick={() => selectAll(readyDocumentIds)}
              className="shrink-0 whitespace-nowrap text-[12px] font-semibold text-accent"
            >
              {t('chat.scopePanel.selectAll')}
            </button>
          </div>
        </>
      )}

      <ul className="max-h-[216px] list-none space-y-1.5 overflow-y-auto p-0">
        {visibleDocuments.map((doc) => {
          const isReady = doc.status === 'Ready'
          const inputId = `scope-doc-${doc.id}`
          return (
            <li
              key={doc.id}
              className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3 py-2.5 text-[12.5px]"
            >
              {isReady ? (
                <label htmlFor={inputId} className="flex min-w-0 flex-1 items-center gap-2">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={selectedDocumentIds.includes(doc.id)}
                    onChange={() => toggleDocument(doc.id)}
                    className="shrink-0 cursor-pointer"
                  />
                  <span className="min-w-0 flex-1 truncate">{doc.filename}</span>
                </label>
              ) : (
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <input
                    id={inputId}
                    type="checkbox"
                    // Controlled, same as the enabled branch, even though a
                    // non-Ready id can never actually be in
                    // selectedDocumentIds (retainOnly prunes to Ready ids
                    // only) -- always false in practice, but an explicit
                    // `checked` means this can't render as checked no
                    // matter what dispatches an event at it, rather than
                    // relying solely on `disabled` to block that.
                    checked={selectedDocumentIds.includes(doc.id)}
                    onChange={() => {}}
                    disabled
                    // UX-DR27: the disabled reason must be exposed
                    // programmatically, not left as sighted-only inline
                    // text -- StatusPill next to it already covers "status
                    // noted inline" as real DOM text. The status itself is
                    // translated the same way StatusPill renders it (not
                    // the raw backend value) -- a screen-reader user
                    // hearing "not available yet (Extracting)" while
                    // StatusPill visibly says "Reading document" would be
                    // hearing pipeline jargon a sighted user never sees.
                    aria-label={t('chat.scopePanel.notAvailableYet', {
                      filename: doc.filename,
                      status: t(`documents.status.${doc.status}`, { defaultValue: doc.status }),
                    })}
                    className="shrink-0"
                  />
                  <span className="min-w-0 flex-1 truncate">{doc.filename}</span>
                </div>
              )}
              <StatusPill status={doc.status} />
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
