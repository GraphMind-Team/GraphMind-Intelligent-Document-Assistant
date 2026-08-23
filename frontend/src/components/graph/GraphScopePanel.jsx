import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listDocuments } from '../../api/documentsClient'
import { listFolders } from '../../api/foldersClient'

// "Choose document" scope panel for Graph Preview: per-document checkboxes
// grouped by folder, a global "Select all," and a per-folder select-all --
// structurally a port of `chat/DocumentsScopePanel.jsx`, adapted for
// folder grouping (`FolderGrid.jsx`'s own derivation) since graph scope
// needs "Folders" as an explicit grouping, not a flat list.
//
// Unlike chat scope, there's no Ready-only gate here -- a not-yet-Ready
// document just contributes zero entities today (a self-explanatory empty
// state), not something worth disabling a checkbox over.
//
// Selection state (`selectedDocumentIds` + the three callbacks) is owned
// by `GraphPage.jsx`, not a Context -- graph scope has exactly one
// consumer, unlike chat scope's two (`DocumentsScopePanel` and
// `ChatPage`'s submit handler), so a dedicated Context would be pure
// ceremony.
//
// A column beside the canvas, not a floating overlay -- GraphPage.jsx
// renders this open by default so choosing documents doesn't require
// opening anything first, and collapses it to a small rail button (its own
// component, GraphPage-owned) on request via `onCollapse`. Sticky on wide
// viewports so it stays in view while the canvas/explorer scroll past it.
export default function GraphScopePanel({ authFetch, selectedDocumentIds, onToggleDocument, onSelectAll, onToggleFolder, onCollapse }) {
  const { t } = useTranslation()
  const [documents, setDocuments] = useState([])
  const [folders, setFolders] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let ignore = false
    Promise.all([listDocuments(authFetch), listFolders(authFetch)])
      .then(([documentsData, foldersData]) => {
        if (ignore) return
        setDocuments(documentsData)
        setFolders(foldersData)
      })
      .catch((err) => {
        if (!ignore) setError(err.message)
      })
    return () => {
      ignore = true
    }
  }, [authFetch])

  // Folders with at least one document, in "Ungrouped" last -- same
  // derivation FolderGrid.jsx already does for its own counts, just
  // grouping the documents themselves rather than counting them.
  const groups = useMemo(() => {
    const byFolderId = new Map()
    const ungrouped = []
    for (const doc of documents) {
      if (doc.folder_id) {
        if (!byFolderId.has(doc.folder_id)) byFolderId.set(doc.folder_id, [])
        byFolderId.get(doc.folder_id).push(doc)
      } else {
        ungrouped.push(doc)
      }
    }
    const result = folders
      .map((folder) => ({ key: folder.id, name: folder.name, documents: byFolderId.get(folder.id) ?? [] }))
      .filter((group) => group.documents.length > 0)
    if (ungrouped.length > 0) {
      result.push({ key: '__ungrouped__', name: t('graph.scopePanel.ungrouped'), documents: ungrouped })
    }
    return result
  }, [documents, folders, t])

  const allDocumentIds = useMemo(() => documents.map((doc) => doc.id), [documents])
  const isAllSelected =
    allDocumentIds.length > 0 && allDocumentIds.every((id) => selectedDocumentIds.includes(id))

  return (
    <aside className="w-full shrink-0 rounded-2xl border border-border bg-card-bg p-5 shadow-card min-[901px]:sticky min-[901px]:top-20 min-[901px]:w-[280px] min-[901px]:self-start">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h2 className="text-[14.5px] font-bold text-primary">{t('graph.scopePanel.title')}</h2>
        <button
          type="button"
          onClick={onCollapse}
          aria-label={t('graph.scopePanel.collapseAria')}
          className="-m-1 shrink-0 rounded-md p-1 text-text2 hover:bg-surface2 hover:text-text"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
            <path d="M6 17l5-5-5-5M13 17l5-5-5-5" />
          </svg>
        </button>
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-danger">
          {error}
        </p>
      )}
      {!error && documents.length === 0 && <p className="text-[13px] text-text2">{t('graph.scopePanel.noDocuments')}</p>}

      {documents.length > 0 && (
        <>
          {/* All-unchecked must read as "showing the graph across every
              document," matching the backend's own empty-selection default
              -- the same OD-6 precedent chat's scope panel already uses. */}
          <p className="mb-2 text-[12.5px] text-text2">
            {selectedDocumentIds.length === 0
              ? t('graph.scopePanel.showingAll', { count: documents.length })
              : t('graph.scopePanel.selected', { selected: selectedDocumentIds.length, total: documents.length })}
          </p>

          {/* A toggle, not a one-way action -- once everything is selected,
              this is also the natural way back to the unfiltered default
              (empty selection), mirroring the per-folder select/clear
              toggle below rather than leaving the global control as a
              dead end once every document is already checked. */}
          <button
            type="button"
            onClick={() => onSelectAll(isAllSelected ? [] : allDocumentIds)}
            className="mb-3 text-[13.5px] font-semibold text-accent"
          >
            {isAllSelected ? t('graph.scopePanel.clearAll') : t('graph.scopePanel.selectAll')}
          </button>

          <div className="space-y-2">
            {groups.map((group) => {
              const groupIds = group.documents.map((doc) => doc.id)
              const isFolderFullySelected = groupIds.every((id) => selectedDocumentIds.includes(id))
              const selectedInGroup = groupIds.filter((id) => selectedDocumentIds.includes(id)).length
              return (
                <div key={group.key} className="flex items-start gap-2">
                  {/* `<details>`/`<summary>`, collapsed by default -- the
                      same disclosure pattern `GraphSummary.jsx` already
                      uses (no JS state, styled via `group-open:`), so a
                      folder's documents aren't all shown at once. The
                      "Select folder" button lives *outside* `<summary>`,
                      as a flex sibling of the whole `<details>` -- a
                      button nested inside `<summary>` would also toggle
                      open/closed on every click, since `<summary>` itself
                      is the disclosure's click target. */}
                  <details className="group min-w-0 flex-1">
                    <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12.5px] font-semibold uppercase tracking-wide text-text2">
                      <span aria-hidden="true" className="shrink-0 transition-transform group-open:rotate-90">
                        ▸
                      </span>
                      <span className="min-w-0 flex-1 truncate">{group.name}</span>
                      <span className="shrink-0 normal-case tracking-normal text-text2/80">
                        {selectedInGroup}/{groupIds.length}
                      </span>
                    </summary>
                    <ul className="mt-1.5 list-none space-y-1.5 p-0">
                      {group.documents.map((doc) => {
                        const inputId = `graph-scope-doc-${doc.id}`
                        return (
                          <li
                            key={doc.id}
                            className="flex items-center gap-2 rounded-xl border border-border bg-surface2 px-3 py-2.5 text-[14px]"
                          >
                            <label htmlFor={inputId} className="flex min-w-0 flex-1 items-center gap-2">
                              <input
                                id={inputId}
                                type="checkbox"
                                checked={selectedDocumentIds.includes(doc.id)}
                                onChange={() => onToggleDocument(doc.id)}
                                className="shrink-0 cursor-pointer"
                              />
                              <span className="min-w-0 flex-1 truncate">{doc.filename}</span>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  </details>
                  <button
                    type="button"
                    onClick={() => onToggleFolder(groupIds, !isFolderFullySelected)}
                    className="mt-[1px] shrink-0 whitespace-nowrap text-[12.5px] font-semibold text-accent"
                  >
                    {isFolderFullySelected ? t('graph.scopePanel.clearFolder') : t('graph.scopePanel.selectFolder')}
                  </button>
                </div>
              )
            })}
          </div>
        </>
      )}
    </aside>
  )
}
