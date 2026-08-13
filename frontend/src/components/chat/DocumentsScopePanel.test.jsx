import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentsScopePanel from './DocumentsScopePanel'
import * as documentsClient from '../../api/documentsClient'

afterEach(() => {
  vi.restoreAllMocks()
})

const DOCS = [
  { id: 'doc-1', filename: 'Vendor_Agreement_2026.pdf', status: 'Ready' },
  { id: 'doc-2', filename: 'Sprint_Planning_Notes.md', status: 'Extracting' },
]

describe('DocumentsScopePanel', () => {
  it('renders each document with its filename and status pill', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    render(<DocumentsScopePanel authFetch={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Vendor_Agreement_2026.pdf')).toBeInTheDocument())
    expect(screen.getByText('Sprint_Planning_Notes.md')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('Extracting')).toBeInTheDocument()
  })

  it('renders no checkboxes -- interactive scoping is Story 3.3, not this story', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)

    render(<DocumentsScopePanel authFetch={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Vendor_Agreement_2026.pdf')).toBeInTheDocument())
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.queryByText(/select all/i)).not.toBeInTheDocument()
  })

  it('shows an empty-library message when there are no documents', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    render(<DocumentsScopePanel authFetch={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('No documents yet.')).toBeInTheDocument())
  })

  it('renders an alert on fetch failure', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockRejectedValue(new Error('Failed to load documents.'))

    render(<DocumentsScopePanel authFetch={vi.fn()} />)

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Failed to load documents.'))
  })

  it('is full-width by default and only fixes to 260px above the 900px breakpoint ChatPage collapses at', () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    const { container } = render(<DocumentsScopePanel authFetch={vi.fn()} />)

    const aside = container.querySelector('aside')
    // A bare `w-[260px]` here would stay a narrow left-aligned block once
    // ChatPage's grid collapses to a single column below 900px, instead of
    // spanning the stacked layout's full width.
    expect(aside).toHaveClass('w-full')
    expect(aside).toHaveClass('min-[901px]:w-[260px]')
    expect(aside).not.toHaveClass('w-[260px]')
  })
})
