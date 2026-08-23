import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import AppearanceCard from '../components/settings/AppearanceCard'
import LanguageCard from '../components/settings/LanguageCard'
import ChangePasswordCard from '../components/settings/ChangePasswordCard'
import DeleteAccountCard from '../components/settings/DeleteAccountCard'
import ProfileCard from '../components/settings/ProfileCard'

// First letter of each of the first two words -- mirrors Shell.jsx's own
// `initialsFor` exactly (kept as a separate copy rather than a shared
// import: it's a three-line pure function, and a shared util for
// something this small is more indirection than the duplication it'd
// save).
function initialsFor(fullName) {
  return fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

// Redesigned (previously a bare page-title + a 2-column card grid, styled
// entirely in v1 tokens -- rounded-lg/border-border/bg-card-bg with no
// icons, no description copy, no identity header -- while every other
// authenticated page had already moved to design system v2). Modeled on
// the account-settings pattern most modern SaaS apps converge on
// (Stripe, Vercel, Linear): an identity header up top, then one setting
// per full-width row -- an icon + title + one-line description on the
// left, its control on the right -- rather than a grid of same-sized
// boxes that gives "change your password" and "toggle dark mode" equal
// visual weight. Each card below (ProfileCard, etc.) owns that row's
// right-hand control and all of its save/error logic; this file only
// owns the shared shell -- the icon badge, title, description -- via
// each card rendering into the layout its own file defines (their
// internals were restyled to match, not restructured).
export default function SettingsPage() {
  const { t } = useTranslation()
  const { accountFullName, accountEmail } = useAuth()

  return (
    <div className="max-w-[1040px]">
      <p className="text-eyebrow uppercase text-accent">{t('settings.eyebrow')}</p>
      <h1 className="text-page-title text-text">{t('settings.title')}</h1>
      <p className="mt-1 max-w-[56ch] text-sm text-text2">{t('settings.subtitle')}</p>

      {/* Identity header -- the same avatar-initials treatment Shell.jsx's
          own nav uses (one visual object for "which account this is",
          not two competing ones). Omitted until accountFullName resolves
          (null on a fresh login until Shell's/ProfileCard's own /auth/me
          fetch lands) rather than rendering a placeholder blank avatar. */}
      {accountFullName && (
        <div className="mt-5 flex items-center gap-3 rounded-2xl border border-border bg-card-bg px-4 py-3 shadow-card">
          <span
            aria-hidden="true"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[image:var(--grad-brand)] text-[13px] font-bold text-white shadow-[var(--glow)]"
          >
            {initialsFor(accountFullName)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-text">{accountFullName}</p>
            <p className="truncate text-xs text-text2">{accountEmail}</p>
          </div>
        </div>
      )}

      {/* Two-up grid rather than a single stacked column: at this page's
          full-page-width now that Shell's nav sits on top instead of at
          the side (see Shell.jsx), one card per row left the whole right
          half of the page empty. Profile pairs with Change Password and
          Appearance pairs with Language -- both natural pairs, each of
          similar visual weight -- while Delete Account claims the full
          row on its own via `sm:col-span-2` (its danger-zone treatment
          reads as more deliberately set apart on its own line than
          paired beside an unrelated card). */}
      <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2">
        <ProfileCard />
        <ChangePasswordCard />
        <AppearanceCard />
        <LanguageCard />
        <DeleteAccountCard />
      </div>
    </div>
  )
}
