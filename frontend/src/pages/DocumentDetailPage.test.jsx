import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentDetailPage from './DocumentDetailPage'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

const UPLOADED_DOC = {
  id: 'doc-1',
  filename: 'vendor-agreement.pdf',
  file_type: 'pdf',
  file_size_bytes: 3 * 1024 * 1024,
  status: 'Uploaded',
  created_at: '2026-08-10T12:00:00Z',
}

function renderDetail(documentId = 'doc-1') {
  return render(
    <MemoryRouter initialEntries={[`/documents/${documentId}`]}>
      <Routes>
        <Route path="/documents" element={<div>Documents library</div>} />
        <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DocumentDetailPage', () => {
  it('requests the document in the URL and renders its title, status and file info', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const getSpy = vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)

    renderDetail()

    expect(
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 }),
    ).toBeInTheDocument()
    expect(getSpy).toHaveBeenCalledWith(expect.any(Function), 'doc-1')
    expect(screen.getByText('Uploaded', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('PDF · 3.0 MB')).toBeInTheDocument()
  })

  it('renders chapter and passage metadata as Pending, never as 0', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)

    renderDetail()

    expect(await screen.findByText('Chapters')).toBeInTheDocument()
    expect(screen.getByText('Passages indexed')).toBeInTheDocument()

    // Both counts read "Pending" -- a fabricated 0 would falsely claim the
    // document has no chapters/passages rather than that nothing has
    // parsed it yet (UX-DR8).
    const pendingValues = screen.getAllByText('Pending')
    expect(pendingValues).toHaveLength(2)
    expect(screen.queryByText('0')).not.toBeInTheDocument()

    // The chapter list itself is pending too, not an empty list.
    expect(screen.getByText(/chapter breakdown appears once/i)).toBeInTheDocument()
  })

  it('renders real chapter and passage values, not Pending, once the document is Ready', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      status: 'Ready',
      chapter_breakdown: { 'Chapter One': 5, 'Chapter Two': 7, 'Chapter Three': 9 },
    })

    renderDetail()

    expect(await screen.findByText('Chapters')).toBeInTheDocument()
    // 3 chapters, 21 passages total (5 + 7 + 9) -- derived client-side from
    // chapter_breakdown, not separately stored/fetched. Values chosen with
    // no collisions against each other or against the per-chapter counts
    // below, so each `getByText` match is unambiguous.
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('21')).toBeInTheDocument()
    expect(screen.queryByText('Pending')).not.toBeInTheDocument()

    // The chapter breakdown list itself, in the backend's insertion order,
    // each with its own passage count.
    expect(screen.getByText('Chapter One')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('Chapter Two')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('Chapter Three')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
    expect(screen.queryByText(/chapter breakdown appears once/i)).not.toBeInTheDocument()
  })

  it('renders the document title as plain text, never as markup', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const hostileName = '<img src=x onerror="alert(1)">.md'
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      filename: hostileName,
      file_type: 'markdown',
    })

    const { container } = renderDetail()

    expect(await screen.findByRole('heading', { name: hostileName })).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('shows the backend message when the document is not found (or not yours)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockRejectedValue(new Error('Document not found.'))

    renderDetail('someone-elses-id')

    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found.')
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })

  it('renders the failed reason when the document is Failed', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      status: 'Failed',
      failed_reason: 'Could not read this document: unexpected EOF',
    })

    renderDetail()

    expect(await screen.findByText('Reason')).toBeInTheDocument()
    expect(
      screen.getByText('Could not read this document: unexpected EOF'),
    ).toBeInTheDocument()
  })

  it('renders a fallback message when a Failed document has no failed_reason', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      status: 'Failed',
      failed_reason: null,
    })

    renderDetail()

    expect(await screen.findByText('Reason')).toBeInTheDocument()
    expect(screen.getByText('No further details available.')).toBeInTheDocument()
  })

  it('renders no failed-reason block for a non-Failed document', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)

    renderDetail()

    await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
    expect(screen.queryByText('Reason')).not.toBeInTheDocument()
  })

  it('offers a way back to the library', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)

    renderDetail()

    const back = await screen.findByRole('link', { name: /back to documents/i })
    expect(back).toHaveAttribute('href', '/documents')
  })
})
