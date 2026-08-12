import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

describe('DocumentsPage', () => {
  it('lists uploaded documents after fetching', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([
      { id: '1', filename: 'report.pdf', file_type: 'pdf', status: 'Uploaded', created_at: '2026-08-12T00:00:00Z' },
    ])

    render(<DocumentsPage />)

    expect(await screen.findByText('report.pdf')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: 'Uploaded' })).toBeInTheDocument()
  })

  it('shows an empty state with no documents', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    render(<DocumentsPage />)

    expect(await screen.findByText(/no documents uploaded yet/i)).toBeInTheDocument()
  })

  it('opens the upload modal on Upload click, and refetches the list once the modal closes', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const listSpy = vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])
    const user = userEvent.setup()

    render(<DocumentsPage />)
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

    render(<DocumentsPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Not authenticated.')
  })
})
