import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../context/AuthContext'
import { deleteAccount } from '../../api/settingsClient'
import SettingsSectionCard from './SettingsSectionCard'

// Story 5.3: wires up Story 5.1's danger-zone shell with the real cascade
// delete. Mirrors DocumentCard.jsx's confirm state machine exactly --
// isConfirming/isDeleting/error local state, an inline `role="alert"` box
// (no modal), focus moving to Cancel on open, Escape and Cancel both
// closing it without interrupting an in-flight delete, and a failed
// request re-enabling the box for retry (Boundaries).
export default function DeleteAccountCard() {
  const { t } = useTranslation()
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
    <SettingsSectionCard
      title={t('settings.deleteAccount.title')}
      description={t('settings.deleteAccount.description')}
      danger
      className="sm:col-span-2"
      icon={
        <>
          <path d="M4 7h16" />
          <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
          <path d="M6.5 7l1 12.5a2 2 0 0 0 2 1.8h5a2 2 0 0 0 2-1.8L17.5 7" />
          <path d="M10 11v6M14 11v6" />
        </>
      }
    >
      {/* Stays mounted whether resting or confirming -- like
          DocumentCard.jsx's trash button -- so `deleteButtonRef` is never
          null when `collapseConfirm` refocuses it. `hidden` (not removal
          from the tree) is what actually hides it while the box is open. */}
      <button
        ref={deleteButtonRef}
        type="button"
        aria-expanded={isConfirming}
        onClick={openConfirm}
        className={`self-start rounded-full border border-danger/40 bg-card-bg px-4 py-2 text-sm font-semibold text-danger hover:bg-danger/10 ${isConfirming ? 'hidden' : ''}`}
      >
        {t('settings.deleteAccount.button')}
      </button>

      {isConfirming && (
        // Inline confirm box (UX-DR14): no modal, built from scratch, same
        // shape as DocumentCard.jsx's own confirm box.
        <div
          role="alert"
          onKeyDown={handleConfirmBoxKeyDown}
          className="flex flex-col gap-3 rounded-xl border border-danger/30 bg-card-bg p-4"
        >
          <p id={boundaryTextId} className="text-sm text-text2">
            {t('settings.deleteAccount.boundaryText')}
          </p>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2.5">
            <button
              ref={cancelButtonRef}
              type="button"
              aria-describedby={boundaryTextId}
              onClick={handleCancel}
              disabled={isDeleting}
              className="rounded-full border border-border bg-card-bg px-4 py-2 text-sm font-semibold text-text disabled:opacity-60"
            >
              {t('settings.deleteAccount.cancel')}
            </button>
            <button
              type="button"
              aria-describedby={boundaryTextId}
              aria-disabled={isDeleting}
              onClick={handleConfirmDelete}
              className="rounded-full bg-danger px-4 py-2 text-sm font-semibold text-white hover:brightness-105"
            >
              {isDeleting ? t('settings.deleteAccount.deleting') : t('settings.deleteAccount.confirm')}
            </button>
          </div>
        </div>
      )}
    </SettingsSectionCard>
  )
}
