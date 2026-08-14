import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentCard from './DocumentCard'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

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

function renderCard(props = {}) {
  const onCardClick = props.onCardClick ?? vi.fn()
  const onDeleted = props.onDeleted ?? vi.fn()
  return {
    onCardClick,
    onDeleted,
    ...render(
      <MemoryRouter>
        <ul>
          <DocumentCard document={DOC} onCardClick={onCardClick} onDeleted={onDeleted} />
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
    expect(within(box).getByText(/removed from search immediately/)).toBeInTheDocument()
    expect(
      within(box).getByText(/remain and may still influence future answers/),
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

    const boundaryText = screen.getByText(/removed from search immediately/)
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
