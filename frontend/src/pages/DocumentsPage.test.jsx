import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DocumentsPage from './DocumentsPage'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'
import * as foldersClient from '../api/foldersClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../components/UploadModal', () => ({
  default: ({ onClose }) => (
    <div>
      <span>Upload modal open</span>
      <button onClick={onClose}>close modal</button>
    </div>
  ),
}))

// Folder-grouping feature: DocumentsPage fetches folders alongside
// documents on mount. Every test in this file gets a default empty
// `listFolders` resolution here, so the pre-existing document-only tests
// below (none of which mock `authFetch` beyond a bare `vi.fn()`) don't
// also surface DocumentsPage's own `folderError` alert banner just from
// the folders fetch failing against an un-implemented `authFetch`. Tests
// that actually exercise folder behavior override this per-test via their
// own `vi.spyOn(foldersClient, 'listFolders')`.
beforeEach(() => {
  vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([])
})

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

const FOLDER_A = { id: 'folder-a', name: 'Contracts', color: 'mint', created_at: '2026-08-10T00:00:00Z' }

// A Ready document's title renders as a Preview-opening button rather
// than a detail-page link (DocumentCard.jsx), so a plain
// `getAllByRole('link')` no longer finds every card the way it did
// before that existed -- this reads each card's own title text directly,
// in DOM order, regardless of which element type rendered it.
function documentTitles() {
  const documentsList = screen.getByRole('list', { name: 'Documents' })
  return within(documentsList)
    .getAllByRole('listitem')
    .map((card) => within(card).getByText(/\.(pdf|md|html?)$/).textContent)
}

describe('DocumentsPage', () => {
  it('renders type, title, status pill, uploaded date and a trash icon per card', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])

    renderPage()

    // The card grid is a list, so each document is a listitem rather than
    // a table row -- same five facts, different container. Scoped to the
    // "Documents" list specifically: the folder tile grid above it (added
    // by the folder-grouping feature) is its own separate list with its
    // own listitems.
    const documentsList = await screen.findByRole('list', { name: 'Documents' })
    const card = within(documentsList).getByRole('listitem')
    expect(within(card).getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
    expect(within(card).getByText('PDF')).toBeInTheDocument()
    expect(within(card).getByText('Uploaded')).toBeInTheDocument()
    expect(within(card).getByText(/2026/)).toBeInTheDocument()
    expect(
      within(card).getByRole('button', { name: 'Delete beta-report.pdf' }),
    ).toBeInTheDocument()
  })

  it('never shows the failed reason inline in a Failed row (Detail-only, Story 2.5)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
      { ...PDF_DOC, status: 'Failed', failed_reason: 'Could not read this document: unexpected EOF' },
    ])

    renderPage()

    const documentsList = await screen.findByRole('list', { name: 'Documents' })
    const card = within(documentsList).getByRole('listitem')
    expect(within(card).getByText('Failed')).toBeInTheDocument()
    expect(screen.queryByText(/unexpected EOF/)).not.toBeInTheDocument()
  })

  it('shows the empty-library state with an empty library, and keeps Upload actionable', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    renderPage()

    expect(await screen.findByText('Upload your first document')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^upload$/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Upload a document' })).toBeEnabled()
  })

  it('reorders rows client-side on sort, without refetching', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    // Default is most-recent-first, so the newer PDF leads. MD_DOC is
    // Ready, so its title is a Preview-opening button rather than a link
    // (DocumentCard.jsx) -- `documentTitles` below reads each card's own
    // title text directly rather than assuming every card uses the same
    // element type.
    expect(documentTitles()).toEqual(['beta-report.pdf', 'alpha-notes.md'])

    await user.selectOptions(screen.getByLabelText('Sort documents'), 'title')

    expect(documentTitles()).toEqual(['alpha-notes.md', 'beta-report.pdf'])
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

  it('narrows rows client-side by name as the search field is typed, without refetching', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    // Case-insensitive, substring match -- not the full filename.
    await user.type(screen.getByLabelText('Search documents by name'), 'ALPHA')

    expect(screen.getByText('alpha-notes.md')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'beta-report.pdf' })).not.toBeInTheDocument()
    expect(listSpy).toHaveBeenCalledTimes(1)
  })

  it('shows the filtered-empty state (not the empty-library one) when the search matches nothing', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    await user.type(screen.getByLabelText('Search documents by name'), 'nothing-matches-this')

    expect(screen.getByText('No documents match this filter.')).toBeInTheDocument()
    expect(screen.queryByText('Upload your first document')).not.toBeInTheDocument()
  })

  it('distinguishes "no match for this filter" from a genuinely empty library', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })

    await user.selectOptions(screen.getByLabelText('Filter documents by type'), 'html')

    expect(screen.getByText('No documents match this filter.')).toBeInTheDocument()
    expect(screen.queryByText('Upload your first document')).not.toBeInTheDocument()
  })

  it('opens Detail when the card is clicked outside the trash icon', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])
    const user = userEvent.setup()

    renderPage()
    const documentsList = await screen.findByRole('list', { name: 'Documents' })
    const card = within(documentsList).getByRole('listitem')

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

  it('deletes a document end-to-end through the real confirm flow, removing only that card', async () => {
    // Story 2.7. `DocumentCard.test.jsx` covers the confirm box in
    // isolation with its own mocked `onDeleted`; this exercises
    // `DocumentsPage`'s real `handleDeleted` -- the function that actually
    // filters the deleted id out of `documents` state -- so an inverted
    // filter condition or a dropped `onDeleted` prop would fail here even
    // though neither would be caught by the isolated component test.
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC, MD_DOC])
    const deleteSpy = vi.spyOn(documentsClient, 'deleteDocument').mockResolvedValue(undefined)
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('link', { name: 'beta-report.pdf' })
    // MD_DOC is Ready, so its title renders as a Preview-opening button
    // rather than a detail-page link (DocumentCard.jsx) -- `getByText`
    // finds it either way, which is what these presence checks actually
    // care about.
    await screen.findByText('alpha-notes.md')

    const trash = screen.getByRole('button', { name: 'Delete beta-report.pdf' })
    await user.click(trash)
    const confirmBox = screen.getByRole('alert')
    await user.click(within(confirmBox).getByRole('button', { name: 'Delete' }))

    await waitFor(() =>
      expect(screen.queryByRole('link', { name: 'beta-report.pdf' })).not.toBeInTheDocument(),
    )
    expect(deleteSpy).toHaveBeenCalledWith(expect.any(Function), PDF_DOC.id)
    // The other document is untouched.
    expect(screen.getByText('alpha-notes.md')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Documents' })).getAllByRole('listitem')).toHaveLength(1)

    // Focus lands on Upload, the one always-present stable control, since
    // the card (and the confirm box's own Delete button, which held focus
    // a moment ago) is now gone from the DOM entirely.
    expect(screen.getByRole('button', { name: /^upload$/i })).toHaveFocus()
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

  it('Retry on the error banner refetches, and a successful retry replaces the error with the grid', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi
      .spyOn(documentsClient, 'listDocuments')
      .mockRejectedValueOnce(new Error('Not authenticated.'))
      .mockResolvedValue([PDF_DOC])
    const user = userEvent.setup()

    renderPage()
    await screen.findByRole('alert')

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(listSpy).toHaveBeenCalledTimes(2)
  })

  describe('ingestion status polling (Story 2.3, extended in 2.4)', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('keeps polling through Extracting and Graphing, and stops only at a terminal status', async () => {
      // Story 2.4 regression guard. Story 2.3 polled `Uploaded` only,
      // which was correct while a parsed document parked at `Extracting`
      // forever -- but once 2.4 advanced the pipeline to `Ready`, that
      // same rule meant the grid stopped watching at the *first*
      // transition and never showed a document finishing. Each mid-flight
      // status below must keep the loop alive; only `Ready` ends it.
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Extracting' }])
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Graphing' }])
        .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      // Poll 1's response moves it to Extracting -- still in flight, so
      // the loop must survive (this is the exact tick the pre-2.4 rule
      // tore the interval down on).
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(2)

      // Poll 2's response moves it to Graphing -- still in flight.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(3)

      // Poll 3's response is Ready. The grid shows the finished document...
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(4)
      // A sync query, not `findByText`: `findBy*` polls on real timers,
      // which never advance under `vi.useFakeTimers` -- and the state is
      // already flushed by the `act` above, so there is nothing to await.
      expect(screen.getByText('Ready')).toBeInTheDocument()

      // ...and only now does polling stop.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 3)
      })
      expect(listSpy).toHaveBeenCalledTimes(4)
    })

    it('stops polling once a document reaches the terminal Failed status', async () => {
      // `Failed` is terminal too -- a failed ingestion must not leave the
      // grid polling for a transition that will never come.
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Extracting' }])
        .mockResolvedValue([{ ...PDF_DOC, status: 'Failed' }])

      vi.useFakeTimers()
      renderPage()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(listSpy).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000)
      })
      expect(listSpy).toHaveBeenCalledTimes(2)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000 * 3)
      })
      expect(listSpy).toHaveBeenCalledTimes(2)
    })

    it('does not poll when every document is already at a terminal status', async () => {
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
      // (45) budgeted attempts actually fire -- checking after incrementing
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
        await vi.advanceTimersByTimeAsync(4000 * 90)
      })

      const MAX_POLL_ATTEMPTS = 45
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
      const MAX_POLL_ATTEMPTS = 45

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

  describe('folder grouping (folder-grouping feature)', () => {
    it('fetches folders once on mount, and pressing "Folders" renders them as tiles in the panel', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
        { ...PDF_DOC, folder_id: 'folder-a' },
        { ...MD_DOC, folder_id: null },
      ])
      const foldersSpy = vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      const user = userEvent.setup()

      renderPage()
      await user.click(screen.getByRole('button', { name: 'Folders' }))

      expect(await screen.findByRole('button', { name: /^Contracts,/ })).toBeInTheDocument()
      expect(foldersSpy).toHaveBeenCalledTimes(1)
    })

    it('surfaces a folder-fetch failure as its own alert, without hiding the document grid', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([PDF_DOC])
      vi.spyOn(foldersClient, 'listFolders').mockRejectedValue(new Error('Failed to load folders (500).'))
      const user = userEvent.setup()

      renderPage()

      expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load folders (500).')
      // The document grid is unaffected -- a folder-fetch failure is
      // distinguishable from "you have zero folders", but it's not the
      // same kind of failure as the document list's own, which does hide
      // the grid.
      expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
      // The two fixed tiles ("All documents"/"Ungrouped") still render --
      // the panel works with zero folder tiles either way.
      await user.click(screen.getByRole('button', { name: 'Folders' }))
      expect(screen.getByRole('button', { name: /^All documents,/ })).toBeInTheDocument()
    })

    it('renders a "Folders" toggle button in the toolbar, closed until pressed', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

      renderPage()

      const trigger = await screen.findByRole('button', { name: 'Folders' })
      expect(trigger).toHaveAttribute('aria-pressed', 'false')
      expect(screen.queryByRole('button', { name: /^All documents,/ })).not.toBeInTheDocument()
    })

    it('selecting a folder tile filters the grid client-side; "All documents" and "Ungrouped" do too', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
        { ...PDF_DOC, folder_id: 'folder-a' },
        { ...MD_DOC, folder_id: null },
      ])
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      const user = userEvent.setup()

      renderPage()
      await screen.findByRole('link', { name: 'beta-report.pdf' })
      await screen.findByText('alpha-notes.md')
      await user.click(screen.getByRole('button', { name: 'Folders' }))

      // Selecting the folder tile narrows to just its member. The panel
      // itself stays open across every selection below -- only an outside
      // click or the trigger closes it, not a tile pick.
      await user.click(screen.getByRole('button', { name: /^Contracts,/ }))
      expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
      expect(screen.queryByText('alpha-notes.md')).not.toBeInTheDocument()

      // "Ungrouped" narrows to the document with no folder_id.
      await user.click(screen.getByRole('button', { name: /^Ungrouped,/ }))
      expect(screen.queryByRole('link', { name: 'beta-report.pdf' })).not.toBeInTheDocument()
      expect(screen.getByText('alpha-notes.md')).toBeInTheDocument()

      // "All documents" shows everything again.
      await user.click(screen.getByRole('button', { name: /^All documents,/ }))
      expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
      expect(screen.getByText('alpha-notes.md')).toBeInTheDocument()

      // No server round trip for any of the above -- filtering stayed
      // entirely client-side over the one initial fetch, matching the
      // existing sort/type-filter convention.
      expect(listSpy).toHaveBeenCalledTimes(1)
    })

    it('assigning a document to a folder via its card "⋮" menu updates the grid and the tile count without a refetch', async () => {
      const authFetch = vi.fn()
      useAuth.mockReturnValue({ authFetch })
      const listSpy = vi
        .spyOn(documentsClient, 'listDocuments')
        .mockResolvedValue([{ ...PDF_DOC, folder_id: null }])
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({
        ...PDF_DOC,
        folder_id: 'folder-a',
      })
      const user = userEvent.setup()

      renderPage()
      await screen.findByRole('link', { name: 'beta-report.pdf' })
      await user.click(screen.getByRole('button', { name: 'Folders' }))
      expect(within(screen.getByRole('button', { name: /^Contracts,/ })).getByText('0 documents')).toBeInTheDocument()

      // The card's own "⋮" menu stops its clicks from propagating (so they
      // never navigate to Detail), which also means the folders panel
      // stays open across this whole interaction -- it's still open below.
      await user.click(screen.getByRole('button', { name: `More actions for ${PDF_DOC.filename}` }))
      await user.click(screen.getByRole('menuitem', { name: 'Contracts' }))

      // The tile's count reflects the reassignment immediately...
      await waitFor(() =>
        expect(
          within(screen.getByRole('button', { name: /^Contracts,/ })).getByText('1 document'),
        ).toBeInTheDocument(),
      )
      // ...and selecting that tile now shows the reassigned document,
      // without DocumentsPage refetching the document list.
      await user.click(screen.getByRole('button', { name: /^Contracts,/ }))
      expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
      expect(listSpy).toHaveBeenCalledTimes(1)
    })

    it('does not navigate to Detail when the per-card "⋮" menu is opened or used', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([{ ...PDF_DOC, folder_id: null }])
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({
        ...PDF_DOC,
        folder_id: 'folder-a',
      })
      const user = userEvent.setup()

      renderPage()
      await screen.findByRole('link', { name: 'beta-report.pdf' })

      await user.click(screen.getByRole('button', { name: `More actions for ${PDF_DOC.filename}` }))
      expect(screen.queryByText(/detail probe/i)).not.toBeInTheDocument()

      await user.click(screen.getByRole('menuitem', { name: 'Contracts' }))
      expect(screen.queryByText(/detail probe/i)).not.toBeInTheDocument()
    })

    it('dragging one ungrouped document onto another opens the create-folder dialog, and confirming assigns both', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
        { ...PDF_DOC, folder_id: null },
        { ...MD_DOC, folder_id: null },
      ])
      vi.spyOn(foldersClient, 'createFolder').mockResolvedValue({
        id: 'new-folder',
        name: 'Reports',
        color: 'sun',
        created_at: '2026-08-21T00:00:00Z',
      })
      const updateSpy = vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({})
      const user = userEvent.setup()

      renderPage()
      const documentsList = await screen.findByRole('list', { name: 'Documents' })
      const [pdfCard, mdCard] = within(documentsList).getAllByRole('listitem')
      await user.click(screen.getByRole('button', { name: 'Folders' }))

      const dataTransfer = {
        store: {},
        setData(type, value) {
          this.store[type] = value
        },
        getData(type) {
          return this.store[type] ?? ''
        },
      }
      fireEvent.dragStart(pdfCard, { dataTransfer })
      fireEvent.dragOver(mdCard, { dataTransfer })
      fireEvent.drop(mdCard, { dataTransfer })

      expect(screen.getByRole('dialog', { name: /new folder/i })).toBeInTheDocument()
      await user.type(screen.getByLabelText('Name'), 'Reports')
      await user.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), PDF_DOC.id, 'new-folder')
        expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), MD_DOC.id, 'new-folder')
      })
      // The new tile now shows both documents, reflected without a
      // document-list refetch.
      await waitFor(() =>
        expect(
          within(screen.getByRole('button', { name: /^Reports,/ })).getByText('2 documents'),
        ).toBeInTheDocument(),
      )
    })

    it('dragging a document onto a folder tile assigns it directly, no dialog', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([{ ...PDF_DOC, folder_id: null }])
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      const updateSpy = vi
        .spyOn(documentsClient, 'updateDocumentFolder')
        .mockResolvedValue({ ...PDF_DOC, folder_id: 'folder-a' })
      const user = userEvent.setup()

      renderPage()
      const documentsList = await screen.findByRole('list', { name: 'Documents' })
      const card = within(documentsList).getByRole('listitem')
      await user.click(screen.getByRole('button', { name: 'Folders' }))
      const tile = screen.getByRole('button', { name: /^Contracts,/ }).closest('div')

      const dataTransfer = {
        store: {},
        setData(type, value) {
          this.store[type] = value
        },
        getData(type) {
          return this.store[type] ?? ''
        },
      }
      fireEvent.dragStart(card, { dataTransfer })
      fireEvent.dragOver(tile, { dataTransfer })
      fireEvent.drop(tile, { dataTransfer })

      await waitFor(() => expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), PDF_DOC.id, 'folder-a'))
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      await waitFor(() =>
        expect(
          within(screen.getByRole('button', { name: /^Contracts,/ })).getByText('1 document'),
        ).toBeInTheDocument(),
      )
    })

    it('deleting a folder removes its tile and ungroups its documents locally, without losing them', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
        { ...PDF_DOC, folder_id: 'folder-a' },
      ])
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([FOLDER_A])
      vi.spyOn(foldersClient, 'deleteFolder').mockResolvedValue(undefined)
      const user = userEvent.setup()

      renderPage()
      await screen.findByRole('link', { name: 'beta-report.pdf' })
      await user.click(screen.getByRole('button', { name: 'Folders' }))

      await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))
      await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

      // The folder tile is gone...
      await waitFor(() =>
        expect(screen.queryByRole('button', { name: /^Contracts,/ })).not.toBeInTheDocument(),
      )
      // ...its document is still in the grid (never deleted), now
      // Ungrouped -- its "⋮" menu no longer offers an "Ungrouped" item
      // (nothing to unassign from) or "Contracts" (the folder is gone).
      expect(screen.getByRole('link', { name: 'beta-report.pdf' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: `More actions for ${PDF_DOC.filename}` }))
      const menu = screen.getByRole('menu')
      expect(within(menu).getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
        'Create new folder',
      ])
    })
  })
})
