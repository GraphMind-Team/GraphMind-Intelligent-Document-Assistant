import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentCard from './DocumentCard'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'
import * as foldersClient from '../api/foldersClient'

const FOLDER_A = { id: 'folder-a', name: 'Contracts', color: 'mint', created_at: '2026-08-10T00:00:00Z' }
const FOLDER_B = { id: 'folder-b', name: 'Invoices', color: 'sky', created_at: '2026-08-11T00:00:00Z' }

// Story 2.7: the trash button's inline confirm box, and the delete call
// it fires on Confirm -- DocumentsPage.test.jsx already covers the
// click-anywhere-navigates-except-the-trash-icon behavior that predates
// this story, so this file focuses on what's new: the confirm box itself,
// its a11y wiring (UX-DR26), and the Confirm/Cancel/Escape interactions.

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
})

const DOC = {
  id: 'doc-1',
  filename: 'vendor-agreement.pdf',
  file_type: 'pdf',
  file_size_bytes: 2048,
  status: 'Ready',
  created_at: '2026-08-10T12:00:00Z',
}

// Testing Library's documented HTML5 DnD pattern: a plain stub object
// (jsdom doesn't implement the real `DataTransfer`), reused across a
// `dragStart`/`drop` pair the same way a browser reuses one `DataTransfer`
// for the whole gesture.
function makeDataTransfer(documentId) {
  const store = {}
  if (documentId !== undefined) store['text/plain'] = documentId
  return {
    setData: vi.fn((type, value) => {
      store[type] = value
    }),
    getData: (type) => store[type] ?? '',
    effectAllowed: null,
  }
}

function renderCard(props = {}) {
  const onCardClick = props.onCardClick ?? vi.fn()
  const onDeleted = props.onDeleted ?? vi.fn()
  const onFolderChanged = props.onFolderChanged ?? vi.fn()
  const onFolderCreated = props.onFolderCreated ?? vi.fn()
  const document = props.document ?? DOC
  return {
    onCardClick,
    onDeleted,
    onFolderChanged,
    onFolderCreated,
    ...render(
      <MemoryRouter>
        <ul>
          <DocumentCard
            document={document}
            onCardClick={onCardClick}
            onDeleted={onDeleted}
            folders={props.folders ?? []}
            onFolderChanged={onFolderChanged}
            onFolderCreated={onFolderCreated}
          />
        </ul>
      </MemoryRouter>,
    ),
  }
}

async function openConfirm(user) {
  await user.click(screen.getByRole('button', { name: `Delete ${DOC.filename}` }))
}

describe('DocumentCard delete', () => {
  it('shows an inline confirm box on trash click, without deleting anything yet', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const deleteSpy = vi.spyOn(documentsClient, 'deleteDocument')
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    const box = screen.getByRole('alert')
    expect(within(box).getByText(/Removes its passages/)).toBeInTheDocument()
    expect(
      within(box).getByText(/not shared with another document/),
    ).toBeInTheDocument()
    expect(within(box).getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(within(box).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(deleteSpy).not.toHaveBeenCalled()
  })

  it('moves focus to Cancel when the confirm box opens (the safer default)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('ties the boundary text to both Confirm and Cancel via aria-describedby', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    const boundaryText = screen.getByText(/Removes its passages/)
    expect(boundaryText).toHaveAttribute('id')
    const boundaryId = boundaryText.getAttribute('id')

    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveAttribute(
      'aria-describedby',
      boundaryId,
    )
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveAttribute(
      'aria-describedby',
      boundaryId,
    )
  })

  it('Cancel collapses the box and returns focus to the trash button', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    const trash = screen.getByRole('button', { name: `Delete ${DOC.filename}` })
    await openConfirm(user)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(trash).toHaveFocus()
  })

  it('Escape collapses the box the same way Cancel does', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    const trash = screen.getByRole('button', { name: `Delete ${DOC.filename}` })
    await openConfirm(user)

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(trash).toHaveFocus()
  })

  it('never navigates the card when interacting with the confirm box', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    const { onCardClick } = renderCard()
    await openConfirm(user)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCardClick).not.toHaveBeenCalled()
  })

  it('Confirm calls deleteDocument and onDeleted on success', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const deleteSpy = vi.spyOn(documentsClient, 'deleteDocument').mockResolvedValue(undefined)
    const user = userEvent.setup()

    const { onDeleted } = renderCard()
    await openConfirm(user)

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(DOC.id))
    expect(deleteSpy).toHaveBeenCalledWith(authFetch, DOC.id)
  })

  it('on failure, shows the error inline and keeps the row and confirm box for retry', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'deleteDocument').mockRejectedValue(new Error('Document not found.'))
    const user = userEvent.setup()

    const { onDeleted } = renderCard()
    await openConfirm(user)

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Document not found.')).toBeInTheDocument()
    expect(onDeleted).not.toHaveBeenCalled()
    // Still open for retry -- Confirm/Cancel remain available.
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })
})

// Round 2 (Spec Change Log): the native <select> is gone, replaced by a
// "⋮" menu -- the one new menu/popover primitive this project now has
// (the original "no new dropdown" boundary is explicitly struck).
describe('DocumentCard "⋮" move-to-folder menu', () => {
  async function openMenu(user) {
    await user.click(screen.getByRole('button', { name: `Move ${DOC.filename} to folder` }))
  }

  it('lists every folder plus a trailing "Create new folder" item, with no "Ungrouped" item for an already-ungrouped document', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard({ folders: [FOLDER_A, FOLDER_B] })
    await openMenu(user)

    const menu = screen.getByRole('menu', { name: 'Move to folder' })
    const items = within(menu).getAllByRole('menuitem')
    expect(items.map((item) => item.textContent)).toEqual(['Contracts', 'Invoices', 'Create new folder'])
  })

  it('includes an "Ungrouped" item first when the document already belongs to a folder', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard({ document: { ...DOC, folder_id: 'folder-a' }, folders: [FOLDER_A] })
    await openMenu(user)

    const menu = screen.getByRole('menu', { name: 'Move to folder' })
    const items = within(menu).getAllByRole('menuitem')
    expect(items.map((item) => item.textContent)).toEqual(['Ungrouped', 'Contracts', 'Create new folder'])
  })

  it('moves focus to the first menu item on open', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard({ folders: [FOLDER_A] })
    await openMenu(user)

    expect(screen.getByRole('menuitem', { name: 'Contracts' })).toHaveFocus()
  })

  it('Escape closes the menu and returns focus to the "⋮" button', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard({ folders: [FOLDER_A] })
    const menuButton = screen.getByRole('button', { name: `Move ${DOC.filename} to folder` })
    await openMenu(user)

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(menuButton).toHaveFocus()
  })

  it('an outside click closes the menu', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const user = userEvent.setup()

    renderCard({ folders: [FOLDER_A] })
    await openMenu(user)
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await user.click(document.body)

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('picking a folder calls updateDocumentFolder with that folder id, reports it via onFolderChanged, and closes the menu', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const updateSpy = vi
      .spyOn(documentsClient, 'updateDocumentFolder')
      .mockResolvedValue({ ...DOC, folder_id: 'folder-a' })
    const user = userEvent.setup()

    const { onFolderChanged } = renderCard({ folders: [FOLDER_A] })
    await openMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Contracts' }))

    await waitFor(() => expect(onFolderChanged).toHaveBeenCalledWith(DOC.id, 'folder-a'))
    expect(updateSpy).toHaveBeenCalledWith(authFetch, DOC.id, 'folder-a')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('picking "Ungrouped" calls updateDocumentFolder with null (unassigning)', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const updateSpy = vi
      .spyOn(documentsClient, 'updateDocumentFolder')
      .mockResolvedValue({ ...DOC, folder_id: null })
    const user = userEvent.setup()

    const { onFolderChanged } = renderCard({
      document: { ...DOC, folder_id: 'folder-a' },
      folders: [FOLDER_A],
    })
    await openMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Ungrouped' }))

    await waitFor(() => expect(onFolderChanged).toHaveBeenCalledWith(DOC.id, null))
    expect(updateSpy).toHaveBeenCalledWith(authFetch, DOC.id, null)
  })

  it('on failure, shows the error inline and reports nothing to the parent', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'updateDocumentFolder').mockRejectedValue(new Error('Folder not found.'))
    const user = userEvent.setup()

    const { onFolderChanged } = renderCard({ folders: [FOLDER_A] })
    await openMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Contracts' }))

    expect(await screen.findByText('Folder not found.')).toBeInTheDocument()
    expect(onFolderChanged).not.toHaveBeenCalled()
  })

  it('never navigates the card when the menu button or a menu item is clicked', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({ ...DOC, folder_id: 'folder-a' })
    const user = userEvent.setup()

    const { onCardClick } = renderCard({ folders: [FOLDER_A] })
    await openMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Contracts' }))

    expect(onCardClick).not.toHaveBeenCalled()
  })

  it('"Create new folder" opens FolderModal, and on save assigns the new folder to this document and reports it up', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(foldersClient, 'createFolder').mockResolvedValue({
      id: 'new-folder',
      name: 'Reports',
      color: 'sun',
      created_at: '2026-08-21T00:00:00Z',
    })
    const updateSpy = vi
      .spyOn(documentsClient, 'updateDocumentFolder')
      .mockResolvedValue({ ...DOC, folder_id: 'new-folder' })
    const user = userEvent.setup()

    const { onFolderCreated, onFolderChanged } = renderCard({ folders: [FOLDER_A] })
    await openMenu(user)
    await user.click(screen.getByRole('menuitem', { name: 'Create new folder' }))

    expect(screen.getByRole('dialog', { name: /new folder/i })).toBeInTheDocument()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()

    await user.type(screen.getByLabelText('Name'), 'Reports')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(onFolderCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'new-folder' })),
    )
    expect(updateSpy).toHaveBeenCalledTimes(1)
    expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), DOC.id, 'new-folder')
    await waitFor(() => expect(onFolderChanged).toHaveBeenCalledWith(DOC.id, 'new-folder'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

// Round 2 (Spec Change Log): native HTML5 drag-and-drop, no new
// dependency (the spec's Boundaries). Only this card is rendered in each
// test -- for the drop-side tests, the dragged document's id is supplied
// directly via the stub `dataTransfer`, the same way a real drag started
// by some other, unrendered card would have set it.
describe('DocumentCard drag-and-drop', () => {
  it('onDragStart writes this document\'s id into the dataTransfer', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    renderCard()

    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer()
    fireEvent.dragStart(card, { dataTransfer })

    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', DOC.id)
  })

  it('dropping onto a card that already belongs to a folder assigns the dragged document to that folder directly, no dialog', async () => {
    const authFetch = vi.fn()
    useAuth.mockReturnValue({ authFetch })
    const updateSpy = vi
      .spyOn(documentsClient, 'updateDocumentFolder')
      .mockResolvedValue({ id: 'dragged-doc', folder_id: 'folder-a' })

    const { onFolderChanged } = renderCard({ document: { ...DOC, folder_id: 'folder-a' } })
    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer('dragged-doc')
    fireEvent.dragOver(card, { dataTransfer })
    fireEvent.drop(card, { dataTransfer })

    await waitFor(() => expect(onFolderChanged).toHaveBeenCalledWith('dragged-doc', 'folder-a'))
    expect(updateSpy).toHaveBeenCalledWith(authFetch, 'dragged-doc', 'folder-a')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('dropping onto an ungrouped card opens the create-folder dialog, and confirming it assigns both documents', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(foldersClient, 'createFolder').mockResolvedValue({
      id: 'new-folder',
      name: 'Reports',
      color: 'sun',
      created_at: '2026-08-21T00:00:00Z',
    })
    const updateSpy = vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({})
    const user = userEvent.setup()

    const { onFolderCreated, onFolderChanged } = renderCard({
      document: { ...DOC, id: 'target-doc', folder_id: null },
    })
    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer('dragged-doc')
    fireEvent.dragOver(card, { dataTransfer })
    fireEvent.drop(card, { dataTransfer })

    expect(screen.getByRole('dialog', { name: /new folder/i })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Name'), 'Reports')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(onFolderCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'new-folder' })),
    )
    await waitFor(() => {
      expect(onFolderChanged).toHaveBeenCalledWith('dragged-doc', 'new-folder')
      expect(onFolderChanged).toHaveBeenCalledWith('target-doc', 'new-folder')
    })
    expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), 'dragged-doc', 'new-folder')
    expect(updateSpy).toHaveBeenCalledWith(expect.any(Function), 'target-doc', 'new-folder')
  })

  it('dropping a document onto itself is a no-op -- no request, no dialog', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const updateSpy = vi.spyOn(documentsClient, 'updateDocumentFolder')

    renderCard()
    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer(DOC.id)
    fireEvent.dragOver(card, { dataTransfer })
    fireEvent.drop(card, { dataTransfer })

    expect(updateSpy).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('a drop with no dragged-document data is a no-op', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    const updateSpy = vi.spyOn(documentsClient, 'updateDocumentFolder')

    renderCard()
    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer()
    fireEvent.dragOver(card, { dataTransfer })
    fireEvent.drop(card, { dataTransfer })

    expect(updateSpy).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('never navigates the card on a drop', () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'updateDocumentFolder').mockResolvedValue({})

    const { onCardClick } = renderCard({ document: { ...DOC, folder_id: 'folder-a' } })
    const card = screen.getByRole('listitem')
    const dataTransfer = makeDataTransfer('dragged-doc')
    fireEvent.dragOver(card, { dataTransfer })
    fireEvent.drop(card, { dataTransfer })

    expect(onCardClick).not.toHaveBeenCalled()
  })
})
