import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { listDocuments } from '../api/documentsClient'
import UploadModal from '../components/UploadModal'

// Documents page (Story 2.1): Upload button + minimal table + the upload
// modal. Full list/detail UI (search, filters, row click-through, delete)
// is Story 2.2/2.7's job -- this table only needs to prove a row appears
// post-upload with the right status.
export default function DocumentsPage() {
  const { authFetch } = useAuth()
  const [documents, setDocuments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const uploadButtonRef = useRef(null)

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await listDocuments(authFetch)
      setDocuments(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    fetchDocuments()
  }, [fetchDocuments])

  // Single boolean gate, one <UploadModal/> ever rendered -- structurally
  // no second modal can open on top of it (AC1).
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

  return (
    <>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-bold text-text">Documents</h1>
        <button
          ref={uploadButtonRef}
          type="button"
          onClick={handleOpenModal}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary"
        >
          Upload
        </button>
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-danger">
          {error}
        </p>
      )}

      {!error && isLoading && <p className="text-sm text-text2">Loading documents...</p>}

      {!error && !isLoading && documents.length === 0 && (
        <p className="text-sm text-text2">No documents uploaded yet.</p>
      )}

      {!error && !isLoading && documents.length > 0 && (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="border-b border-border bg-surface px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.04em] text-text2">
                Title
              </th>
              <th className="border-b border-border bg-surface px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.04em] text-text2">
                Type
              </th>
              <th className="border-b border-border bg-surface px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.04em] text-text2">
                Status
              </th>
              <th className="border-b border-border bg-surface px-4 py-3 text-left text-[11px] font-bold uppercase tracking-[0.04em] text-text2">
                Uploaded
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr key={document.id}>
                <td className="border-b border-border px-4 py-3 text-text">{document.filename}</td>
                <td className="border-b border-border px-4 py-3 text-text">{document.file_type}</td>
                <td className="border-b border-border px-4 py-3 text-text">{document.status}</td>
                <td className="border-b border-border px-4 py-3 text-text">
                  {new Date(document.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isModalOpen && <UploadModal onClose={handleCloseModal} />}
    </>
  )
}
