---
title: 'Story 1.5: Authenticated shell and tenancy-enforced data access'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '3f24059af2cd6d75c1604ccf666e8e2e674cf069'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Login/registration exist (1.3/1.4) but there's no authenticated shell to land in, and the DAL contracts Epic 2/3 will build against in parallel are undocumented. Nothing currently proves the tenancy guarantee (user_id resolved server-side, never client-supplied).

**Approach:** Build a fixed 220px sidebar shell (User Settings, Documents, Chat, Graph Preview, Exit) wrapping protected routes, with minimal placeholder pages for the not-yet-built Documents/Chat/Graph/Settings destinations (their real content ships in Epics 2–5). Wire route protection and logout through the existing `AuthContext`/`get_current_user`. Document the Weaviate passage shape and Neo4j entity shape as the contract Epic 2/3 build against. Prove tenancy with a two-account test against every current authenticated endpoint.

## Boundaries & Constraints

**Always:**
- Sidebar order top-to-bottom: User Settings, Documents, Chat, Graph Preview, then Exit — bottom-anchored (`margin-top: auto`), visually separated from the other four. Exactly one nav item shows `active` state via `NavLink`'s built-in matching.
- Documents is the default post-login landing route (`/documents`); unauthenticated access to any shell route redirects to `/login`.
- Placeholder pages (Documents/Chat/Graph/Settings) render inside the shell with just a page heading and "coming in Epic N" copy — no feature logic, so later epics can replace their bodies without touching the shell.
- Exit calls `logout()` (already in `AuthContext`) and navigates to `/login`.
- Tab order on every shell page: sidebar → page heading → content. No CSS `order`/`row-reverse` on any layout carrying interactive elements (UX-DR18). Focus-visible ring (from 1.2's `--focus-ring` token) must be visible on every sidebar link in both themes.
- At 200% zoom, the fixed-sidebar layout reflows without horizontal scroll or clipping.
- Document Weaviate passage shape (`chunk_id, document_id, user_id, chapter, chunk_index, text, embedding` — flat, no nested metadata) and Neo4j entity shape (`name` + `type`, typed relationships) as docstrings/type definitions in `shared/data_access/`, plus the forward-looking rule that any future NL-to-Cypher query must inject `user_id` server-side. Documentation only — no real Weaviate/Neo4j client code (that's Epic 2/3's job).
- Every current and future protected endpoint resolves `user_id` only from `get_current_user` (already built in 1.4) — never from a client-supplied id/query param. Add a test asserting this holds for `/auth/me` with two real accounts.
- Add the missing `--on-primary` token to `index.css` — `LoginPage`/`RegisterPage`'s submit buttons already reference `var(--on-primary)` but it was never defined, so their text is currently invisible/uncolored. Per the reference mockup (`mockups/key-screens-{light,dark}.html`, which the human directed to be matched pixel-for-pixel — supersedes the "out of scope" restriction originally in this section), the correct value is `#FFFFFF` in light but `#1E222B` in dark (dark text on the lighter primary-dark button fill, for contrast — DESIGN.md's YAML lists only the light value).
- Sidebar, Login, and Register pixel-match the reference mockup exactly: sidebar gets a logo row (mark + wordmark), emoji-prefixed nav items (DESIGN.md's one accepted emoji-as-substance exception), inactive-link text `#E4ECFA` (the mockup's literal value, lighter than DESIGN.md's YAML `#DCE6F5`), separate hover (`rgba(255,255,255,.08)` light / `rgba(255,255,255,.06)` dark) vs. active (`.14`/`rgba(91,140,255,.18)`) backgrounds, `10px 12px` link padding, `2px` inter-item gap, no divider above Exit (mockup has none — separation is `margin-top:auto` alone). Login/Register get a `--card-bg` (matches `--bg` light / `--surface` dark, distinct from both), `--input-bg` (matches `--bg` light / `--surface2` dark), `--card-shadow`, and the auth logo-mark block; Login's copy matches the mockup ("Welcome back" / "Log in to your GraphMind workspace.").

**Ask First:** none expected.

**Never:**
- Do not build real Documents/Chat/Graph/Settings functionality — placeholders only, per epic sequencing.
- Do not add real Weaviate or Neo4j client code/credentials — shape documentation only.
- Do not touch `backend/app/auth/{routes,service,repository}.py` beyond what's needed for the tenancy test — 1.3/1.4's auth logic is done and out of scope.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Authenticated, lands in app | Valid stored token | Sidebar renders, redirected/lands on `/documents`, exactly one nav item active | N/A |
| Unauthenticated, visits shell route | No token / expired token | Redirected to `/login` | N/A |
| Cross-tenant request | Account B's token requests account A's data via any endpoint | No account-A data returned; `user_id` always resolved from B's own JWT | N/A |
| Exit | Authenticated user clicks Exit | Session ends, redirected to `/login`, protected routes now redirect again | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/components/Shell.jsx` -- new: sidebar (logo, icons, `<ul>/<li>` nav) + `<Outlet/>` layout, `NavLink`s, Exit button
- `frontend/src/components/ProtectedRoute.jsx` -- new: redirects to `/login` when `!isAuthenticated`, carries `location.state.from`
- `frontend/src/components/PublicOnlyRoute.jsx` -- new: redirects authenticated visitors away from `/` and `/login`, reads the same `from` state
- `frontend/src/pages/{Documents,Chat,Graph,Settings}Page.jsx` -- new: minimal placeholders
- `frontend/src/App.jsx` -- edit: nest shell routes under `ProtectedRoute`+`Shell`, auth routes under `PublicOnlyRoute`, default `/documents`
- `frontend/src/pages/LoginPage.jsx` -- edit: `from`-aware post-login redirect, mockup-matched copy/logo-mark/card styling
- `frontend/src/pages/RegisterPage.jsx` -- edit: mockup-matched logo-mark/card styling
- `frontend/src/index.css` -- edit: `--on-primary` (+ dark override), `--card-bg`, `--card-shadow`, `--input-bg`, `--sidebar-hover-bg`, `--sidebar-logo-mark-bg`, corrected `--sidebar-foreground`
- `backend/app/shared/data_access/shapes.py` -- new: documented Weaviate passage / Neo4j entity + relationship shape contracts
- `backend/tests/test_tenancy.py` -- new: two-account isolation test against `/auth/me`
- `frontend/src/context/AuthContext.jsx` -- read-only reference (`isAuthenticated`, `logout`); no changes expected

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/components/Shell.jsx` -- sidebar with 5 nav items, bottom-anchored Exit, `<Outlet/>` for page content -- satisfies AC1/UX-DR1
- [x] `frontend/src/components/ProtectedRoute.jsx` -- gate shell routes on `isAuthenticated`, carry `from` -- enforces the auth boundary client-side (server already enforces via 401)
- [x] `frontend/src/components/PublicOnlyRoute.jsx` -- gate auth routes the opposite direction -- authenticated visitors don't see Register/Login again
- [x] `frontend/src/pages/{Documents,Chat,Graph,Settings}Page.jsx` -- placeholder pages -- makes all 4 nav destinations real routes
- [x] `frontend/src/App.jsx` -- restructure routing, default `/documents` -- wires shell into the route tree
- [x] `frontend/src/index.css` -- define `--on-primary` (+ dark override), `--card-bg`, `--input-bg`, `--card-shadow`, sidebar hover/logo tokens, corrected `--sidebar-foreground` -- fixes invisible button text and pixel-matches the mockup
- [x] `frontend/src/pages/{Login,Register}Page.jsx` -- logo-mark, card/input tokens, mockup copy -- pixel-perfect per human request
- [x] `backend/app/shared/data_access/shapes.py` -- document Weaviate passage + Neo4j entity/relationship shapes, NL-to-Cypher user_id rule -- Epic 2/3 contract
- [x] `backend/tests/test_tenancy.py` -- two accounts, assert `/auth/me` never leaks cross-account data and ignores any client-supplied id -- first SM-3 verification

**Acceptance Criteria:**
- Given I'm authenticated and land in the app, when the shell renders, then all 5 nav items appear in the specified order with exactly one active.
- Given any endpoint touching user-owned data, when it's called, then `user_id` comes only from the server-side-resolved JWT identity, never a client-supplied value.
- Given two test accounts, when account B calls any authenticated endpoint, then no account-A data is returned.
- Given any shell page, when tabbed through, then focus order is sidebar → heading → content, with a visible focus ring in both themes.
- Given the shell at 200% zoom, when viewed, then no horizontal scroll or clipping occurs.
- Given Exit is selected, when clicked, then the session ends and the user lands on `/login`.

## Spec Change Log

- **Trigger:** Direct human request mid-implementation ("make it pixel perfect with the design mockups... for the sidebar but also for the login and registration pages"), not an automated review finding.
- **Amended:** Removed the original `Never` bullet forbidding LoginPage/RegisterPage styling changes; added an `Always` bullet requiring pixel-match against `mockups/key-screens-{light,dark}.html` for sidebar/Login/Register, with the specific corrected values (see Boundaries).
- **Known-bad state avoided:** The original scope left the sidebar using generic surface/primary-text colors that didn't match DESIGN.md's actual `components.sidebar` spec (solid primary fill in light, no icons, no logo), and Login/Register with an undefined `--on-primary` value and copy that didn't match the mockup.
- **KEEP:** The tenancy test, DAL shapes, routing structure (`ProtectedRoute`/`Shell`/placeholders), and the `--on-primary` dark-mode correction (`#1E222B`, verified against the mockup's actual `.btn-primary{color:#1E222B}` dark rule, not assumed) all still stand as originally built — only the sidebar/auth-page visual layer was expanded.

## Design Notes

`Shell.jsx` renders a `<div className="flex">` — `<nav>` (220px fixed) + `<main className="flex-1"><Outlet/></main>`. DOM order matches visual order (sidebar first) so tab order is correct with zero extra `tabIndex` management. `NavLink`'s `className` render-prop applies the active style — no manual `useLocation` comparison needed.

## Verification

**Commands:**
- `npm run build` (from `frontend/`) -- expected: succeeds
- `npm run lint` (from `frontend/`) -- expected: passes
- `pytest` (from `backend/`) -- expected: all pass, including new `test_tenancy.py`

**Manual checks (if no CLI):**
- Tab through a shell page: confirm order (sidebar → heading → content) and visible focus ring in both themes.
- Zoom to 200%: confirm no horizontal scroll/clipping.
- Log in, click Exit, confirm redirect to `/login` and that `/documents` now redirects back to `/login`.

## Suggested Review Order

**Tenancy & DAL contract (backend)**

- The structural guarantee this story exists to prove: `user_id` resolved server-side, never client-supplied.
  [`dependencies.py:27`](../../backend/app/auth/dependencies.py#L27)

- Documented Weaviate/Neo4j shapes Epic 2/3 build against, including the `Neo4jEntity`/`Neo4jRelationship` `user_id` fields added after review.
  [`shapes.py:19`](../../backend/app/shared/data_access/shapes.py#L19)

- Two-account proof: no cross-tenant leakage, and a client-supplied id is ignored.
  [`test_tenancy.py:25`](../../backend/tests/test_tenancy.py#L25)

**Route gating (frontend)**

- Shared helper both redirect directions use, added after review caught a race condition and a dropped-query-string edge case.
  [`authRedirect.js:7`](../../frontend/src/utils/authRedirect.js#L7)

- Unauthenticated → `/login`, carrying `from` for redirect-back.
  [`ProtectedRoute.jsx:8`](../../frontend/src/components/ProtectedRoute.jsx#L8)

- Authenticated → shell, same target logic (this is the side that raced against `LoginPage`'s own navigate before the shared helper existed).
  [`PublicOnlyRoute.jsx:22`](../../frontend/src/components/PublicOnlyRoute.jsx#L22)

- Post-login navigate using the shared helper.
  [`LoginPage.jsx:26`](../../frontend/src/pages/LoginPage.jsx#L26)

**Shell & pixel-match (frontend)**

- Sidebar structure: logo, icon-prefixed nav, distinct hover/active states, exact mockup padding/gap.
  [`Shell.jsx:35`](../../frontend/src/components/Shell.jsx#L35)

- Token corrections from mockup cross-referencing: `--on-primary` (+ dark override), `--card-bg`, `--input-bg`, corrected `--sidebar-foreground`.
  [`index.css:24`](../../frontend/src/index.css#L24)

- `htmlFor`/`id` pairing restored after review caught the label association regression.
  [`LoginPage.jsx:45`](../../frontend/src/pages/LoginPage.jsx#L45)

**Peripherals**

- Placeholder pages and routing tree.
  [`App.jsx:24`](../../frontend/src/App.jsx#L24)
