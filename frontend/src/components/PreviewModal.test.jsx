import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PreviewModal from './PreviewModal'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

// jsdom has no real createObjectURL implementation -- stubbed the same way
// this component itself only ever treats the return value as an opaque
// string handed to an iframe's `src`.
let revokedUrls
beforeEach(() => {
  revokedUrls = []
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:mock-object-url'),
    revokeObjectURL: vi.fn((url) => revokedUrls.push(url)),
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('PreviewModal accessibility', () => {
  it('renders as a labelled modal dialog with initial focus on Close', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    const dialog = screen.getByRole('dialog', { name: /report\.pdf/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('button', { name: /close/i })).toHaveFocus()
  })

  it('returns focus to whatever was focused before it opened, on unmount', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const previewButton = document.createElement('button')
    previewButton.textContent = 'Preview'
    document.body.appendChild(previewButton)
    previewButton.focus()

    const { unmount } = render(
      <PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />,
    )
    expect(document.activeElement).not.toBe(previewButton)

    unmount()
    expect(document.activeElement).toBe(previewButton)
    previewButton.remove()
  })

  it('closes on Escape', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={onClose} />)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on explicit Close click', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('PreviewModal content rendering', () => {
  it('shows a loading state, then an object-URL iframe for a PDF', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    expect(screen.getByText(/loading preview/i)).toBeInTheDocument()

    const frame = await screen.findByTitle('report.pdf')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame).toHaveAttribute('src', 'blob:mock-object-url')
  })

  it('renders markdown as plain text, not through an iframe', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['# Heading\n\nBody text'], { type: 'text/markdown' }),
    )

    render(<PreviewModal documentId="doc-1" filename="notes.md" fileType="markdown" onClose={vi.fn()} />)

    expect(await screen.findByText(/# Heading/)).toBeInTheDocument()
    expect(screen.queryByTitle('notes.md')).not.toBeInTheDocument()
    // No object URL created for markdown -- the text goes straight into a
    // <pre>, never through URL.createObjectURL.
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('renders HTML through a sandboxed iframe with scripts disabled', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['<html><body>Hi</body></html>'], { type: 'text/html' }),
    )

    render(<PreviewModal documentId="doc-1" filename="page.html" fileType="html" onClose={vi.fn()} />)

    const frame = await screen.findByTitle('page.html')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame).toHaveAttribute('sandbox', '')
    expect(frame).not.toHaveAttribute('sandbox', expect.stringContaining('allow-scripts'))
  })

  it('shows an alert with the error message when the fetch fails', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockRejectedValue(
      new Error('Document not found.'),
    )

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found.')
  })

  it('revokes the created object URL on unmount', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )

    const { unmount } = render(
      <PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />,
    )
    await screen.findByTitle('report.pdf')

    unmount()

    await waitFor(() => expect(revokedUrls).toContain('blob:mock-object-url'))
  })
})
