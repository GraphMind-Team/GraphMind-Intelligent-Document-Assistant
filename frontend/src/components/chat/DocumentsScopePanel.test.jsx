import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentsScopePanel from './DocumentsScopePanel'
import * as documentsClient from '../../api/documentsClient'
import { ChatScopeProvider } from '../../context/ChatScopeContext'
import { useAuth } from '../../context/AuthContext'

// PreviewModal (opened by clicking a document's filename, below) calls
// useAuth() itself -- unmocked, that throws outside an AuthProvider.
vi.mock('../../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const DOCS = [
  { id: 'doc-1', filename: 'Vendor_Agreement_2026.pdf', status: 'Ready', file_type: 'pdf' },
  { id: 'doc-2', filename: 'Sprint_Planning_Notes.md', status: 'Extracting', file_type: 'markdown' },
]

// Mirrors DocumentCard.test.jsx/DocumentDetailPage.test.jsx's own stub --
// PreviewModal needs these regardless of which page mounts it.
function stubObjectUrls() {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:mock-object-url'),
    revokeObjectURL: vi.fn(),
  })
}

function renderPanel(authFetch = vi.fn()) {
  return render(
    <ChatScopeProvider>
      <DocumentsScopePanel authFetch={authFetch} />
    </ChatScopeProvider>,
  )
}

describe('DocumentsScopePanel', () => {
  it('renders each document with its filename and status pill', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    renderPanel()

    await waitFor(() => expect(screen.getByText('Vendor_Agreement_2026.pdf')).toBeInTheDocument())
    expect(screen.getByText('Sprint_Planning_Notes.md')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('Reading document')).toBeInTheDocument()
  })

  it('shows an empty-library message when there are no documents', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    renderPanel()

    await waitFor(() => expect(screen.getByText('No documents yet.')).toBeInTheDocument())
  })

  it('renders an alert on fetch failure', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockRejectedValue(new Error('Failed to load documents.'))

    renderPanel()

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Failed to load documents.'))
  })

  it('is full-width by default and only fixes to 260px above the 900px breakpoint ChatPage collapses at', () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    const { container } = renderPanel()

    const aside = container.querySelector('aside')
    // A bare `w-[260px]` here would stay a narrow left-aligned block once
    // ChatPage's grid collapses to a single column below 900px, instead of
    // spanning the stacked layout's full width.
    expect(aside).toHaveClass('w-full')
    expect(aside).toHaveClass('min-[901px]:w-[260px]')
    expect(aside).not.toHaveClass('w-[260px]')
  })

  it('renders one checkbox per document, unchecked by default (OD-6)', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    renderPanel()

    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2))
    for (const checkbox of screen.getAllByRole('checkbox')) {
      expect(checkbox).not.toBeChecked()
    }
    expect(screen.getByText('Asking across all 2 documents.')).toBeInTheDocument()
  })

  it('disables a non-Ready document checkbox and exposes the status via aria-label (UX-DR9/27)', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    renderPanel()

    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2))
    // The human-readable label ("Reading document"), not the raw backend
    // status word ("Extracting") -- a screen-reader user hearing this
    // must get the same wording StatusPill shows sighted users, not
    // pipeline jargon neither of them sees anywhere else on screen.
    const extractingCheckbox = screen.getByLabelText(/Sprint_Planning_Notes\.md.*Reading document/)
    expect(extractingCheckbox).toBeDisabled()

    const readyCheckbox = screen.getByLabelText('Select Vendor_Agreement_2026.pdf')
    expect(readyCheckbox).not.toBeDisabled()
  })

  it('clicking a checkbox toggles it immediately, with no separate apply step (UX-DR9)', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    const user = userEvent.setup()

    renderPanel()

    const readyCheckbox = await screen.findByLabelText('Select Vendor_Agreement_2026.pdf')
    expect(readyCheckbox).not.toBeChecked()

    await user.click(readyCheckbox)
    expect(readyCheckbox).toBeChecked()
    expect(screen.getByText('1 of 2 selected.')).toBeInTheDocument()

    await user.click(readyCheckbox)
    expect(readyCheckbox).not.toBeChecked()
  })

  it('"Select all" checks every Ready document and leaves non-Ready ones untouched', async () => {
    const docs = [
      ...DOCS,
      { id: 'doc-3', filename: 'Refund_Policy.pdf', status: 'Ready' },
    ]
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(docs)
    const user = userEvent.setup()

    renderPanel()

    await screen.findByText('Vendor_Agreement_2026.pdf')
    await user.click(screen.getByRole('button', { name: 'Select all' }))

    expect(screen.getByLabelText('Select Vendor_Agreement_2026.pdf')).toBeChecked()
    expect(screen.getByLabelText('Select Refund_Policy.pdf')).toBeChecked()
    expect(screen.getByText('2 of 3 selected.')).toBeInTheDocument()
  })

  it('the filter input narrows the visible list without touching the selection (OD-5)', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    const user = userEvent.setup()

    renderPanel()

    const readyCheckbox = await screen.findByLabelText('Select Vendor_Agreement_2026.pdf')
    await user.click(readyCheckbox)

    await user.type(screen.getByLabelText('Filter documents in scope'), 'Vendor')

    expect(screen.getByText('Vendor_Agreement_2026.pdf')).toBeInTheDocument()
    expect(screen.queryByText('Sprint_Planning_Notes.md')).not.toBeInTheDocument()
    // Still reflected as selected even though it's the only visible row now.
    expect(screen.getByText('1 of 2 selected.')).toBeInTheDocument()
  })

  it('drops a selected document that a later fetch no longer includes as Ready', async () => {
    const listDocumentsSpy = vi
      .spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce(DOCS)
      .mockResolvedValueOnce([DOCS[1]]) // doc-1 gone from the second fetch
    const user = userEvent.setup()

    const { rerender } = render(
      <ChatScopeProvider>
        <DocumentsScopePanel authFetch={vi.fn()} />
      </ChatScopeProvider>,
    )

    const readyCheckbox = await screen.findByLabelText('Select Vendor_Agreement_2026.pdf')
    await user.click(readyCheckbox)
    expect(screen.getByText('1 of 2 selected.')).toBeInTheDocument()

    // A new authFetch reference re-triggers the fetch effect (same
    // ChatScopeProvider instance, so the selection persists across it).
    rerender(
      <ChatScopeProvider>
        <DocumentsScopePanel authFetch={vi.fn()} />
      </ChatScopeProvider>,
    )

    await waitFor(() => expect(listDocumentsSpy).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByText('Asking across all 1 document.')).toBeInTheDocument())
  })

  it('clicking a Ready document\'s filename opens a preview of it, without touching its checkbox', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    stubObjectUrls()
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const user = userEvent.setup()

    renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Vendor_Agreement_2026.pdf' }))

    expect(await screen.findByRole('dialog', { name: 'Vendor_Agreement_2026.pdf' })).toBeInTheDocument()
    expect(screen.getByLabelText('Select Vendor_Agreement_2026.pdf')).not.toBeChecked()
  })

  it('a non-Ready document\'s filename is plain text, not a preview trigger -- there is nothing to preview yet', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    renderPanel()

    await screen.findByText('Sprint_Planning_Notes.md')
    expect(screen.queryByRole('button', { name: 'Sprint_Planning_Notes.md' })).not.toBeInTheDocument()
  })
})
