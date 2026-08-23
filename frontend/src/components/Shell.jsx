import { useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import DocumentReadyToasts from './DocumentReadyToasts'
import Icon from './Icon'

// Authenticated shell: fixed-width sidebar + fluid content, per UX-DR1.
// DOM order matches visual order (sidebar first, then <Outlet/>) so tab
// order is correct with zero tabIndex management (UX-DR18 -- no CSS
// `order`/`row-reverse` on this layout).
//
// Design system v2: the rail is now a *floating glass card* (sticky,
// inset from the viewport edges) over the app's ambient aurora ground,
// rather than a solid primary-fill block flush to the edge, and the nav
// items are pill-shaped with a gradient active state plus a left
// indicator bar. The emoji glyphs are replaced by inline stroke icons --
// emoji render as a different typeface (and often a different color)
// on every platform, which is exactly the inconsistency a design system
// exists to remove. They stay `aria-hidden`; the link text is the label,
// as before.
//
// NavLink's className render-prop supplies the `active` state from the
// current URL, so exactly one link is ever active with no manual
// `useLocation` comparison.

// Ordered by how often a session actually touches each destination --
// Documents/Chat/Graph are the working screens, so they lead; Settings is
// a once-in-a-while destination and now sits last, next to the identity
// block and Log out it's conceptually grouped with (was first, ahead of
// every screen the product is actually for).
const NAV_ITEMS = [
  {
    to: '/documents',
    labelKey: 'nav.documents',
    icon: (
      <>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6M9 17h4" />
      </>
    ),
  },
  {
    to: '/chat',
    labelKey: 'nav.chat',
    icon: (
      <>
        <path d="M20 14a3 3 0 0 1-3 3H8l-4 3V7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3Z" />
        <path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01" />
      </>
    ),
  },
  {
    to: '/graph',
    labelKey: 'nav.graph',
    icon: (
      <>
        <circle cx="6" cy="7" r="2.4" />
        <circle cx="18" cy="9" r="2.4" />
        <circle cx="11" cy="18" r="2.4" />
        <path d="M8.2 8.2 15.7 9M7.2 9.2 10 15.7M16.6 11.1 12.6 16.4" />
      </>
    ),
  },
  {
    to: '/settings',
    labelKey: 'nav.settings',
    icon: (
      <>
        <circle cx="12" cy="12" r="3.2" />
        <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 7.5l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1.3Z" />
      </>
    ),
  },
]

const NAV_LINK_CLASS = ({ isActive }) =>
  [
    // `relative` + the ::before-style indicator span inside each link is
    // what makes the active item legible without relying on the tint
    // alone -- the fill, the indicator bar and the font weight are three
    // redundant cues, not one.
    'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13.5px]',
    isActive
      ? 'bg-sidebar-active-bg font-semibold text-sidebar-active-foreground shadow-[inset_0_1px_0_rgba(255,255,255,.2)]'
      : 'text-sidebar-foreground hover:bg-sidebar-hover-bg hover:text-sidebar-active-foreground',
  ].join(' ')

// First letter of each of the first two words -- "Priya Raman" -> "PR",
// a single-word name -> just that letter. Mirrors ProfileCard.jsx's own
// `/auth/me` fetch below: nothing here needs the rest of that response,
// just enough to render an avatar and confirm which account this is.
function initialsFor(fullName) {
  return fullName
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

export default function Shell() {
  const { logout, authFetch, accountFullName, accountEmail, setAccountFullName, setAccountEmail } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()

  // `accountFullName`/`accountEmail` are shared AuthContext state (not
  // local to this component) precisely so a name change saved on
  // Settings -> ProfileCard shows up here immediately: ProfileCard writes
  // through the same `setAccountFullName`/`setAccountEmail` this effect
  // uses, so both ultimately point at one value instead of Shell holding
  // its own stale copy until a reload. This fetch only runs when that
  // value isn't already known -- typically right after a fresh login,
  // since login() itself has nothing to seed it from (unlike
  // accountTheme/accountLanguage, full_name/email aren't part of
  // LoginResponse) and the boot-time `/auth/me` check only fires for a
  // *stored* token, not one just issued by login(). A failed fetch is
  // swallowed rather than surfaced as an error banner: the rail still
  // works with no name shown, same as before this existed.
  useEffect(() => {
    if (accountFullName !== null) return
    let cancelled = false
    authFetch('/auth/me')
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (!cancelled && data) {
          setAccountFullName(data.full_name)
          setAccountEmail(data.email)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accountFullName, authFetch, setAccountFullName, setAccountEmail])

  function handleExit() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-aurora flex min-h-screen gap-4 p-3 sm:p-4">
      <nav
        aria-label="Main"
        className="glass sticky top-4 flex h-[calc(100vh-2rem)] w-[236px] shrink-0 flex-col gap-1 rounded-2xl p-3.5 shadow-card max-[900px]:w-[76px]"
      >
        {/* Logo lockup. The mark is the brand gradient with a knocked-out
            ring -- the same gradient the primary button and the mascot
            use, so the identity is one object seen in three places. */}
        <div className="mb-6 flex items-center gap-3 px-1.5 pt-1">
          <span
            aria-hidden="true"
            className="relative block h-9 w-9 shrink-0 rounded-[12px] bg-[image:var(--grad-brand)] shadow-[var(--glow)] after:absolute after:inset-[9px] after:rounded-full after:border-2 after:border-white after:content-['']"
          />
          <span className="font-display text-[17px] font-bold tracking-[-0.02em] text-sidebar-active-foreground max-[900px]:hidden">
            GraphMind
          </span>
        </div>

        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} className={NAV_LINK_CLASS}>
                {({ isActive }) => (
                  <>
                    {/* Active indicator bar -- a second, non-color cue
                        (position + presence) alongside the tint. */}
                    <span
                      aria-hidden="true"
                      className={[
                        'absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[image:var(--grad-brand)]',
                        isActive ? 'opacity-100' : 'opacity-0',
                      ].join(' ')}
                    />
                    <Icon>{item.icon}</Icon>
                    <span className="max-[900px]:sr-only">{t(item.labelKey)}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>

        {/* Bottom-anchored via margin-top:auto, separated from the nav
            destinations by spacing plus a hairline rule -- whose account
            is signed in, then the way out, grouped together since neither
            is a working screen. */}
        <div className="mt-auto flex flex-col gap-1 border-t border-sidebar-border pt-1">
          {accountFullName && (
            <div className="flex items-center gap-3 px-3 py-2" title={`${accountFullName} · ${accountEmail}`}>
              <span
                aria-hidden="true"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[image:var(--grad-brand)] text-[12px] font-bold text-white"
              >
                {initialsFor(accountFullName)}
              </span>
              <div className="min-w-0 flex-1 max-[900px]:sr-only">
                <p className="truncate text-[13px] font-semibold text-sidebar-active-foreground">
                  {accountFullName}
                </p>
                <p className="truncate text-[11.5px] text-sidebar-foreground">{accountEmail}</p>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={handleExit}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13.5px] text-sidebar-foreground hover:bg-sidebar-hover-bg hover:text-sidebar-active-foreground"
          >
            <Icon>
              <path d="M15 17l5-5-5-5" />
              <path d="M20 12H9" />
              <path d="M12 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h6" />
            </Icon>
            <span className="max-[900px]:sr-only">{t('nav.logout')}</span>
          </button>
        </div>
      </nav>

      <main className="min-w-0 flex-1 px-2 py-4 sm:px-6">
        <Outlet />
      </main>

      {/* Session-scoped, not page-scoped -- see its own file comment for
          why this can't live inside DocumentsPage. */}
      <DocumentReadyToasts />
    </div>
  )
}
