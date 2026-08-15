import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('never promises a Failed document is still being parsed and indexed', async () => {
    // A Failed document's ingestion is terminal, so "Pending" and the
    // "appears once this document has been parsed and indexed" copy would
    // contradict the failure reason rendered directly below them.
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      status: 'Failed',
      chapter_breakdown: null,
      failed_reason: 'Could not read this document: unexpected EOF',
    })

    renderDetail()

    await screen.findByText('Reason')
    expect(screen.queryByText(/appears once this document has been parsed/)).not.toBeInTheDocument()
    expect(screen.queryByText('Pending')).not.toBeInTheDocument()
    expect(screen.getByText('Unavailable — this document failed to process.')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable')).toHaveLength(2) // Chapters, Passages indexed
  })

  it('still shows Pending for a document that is genuinely still in flight', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocument').mockResolvedValue({
      ...UPLOADED_DOC,
      status: 'Graphing',
      chapter_breakdown: null,
    })

    renderDetail()

    await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
    expect(screen.getByText(/appears once this document has been parsed/)).toBeInTheDocument()
    expect(screen.getAllByText('Pending')).toHaveLength(2)
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
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

  describe('delete (Story 2.7)', () => {
    it('shows an inline confirm box on Delete click, without deleting anything yet', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)
      const deleteSpy = vi.spyOn(documentsClient, 'deleteDocument')
      const user = userEvent.setup()

      renderDetail()
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })

      await user.click(screen.getByRole('button', { name: 'Delete' }))

      const box = screen.getByRole('alert')
      expect(box).toHaveTextContent(/Removes its passages/)
      expect(box).toHaveTextContent(/not shared with another document/)
      expect(deleteSpy).not.toHaveBeenCalled()
    })

    it('moves focus to Cancel on open, ties the boundary text via aria-describedby, and Escape returns focus to Delete', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)
      const user = userEvent.setup()

      renderDetail()
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
      const deleteButton = screen.getByRole('button', { name: 'Delete' })

      await user.click(deleteButton)

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      expect(cancelButton).toHaveFocus()

      const boundaryText = screen.getByText(/Removes its passages/)
      const boundaryId = boundaryText.getAttribute('id')
      expect(boundaryId).toBeTruthy()
      expect(cancelButton).toHaveAttribute('aria-describedby', boundaryId)
      // Two buttons render the visible label "Delete" once the box is
      // open (the trigger and the confirm action) -- select the one
      // inside the alert box for this assertion.
      const confirmButton = within(screen.getByRole('alert')).getByRole('button', {
        name: 'Delete',
      })
      expect(confirmButton).toHaveAttribute('aria-describedby', boundaryId)

      await user.keyboard('{Escape}')

      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(deleteButton).toHaveFocus()
    })

    it('Cancel collapses the box the same way Escape does', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)
      const user = userEvent.setup()

      renderDetail()
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
      const deleteButton = screen.getByRole('button', { name: 'Delete' })
      await user.click(deleteButton)

      await user.click(screen.getByRole('button', { name: 'Cancel' }))

      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(deleteButton).toHaveFocus()
    })

    it('navigates back to /documents on a successful delete', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const deleteSpy = vi.spyOn(documentsClient, 'deleteDocument').mockResolvedValue(undefined)
      vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)
      const user = userEvent.setup()

      renderDetail()
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
      await user.click(screen.getByRole('button', { name: 'Delete' }))
      await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(screen.getByText('Documents library')).toBeInTheDocument())
      expect(deleteSpy).toHaveBeenCalledWith(expect.any(Function), 'doc-1')
    })

    it('on failure, shows the error inline and stays on the page for retry', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'getDocument').mockResolvedValue(UPLOADED_DOC)
      vi.spyOn(documentsClient, 'deleteDocument').mockRejectedValue(
        new Error('Document not found.'),
      )
      const user = userEvent.setup()

      renderDetail()
      await screen.findByRole('heading', { name: 'vendor-agreement.pdf', level: 1 })
      await user.click(screen.getByRole('button', { name: 'Delete' }))
      await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

      expect(await screen.findByText('Document not found.')).toBeInTheDocument()
      // Still on Document Detail, confirm box still open for retry.
      expect(
        screen.getByRole('heading', { name: 'vendor-agreement.pdf', level: 1 }),
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })
  })
})
