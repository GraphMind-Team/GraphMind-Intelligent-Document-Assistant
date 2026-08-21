import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import FolderModal from './FolderModal'
import { useAuth } from '../context/AuthContext'
import * as foldersClient from '../api/foldersClient'

// Folder-grouping feature: single dialog reused for both create and edit,
// built on UploadModal.jsx's dialog shape -- mirrors UploadModal.test.jsx's
// own accessibility coverage (labelled dialog, initial focus, focus
// return, Escape/Cancel) plus the create/edit/error-retry behavior
// specific to this dialog.

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

const EXISTING_FOLDER = { id: 'folder-1', name: 'Contracts', color: 'mint', created_at: '2026-08-10T00:00:00Z' }

describe('FolderModal accessibility', () => {
  it('renders as a labelled modal dialog with initial focus on the name field, in create mode', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })

    render(<FolderModal folder={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    const dialog = screen.getByRole('dialog', { name: /new folder/i })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('Name')).toHaveFocus()
  })

  it('returns focus to whatever was focused before it opened, on unmount', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const trigger = document.createElement('button')
    trigger.textContent = 'New folder'
    document.body.appendChild(trigger)
    trigger.focus()

    const { unmount } = render(<FolderModal folder={null} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(document.activeElement).not.toBe(trigger)

    unmount()
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })

  it('closes on Escape', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<FolderModal folder={null} onClose={onClose} onSaved={vi.fn()} />)

    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on explicit Cancel', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<FolderModal folder={null} onClose={onClose} onSaved={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('FolderModal create', () => {
  it('renders "New folder" with an empty name and the first color preselected', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })

    render(<FolderModal folder={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    expect(screen.getByLabelText('Name')).toHaveValue('')
    expect(screen.getByRole('radio', { name: 'rose' })).toHaveAttribute('aria-checked', 'true')
  })

  it('disables Save while the name is blank', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })

    render(<FolderModal folder={null} onClose={vi.fn()} onSaved={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('calls createFolder with the entered name and selected color, then onSaved and onClose', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const createSpy = vi
      .spyOn(foldersClient, 'createFolder')
      .mockResolvedValue({ id: 'new-folder', name: 'Reports', color: 'sky', created_at: '2026-08-21T00:00:00Z' })
    const onClose = vi.fn()
    const onSaved = vi.fn()
    const user = userEvent.setup()

    render(<FolderModal folder={null} onClose={onClose} onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Name'), 'Reports')
    await user.click(screen.getByRole('radio', { name: 'sky' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({
      id: 'new-folder',
      name: 'Reports',
      color: 'sky',
      created_at: '2026-08-21T00:00:00Z',
    }))
    expect(createSpy).toHaveBeenCalledWith(authFetch, { name: 'Reports', color: 'sky' })
    expect(onClose).toHaveBeenCalled()
  })

  it('on failure, shows the error inline and keeps the dialog open for retry', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(foldersClient, 'createFolder').mockRejectedValue(new Error('Folder name must not be blank.'))
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(<FolderModal folder={null} onClose={onClose} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Name'), 'x')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByText('Folder name must not be blank.')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })
})

describe('FolderModal edit', () => {
  it('renders "Edit folder" pre-filled with the existing name and color', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })

    render(<FolderModal folder={EXISTING_FOLDER} onClose={vi.fn()} onSaved={vi.fn()} />)

    expect(screen.getByRole('dialog', { name: /edit folder/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Contracts')
    expect(screen.getByRole('radio', { name: 'mint' })).toHaveAttribute('aria-checked', 'true')
  })

  it('calls updateFolder with the folder id and edited fields', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const updateSpy = vi
      .spyOn(foldersClient, 'updateFolder')
      .mockResolvedValue({ ...EXISTING_FOLDER, name: 'Renamed', color: 'lilac' })
    const onSaved = vi.fn()
    const user = userEvent.setup()

    render(<FolderModal folder={EXISTING_FOLDER} onClose={vi.fn()} onSaved={onSaved} />)

    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Renamed')
    await user.click(screen.getByRole('radio', { name: 'lilac' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(updateSpy).toHaveBeenCalledWith(authFetch, 'folder-1', { name: 'Renamed', color: 'lilac' })
  })
})
