// Story 5.1 ships only this static shell -- danger-tinted per
// DocumentCard.jsx's `border-danger/30 bg-danger/5` convention, visually
// separated from the other three cards. The button is disabled (no-op):
// Story 5.3 owns the cascade-delete logic and will wire this up.
export default function DeleteAccountCard() {
  return (
    <div className="rounded-lg border border-danger/30 bg-danger/5 p-[22px]">
      <h2 className="text-base font-bold text-text">Delete Account</h2>
      <p className="mt-2 text-sm text-text">
        Permanently delete your account and all associated documents. This action cannot be undone.
      </p>
      <button
        type="button"
        disabled
        aria-disabled="true"
        className="mt-4 self-start rounded-md border border-border px-3 py-1.5 text-sm text-danger opacity-50"
      >
        Delete Account
      </button>
    </div>
  )
}
