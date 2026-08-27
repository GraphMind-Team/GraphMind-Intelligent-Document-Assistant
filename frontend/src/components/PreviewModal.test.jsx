import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import JSZip from 'jszip'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PreviewModal from './PreviewModal'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'
import { renderAsync as renderDocxAsync } from 'docx-preview'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
// docx-preview manipulates real layout/font APIs jsdom doesn't implement,
// so the actual rendering pipeline is out of scope here -- these tests
// only assert PreviewModal calls it correctly and handles its outcome.
vi.mock('docx-preview', () => ({ renderAsync: vi.fn() }))

// Builds a minimal real PPTX-shaped zip (JSZip in, JSZip out -- the same
// library PreviewModal's pptxOutline helper reads) rather than mocking
// JSZip: exercises the actual slide-path regex and XML text-run
// extraction instead of assuming they work.
async function buildPptxBlob(slideTexts) {
  const zip = new JSZip()
  slideTexts.forEach((lines, index) => {
    const paragraphs = lines
      .map((line) => `<a:p><a:r><a:t>${line}</a:t></a:r></a:p>`)
      .join('')
    zip.file(
      `ppt/slides/slide${index + 1}.xml`,
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ` +
        `xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">` +
        `<p:cSld><p:spTree><p:sp><p:txBody>${paragraphs}</p:txBody></p:sp></p:spTree></p:cSld>` +
        `</p:sld>`,
    )
  })
  const arrayBuffer = await zip.generateAsync({ type: 'arraybuffer' })
  return new Blob([arrayBuffer], {
    type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  })
}

// jsdom has no real createObjectURL implementation -- stubbed the same way
// this component itself only ever treats the return value as an opaque
// string handed to an iframe's `src`.
let revokedUrls
beforeEach(() => {
  revokedUrls = []
  renderDocxAsync.mockReset().mockResolvedValue(undefined)
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

  it('renders a DOCX file through docx-preview', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const blob = new Blob(['docx bytes'], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(blob)

    render(<PreviewModal documentId="doc-1" filename="report.docx" fileType="docx" onClose={vi.fn()} />)

    await waitFor(() => expect(renderDocxAsync).toHaveBeenCalledTimes(1))
    const [renderedBlob, container] = renderDocxAsync.mock.calls[0]
    expect(renderedBlob).toBe(blob)
    expect(container).toBeInstanceOf(HTMLElement)
    // No object URL and no download fallback -- docx-preview reads the
    // Blob directly rather than this modal handing it an iframe/link.
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(screen.queryByText(/can't be previewed/i)).not.toBeInTheDocument()
  })

  it('surfaces an error when docx-preview fails to render', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(new Blob(['bad docx bytes']))
    renderDocxAsync.mockRejectedValue(new Error('Could not render this document.'))

    render(<PreviewModal documentId="doc-1" filename="report.docx" fileType="docx" onClose={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not render this document.')
  })

  it('renders a PPTX file as a slide-by-slide text outline', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const blob = await buildPptxBlob([
      ['Welcome', 'First bullet', 'Second bullet'],
      [],
    ])
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(blob)

    render(<PreviewModal documentId="doc-1" filename="deck.pptx" fileType="pptx" onClose={vi.fn()} />)

    expect(await screen.findByText('Slide 1')).toBeInTheDocument()
    expect(screen.getByText('Welcome')).toBeInTheDocument()
    expect(screen.getByText('First bullet')).toBeInTheDocument()
    expect(screen.getByText('Second bullet')).toBeInTheDocument()
    // Second slide has no text runs at all -- shown as an explicit empty
    // state rather than a slide heading with nothing underneath it.
    expect(screen.getByText('Slide 2')).toBeInTheDocument()
    expect(screen.getByText(/no text on this slide/i)).toBeInTheDocument()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('shows an alert if the PPTX cannot be parsed as a zip', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['not actually a zip']),
    )

    render(<PreviewModal documentId="doc-1" filename="deck.pptx" fileType="pptx" onClose={vi.fn()} />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('shows a download fallback for a file type with no inline renderer', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'getDocumentContent').mockResolvedValue(
      new Blob(['csv bytes'], { type: 'text/csv' }),
    )

    render(<PreviewModal documentId="doc-1" filename="report.csv" fileType="csv" onClose={vi.fn()} />)

    expect(await screen.findByText(/can't be previewed/i)).toBeInTheDocument()
    // Regression: the modal used to render nothing at all for an unhandled
    // file type -- status flipped to 'ready' with no branch matching it,
    // so it silently showed an empty body.
    expect(screen.queryByTitle('report.csv')).not.toBeInTheDocument()
    const downloadLink = screen.getByRole('link', { name: /download/i })
    expect(downloadLink).toHaveAttribute('href', 'blob:mock-object-url')
    expect(downloadLink).toHaveAttribute('download', 'report.csv')
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
