import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

    it('stops polling after exactly the attempt cap even if status never changes', async () => {
      // Pins the exact count, not just "eventually stops": the cap check
      // must run *before* incrementing/fetching, so all MAX_POLL_ATTEMPTS
      // (15) budgeted attempts actually fire -- checking after incrementing
      // was an off-by-one that silently dropped the last one.
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValue([{ ...PDF_DOC, status: 'Uploaded' }])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1) // the initial mount fetch

      // Advance far past what the attempt cap allows -- the count must
      // stop growing well before this, not keep polling forever.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 30)
      })

      const MAX_POLL_ATTEMPTS = 15
      expect(listSpy).toHaveBeenCalledTimes(1 + MAX_POLL_ATTEMPTS)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 10)
      })
      expect(listSpy).toHaveBeenCalledTimes(1 + MAX_POLL_ATTEMPTS)
    })

    it('resets the poll budget when a new pollable document appears, even while an old one stays stuck', async () => {
      // A document that never leaves Uploaded (e.g. the process restarted
      // between upload and its background task ever running) must not
      // permanently exhaust polling for the whole session -- a later,
      // genuinely fresh upload has to get its own budget. Gating the
      // effect on a plain "is anything pollable" boolean would fail this:
      // that boolean stays true across the whole scenario below, so the
      // effect (and the budget) would never restart.
      const STUCK_DOC = { ...PDF_DOC, id: 'doc-stuck', status: 'Uploaded' }
      const NEW_DOC = { ...MD_DOC, id: 'doc-new', status: 'Uploaded' }
      const MAX_POLL_ATTEMPTS = 15

      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([STUCK_DOC])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      // Exhaust the budget while only the stuck document is present.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * (MAX_POLL_ATTEMPTS + 5))
      })
      expect(listSpy).toHaveBeenCalledTimes(1 + MAX_POLL_ATTEMPTS)

      // A fresh upload lands -- the modal-close refetch now returns the
      // stuck document plus a brand new Uploaded one.
      listSpy.mockResolvedValue([STUCK_DOC, NEW_DOC])
      fireEvent.click(screen.getByRole('button', { name: /^upload$/i }))
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /close modal/i }))
        await vi.advanceTimersByTimeAsync(0)
      })
      const countAfterNewUpload = listSpy.mock.calls.length

      // Polling resumes for the new document.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy.mock.calls.length).toBeGreaterThan(countAfterNewUpload)
    })

    it('does not let a background silent poll blank out a visible error banner', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }]) // initial mount fetch
        .mockRejectedValueOnce(new Error('Network error')) // modal-close refetch fails
        .mockRejectedValue(new Error('Network error')) // subsequent silent polls also fail

      // Fake timers from the start, and `fireEvent` instead of
      // `userEvent` for the modal buttons -- userEvent's internal delays
      // rely on real timers, which would fight `vi.advanceTimersByTimeAsync`
      // below controlling the polling interval that starts at mount.
      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      // A non-silent refetch (modal close) fails -- the error banner
      // appears, and the last-known document list (still showing an
      // Uploaded doc) is untouched, so polling keeps running.
      fireEvent.click(screen.getByRole('button', { name: /^upload$/i }))
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /close modal/i }))
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(screen.getByRole('alert')).toHaveTextContent('Network error')

      // A silent background poll tick runs next, and it fails too -- the
      // bug was `setError(null)` running unconditionally before the
      // silent/non-silent branch, wiping the visible banner regardless of
      // whether the silent poll's own fetch succeeded or failed.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })

      expect(screen.getByRole('alert')).toHaveTextContent('Network error')
    })
  })
})
