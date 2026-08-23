import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GraphScopePanel from './GraphScopePanel'
import * as documentsClient from '../../api/documentsClient'
import * as foldersClient from '../../api/foldersClient'

afterEach(() => {
  vi.restoreAllMocks()
})

const DOCS = [
  { id: 'doc-1', filename: 'Team_Directory.md', folder_id: 'folder-1' },
  { id: 'doc-2', filename: 'Project_Aurora.md', folder_id: 'folder-1' },
  { id: 'doc-3', filename: 'Vendor.pdf', folder_id: null },
]
const FOLDERS = [{ id: 'folder-1', name: 'TEST', color: '#000' }]

function renderPanel(overrides = {}) {
  const props = {
    authFetch: vi.fn(),
    selectedDocumentIds: [],
    onToggleDocument: vi.fn(),
    onSelectAll: vi.fn(),
    onToggleFolder: vi.fn(),
    ...overrides,
  }
  const utils = render(<GraphScopePanel {...props} />)
  return { ...utils, props }
}

describe('GraphScopePanel', () => {
  it('groups documents by folder, with an Ungrouped bucket for those without one', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)

    renderPanel()

    expect(await screen.findByText('TEST')).toBeInTheDocument()
    expect(screen.getByText('Ungrouped')).toBeInTheDocument()
    expect(screen.getByText('Team_Directory.md')).toBeInTheDocument()
    expect(screen.getByText('Vendor.pdf')).toBeInTheDocument()
  })

  it('renders each folder collapsed by default, not showing every document at once', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)

    renderPanel()

    const summary = await screen.findByText('TEST')
    const details = summary.closest('details')
    expect(details).not.toBeNull()
    expect(details.open).toBe(false)
  })

  it('expands a folder on clicking its name, without an "Apply" step', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    renderPanel()

    const summary = await screen.findByText('TEST')
    await user.click(summary)

    expect(summary.closest('details').open).toBe(true)
  })

  it('clicking a checkbox calls onToggleDocument with that document\'s id', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    const { props } = renderPanel()

    const checkbox = await screen.findByLabelText('Vendor.pdf')
    await user.click(checkbox)

    expect(props.onToggleDocument).toHaveBeenCalledWith('doc-3')
  })

  it('"Select folder" calls onToggleFolder with every document id in that folder, and does not toggle the disclosure open/closed', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    const { props } = renderPanel()

    const summary = await screen.findByText('TEST')
    const groupRow = summary.closest('.flex.items-start.gap-2')
    const details = summary.closest('details')
    expect(details.open).toBe(false)

    await user.click(within(groupRow).getByRole('button', { name: 'Select folder' }))

    expect(props.onToggleFolder).toHaveBeenCalledWith(['doc-1', 'doc-2'], true)
    // A button click sitting outside <summary> must not also flip the
    // disclosure -- selecting a folder's documents shouldn't force it open.
    expect(details.open).toBe(false)
  })

  it('shows "Clear folder" and a shouldSelect=false toggle once every document in that folder is selected', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    const { props } = renderPanel({ selectedDocumentIds: ['doc-1', 'doc-2'] })

    const summary = await screen.findByText('TEST')
    const groupRow = summary.closest('.flex.items-start.gap-2')
    await user.click(within(groupRow).getByRole('button', { name: 'Clear folder' }))

    expect(props.onToggleFolder).toHaveBeenCalledWith(['doc-1', 'doc-2'], false)
  })

  it('"Select all" calls onSelectAll with every document id', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    const { props } = renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Select all' }))

    expect(props.onSelectAll).toHaveBeenCalledWith(['doc-1', 'doc-2', 'doc-3'])
  })

  it('becomes "Clear all" once every document is selected, and clears the selection on click', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)
    const user = userEvent.setup()

    const { props } = renderPanel({ selectedDocumentIds: ['doc-1', 'doc-2', 'doc-3'] })

    const button = await screen.findByRole('button', { name: 'Clear all' })
    await user.click(button)

    expect(props.onSelectAll).toHaveBeenCalledWith([])
  })

  it('an all-unchecked selection reads as showing the graph across every document (OD-6 parity)', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)

    renderPanel()

    expect(await screen.findByText('Showing the graph across all 3 documents.')).toBeInTheDocument()
  })

  it('shows a partial-selection count once some documents are selected', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue(FOLDERS)

    renderPanel({ selectedDocumentIds: ['doc-1'] })

    expect(await screen.findByText('1 of 3 selected.')).toBeInTheDocument()
  })

  it('shows an empty-library message when there are no documents', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([])

    renderPanel()

    expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  })

  it('renders an alert on fetch failure', async () => {
    vi.spyOn(documentsClient, 'listDocuments').mockRejectedValue(new Error('Failed to load documents.'))
    vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([])

    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load documents.')
  })
})
