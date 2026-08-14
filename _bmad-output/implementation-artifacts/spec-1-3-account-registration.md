---
title: 'Story 1.3: Account registration'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: '8e903aa5200f19509ad7f23602d2200ddc0a284a'
provenance: 'reconstructed-after-implementation'
---

> **Provenance — read this before trusting the Boundaries below.**
>
> This spec was authored on 2026-08-14, two epics after Story 1.3 shipped (`2f39942`, merged during Epic 1) and after one review-round fix on it. Story 1.3 is the earliest story in this project without a spec file — earlier even than Story 2.3, whose own missing-spec entry (`deferred-work.md`) explicitly warned the gap would recur, and it already had: 1.3 and its sibling 1.4 both shipped without one, before 2.3 ever did.
>
> The Boundaries below are reconstructed from `epics.md`'s Story 1.3 acceptance criteria, the shipped code's own comments, and one review-round commit (`d92cdfd`). They describe what the story turned out to be bound by, not decisions a human approved in advance. Nothing here was negotiated before implementation. See `spec-3-1`'s and `spec-2-3`'s own provenance notes for the fuller version of why this distinction matters — the short version is that a retro-spec presenting itself as frozen would let a future story wrongly treat a reconstructed line as a decision no one is allowed to revisit.
>
> **Scope note:** several things this story built were later extended by name in its own commit message ("two intentional scope overlaps for later stories"): the Postgres session plumbing here (`shared/data_access/session.py`) belongs to Story 1.5's shared DAL and was extended, not rebuilt, there; the minimal OS-preference `ThemeContext` here belongs to Story 1.2's full token/toggle system and was likewise extended. This spec's claim on those two files is limited to what 1.3 itself put there.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.1 ships an empty skeleton with no schema, no persistence, and a `/health` endpoint as its only real route. Nothing exists to create an account against, so every later story (auth-gated shell, uploads, chat) has no identity to scope data to.

**Approach:** The first real backend logic and the first real database table. `POST /auth/register` hashes the password (bcrypt_sha256), persists a `users` row via the first Alembic migration, and rejects a duplicate email with a 409. A themed Registration page renders outside the (not-yet-built) authenticated shell, using a minimal OS-preference-only theme context as a stopgap ahead of Story 1.2's full token system. Password reset and email verification are explicitly out of v1 scope.

## Boundaries & Constraints

**Always:**
- The password is stored hashed with `bcrypt_sha256`, never in plaintext (FR-1) — verified by reading the stored `password_hash` back through the endpoint, not merely asserting a hashing function was called.
- The Alembic migration for this story creates only the `users` table — no other table is created ahead of the story that actually needs it (a standing convention this project holds through every later migration).
- A rejected request returns FastAPI's own `HTTPException` `{"detail": ...}` shape — no custom error envelope (AD-3, first applied here). The message is plain and declarative, no apologetic filler or emoji (UX-DR19).
- No password reset flow, no email verification flow — both explicitly out of v1 scope; not a partial stub, not present at all.
- The Registration page renders correctly in both light and dark themes (UX-DR2), even though it sits outside the authenticated shell and Story 1.2's full token system doesn't exist yet.
- Email normalization happens once, at the schema/validator layer (`RegisterRequest`), not in the service — so Story 1.4's login can't drift onto a different casing rule than registration used to create the account.
- The DB engine and session factory are constructed lazily, never at module import time — an eager construction would open a live Neon connection on every test-process import and crash the suite outright on any machine without `backend/.env` configured.

**Ask First:** none outstanding at the time this spec was reconstructed.

**Never:**
- No password reset or email verification flow (see Always — repeated because it is the AC most likely to be "helpfully" half-built by a future change).
- No rebuilding of the Postgres session plumbing or the theme context when Story 1.5 / Story 1.2 land — those stories extend what 1.3 built here, per this story's own commit message recording the overlap as intentional.
- Real Neon credentials never become visible to the test process — `conftest.py`'s env-var fallbacks are set at module import time, before any test module (starting with `test_health.py`) is collected, specifically so a developer's real `.env` can never leak into a pytest run via import order.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal registration | Valid, unique email + password | 201, account created, `password_hash` is a real bcrypt_sha256 hash | N/A |
| Duplicate email | Email already registered | 409 | `{"detail": ...}`, plain message |
| Concurrent duplicate registration | Two requests for the same email race past an application-level check | 409 from the DB-level `IntegrityError`, not a 500 | Caught and translated, not left to propagate |
| Invalid/incomplete input | Missing field, malformed email | FastAPI's own validation-error shape | `{"detail": ...}`, no custom envelope |
| Password below/above length bound | Too short, or over 128 chars | Rejected at the schema layer | `{"detail": ...}` |
| Test suite runs with no `backend/.env` | No real Neon DSN available | Suite still passes — engine construction is lazy, `conftest.py` supplies fallbacks before collection | N/A |

</frozen-after-approval>

## Spec Change Log

Story 1.3 shipped before this file existed, so this entry is reconstructed from the one pre-merge review-round commit (`d92cdfd`, "address Story 1.3 code review findings"). Recorded here because the reasoning was previously only discoverable by reading `git log`.

- **Trigger:** Review pass on the initial implementation (`f9290c8`), all tests green.
- **Email normalization moved:** from the service into `RegisterRequest`'s own validator — so a later story (1.4, login) reading the same request shape can't apply a different casing rule than registration used, which would make an account effectively unreachable by a differently-cased but semantically identical email.
- **Password length capped at 128** to match the mockup's implied bound — previously unbounded on the high end.
- **Commit/rollback boundary moved up:** from `repository` into `service` — the repository now only adds and flushes. Recorded explicitly as forward-looking: a future multi-write operation needs to own its own transaction boundary, not delegate it to the lowest layer.
- **`get_db_session`'s return type fixed:** `Iterator[Session]`, not `Session` — it's a generator, and the prior annotation was simply wrong.
- **Two tests added that AC1 already implied but nothing pinned:** the DB-level `IntegrityError` race path (two near-simultaneous registrations for the same email) actually returns 409, not a 500; and the stored `password_hash` is verified as a real bcrypt_sha256 hash by reading it back through the endpoint, not merely asserting a hashing call happened.
- **Frontend contrast and routing fixes:** `--danger`/`--on-primary` tokens sourced from the reference mockup's `.btn-primary` rule, replacing hardcoded Tailwind color classes that failed AA contrast in dark mode; a `prefers-color-scheme` media-query default to prevent a light-theme flash on load for dark-OS users, ahead of `ThemeContext`'s own JS running; FastAPI's list-shaped validation `detail` now parsed properly in `authClient` instead of falling back to a generic status-code message; a placeholder `/login` route (plus a catch-all) added so the page's own "Log in" link doesn't dead-end on a blank screen before Story 1.4 exists; `role="alert"` and `autoComplete` attributes added to the form.
- **A fourth token gap recorded, not fixed:** `epic-1-context.md` gained an entry noting `--accent` used as link/small-text color fails AA contrast in both themes — inherited from the reference mockup, not introduced by this story, and flagged for Story 1.2 to resolve rather than guessed at unilaterally here.
- **KEEP:** every boundary above.

## Code Map

- `backend/alembic/versions/473e7200923a_create_users_table.py` -- new: the first migration, `users` table only
- `backend/app/shared/models.py` -- edit: `User` ORM model
- `backend/app/shared/data_access/session.py` -- new: lazy engine/session-factory construction (later extended into the shared DAL by Story 1.5 — see this file's Scope note)
- `backend/app/shared/data_access/__init__.py` -- edit: exports the session dependency
- `backend/app/auth/schemas.py` -- new: `RegisterRequest` (email normalization, password length bound), response shape
- `backend/app/auth/repository.py` -- new: add + flush only; commit boundary owned by `service.py` (review-round fix)
- `backend/app/auth/service.py` -- new: `register_account` — hash, persist, 409 translation on both the pre-check and the DB-level race
- `backend/app/auth/routes.py` -- new: `POST /auth/register`
- `backend/app/main.py` -- edit: env-var validation extended for the DB connection string
- `backend/requirements.txt` -- edit: `bcrypt`/`passlib`-family hashing dependency, Alembic, SQLAlchemy driver
- `frontend/src/context/ThemeContext.jsx` -- new: minimal OS-preference-only theme (later replaced by Story 1.2's full token/toggle system — see this file's Scope note)
- `frontend/src/pages/RegisterPage.jsx` -- new: the Registration page, outside the authenticated shell
- `frontend/src/api/authClient.js` -- new: `registerAccount`, FastAPI validation-`detail` parsing (review-round fix)
- `frontend/src/App.jsx` -- edit: routing for `/register`, placeholder `/login` + catch-all (review-round addition)
- `frontend/src/main.jsx` -- edit: theme context provider wiring
- `frontend/src/index.css` -- edit: `--danger`/`--on-primary` tokens, `prefers-color-scheme` default (review-round fixes)
- `backend/tests/conftest.py` -- edit: module-import-time env-var fallbacks, so a real `.env` can never leak into the test process
- `backend/tests/test_auth_registration.py` -- new: registration endpoint, including the two review-round-added tests (IntegrityError race → 409, real hash verification)
- `backend/tests/test_auth_service.py` -- new: service-layer unit coverage

## Tasks & Acceptance

**Execution:**
- [x] `backend/alembic/versions/473e7200923a_create_users_table.py` -- first migration, `users` only
- [x] `backend/app/shared/data_access/session.py` -- lazy engine/session construction
- [x] `backend/app/auth/schemas.py` + `repository.py` + `service.py` + `routes.py` -- registration path end to end
- [x] `frontend/src/context/ThemeContext.jsx` -- minimal stopgap theme context
- [x] `frontend/src/pages/RegisterPage.jsx` + `api/authClient.js` -- Registration page and its API client
- [x] `backend/tests/test_auth_registration.py`, `test_auth_service.py` -- including the review-round IntegrityError-race and real-hash tests

**Acceptance Criteria:**
- Given valid credentials submitted on the Registration page, when the request succeeds, then an account is created and the password is stored bcrypt_sha256-hashed, never in plaintext.
- Given no database schema exists yet, when this story is implemented, then the migration creates only the `users` table.
- Given invalid or incomplete input, when the request is rejected, then it returns as `HTTPException` with a `{"detail": ...}` body, plain and declarative.
- Given password reset and email verification are out of v1 scope, when registration is built, then neither flow is implemented, even partially.
- Given the Registration page is outside the authenticated shell, when it renders, then it displays correctly in both light and dark themes.

## Design Notes

`bcrypt_sha256` (not bare bcrypt) sidesteps bcrypt's 72-byte input truncation by pre-hashing with SHA-256 first — chosen so an unusually long password isn't silently truncated before hashing, which would make two different long passwords collide on the same stored hash.

The lazy engine-construction fix was not part of the original plan — it surfaced as a pre-commit finding during this same story's implementation (per `f9290c8`'s own commit message) and was folded in immediately: an eagerly-constructed engine at import time both leaked a live Neon connection pool into every pytest run and would crash the suite outright on any machine without `backend/.env` present. `conftest.py`'s fallback env vars are set at *module* import time, before test collection begins, specifically so import order can't let a real DSN slip through before the fallback takes effect.

The minimal `ThemeContext` built here reads only the OS `prefers-color-scheme` media query — no manual toggle, no persistence. It exists so the Registration page (built here, outside the authenticated shell Story 1.5 hasn't built yet) isn't stuck rendering only a light theme ahead of Story 1.2's real token/toggle system landing.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the review-round-added IntegrityError-race and hash-verification tests
- `npm run build` (from `frontend/`) -- expected: clean (no dedicated `RegisterPage` test file exists for this story; frontend coverage for this flow is build-clean plus the backend endpoint tests)

**Manual checks (if no CLI):**
- Register a new account, confirm the row's `password_hash` is not the plaintext password and is a valid bcrypt_sha256 hash. Attempt to register the same email twice and confirm a 409 with a plain, non-apologetic message. Load the Registration page under both an OS light and OS dark preference and confirm it renders correctly in each without a flash of the wrong theme.
