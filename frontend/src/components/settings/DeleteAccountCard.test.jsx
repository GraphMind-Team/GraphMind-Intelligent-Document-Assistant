import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DeleteAccountCard from './DeleteAccountCard'
import { useAuth } from '../../context/AuthContext'
import { deleteAccount } from '../../api/settingsClient'

// Story 5.3: the Delete Account danger-zone card's confirm state machine
// and the real cascade-delete wiring -- styled on AppearanceCard.test.jsx,
// with the confirm-box interaction coverage mirroring
// DocumentCard.test.jsx's own delete-confirm tests (Story 2.7's
// precedent this card is built to match).

vi.mock('../../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/settingsClient', () => ({ deleteAccount: vi.fn() }))

// `vi.restoreAllMocks()` only restores spies created via `vi.spyOn` -- it
// does not reset call history on a bare `vi.fn()` from a `vi.mock(...)`
// factory (like `deleteAccount` and `useAuth` above), so it would leak
// call counts across tests. `vi.clearAllMocks()` is what AppearanceCard.test.jsx
// uses for the same reason.
beforeEach(() => {
  vi.clearAllMocks()
})

const authFetch = vi.fn()

function renderCard({ initialEntries = ['/settings'] } = {}) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/settings" element={<DeleteAccountCard />} />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function openConfirm(user) {
  await user.click(screen.getByRole('button', { name: 'Delete Account' }))
}

describe('DeleteAccountCard', () => {
  it('shows an inline confirm box on click, without deleting anything yet', async () => {
    const logout = vi.fn()
    useAuth.mockReturnValue({ authFetch, logout })
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    const box = screen.getByRole('alert')
    expect(box).toHaveTextContent(/Permanently deletes your account/)
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeInTheDocument()
    expect(deleteAccount).not.toHaveBeenCalled()
  })

  it('moves focus to Cancel when the confirm box opens (the safer default)', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('ties the boundary text to both Cancel and Confirm via aria-describedby', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)

    const boundaryText = screen.getByText(/Permanently deletes your account/)
    expect(boundaryText).toHaveAttribute('id')
    const boundaryId = boundaryText.getAttribute('id')

    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveAttribute(
      'aria-describedby',
      boundaryId,
    )
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toHaveAttribute(
      'aria-describedby',
      boundaryId,
    )
  })

  it('Cancel collapses the box and returns focus to the Delete Account button', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    const trigger = screen.getByRole('button', { name: 'Delete Account' })
    await openConfirm(user)

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('Escape collapses the box the same way Cancel does', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    const user = userEvent.setup()

    renderCard()
    const trigger = screen.getByRole('button', { name: 'Delete Account' })
    await openConfirm(user)

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('Confirm calls deleteAccount, logs out, and navigates to /login on success', async () => {
    const logout = vi.fn()
    useAuth.mockReturnValue({ authFetch, logout })
    deleteAccount.mockResolvedValue(undefined)
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)
    await user.click(screen.getByRole('button', { name: 'Delete My Account' }))

    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
    expect(deleteAccount).toHaveBeenCalledWith(authFetch)
    expect(logout).toHaveBeenCalledOnce()
  })

  it('on failure, shows the error inline and keeps the confirm box open for retry', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    deleteAccount.mockRejectedValue(new Error("Document is still being processed and can't be deleted yet."))
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)
    await user.click(screen.getByRole('button', { name: 'Delete My Account' }))

    expect(
      await screen.findByText("Document is still being processed and can't be deleted yet."),
    ).toBeInTheDocument()
    // Still on the settings card, not navigated away, and still open for retry.
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete My Account' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('a second click while deleting is in flight does not fire a second request', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    let resolveDelete
    deleteAccount.mockReturnValue(
      new Promise((resolve) => {
        resolveDelete = resolve
      }),
    )
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)
    const confirmButton = screen.getByRole('button', { name: 'Delete My Account' })

    await user.click(confirmButton)
    expect(confirmButton).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Deleting…')).toBeInTheDocument()

    // Second click while the first request is still in flight.
    await user.click(confirmButton)
    expect(deleteAccount).toHaveBeenCalledTimes(1)

    resolveDelete(undefined)
    await waitFor(() => expect(screen.getByText('Login page')).toBeInTheDocument())
  })

  it('Cancel is disabled (not interrupted) while a delete is in flight', async () => {
    useAuth.mockReturnValue({ authFetch, logout: vi.fn() })
    deleteAccount.mockReturnValue(new Promise(() => {})) // never resolves in this test
    const user = userEvent.setup()

    renderCard()
    await openConfirm(user)
    await user.click(screen.getByRole('button', { name: 'Delete My Account' }))

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })
})
