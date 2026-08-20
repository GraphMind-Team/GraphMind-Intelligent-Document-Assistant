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

  it('lets Tab reach the previewed document and keeps focus inside the dialog', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    )
    const user = userEvent.setup()

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    const frame = await screen.findByTitle('report.pdf')
    const closeButton = screen.getByRole('button', { name: /close/i })
    expect(closeButton).toHaveFocus()

    // The regression this guards: with only the Close button in the trap's
    // focusable set, it was both first and last, so every Tab was
    // preventDefault'd back onto it and the document being previewed was
    // unreachable -- and unscrollable -- by keyboard.
    await user.tab()
    expect(screen.getByLabelText('Document preview')).toHaveFocus()

    // Shift+Tab off the first stop wraps to the *last* one, which is now
    // the preview iframe rather than the Close button it used to be --
    // proof the previewed document is inside the trap, not excluded from
    // it. Asserted this way round because it runs entirely through the
    // component's own handler: real browsers put iframes in the tab
    // sequence, but userEvent's simulated tab order skips them, so a plain
    // `user.tab()` can never land on one here.
    closeButton.focus()
    await user.tab({ shift: true })
    expect(frame).toHaveFocus()

    // ...and Tab off that last stop wraps back inside, never out to the
    // page behind the modal.
    await user.tab()
    expect(closeButton).toHaveFocus()
  })

  it('announces the loading state through a live region', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    // Never settles: holds the component on its loading state so the live
    // region is what's asserted, not the transition off it.
    vi.spyOn(documentsClient, 'getDocumentContent').mockReturnValue(new Promise(() => {}))

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    expect(screen.getByRole('status')).toHaveTextContent(/loading preview/i)
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
  })

  it('shows an alert with the error message when the fetch fails', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockRejectedValue(
      new Error('Document not found.'),
    )

    render(<PreviewModal documentId="doc-1" filename="report.pdf" fileType="pdf" onClose={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Document not found.')
  })

  it('surfaces an error instead of hanging when the markdown body cannot be decoded', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    // Resolves to a blob whose `.text()` rejects -- the one failure that
    // happens *after* the fetch succeeded, and the only path where the
    // component awaits a second promise. Unreturned, that rejection landed
    // outside the chain and left the modal on "Loading preview..." forever.
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue({
      text: () => Promise.reject(new Error('Could not decode this document.')),
    })

    render(
      <PreviewModal documentId="doc-1" filename="notes.md" fileType="markdown" onClose={vi.fn()} />,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not decode this document.')
    expect(screen.queryByText(/loading preview/i)).not.toBeInTheDocument()
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
