import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import UploadModal from './UploadModal'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

function makeFile(name, type = 'application/pdf') {
  return new File(['content'], name, { type })
}

// UploadModal renders a react-router `Link` in the duplicate-row branch
// (Story 2.6) -- only that branch needs a Router ancestor, but wrapping
// every render here keeps the helper uniform.
function renderModal(props) {
  return render(
    <MemoryRouter>
      <UploadModal {...props} />
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('UploadModal accessibility', () => {
  it('renders as a labelled, modal dialog with initial focus on the dropzone', () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    render(
      <>
        <button>Upload</button>
        <UploadModal onClose={vi.fn()} />
      </>,
    )

    const dialog = screen.getByRole('dialog', { name: /upload documents/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('button', { name: /drag and drop files/i })).toHaveFocus()
  })

  it('returns focus to whatever was focused before it opened, on unmount', () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    const uploadButton = document.createElement('button')
    uploadButton.textContent = 'Upload'
    document.body.appendChild(uploadButton)
    uploadButton.focus()
    expect(document.activeElement).toBe(uploadButton)

    const { unmount } = render(<UploadModal onClose={vi.fn()} />)
    expect(document.activeElement).not.toBe(uploadButton)

    unmount()
    expect(document.activeElement).toBe(uploadButton)
    uploadButton.remove()
  })

  it('closes on Escape', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<UploadModal onClose={onClose} />)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on explicit Cancel', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<UploadModal onClose={onClose} />)

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('UploadModal file handling', () => {
  it('rejects an invalid file before sending any upload request', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    const uploadSpy = vi.spyOn(documentsClient, 'uploadDocument')

    render(<UploadModal onClose={vi.fn()} />)

    // Dropped, not selected via the file input: the input's `accept`
    // attribute is a picker hint the OS honors, so a real .docx would
    // never even be offered there -- drag-and-drop is the path that
    // actually reaches this component's own validation.
    const dropzone = screen.getByRole('button', { name: /drag and drop files/i })
    fireEvent.drop(dropzone, { dataTransfer: { files: [makeFile('resume.docx', 'application/msword')] } })

    expect(await screen.findByText('resume.docx')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/unsupported file format/i)
    expect(uploadSpy).not.toHaveBeenCalled()
  })

  it('uploads a valid file, shows independent progress, and auto-closes once resolved', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    let resolveUpload
    vi.spyOn(documentsClient, 'uploadDocument').mockImplementation((_token, _file, onProgress) => {
      onProgress(42)
      return new Promise((resolve) => {
        resolveUpload = resolve
      })
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<UploadModal onClose={onClose} />)

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, makeFile('report.pdf'))

    expect(await screen.findByText('report.pdf')).toBeInTheDocument()
    const progressbar = screen.getByRole('progressbar', { name: /report\.pdf/i })
    await waitFor(() => expect(progressbar).toHaveAttribute('aria-valuenow', '42'))

    expect(onClose).not.toHaveBeenCalled()

    resolveUpload({ id: 'doc-1', status: 'Uploaded' })

    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('keeps two files independent -- one erroring does not affect the other uploading', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockImplementation((_token, file) => {
      if (file.name === 'slow.pdf') return new Promise(() => {}) // never resolves in this test
      return Promise.reject(new Error('Upload failed (500).'))
    })
    const user = userEvent.setup()

    render(<UploadModal onClose={vi.fn()} />)

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, [makeFile('fails.pdf'), makeFile('slow.pdf')])

    expect(await screen.findByText(/upload failed/i)).toBeInTheDocument()
    expect(screen.getByText('slow.pdf')).toBeInTheDocument()
    // The slow file's own progressbar is still present/unresolved -- its
    // sibling erroring didn't touch it.
    expect(screen.getByRole('progressbar', { name: /slow\.pdf/i })).toBeInTheDocument()
  })

  it('does not cancel an in-flight upload when the modal closes (UX-DR6)', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })

    // Held open so the upload is genuinely still in flight at unmount,
    // then resolved afterwards. Guards UX-DR6 against a future "cleanup"
    // that adds xhr.abort() on unmount: the upload must survive the close
    // and still write its row, which the parent picks up on refetch.
    let resolveUpload
    let abortCalled = false
    const uploadSpy = vi.spyOn(documentsClient, 'uploadDocument').mockImplementation(() => {
      const promise = new Promise((resolve) => { resolveUpload = resolve })
      promise.abort = () => { abortCalled = true }
      return promise
    })
    const user = userEvent.setup()

    const { unmount } = render(<UploadModal onClose={vi.fn()} />)
    await user.upload(screen.getByLabelText(/choose files to upload/i), makeFile('slow.pdf'))
    await screen.findByRole('progressbar', { name: /slow\.pdf/i })

    unmount()
    resolveUpload({ id: 'doc-1' })
    await Promise.resolve()

    expect(uploadSpy).toHaveBeenCalledTimes(1)
    expect(abortCalled).toBe(false)
  })
})

describe('UploadModal duplicate handling (Story 2.6)', () => {
  it('shows "Already uploaded" and links to the existing document when is_duplicate is true', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockResolvedValue({
      id: 'existing-doc-1',
      status: 'Uploaded',
      is_duplicate: true,
    })
    const user = userEvent.setup()

    renderModal({ onClose: vi.fn() })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, makeFile('report.pdf'))

    expect(await screen.findByText(/already uploaded/i)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /view document/i })
    expect(link).toHaveAttribute('href', '/documents/existing-doc-1')
  })

  it('does not show the duplicate message for a genuinely new upload', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockResolvedValue({
      id: 'new-doc-1',
      status: 'Uploaded',
      is_duplicate: false,
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, makeFile('report.pdf'))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(screen.queryByText(/already uploaded/i)).not.toBeInTheDocument()
  })

  it('does NOT auto-close a single duplicate upload -- the user must see the message', async () => {
    // Regression test for a real bug report: a lone duplicate upload was
    // closing the modal the instant the request resolved, so the
    // "Already uploaded" message and its link were never visible. A
    // duplicate result must behave like an error for auto-close purposes
    // (settled, but not "good enough to auto-close") even though it's a
    // perfectly normal, expected outcome -- not a failure.
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockResolvedValue({
      id: 'existing-doc-2',
      status: 'Uploaded',
      is_duplicate: true,
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, makeFile('report.pdf'))

    await screen.findByText(/already uploaded/i)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not auto-close an all-duplicate batch', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockResolvedValue({
      id: 'existing-doc-2',
      status: 'Uploaded',
      is_duplicate: true,
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, [makeFile('a.pdf'), makeFile('b.pdf')])

    await waitFor(() => {
      expect(screen.getAllByText(/already uploaded/i)).toHaveLength(2)
    })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not auto-close a mixed duplicate+error batch', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockImplementation((_token, file) => {
      if (file.name === 'fails.pdf') return Promise.reject(new Error('Upload failed (500).'))
      return Promise.resolve({ id: 'existing-doc-3', status: 'Uploaded', is_duplicate: true })
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, [makeFile('fails.pdf'), makeFile('dup.pdf')])

    await waitFor(() => {
      expect(screen.getByText(/already uploaded/i)).toBeInTheDocument()
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('still auto-closes a batch with at least one genuinely new upload alongside a duplicate', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockImplementation((_token, file) => {
      if (file.name === 'dup.pdf') {
        return Promise.resolve({ id: 'existing-doc-4', status: 'Uploaded', is_duplicate: true })
      }
      return Promise.resolve({ id: 'new-doc-2', status: 'Uploaded', is_duplicate: false })
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, [makeFile('new.pdf'), makeFile('dup.pdf')])

    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('a Cancel click still closes an all-duplicate batch', async () => {
    useAuth.mockReturnValue({ token: 'a-token' })
    vi.spyOn(documentsClient, 'uploadDocument').mockResolvedValue({
      id: 'existing-doc-5',
      status: 'Uploaded',
      is_duplicate: true,
    })
    const onClose = vi.fn()
    const user = userEvent.setup()

    renderModal({ onClose })

    const input = screen.getByLabelText(/choose files to upload/i)
    await user.upload(input, makeFile('report.pdf'))
    await screen.findByText(/already uploaded/i)

    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
