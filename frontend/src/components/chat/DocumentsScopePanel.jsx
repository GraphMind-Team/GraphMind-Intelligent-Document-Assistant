import { useEffect, useState } from 'react'
import { listDocuments } from '../../api/documentsClient'
import StatusPill from '../StatusPill'

// Documents-in-scope panel (Story 3.1, UX-DR9): a static, read-only list of
// the user's documents (filename + status pill). No checkboxes, no
// "select all", no filter -- that interactivity, and FR-11's all-vs-subset
// retrieval logic, is explicitly Story 3.3's job. Retrieval in this story
// always searches all of the user's documents.
export default function DocumentsScopePanel({ authFetch }) {
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    listDocuments(authFetch)
      .then((data) => {
        if (!cancelled) setDocuments(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch])

  return (
    <aside className="w-[260px] shrink-0 rounded-xl border border-border bg-card-bg p-4">
      <h2 className="mb-2.5 text-[13px] font-bold text-primary">Documents in scope</h2>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {!error && documents.length === 0 && <p className="text-xs text-text2">No documents yet.</p>}
      <ul className="list-none space-y-1.5 p-0">
        {documents.map((doc) => (
          <li
            key={doc.id}
            className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-[12.5px]"
          >
            <span className="min-w-0 flex-1 truncate">{doc.filename}</span>
            <StatusPill status={doc.status} />
          </li>
        ))}
      </ul>
    </aside>
  )
}
