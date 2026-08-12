import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

// Authenticated shell (Story 1.5): fixed 220px sidebar + fluid content,
// per UX-DR1. DOM order matches visual order (sidebar first, then
// <Outlet/> content) so tab order is correct with zero extra tabIndex
// management (UX-DR18 -- no CSS `order`/`row-reverse` on this layout).
//
// Structure/values match the reference mockup's `.sidebar` exactly:
// logo row, emoji-prefixed nav links (the one accepted emoji-as-substance
// exception, per DESIGN.md), 10px/12px link padding, 2-4px inter-item
// gap, distinct hover vs. active backgrounds, Exit separated purely by
// margin-top:auto (no divider line -- the mockup doesn't have one).
//
// NavLink's className render-prop supplies the `active` state itself
// (based on the current URL), so exactly one of the four route links is
// ever active without any manual `useLocation` comparison.
const NAV_LINK_CLASS = ({ isActive }) =>
  [
    'flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm',
    isActive
      ? 'bg-sidebar-active-bg font-semibold text-sidebar-active-foreground'
      : 'text-sidebar-foreground hover:bg-sidebar-hover-bg hover:text-sidebar-active-foreground',
  ].join(' ')

export default function Shell() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleExit() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen bg-bg">
      <nav
        aria-label="Main"
        className="flex w-[220px] shrink-0 flex-col gap-1 bg-sidebar-bg p-3.5"
      >
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="relative block h-[26px] w-[26px] shrink-0 rounded-[7px] bg-sidebar-logo-mark-bg after:absolute after:inset-[6px] after:rounded-full after:border-2 after:border-sidebar-bg after:content-['']" />
          <span className="text-[15px] font-bold text-sidebar-active-foreground">GraphMind</span>
        </div>

        <ul className="flex flex-col gap-[2px]">
          <li>
            <NavLink to="/settings" className={NAV_LINK_CLASS}>
              <span aria-hidden="true">⚙</span> User Settings
            </NavLink>
          </li>
          <li>
            <NavLink to="/documents" className={NAV_LINK_CLASS}>
              <span aria-hidden="true">📄</span> Documents
            </NavLink>
          </li>
          <li>
            <NavLink to="/chat" className={NAV_LINK_CLASS}>
              <span aria-hidden="true">💬</span> Chat
            </NavLink>
          </li>
          <li>
            <NavLink to="/graph" className={NAV_LINK_CLASS}>
              <span aria-hidden="true">🕸</span> Graph Preview
            </NavLink>
          </li>
        </ul>

        {/* Bottom-anchored via margin-top: auto, separated from the four
            nav-destination links purely by that spacing -- the mockup has
            no divider line here. */}
        <button
          type="button"
          onClick={handleExit}
          className="mt-auto flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm text-sidebar-foreground hover:bg-sidebar-hover-bg hover:text-sidebar-active-foreground"
        >
          <span aria-hidden="true">↩</span> Exit
        </button>
      </nav>

      <main className="min-w-0 flex-1 p-8">
        <Outlet />
      </main>
    </div>
  )
}
