import AppearanceCard from '../components/settings/AppearanceCard'

// Grid sized for all four Epic 5 cards (UX-DR12); only Appearance (Story
// 5.2) is populated so far. Profile/Change Password (Story 5.1) and Delete
// Account (Story 5.3) land here later without touching this shell.
export default function SettingsPage() {
  return (
    <>
      <h1 className="text-xl font-bold text-text">User Settings</h1>
      <div className="mt-6 grid max-w-[900px] grid-cols-1 gap-5 sm:grid-cols-2">
        <AppearanceCard />
      </div>
    </>
  )
}
