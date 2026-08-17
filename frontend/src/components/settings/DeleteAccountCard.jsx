import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { deleteAccount } from '../../api/settingsClient'

// Story 5.3: wires up Story 5.1's danger-zone shell with the real cascade
// delete. Mirrors DocumentCard.jsx's confirm state machine exactly --
// isConfirming/isDeleting/error local state, an inline `role="alert"` box
// (no modal), focus moving to Cancel on open, Escape and Cancel both
// closing it without interrupting an in-flight delete, and a failed
// request re-enabling the box for retry (Boundaries).
const DELETE_ACCOUNT_BOUNDARY_TEXT =
  'Permanently deletes your account, every document you uploaded, and everything extracted from them. This cannot be undone.'

export default function DeleteAccountCard() {
  const { authFetch, logout } = useAuth()
  const navigate = useNavigate()

  const [isConfirming, setIsConfirming] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState(null)

  const deleteButtonRef = useRef(null)
  const cancelButtonRef = useRef(null)
  // The trigger button stays mounted the whole time (hidden via CSS
  // `hidden`, not removed from the tree) -- like DocumentCard.jsx's trash
  // button -- so its ref is always non-null. But a `display:none` element
  // can't take focus in a real browser (jsdom is lenient about this and
  // won't catch it): calling `.focus()` synchronously in the same handler
  // that just called `setIsConfirming(false)` would still target the
  // element from *before* the re-render removes `hidden`. This flag defers
  // the focus call to the effect below, which runs after that re-render.
  const shouldFocusTriggerRef = useRef(false)

  const boundaryTextId = 'delete-account-boundary'

  // Focus moves into the box on open, to Cancel -- the safer default for a
  // destructive action (Design Notes, UX-DR26), same as DocumentCard.jsx.
  useEffect(() => {
    if (isConfirming) cancelButtonRef.current?.focus()
  }, [isConfirming])

  useEffect(() => {
    if (isConfirming || !shouldFocusTriggerRef.current) return
    deleteButtonRef.current?.focus()
    shouldFocusTriggerRef.current = false
  }, [isConfirming])

  function openConfirm() {
    setError(null)
    setIsConfirming(true)
  }

  // Escape and Cancel both collapse back to the resting state and return
  // focus to the control that opened the box -- but only on a non-deleting
  // close; a delete already in flight isn't interrupted by either.
  function collapseConfirm() {
    if (isDeleting) return
    shouldFocusTriggerRef.current = true
    setIsConfirming(false)
    setError(null)
  }

  function handleConfirmBoxKeyDown(event) {
    if (event.key !== 'Escape') return
    collapseConfirm()
  }

  function handleCancel() {
    collapseConfirm()
  }

  async function handleConfirmDelete() {
    // Guards the rapid-double-click case (I/O matrix): `aria-disabled`
    // (not the native `disabled` attribute, matching this card's
    // pre-Story-5.3 inert-button convention) keeps the control focusable
    // and announced while a delete is in flight -- this in-handler check
    // is what actually keeps a second click from firing a second request.
    if (isDeleting) return
    setIsDeleting(true)
    setError(null)
    try {
      await deleteAccount(authFetch)
      // Success (204): log out immediately and leave the authenticated
      // shell -- mirrors Shell.jsx's own Exit handler (logout() then
      // navigate('/login', { replace: true })).
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      // On failure: error shown, confirm box stays open for retry (I/O
      // matrix) -- focus is left where it is rather than forced anywhere.
      setError(err.message)
      setIsDeleting(false)
    }
  }

  return (
    <div className="rounded-lg border border-danger/30 bg-danger/5 p-[22px]">
      <h2 className="text-base font-bold text-text">Delete Account</h2>
      <p className="mt-2 text-sm text-text">
        Permanently delete your account and all associated documents. This action cannot be undone.
      </p>

      {/* Stays mounted whether resting or confirming -- like
          DocumentCard.jsx's trash button -- so `deleteButtonRef` is never
          null when `collapseConfirm` refocuses it. `hidden` (not removal
          from the tree) is what actually hides it while the box is open. */}
      <button
        ref={deleteButtonRef}
        type="button"
        aria-expanded={isConfirming}
        onClick={openConfirm}
        className={`mt-4 self-start rounded-md border border-border bg-card-bg px-3 py-1.5 text-sm text-danger ${isConfirming ? 'hidden' : ''}`}
      >
        Delete Account
      </button>

      {isConfirming && (
        // Inline confirm box (UX-DR14): no modal, built from scratch, same
        // shape as DocumentCard.jsx's own confirm box.
        <div
          role="alert"
          onKeyDown={handleConfirmBoxKeyDown}
          className="mt-4 flex flex-col gap-2 rounded-md border border-danger/30 bg-card-bg p-2.5"
        >
          <p id={boundaryTextId} className="text-xs text-text">
            {DELETE_ACCOUNT_BOUNDARY_TEXT}
          </p>
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              ref={cancelButtonRef}
              type="button"
              aria-describedby={boundaryTextId}
              onClick={handleCancel}
              disabled={isDeleting}
              className="rounded-md border border-border bg-card-bg px-2.5 py-1 text-xs font-semibold text-primary"
            >
              Cancel
            </button>
            <button
              type="button"
              aria-describedby={boundaryTextId}
              aria-disabled={isDeleting}
              onClick={handleConfirmDelete}
              className="rounded-md border border-border bg-card-bg px-2.5 py-1 text-xs font-semibold text-danger"
            >
              {isDeleting ? 'Deleting…' : 'Delete My Account'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
