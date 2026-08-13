import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getDocument } from '../api/documentsClient'
import StatusPill from '../components/StatusPill'
import { formatFileSize, formatFileType, formatUploadedDate } from '../utils/documentFormat'

// Document Detail (Story 2.2), rendered at `/documents/:documentId`.
//
// A nested *route*, not in-page state on DocumentsPage: that's what makes
// the back button, deep links, and the logged-out-deep-link flow work with
// no code of their own -- ProtectedRoute already stashes `location.state
// .from` and LoginPage already redirects back to it (Story 1.5).
//
// Everything rendered here is document-derived text (`filename` is
// attacker-controlled, and `.md`/`.html` are ingestible formats) and is
// therefore emitted as plain React text children only. No
// `dangerouslySetInnerHTML`, no Markdown/HTML renderer -- a standing
// constraint in `deferred-work.md`, not a preference.
//
// There is deliberately no `Ready`-state branch yet. Chapter count,
// passages-indexed, and the chapter list all come from Story 2.3's
// parsing; no document can reach `Ready` today and no column holds those
// values, so 2.3 adds the columns and the Ready branch together against a
// real shape rather than dormant code against a guessed one.
const PENDING = 'Pending'

function MetaItem({ label, value }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2.5">
      <dt className="text-eyebrow uppercase text-text2">{label}</dt>
      <dd className="mt-0.5 text-sm text-text">{value}</dd>
    </div>
  )
}

export default function DocumentDetailPage() {
  const { documentId } = useParams()
  const { authFetch } = useAuth()
  const [doc, setDoc] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)
    setDoc(null)

    getDocument(authFetch, documentId)
      .then((data) => {
        if (!cancelled) setDoc(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [authFetch, documentId])

  return (
    <div className="mx-auto max-w-[640px]">
      <Link to="/documents" className="mb-4 inline-block text-sm text-link hover:underline">
        Back to documents
      </Link>

      {isLoading && <p className="text-sm text-text2">Loading document...</p>}

      {/* A document that belongs to another account returns the same 404
          -- and therefore the same message -- as one that doesn't exist.
          This view has no way to tell them apart, by design. */}
      {!isLoading && error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {!isLoading && !error && doc && (
        <div className="rounded-xl border border-border bg-card-bg p-[26px]">
          <h1 className="text-[18px] font-bold text-primary">{doc.filename}</h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[13px] text-text2">
            <span>Uploaded {formatUploadedDate(doc.created_at)}</span>
            <StatusPill status={doc.status} />
          </p>

          <dl className="my-[18px] grid grid-cols-2 gap-3.5">
            <MetaItem label="Uploaded" value={formatUploadedDate(doc.created_at)} />
            <MetaItem
              label="File type"
              value={`${formatFileType(doc.file_type)} · ${formatFileSize(doc.file_size_bytes)}`}
            />
            {/* Explicitly "Pending", never a fabricated 0 (UX-DR8): a 0
                here would read as "this document has no chapters", which
                is a different and false claim from "nothing has parsed it
                yet". */}
            <MetaItem label="Chapters" value={PENDING} />
            <MetaItem label="Passages indexed" value={PENDING} />
          </dl>

          <section>
            <h2 className="text-eyebrow uppercase text-text2">Chapter breakdown</h2>
            <p className="mt-2 text-sm text-text2">
              Pending — the chapter breakdown appears once this document has been parsed and
              indexed.
            </p>
          </section>
        </div>
      )}
    </div>
  )
}
