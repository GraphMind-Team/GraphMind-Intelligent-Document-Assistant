import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentsPage from './DocumentsPage'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../components/UploadModal', () => ({
  default: ({ onClose }) => (
    <div>
      <span>Upload modal open</span>
      <button onClick={onClose}>close modal</button>
    </div>
  ),
}))

afterEach(() => {
  vi.restoreAllMocks()
})

// Stands in for DocumentDetailPage so a navigation is observable without
// pulling that page's own fetching into these tests.
function DetailProbe() {
  const { documentId } = useParams()
  return <div>Detail probe for {documentId}</div>
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<DetailProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

const PDF_DOC = {
  id: 'doc-pdf',
  filename: 'beta-report.pdf',
  file_type: 'pdf',
  file_size_bytes: 2048,
  status: 'Uploaded',
  created_at: '2026-08-12T00:00:00Z',
}

const MD_DOC = {
  id: 'doc-md',
  filename: 'alpha-notes.md',
  file_type: 'markdown',
  file_size_bytes: 512,
  status: 'Ready',
  created_at: '2026-08-01T00:00:00Z',
}

describe('DocumentsPage', () => {
  it('renders type, title, status pill, uploaded date and a trash icon per card', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])

    renderPage()

    // The card grid is a list, so each document is a listitem rather than
    // a table row -- same five facts, different container.
    const card = await screen.findByRole('listitem')
    expect(within(card).getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
    expect(within(card).getByText('PDF')).toBeInTheDocument()
    expect(within(card).getByText('Uploaded')).toBeInTheDocument()
    expect(within(card).getByText(/2026/)).toBeInTheDocument()
    expect(
      within(card).getByRole('button', { name: 'Delete beta-report.pdf' }),
    ).toBeInTheDocument()
  })

  it('shows "No documents yet." with an empty library, and keeps Upload actionable', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    renderPage()

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^upload$/i })).toBeEnabled()
  })

  it('reorders rows client-side on sort, without refetching', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    // Default is most-recent-first, so the newer PDF leads.
    const initialTitles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(initialTitles).toEqual(['beta-report.pdf', 'alpha-notes.md'])

    await user.selectOptions(screen.getByLabelText('Sort documents'), 'title')

    const sortedTitles = screen.getAllByRole('link').map((link) => link.textContent)
    expect(sortedTitles).toEqual(['alpha-notes.md', 'beta-report.pdf'])
    expect(listSpy).toHaveBeenCalledTimes(1)
  })

  it('narrows rows client-side on filter, without refetching', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    await user.selectOptions(screen.getByLabelText('Filter documents by type'), 'pdf')

    expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'alpha-notes.md' })).not.toBeInTheDocument()
    expect(listSpy).toHaveBeenCalledTimes(1)
  })

  it('distinguishes "no match for this filter" from a genuinely empty library', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    await user.selectOptions(screen.getByLabelText('Filter documents by type'), 'html')

    expect(screen.getByText('No documents match this filter.')).toBeInTheDocument()
    expect(screen.queryByText('No documents yet.')).not.toBeInTheDocument()
  })

  it('opens Detail when the card is clicked outside the trash icon', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])
    const user = userEvent.setup()

    renderPage()
    const card = await screen.findByRole('listitem')

    await user.click(card)

    expect(screen.getByText('Detail probe for doc-pdf')).toBeInTheDocument()
  })

  it('opens Detail from the title link too (the keyboard-reachable path)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])
    const user = userEvent.setup()

    renderPage()

    await user.click(await screen.findByRole('link', { name: 'beta-report.pdf' }))

    expect(screen.getByText('Detail probe for doc-pdf')).toBeInTheDocument()
  })

  it('does not navigate when the trash icon is clicked or activated by keyboard', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])
    const user = userEvent.setup()

    renderPage()
    const trash = await screen.findByRole('button', { name: 'Delete beta-report.pdf' })

    await user.click(trash)
    expect(screen.queryByText(/detail probe/i)).not.toBeInTheDocument()

    // Enter on a focused <button> dispatches a click that bubbles to the
    // row -- the row handler must ignore it, same as the mouse case.
    trash.focus()
    expect(trash).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.queryByText(/detail probe/i)).not.toBeInTheDocument()

    await user.keyboard(' ')
    expect(screen.queryByText(/detail probe/i)).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
  })

  it('opens the upload modal on Upload click, and refetches the list once the modal closes', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])
    const user = userEvent.setup()

    renderPage()
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1))

    await user.click(screen.getByRole('button', { name: /^upload$/i }))
    expect(screen.getByText('Upload modal open')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /close modal/i }))

    expect(screen.queryByText('Upload modal open')).not.toBeInTheDocument()
    await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2))
  })

  it('shows the fetch error instead of the table when listing fails', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockRejectedValue(new Error('Not authenticated.'))

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Not authenticated.')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  describe('Story 2.3 status polling', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('polls while a document is Uploaded, and stops once it leaves Uploaded', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
        .mockResolvedValue([{ ...PDF_DOC, status: 'Extracting' }])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      // Still Uploaded -> another poll fires after the interval.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(2)

      // This poll's response flips status to Extracting.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(3)

      // No document is Uploaded anymore -- no further polls, even after
      // more time passes.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(3)
    })

    it('does not poll when no document is Uploaded', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([MD_DOC])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10000)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)
    })

    it('stops polling after the attempt cap even if status never changes', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValue([{ ...PDF_DOC, status: 'Uploaded' }])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })

      // Advance far past what the attempt cap allows -- the count must
      // stop growing well before this, not keep polling forever.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 30)
      })

      const cappedCount = listSpy.mock.calls.length
      expect(cappedCount).toBeLessThan(30)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 10)
      })
      expect(listSpy).toHaveBeenCalledTimes(cappedCount)
    })
  })
})
