---
title: 'Story 5.2: Choose light or dark appearance and have it remembered'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: '68e15cb'
provenance: 'authored-after-implementation'
---

> **Provenance note (read this first):** unlike every other spec in this folder, this file was written *after* the story shipped (commit `bbdd029`), not before. The work was driven through native plan-mode planning rather than the `bmad-build` skill, so no spec was authored up front. It is backfilled here for traceability, and the "frozen" block below is therefore a faithful record of what the approved plan actually said — reconstructed from that plan and the shipped code — not a contract that predated the code. Treat its authority accordingly.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Dual-theme rendering has existed since Story 1.2 — `ThemeContext.jsx` flips `data-theme` on `<html>`, every screen is built on swappable tokens — but the choice lives only in `localStorage`, and the only way to change it is a dev-only throwaway button on `HealthPage` (`import.meta.env.DEV`-gated, explicitly marked for removal once this story ships). So the preference is per-browser, not per-account: the same user on a second machine gets the default. `SettingsPage.jsx` is still the Story 1.5 placeholder ("Coming in Epic 5").

**Approach:** Add a `theme` column to `users`, expose it on the auth module's existing endpoints, and add `PATCH /auth/theme`. On the frontend, keep `ThemeContext` exactly as-is (fully decoupled from auth) and introduce a small always-mounted `ThemeAccountSync` bridge that pushes the account's value into it — so neither context imports the other, mirroring the precedent set by `documentsClient.js` taking `authFetch` as a parameter rather than importing `AuthContext`. `AppearanceCard` owns the PATCH call directly, the way `DocumentCard`/`DocumentDetailPage` own `deleteDocument`, rather than routing a mutation through a context.

## Boundaries & Constraints

**Always:**
- `LoginResponse` carries `theme` directly. A second `/auth/me` request after login would be a correctness bug, not just an efficiency nit: `isInitializing` starts `false` when there is no stored token (the fresh-login case), so `ProtectedRoute` renders `Outlet` the moment `login()` resolves — nothing gates on a follow-up fetch, and the first screen after login would paint in the wrong theme until it landed.
- `ThemeContext.jsx` is not modified by this story. It stays stand-alone-usable (pre-auth pages, tests) and auth-agnostic.
- `AuthContext` gains exactly one new field, `accountTheme` — not a general `user` object. Story 5.1 owns the profile shape; guessing at it here would be doing part of 5.1's job.
- The boot-time `/auth/me` call must check `response.ok` before parsing. `authFetch` resolves (does not throw) on 401/500, so an unguarded `.json()` would either set `accountTheme` to `undefined` or throw on a non-JSON error body.
- Toggling is optimistic: `setTheme` applies immediately (UX-DR13's "applies immediately"), and a failed PATCH does **not** revert it — reverting a purely cosmetic toggle is jarring. The inline error must say specifically that the change didn't save *to the account* (UX-DR19), so the user isn't misled into thinking it synced everywhere.
- Toggle clicks are serialized (`saving` disables the control) — two rapid clicks would otherwise fire two PATCHes that can resolve out of order and leave the account one flip behind the visible UI.
- The migration column is added in one step with a constant `server_default='light'`; the model carries a Python-side `default="light"` and no `server_default`, mirroring `id`'s documented rationale (tests build schema via `Base.metadata.create_all()`, not Alembic).
- No OS-preference detection is introduced anywhere (FR-15). `ThemeContext`'s existing deliberate avoidance of `prefers-color-scheme` stands.

**Ask First:** none outstanding. Two judgment calls were raised and settled with the human during planning: provider nesting in `main.jsx` is left untouched (the bridge component makes reordering unnecessary), and `ThemeResponse` echoes the validated request value rather than re-reading the ORM object after commit (see Design Notes).

**Never:**
- No `db.refresh(user)` after commit in `update_theme` — nothing reads the ORM object back afterwards.
- No DB-level `CHECK` constraint or Postgres enum on `theme` — validation is Pydantic-only, consistent with `Document.status`'s plain-`String`-no-DB-enum precedent and its stated SQLite-testability reasoning.
- No clearing of `localStorage`'s `theme` key on logout — see the accepted trade-off in Design Notes.
- No Profile / Change Password / Delete Account cards — those are Stories 5.1 and 5.3. The Settings grid is sized for four cards; only Appearance is populated.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh account | Newly registered user | `theme` defaults to `"light"`; returned on both `/auth/login` and `/auth/me` | N/A |
| Toggle succeeds | Authenticated PATCH with `"light"`/`"dark"` | 200 `{"theme": ...}`; row updated; `accountTheme` synced in `AuthContext` | N/A |
| Toggle fails | PATCH rejects (network/5xx) | Local theme stays applied; inline `role="alert"` states it didn't save to the account | Message from `formatDetail`, or a status-code fallback |
| Rapid double-toggle | Second click while a PATCH is in flight | Second click is inert (`aria-disabled`); exactly one request fires | N/A |
| Invalid theme value | `{"theme": "blue"}` | 422 from Pydantic's `Literal`, before the route body runs | FastAPI default envelope |
| Unauthenticated PATCH | No/invalid bearer token | 401 `{"detail": "Not authenticated."}` | AD-3 shape |
| Logout mid-boot-check | `/auth/me` resolves *after* `logout()` | Stale response must not repopulate `accountTheme` | Guarded on `tokenRef.current` |
| New browser, empty storage | Valid token, no `localStorage.theme` | Brief default-theme paint, then `/auth/me` resolves and the account value wins | N/A (accepted, see Design Notes) |

</frozen-after-approval>

## Code Map

- `backend/alembic/versions/d9814d322f6d_add_theme_to_users.py` -- new: single-step `add_column` with `server_default='light'`; `downgrade` drops it
- `backend/app/shared/models.py` -- edit: `User.theme`, Python-side default
- `backend/app/auth/schemas.py` -- edit: `theme` on `MeResponse` and `LoginResponse`; new `UpdateThemeRequest` (`Literal["light","dark"]`) and `ThemeResponse`
- `backend/app/auth/repository.py` -- edit: `update_user_theme`
- `backend/app/auth/service.py` -- edit: `update_theme`
- `backend/app/auth/routes.py` -- edit: `login()` returns `theme`; new `PATCH /auth/theme`
- `backend/tests/test_auth_theme.py` -- new: persistence, fresh-login persistence, 401, 422
- `backend/tests/test_auth_login.py` -- edit: `theme` asserted on the login and `/me` responses
- `frontend/src/context/AuthContext.jsx` -- edit: `accountTheme` state, `response.ok` guard, `setAccountTheme` exposed, reset on logout
- `frontend/src/components/ThemeAccountSync.jsx` -- new: no-UI bridge, effect keyed on `[accountTheme]`
- `frontend/src/App.jsx` -- edit: mounts `ThemeAccountSync` above `<Routes>`
- `frontend/src/api/settingsClient.js` -- new: `updateTheme(authFetch, theme)`
- `frontend/src/components/ToggleSwitch.jsx` -- new: generic 40×22px pill switch
- `frontend/src/components/settings/AppearanceCard.jsx` -- new
- `frontend/src/pages/SettingsPage.jsx` -- rewrite: four-card grid, Appearance only
- tests: `ThemeContext.test.jsx`, `ThemeAccountSync.test.jsx`, `ToggleSwitch.test.jsx`, `AppearanceCard.test.jsx`, `settingsClient.test.js` (all new)

## Tasks & Acceptance

**Execution:**
- [x] migration + `User.theme`
- [x] auth schemas, repository, service, routes (`PATCH /auth/theme`, `theme` on login/me)
- [x] backend tests; `pytest`: 244 passed
- [x] `AuthContext.accountTheme` + `ThemeAccountSync` bridge, mounted in `App.jsx`
- [x] `settingsClient.js`, `ToggleSwitch.jsx`, `AppearanceCard.jsx`, `SettingsPage.jsx` grid
- [x] frontend tests; `npm test`: 217 passed; lint clean
- [x] manual verification against the real dev servers and real Postgres (Neon)
- [x] three-lens code review + all findings fixed (see Review Findings below)

**Acceptance Criteria:** (mirrors the story's own Gherkin in `epics.md`)
- Given the Appearance card, when it renders, then a two-state toggle switch appears with a 40×22px pill track, the border colour when off, the primary colour when on, and a white thumb (UX-DR13).
- Given I select a theme, when the selection registers, then it applies immediately across the whole application through the shared React Context, not through prop-drilling or a separate state library (FR-15, AD-5).
- Given I select a theme, when I log out and log back in, then my choice persists, stored against my account rather than only in this browser (FR-15).
- Given v1 scope, when the theme is determined, then it comes solely from my manual choice, and no OS-preference auto-detection is applied (FR-15).
- Given both themes, when I move through the product, then every screen renders correctly in each, including the Login and Registration pages (FR-15, UX-DR2).

## Design Notes

- **`LoginResponse` was extended rather than adding a post-login `/auth/me` fetch.** See the first Boundaries bullet for the full reasoning — this is the one design decision in the story that a reviewer flagged as load-bearing rather than cosmetic. `authenticate_user` already returns the full `User` before `LoginResponse` is constructed, so it costs no extra query.
- **`ThemeResponse` echoes the validated request value (`data.theme`), not `user.theme` re-read after commit.** The session's `sessionmaker` does not set `expire_on_commit=False` (`shared/data_access/session.py`), so reading the ORM attribute post-commit would trigger a lazy re-`SELECT`. Echoing the value Pydantic already constrained to `Literal["light","dark"]` avoids that round trip entirely. Reviewed and consciously kept; the trade-off is that the response reflects what was asked for rather than what was read back.
- **Accepted trade-off — `localStorage.theme` is not cleared on logout.** `logout()` resets `accountTheme` to `null`, but the local copy stays, so the Login page immediately after logout still shows the previous account's theme. It self-heals on the next login (`accountTheme` always transitions from `null`, so the sync effect always fires). No account data leaks — it's a visual holdover — and clearing it would mean an unauthenticated visitor loses their own device preference too.
- **Accepted trade-off — first-paint flash on a new browser.** `localStorage` (or the light default) paints first; the account value lands when `/auth/me` resolves and corrects it. Only observable on a browser with empty storage; the alternative (blocking first paint on a network call) is worse.
- **Accepted trade-off — a failed PATCH leaves local and account state diverged.** The optimistic `setTheme` has already written to `localStorage`, so this browser remembers a value the account doesn't have, until a later successful save or a login elsewhere re-syncs it. Deliberate: see the Boundaries bullet on not reverting.
- **`ThemeAccountSync`'s effect is keyed on `[accountTheme]` alone.** Including `theme` would re-apply the account's last-known value immediately after the user's own toggle, fighting their click. `theme`/`setTheme` are read through a ref updated in a dependency-less `useEffect` (not assigned during render, which would be a render-phase write).
- **`ToggleSwitch` uses `aria-disabled` + an early return, not the native `disabled` attribute.** `disabled` pulls focus off the control the moment a save starts, which is disruptive mid-interaction for a keyboard user; `aria-disabled` keeps it focusable and simply no-ops.

## Review Findings

A three-lens review (edge-case hunter, blind hunter, acceptance auditor) ran against the working diff before commit. Fifteen-plus raised, eight survived verification against the real code and were fixed in the same commit; the rest were either already-recorded accepted trade-offs (above), or false positives — notably a claimed missing focus ring (`index.css` already applies `:focus-visible` globally to every `button`) and duplicated test helpers (which match the existing per-file convention in `test_auth_registration.py`/`test_auth_login.py`).

Fixed:
- **WCAG 1.4.11 on the toggle thumb.** White thumb on the light-mode off-state track (`--border` `#C7D2E6`) measured ~1.53:1, well under 3:1 for non-text UI boundaries. Fixed with a fixed 1px `rgba(0,0,0,0.5)` ring on the thumb (~3.6:1 against that track) rather than re-tuning the track/on colours DESIGN.md prescribes. Dark mode already passed (~10:1) and gets the same ring rather than a theme-conditional treatment.
- **Stale boot-response race.** `/auth/me` resolving after `logout()` could repopulate `accountTheme`. The effect's own `cancelled` flag does not cover this — `AuthProvider` never unmounts on logout, so cleanup never runs — so the guard is on `tokenRef.current`, which `setTokenEverywhere` nulls synchronously. Regression-tested.
- **`accountTheme` went stale after a successful save.** `setAccountTheme` is now exposed and called by `AppearanceCard`.
- **Label not programmatically associated.** The visible "Dark mode" text now carries an id referenced by `aria-labelledby` (replacing a duplicated `aria-label`) and is itself clickable.
- **No save feedback for screen readers.** Added an `aria-live="polite"` `sr-only` region announcing "Saving appearance…" / "Appearance saved.", plus `aria-busy` on the control — previously only failure was announced.
- **Render-phase ref write** in `ThemeAccountSync`, moved into an effect.
- **`settingsClient.js` had no direct test file**, unlike every sibling client. Added.
- **No test proved the AC3 guarantee.** `test_update_theme_persists` only checked `/auth/me` on the *same* session; added `test_update_theme_survives_a_fresh_login`, which is what the AC literally says.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- 244 passed.
- `npm test -- --run` / `npm run lint` (from `frontend/`) -- 217 passed; lint clean apart from the four pre-existing `only-export-components` fast-refresh warnings shared with `AuthContext.jsx`/`ThemeContext.jsx`/`ChatScopeContext.jsx`/`StatusPill.jsx`.
- `alembic upgrade head` applied `d9814d322f6d` against the real Neon dev database.

**Manual checks -- against the real dev servers and real Postgres, QA account `essinkabg@gmail.com`:**
- Toggled on Settings: `data-theme` flipped light↔dark instantly, `PATCH /auth/theme` returned 200, no console errors.
- Reloaded with `localStorage.theme` deleted but the session intact: the page came back in the account's theme, proving the value came from `/auth/me` and not from browser storage — this is the AC3 behaviour, checked live rather than only in tests.
- Computed styles on the switch: track `40×22px`, thumb `18×18px` at `top:2px`, `left:2px`→`20px`, track `--border` off / `--primary` on, thumb ring present (`rgba(0,0,0,0.5) 0 0 0 1px`). Confirms UX-DR13 against the rendered element, not just the class list.
- `aria-labelledby` resolves to the visible "Dark mode" text, `aria-label` absent (no duplication), and clicking the text toggled the switch. Live region read "Appearance saved." after a successful save.
- **AC5, checked directly (the one AC the acceptance-auditor lens flagged as unproven):** forced `data-theme=dark` and loaded `/login` and `/` (Registration) signed out. Login: card `#262B35`, border `#3A4150`, input `#2E333F` with `#E4E7EC` text (10.2:1), submit `#5B8CFF` with `#1E222B` text (5.0:1), link `#6690FF`. Registration: outer surface `#1E222B` (`--bg` dark), card `#262B35`, and a sweep of every element on the page found **zero** still painting `rgb(255,255,255)`. Both pages are fully theme-correct; nothing in this story touched them, so this is confirmation rather than new work.
- Cleanup: the QA account was left on `light`, the dev browser's session restored exactly as found, and the temporary storage key used to park the token during the signed-out check removed.

**Not verified:** the `downgrade()` path of the migration was never executed (no test or manual run drops the column) — consistent with how every prior migration in this project has been handled, but stated rather than implied.
