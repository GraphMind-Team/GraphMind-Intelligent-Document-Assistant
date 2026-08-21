import { useTranslation } from 'react-i18next'
import AppearanceCard from '../components/settings/AppearanceCard'
import LanguageCard from '../components/settings/LanguageCard'
import ChangePasswordCard from '../components/settings/ChangePasswordCard'
import DeleteAccountCard from '../components/settings/DeleteAccountCard'
import ProfileCard from '../components/settings/ProfileCard'

// Grid sized for all five cards (UX-DR12): Profile, Change Password,
// Appearance, Language, and the Delete Account shell -- additive only,
// this shell itself is unchanged.
export default function SettingsPage() {
  const { t } = useTranslation()
  return (
    <>
      <h1 className="text-page-title text-text">{t('settings.title')}</h1>
      <div className="mt-6 grid max-w-[900px] grid-cols-1 gap-5 sm:grid-cols-2">
        <ProfileCard />
        <ChangePasswordCard />
        <AppearanceCard />
        <LanguageCard />
        <DeleteAccountCard />
      </div>
    </>
  )
}
