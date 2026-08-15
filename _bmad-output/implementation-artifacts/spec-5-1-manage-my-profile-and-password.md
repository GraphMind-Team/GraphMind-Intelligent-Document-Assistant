---
title: 'Manage my profile and password'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '468eb666c918a71064216cea56951ab35170f46c'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Users have no way to view/update their account details or change their password without help; the `/settings` route currently renders a placeholder page.

**Approach:** Story 5.2 already shipped the settings grid shell (`SettingsPage.jsx`, `.settings-grid`) with a working `AppearanceCard`. Add Profile and Change Password as fully functional, independently-saving cards into that existing grid, backed by new `auth` endpoints. Add a static Delete Account card shell (danger-tinted, non-functional button) — its cascade-delete logic ships in Story 5.3.

## Boundaries & Constraints

**Always:**
- Profile and Change Password save independently — submitting one never touches the other's state or requires re-entering the other's fields.
- New password is hashed with `bcrypt_sha256` via the same `hash_password` helper used at registration (`backend/app/auth/service.py`).
- Password change requires the user's current password to be re-verified server-side before accepting the new one (in-session change, not a reset flow).
- All new/changed routes require `Depends(get_current_user)` and use `response_model` + `HTTPException(status_code, detail)` per AD-3 — no custom error envelope.
- Validation errors return plain, declarative messages (no hedging language).
- Delete Account card renders with danger-tinted border/background (mirror `DocumentCard.jsx`'s `border-danger/30 bg-danger/5` convention), visually separated from the other three cards, but its button is non-functional (disabled or no-op) in this story — Story 5.3 owns wiring it up.
- New API client functions follow `settingsClient.js`'s established pattern exactly: `authFetch` as first param, `formatDetail` for error messages.
- Profile card, if it needs a saving/busy affordance, reuses `ToggleSwitch`-adjacent conventions from `AppearanceCard.jsx` (optimistic-update + serialized-saves + inline `role="alert"`) where applicable — do not invent a different save-state pattern.
- `SettingsPage.jsx`'s existing grid (`max-w-[900px] grid-cols-1 sm:grid-cols-2`) and `AppearanceCard` usage are additive-only — new cards are added alongside `<AppearanceCard />`, not by restructuring the grid.

**Ask First:**
- None — email-editability question already resolved: `full_name` is editable, `email` is displayed read-only.

**Never:**
- No forgot-password/reset-via-email flow — out of v1 scope.
- No changes to `AppearanceCard.jsx`, `ToggleSwitch.jsx`, or theme persistence logic — Story 5.2 already shipped and owns these.
- No cascade-delete logic — Story 5.3 owns it; this story only ships the Delete Account card's static shell.
- No new Postgres columns/migrations for profile data — `full_name`/`email`/`password_hash` already exist on `User`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Update profile happy path | Authenticated user submits new `full_name` | 200, `full_name` updated in DB and reflected in response | N/A |
| Empty full name | `full_name` = "" or whitespace-only | Rejected | 422 with plain field-validation detail |
| Change password happy path | Correct `current_password` + valid `new_password` | 200, `password_hash` updated via `bcrypt_sha256` | N/A |
| Wrong current password | `current_password` does not match stored hash | Password not changed | 400 `HTTPException` with plain "current password is incorrect" detail |
| Too-short new password | `new_password` under 8 chars | Password not changed | 422, reusing `RegisterRequest`'s `min_length=8, max_length=128` bound |

</frozen-after-approval>

## Code Map

**Already shipped by Story 5.2 — reuse, do not modify:**
- `frontend/src/pages/SettingsPage.jsx` -- existing grid (`max-w-[900px] grid-cols-1 sm:grid-cols-2 gap-5`) renders `<AppearanceCard />`; add `<ProfileCard />`, `<ChangePasswordCard />`, `<DeleteAccountCard />` alongside it.
- `frontend/src/components/settings/AppearanceCard.jsx` -- golden example of a self-saving card: optimistic update, `saving` flag serializing clicks, inline `role="alert"` on failure, `sr-only` `aria-live` status. Mirror this pattern for Profile/Change Password.
- `frontend/src/components/ToggleSwitch.jsx` -- generic switch, reusable if any new card needs one (unlikely for 5.1, but do not duplicate if so).
- `frontend/src/api/settingsClient.js` -- template for new client functions: `authFetch` first param, `formatDetail` from `authClient.js` for error shape, throws `Error` with message on non-ok response. Add `updateProfile`/`changePassword` here.
- `backend/app/auth/schemas.py` -- has `UpdateThemeRequest`/`ThemeResponse`, `RegisterRequest`'s trim validators (lines ~10-30), `MeResponse` (with `theme` field). Add `UpdateProfileRequest`, `ChangePasswordRequest`, response schemas following the same style.
- `backend/app/auth/routes.py` -- has `POST /register`, `POST /login`, `GET /me`, `PATCH /theme` on `router = APIRouter(prefix="/auth", tags=["auth"])`. Add `PATCH /auth/me` and `POST /auth/me/password`, both `Depends(get_current_user)`, following the `update_theme` route's shape.
- `backend/app/auth/service.py` -- `hash_password` (bcrypt_sha256.hash), `authenticate_user` (shows `bcrypt_sha256.verify` pattern for validating current password), `update_theme` (shows the service-function shape: mutate via repository, `db.commit()`). Add `update_profile` and `change_password` following this shape.
- `backend/app/auth/repository.py` -- `get_user_by_id`, `update_user_theme` (shows the mutate-and-flush pattern). Add analogous update helper(s) for `full_name`/`password_hash`.
- `backend/app/auth/dependencies.py` -- `get_current_user` -- auth dependency for both new routes.
- `backend/app/shared/models.py` -- `User` model already has `id`, `full_name`, `email`, `password_hash`, `theme`, `created_at`. No migration needed (alembic head is `d9814d322f6d`, already includes `theme`).

**New for this story:**
- `frontend/src/components/settings/ProfileCard.jsx` -- new file, mirrors `AppearanceCard.jsx` structure.
- `frontend/src/components/settings/ChangePasswordCard.jsx` -- new file, same pattern; needs current + new password fields.
- `frontend/src/components/settings/DeleteAccountCard.jsx` -- new file, static shell only (danger-tinted, per `DocumentCard.jsx`'s `border-danger/30 bg-danger/5` convention), button disabled/no-op.
- `backend/tests/test_auth_profile.py` -- new file, covers the I/O Matrix; mirror `backend/tests/test_auth_login.py`'s register→auth-header→assert pattern. Fixtures in `backend/tests/conftest.py` (`db_session`, `client`).

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/auth/schemas.py` -- add `UpdateProfileRequest`, `ChangePasswordRequest`, and response schemas with trim/strength validators -- backend needs typed request/response contracts
- [x] `backend/app/auth/service.py` -- add `update_profile(db, user, data)` and `change_password(db, user, data)` -- houses hashing/verification business logic per AD-2
- [x] `backend/app/auth/repository.py` -- add persistence helper(s) for updating a user row -- keeps DB access in the repository layer
- [x] `backend/app/auth/routes.py` -- add `PATCH /auth/me` and `POST /auth/me/password`, both `Depends(get_current_user)` -- exposes the new functionality per AD-3
- [x] `backend/tests/test_auth_profile.py` -- new file, cover all I/O Matrix rows -- verifies happy path + each error case
- [x] `frontend/src/api/settingsClient.js` -- add `updateProfile(authFetch, data)` and `changePassword(authFetch, data)` -- typed client calls following the existing `updateTheme` pattern in this file
- [x] `frontend/src/components/settings/ProfileCard.jsx` -- new self-saving card mirroring `AppearanceCard.jsx`'s optimistic-update/saving/error pattern -- delivers Profile functionality
- [x] `frontend/src/components/settings/ChangePasswordCard.jsx` -- new self-saving card, same pattern, with current/new password fields -- delivers Change Password functionality
- [x] `frontend/src/components/settings/DeleteAccountCard.jsx` -- new static danger-tinted shell, button disabled/no-op -- delivers the card shell Story 5.3 will wire up
- [x] `frontend/src/pages/SettingsPage.jsx` -- add `<ProfileCard />`, `<ChangePasswordCard />`, `<DeleteAccountCard />` into the existing grid alongside `<AppearanceCard />` -- completes the four-card layout

**Acceptance Criteria:**
- Given I open User Settings, when the page renders, then four independent cards (Profile, Change Password, Appearance, Delete Account) appear in the existing two-column grid at 900px max width
- Given the four cards, when I save one, then it saves independently — no other card's state is touched or required
- Given the Change Password card, when I submit a new password from my authenticated session, then the password is changed and hashed with `bcrypt_sha256`
- Given the Delete Account card, when it renders, then it carries the danger-tinted border/background, visually separated from the other three, and its action does nothing (no crash, no request sent) since Story 5.3 owns the logic
- Given any validation failure on Profile or Change Password, when the error returns, then it uses the `HTTPException` `{"detail": ...}` shape with a plain, declarative message

## Spec Change Log

## Verification

**Commands:**
- `cd backend && pytest tests/test_auth_profile.py -v` -- expected: all new tests pass
- `cd backend && pytest tests/ -v` -- expected: no regressions in existing auth/document tests
- `cd frontend && npm run build` -- expected: builds without errors

**Manual checks (if no CLI):**
- Open `/settings` in the browser: confirm four-card grid renders at 900px max width, two columns; update full name and confirm it persists on reload; change password and confirm re-login works with the new password and fails with the old one; confirm Delete Account card is visually danger-tinted and its button does nothing (no crash) when clicked.

## Suggested Review Order

**Password change (backend)**

- Entry point: verifies the current password server-side before rehashing and persisting the new one — the core of the in-session change requirement.
  [`service.py:138`](../../backend/app/auth/service.py#L138)

- Rate limiter keyed by the authenticated user's id (not IP) — added during review since this route is otherwise the only unrate-limited auth mutation.
  [`rate_limiter.py:50`](../../backend/app/auth/rate_limiter.py#L50)

- Route wires the limiter and delegates to the service; no business logic lives here.
  [`routes.py:90`](../../backend/app/auth/routes.py#L90)

- Request schema reuses `RegisterRequest`'s `min_length=8, max_length=128` bound so registration and password-change enforce the same rule.
  [`schemas.py:106`](../../backend/app/auth/schemas.py#L106)

**Profile update (backend)**

- Route + response shape for the profile PATCH.
  [`routes.py:80`](../../backend/app/auth/routes.py#L80)

- Validator mirrors `RegisterRequest._strip_full_name` exactly so both entry points reject blank names identically.
  [`schemas.py:91`](../../backend/app/auth/schemas.py#L91)

**Settings UI**

- Self-saving card mirroring `AppearanceCard`'s pattern; loads its own `/auth/me` copy since `AuthContext` doesn't carry profile fields.
  [`ProfileCard.jsx:11`](../../frontend/src/components/settings/ProfileCard.jsx#L11)

- Failed initial load now surfaces via the existing `role="alert"` path instead of leaving a silently blank form — the review-round fix.
  [`ProfileCard.jsx:36`](../../frontend/src/components/settings/ProfileCard.jsx#L36)

- Independent current/new password fields and save state, isolated from `ProfileCard`.
  [`ChangePasswordCard.jsx:6`](../../frontend/src/components/settings/ChangePasswordCard.jsx#L6)

- Static danger-tinted shell only — Story 5.3 owns wiring the button.
  [`DeleteAccountCard.jsx:5`](../../frontend/src/components/settings/DeleteAccountCard.jsx#L5)

- Grid gains the three new cards alongside Story 5.2's `AppearanceCard`; the grid itself is unchanged.
  [`SettingsPage.jsx:1`](../../frontend/src/pages/SettingsPage.jsx#L1)

- Client functions mirror `updateTheme`'s exact shape (`authFetch` first, `formatDetail` for errors).
  [`settingsClient.js:21`](../../frontend/src/api/settingsClient.js#L21)

**Tests**

- Backend I/O-matrix coverage plus the two rate-limit tests added in review.
  [`test_auth_profile.py:1`](../../backend/tests/test_auth_profile.py#L1)

- New `updateProfile`/`changePassword` client tests, added in review, mirroring `updateTheme`'s existing three-test shape.
  [`settingsClient.test.js:33`](../../frontend/src/api/settingsClient.test.js#L33)
