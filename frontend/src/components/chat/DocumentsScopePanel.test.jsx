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
})
