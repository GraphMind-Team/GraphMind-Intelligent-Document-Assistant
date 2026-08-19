import AppearanceCard from '../components/settings/AppearanceCard'
import ChangePasswordCard from '../components/settings/ChangePasswordCard'
import DeleteAccountCard from '../components/settings/DeleteAccountCard'
import ProfileCard from '../components/settings/ProfileCard'

// Grid sized for all four Epic 5 cards (UX-DR12). Story 5.1 adds Profile,
// Change Password, and the Delete Account shell alongside Story 5.2's
// Appearance card -- additive only, this shell itself is unchanged.
export default function SettingsPage() {
  return (
    <>
      <h1 className="text-page-title text-text">User Settings</h1>
      <div className="mt-6 grid max-w-[900px] grid-cols-1 gap-5 sm:grid-cols-2">
        <ProfileCard />
        <ChangePasswordCard />
        <AppearanceCard />
        <DeleteAccountCard />
      </div>
    </>
  )
}
