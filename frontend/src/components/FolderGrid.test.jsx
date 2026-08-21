import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import FolderGrid, { ALL_DOCUMENTS_FILTER, UNGROUPED_FILTER } from './FolderGrid'
import { useAuth } from '../context/AuthContext'
import * as foldersClient from '../api/foldersClient'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

// `FolderGrid` itself calls `useAuth()` (for the drop-target handler,
// Round 2), not just its nested `FolderTile` -- every test needs this
// mocked, not only the ones that render a real folder tile.
beforeEach(() => {
  useAuth.mockReturnValue({ authFetch: vi.fn() })
})

afterEach(() => {
  vi.restoreAllMocks()
})

const FOLDER_A = { id: 'folder-a', name: 'Contracts', color: 'mint', created_at: '2026-08-10T00:00:00Z' }
const FOLDER_B = { id: 'folder-b', name: 'Invoices', color: 'sky', created_at: '2026-08-11T00:00:00Z' }

const DOC_UNGROUPED = { id: 'doc-1', folder_id: null }
const DOC_IN_A = { id: 'doc-2', folder_id: 'folder-a' }
const DOC_ALSO_IN_A = { id: 'doc-3', folder_id: 'folder-a' }

// Testing Library's documented HTML5 DnD pattern: a plain stub object
// (jsdom doesn't implement the real `DataTransfer`), reused across the
// `dragStart`/`drop` pair the same way a browser reuses one `DataTransfer`
// for the whole gesture.
function makeDataTransfer(documentId) {
  const store = {}
  if (documentId !== undefined) store['text/plain'] = documentId
  return {
    setData: (type, value) => {
      store[type] = value
    },
    getData: (type) => store[type] ?? '',
    effectAllowed: null,
  }
}

function renderGrid(props = {}) {
  const onSelectFilter = props.onSelectFilter ?? vi.fn()
  const onFolderCreated = props.onFolderCreated ?? vi.fn()
  const onFolderUpdated = props.onFolderUpdated ?? vi.fn()
  const onFolderDeleted = props.onFolderDeleted ?? vi.fn()
  const onDocumentFolderChanged = props.onDocumentFolderChanged ?? vi.fn()
  return {
    onSelectFilter,
    onFolderCreated,
    onFolderUpdated,
    onFolderDeleted,
    onDocumentFolderChanged,
    ...render(
      <FolderGrid
        folders={props.folders ?? []}
        documents={props.documents ?? []}
        activeFilter={props.activeFilter ?? ALL_DOCUMENTS_FILTER}
        onSelectFilter={onSelectFilter}
        onFolderCreated={onFolderCreated}
        onFolderUpdated={onFolderUpdated}
        onFolderDeleted={onFolderDeleted}
        onDocumentFolderChanged={onDocumentFolderChanged}
      />,
    ),
  }
}

describe('FolderGrid: fixed tiles', () => {
  it('with no folders, shows only "All documents" and "Ungrouped" (no empty folder tiles)', () => {
    renderGrid({ documents: [DOC_UNGROUPED] })

    expect(screen.getByRole('button', { name: /all documents/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ungrouped/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /contracts/i })).not.toBeInTheDocument()
  })

  it('computes "All documents" and "Ungrouped" counts client-side from the document list', () => {
    renderGrid({ documents: [DOC_UNGROUPED, DOC_IN_A, DOC_ALSO_IN_A], folders: [FOLDER_A] })

    expect(within(screen.getByRole('button', { name: /all documents/i })).getByText('3 documents')).toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: /ungrouped/i })).getByText('1 document')).toBeInTheDocument()
  })

  it('marks the active fixed tile with aria-pressed', () => {
    renderGrid({ activeFilter: UNGROUPED_FILTER })

    expect(screen.getByRole('button', { name: /all documents/i })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: /ungrouped/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('selecting "Ungrouped" calls onSelectFilter with the ungrouped sentinel', async () => {
    const user = userEvent.setup()
    const { onSelectFilter } = renderGrid()

    await user.click(screen.getByRole('button', { name: /ungrouped/i }))

    expect(onSelectFilter).toHaveBeenCalledWith(UNGROUPED_FILTER)
  })
})

describe('FolderGrid: real folder tiles', () => {
  it('renders one tile per folder with its name and document count', () => {
    renderGrid({ folders: [FOLDER_A, FOLDER_B], documents: [DOC_IN_A, DOC_ALSO_IN_A] })

    const contractsTile = screen.getByRole('button', { name: /^Contracts,/ })
    expect(within(contractsTile).getByText('2 documents')).toBeInTheDocument()

    const invoicesTile = screen.getByRole('button', { name: /^Invoices,/ })
    expect(within(invoicesTile).getByText('0 documents')).toBeInTheDocument()
  })

  it('selecting a folder tile calls onSelectFilter with that folder\'s id', async () => {
    const user = userEvent.setup()
    const { onSelectFilter } = renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: /^Contracts,/ }))

    expect(onSelectFilter).toHaveBeenCalledWith('folder-a')
  })

  it('marks the active folder tile with aria-pressed', () => {
    renderGrid({ folders: [FOLDER_A, FOLDER_B], activeFilter: 'folder-a' })

    expect(screen.getByRole('button', { name: /^Contracts,/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /^Invoices,/ })).toHaveAttribute('aria-pressed', 'false')
  })
})

describe('FolderGrid: create', () => {
  it('opens FolderModal in create mode from the "+ New folder" tile, and reports the new folder on save', async () => {
    vi.spyOn(foldersClient, 'createFolder').mockResolvedValue({
      id: 'new-folder',
      name: 'Reports',
      color: 'sun',
      created_at: '2026-08-21T00:00:00Z',
    })
    const user = userEvent.setup()
    const { onFolderCreated } = renderGrid()

    await user.click(screen.getByRole('button', { name: /new folder/i }))
    expect(screen.getByRole('dialog', { name: /new folder/i })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Name'), 'Reports')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(onFolderCreated).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'new-folder', name: 'Reports' }),
      ),
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('FolderGrid: edit', () => {
  it('opens FolderModal in edit mode pre-filled from the tile\'s Edit icon, and reports the update on save', async () => {
    vi.spyOn(foldersClient, 'updateFolder').mockResolvedValue({ ...FOLDER_A, name: 'Renamed' })
    const user = userEvent.setup()
    const { onFolderUpdated } = renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: 'Edit Contracts' }))
    expect(screen.getByRole('dialog', { name: /edit folder/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Contracts')

    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Renamed')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(onFolderUpdated).toHaveBeenCalledWith(expect.objectContaining({ name: 'Renamed' })),
    )
  })
})

describe('FolderGrid: delete', () => {
  it('shows an inline confirm box on the delete icon, without deleting anything yet', async () => {
    const deleteSpy = vi.spyOn(foldersClient, 'deleteFolder')
    const user = userEvent.setup()
    renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('Cancel collapses the confirm box without deleting', async () => {
    const deleteSpy = vi.spyOn(foldersClient, 'deleteFolder')
    const user = userEvent.setup()
    renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('Confirm calls deleteFolder and reports the deletion up', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const deleteSpy = vi.spyOn(foldersClient, 'deleteFolder').mockResolvedValue(undefined)
    const user = userEvent.setup()
    const { onFolderDeleted } = renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onFolderDeleted).toHaveBeenCalledWith('folder-a'))
    expect(deleteSpy).toHaveBeenCalledWith(authFetch, 'folder-a')
  })

  it('when the deleted folder was the active filter, also resets the filter to "All documents"', async () => {
    vi.spyOn(foldersClient, 'deleteFolder').mockResolvedValue(undefined)
    const user = userEvent.setup()
    const { onSelectFilter } = renderGrid({ folders: [FOLDER_A], activeFilter: 'folder-a' })

    await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onSelectFilter).toHaveBeenCalledWith(ALL_DOCUMENTS_FILTER))
  })

  it('on failure, shows the error inline and keeps the confirm box for retry', async () => {
    vi.spyOn(foldersClient, 'deleteFolder').mockRejectedValue(new Error('Folder not found.'))
    const user = userEvent.setup()
    const { onFolderDeleted } = renderGrid({ folders: [FOLDER_A] })

    await user.click(screen.getByRole('button', { name: 'Delete Contracts' }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Folder not found.')).toBeInTheDocument()
    expect(onFolderDeleted).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })
})

// Round 2 (Spec Change Log): "drag doc onto a folder tile" -- moves the
// dragged document into that folder directly, no dialog (the spec's I/O
// matrix). Simulated via `fireEvent.dragOver`/`drop` with a stub
// `dataTransfer`, per Testing Library's documented DnD pattern (jsdom has
// no real `DataTransfer`).
describe('FolderGrid: drag a document onto a folder tile', () => {
  it('assigns the dragged document to that folder directly, with no dialog', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const updateSpy = vi
      .spyOn(documentsClient, 'updateDocumentFolder')
      .mockResolvedValue({ id: 'doc-1', folder_id: 'folder-a' })
    const { onDocumentFolderChanged } = renderGrid({ folders: [FOLDER_A] })

    const tile = screen.getByRole('button', { name: /^Contracts,/ }).closest('div')
    const dataTransfer = makeDataTransfer('doc-1')
    fireEvent.dragOver(tile, { dataTransfer })
    fireEvent.drop(tile, { dataTransfer })

    await waitFor(() => expect(onDocumentFolderChanged).toHaveBeenCalledWith('doc-1', 'folder-a'))
    expect(updateSpy).toHaveBeenCalledWith(authFetch, 'doc-1', 'folder-a')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does nothing when the drop carries no dragged-document data', async () => {
    const updateSpy = vi.spyOn(documentsClient, 'updateDocumentFolder')
    renderGrid({ folders: [FOLDER_A] })

    const tile = screen.getByRole('button', { name: /^Contracts,/ }).closest('div')
    const dataTransfer = makeDataTransfer()
    fireEvent.dragOver(tile, { dataTransfer })
    fireEvent.drop(tile, { dataTransfer })

    expect(updateSpy).not.toHaveBeenCalled()
  })

  it('on failure, shows an inline error naming the failure', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'updateDocumentFolder').mockRejectedValue(new Error('Document not found.'))
    const { onDocumentFolderChanged } = renderGrid({ folders: [FOLDER_A] })

    const tile = screen.getByRole('button', { name: /^Contracts,/ }).closest('div')
    const dataTransfer = makeDataTransfer('doc-1')
    fireEvent.dragOver(tile, { dataTransfer })
    fireEvent.drop(tile, { dataTransfer })

    expect(await screen.findByText('Document not found.')).toBeInTheDocument()
    expect(onDocumentFolderChanged).not.toHaveBeenCalled()
  })
})
