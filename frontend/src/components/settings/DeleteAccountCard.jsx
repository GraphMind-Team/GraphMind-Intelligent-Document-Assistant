// Story 5.1 ships only this static shell -- danger-tinted per
// DocumentCard.jsx's `border-danger/30 bg-danger/5` convention, visually
// separated from the other three cards. Story 5.3 owns the cascade-delete
// logic and will wire this button up.
//
// Inert via `aria-disabled` + an early return rather than the native
// `disabled` attribute, matching ToggleSwitch.jsx's convention on this
// same page: `disabled` drops the control out of the tab order entirely,
// so someone navigating by keyboard or screen reader would never reach it
// and would have no way to learn the feature exists. aria-disabled keeps
// it focusable and announced, and just no-ops the action.
export default function DeleteAccountCard() {
  const handleClick = () => {
    // No-op until Story 5.3 wires up the cascade delete.
  }

  return (
    <div className="rounded-lg border border-danger/30 bg-danger/5 p-[22px]">
      <h2 className="text-base font-bold text-text">Delete Account</h2>
      <p className="mt-2 text-sm text-text">
        Permanently delete your account and all associated documents. This action cannot be undone.
      </p>
      <button
        type="button"
        aria-disabled="true"
        onClick={handleClick}
        className="mt-4 self-start cursor-not-allowed rounded-md border border-border px-3 py-1.5 text-sm text-danger opacity-50"
      >
        Delete Account
      </button>
    </div>
  )
}
