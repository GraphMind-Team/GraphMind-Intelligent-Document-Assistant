---
title: 'Story 1.4: Login and JWT session'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '2f399428c2f13757986c11143b8ba901d773b338'
provenance: 'reconstructed-after-implementation'
---

> **Provenance — read this before trusting the Boundaries below.**
>
> This spec was authored on 2026-08-14, two epics after Story 1.4 shipped (`efce0ee`, merged during Epic 1, single commit `65ab9fd`, no separate review-round fix). Story 1.4 has the same missing-spec-file gap as its sibling Story 1.3 (`spec-1-3`, resolved alongside this file) and as Story 2.3 (`spec-2-3`) and Story 3.1 (`spec-3-1`) — four occurrences of the same process gap across this project, the first two (1.3, 1.4) never previously recorded anywhere.
>
> The Boundaries below are reconstructed from `epics.md`'s Story 1.4 acceptance criteria and the shipped code's own comments — there is only one commit for this story, so unlike `spec-1-3`/`spec-2-3`/`spec-3-1` there is no review-round Spec Change Log to draw on. They describe what the story turned out to be bound by, not decisions a human approved in advance. See `spec-1-3`'s, `spec-2-3`'s, and `spec-3-1`'s own provenance notes for the fuller reasoning — the short version is that a retro-spec presenting itself as frozen would let a future story wrongly treat a reconstructed line as a decision no one is allowed to revisit.
>
> **Scope note:** `TRUSTED_PROXY_HOSTS` (`backend/app/main.py`) was added later, by Story 1.5, to correct a limitation in *this* story's rate limiter — `request.client.host` resolves to a reverse proxy's own IP once deployed behind one, degrading the per-`(ip, email)` limiter built here to a single shared budget for the whole site. That fix belongs to `spec-1-5`'s Code Map, not this one; it is referenced in Design Notes below only as a forward pointer. Frontend automated test coverage for this story's own surfaces (`LoginPage.test.jsx`, `AuthContext.test.jsx`) was likewise added later, by a distinct subsequent commit (`8b35660`) — not part of what 1.4 itself shipped with. See Verification for what that means for this spec's own commands.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.3 can create an account, but nothing can authenticate against one — no login endpoint, no session mechanism, no way for a later protected route (documents, chat, kg) to know who's asking. A pre-restart version of this project's auth layer had a known, recorded set of pitfalls (no rate limiting, a weakly-typed JWT algorithm, account-enumeration-revealing responses) that this rebuild is positioned to avoid rather than repeat.

**Approach:** `POST /auth/login` issues a JWT on valid credentials; `GET /auth/me` proves the token round-trips through a protected route. A `get_current_user` FastAPI dependency resolves `user_id` server-side from the token and becomes the reusable gate every later protected route in every module depends on. A generic 401 covers both "no such email" and "wrong password" with dummy-hash timing parity, closing the enumeration gap the pre-restart codebase had. An in-process per-`(ip, email)` rate limiter on `/auth/login` closes the other gap explicitly carried forward from Story 1.3's own review. Frontend: `LoginPage` plus a `localStorage`-backed `AuthContext` exposing `authFetch`, the helper every later story's protected calls build on.

## Boundaries & Constraints

**Always:**
- Valid credentials issue a JWT, sent in the `Authorization` header on every subsequent request (FR-1).
- Invalid credentials receive a clear error and no session is established — and the error is the *same* generic message ("Invalid email or password.") whether the email doesn't exist or the password is wrong. Enumeration through response content is exactly the pitfall this story exists to close.
- `user_id` is resolved server-side from the token via `get_current_user` — no client-supplied user identifier is ever trusted for this (FR-2). This dependency is the reusable gate every future protected route in every module (documents, chat, kg) depends on, not a one-off check local to `/auth/me`.
- An expired, malformed, or absent JWT is rejected with 401 *before* any data access occurs — including the auth check's own DB lookup: `get_current_user` decodes and validates the token first, and only reaches `repository.get_user_by_id` once the token itself has already passed.
- The JWT algorithm is named in exactly one place (`JWT_ALGORITHM`), used by every encode/decode call in this module, hardcoded rather than environment-configurable — there is no legitimate reason to change it at runtime, and hardcoding removes any path to a misconfigured or attacker-influenced algorithm (e.g. `"none"`).
- A login attempt against a nonexistent email still runs a real `bcrypt_sha256.verify` call, against a precomputed dummy hash, so its wall-clock time is not distinguishable from a wrong-password attempt against a real account — a timing side-channel is exactly as capable of revealing which emails are registered as a differing error message would be.
- `/auth/login` is rate-limited per `(client IP, normalized email)` — 5 attempts per 60-second window, reset on a successful login so legitimate repeat logins don't erode the same budget as failed guesses. This closes the gap Story 1.3's own review explicitly carried forward: registration's 409 already reveals email existence by necessity (you must tell a user the address is taken), so throttling — not message-vagueness — was recorded as the real mitigation needed once a login endpoint existed to abuse.
- `authFetch` (the `AuthContext` helper every later story's protected calls use) treats a 401 response as an invalid/expired session and logs out automatically — later stories build their protected calls on top of this, not around it.

**Ask First:** none outstanding at the time this spec was reconstructed.

**Never:**
- No account-enumeration-revealing login response — neither in message content nor in response timing.
- No client-configurable or client-supplied JWT algorithm.
- No trusting a client-supplied `user_id` anywhere a request claims to act as a particular user — always re-resolved from the verified token.
- No distributed rate-limiting infrastructure — the in-process limiter is explicitly scoped as correct for a single-process MVP deployment, not a promise to scale past it. (Recorded in the limiter's own docstring, not silently assumed.)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal login | Valid email + password | 200, JWT issued | N/A |
| Wrong password | Valid email, wrong password | 401, generic message | Same message and comparable timing as "no such email" |
| Nonexistent email | Email not registered | 401, generic message | Dummy-hash verify runs regardless, for timing parity |
| 6th login attempt within 60s | Same `(ip, email)` pair, 5 already recorded | 429 | `{"detail": "Too many login attempts. Try again later."}` |
| Login succeeds after prior failures | A now-correct attempt within the same window | 200, and the `(ip, email)` attempt history is cleared | N/A |
| Protected route, absent token | No `Authorization` header | 401, before any DB call | N/A |
| Protected route, malformed token | Garbage/truncated JWT | 401, before any DB call | N/A |
| Protected route, expired token | Valid signature, `exp` in the past | 401, before any DB call | N/A |
| Protected route, valid token for a deleted user | Token verifies, but `repository.get_user_by_id` finds nothing | 401 | The DB call *does* run here — the token alone can't prove the account still exists |
| `authFetch` receives a 401 | Any protected call the frontend makes | Session is cleared, user is logged out | N/A |

</frozen-after-approval>

## Spec Change Log

Story 1.4 shipped as a single commit (`65ab9fd`) with no separate pre-merge review-round fix — unlike Story 1.3 (`d92cdfd`), Story 2.3 (five review rounds), or Story 3.1 (three). There is no Change Log to reconstruct here; this section exists only to record that fact explicitly, so its absence reads as "there wasn't one" rather than as this retro-spec having missed something.

- **KEEP:** every boundary above, as shipped in the one commit.

## Code Map

- `backend/app/auth/service.py` -- edit: `JWT_ALGORITHM` constant, `create_access_token`/`decode_access_token`, `authenticate_user` (dummy-hash timing parity)
- `backend/app/auth/dependencies.py` -- new: `get_current_user` — the reusable protected-route dependency every later module's protected routes build on
- `backend/app/auth/rate_limiter.py` -- new: `LoginRateLimiter`, per-`(ip, email)` fixed-window counter, `get_login_rate_limiter` FastAPI dependency
- `backend/app/auth/routes.py` -- edit: `POST /auth/login`, `GET /auth/me`
- `backend/app/auth/schemas.py` -- edit: `LoginRequest`, `LoginResponse`, `MeResponse`
- `backend/app/auth/repository.py` -- edit: `get_user_by_id` (alongside 1.3's `get_user_by_email`)
- `backend/.env.example` -- edit: documents `JWT_SECRET`/`ACCESS_TOKEN_EXPIRE_MINUTES`
- `backend/requirements.txt` -- edit: `PyJWT`
- `frontend/src/context/AuthContext.jsx` -- new: `localStorage`-backed token state, `authFetch` (auto-logout on 401) — the helper every later story's protected calls are built on
- `frontend/src/pages/LoginPage.jsx` -- new: the Login page
- `frontend/src/api/authClient.js` -- edit: `loginAccount`
- `frontend/src/App.jsx` -- edit: routing/provider wiring for the login flow
- `frontend/src/main.jsx` -- edit: `AuthProvider` wiring
- `.claude/launch.json` -- new: dev-server launch config (tooling, not app behavior)
- `backend/tests/test_auth_login.py` -- new: login success/failure, rate limiting, `/auth/me`, token validation edge cases
- `backend/tests/test_auth_service.py` -- edit: `create_access_token`/`decode_access_token`/`authenticate_user` unit coverage
- `backend/tests/conftest.py` -- edit: minor fixture adjustment for the new auth surface

**Not part of this story's own Code Map, added later:** `frontend/src/pages/LoginPage.test.jsx` and `frontend/src/context/AuthContext.test.jsx` were added by a distinct subsequent commit (`8b35660`), not `65ab9fd`. See this file's provenance note.

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/auth/service.py` -- JWT issue/decode, dummy-hash timing parity for `authenticate_user`
- [x] `backend/app/auth/dependencies.py` -- `get_current_user`, 401-before-DB-access ordering
- [x] `backend/app/auth/rate_limiter.py` -- per-`(ip, email)` login rate limiting
- [x] `backend/app/auth/routes.py` + `schemas.py` + `repository.py` -- `POST /auth/login`, `GET /auth/me`
- [x] `frontend/src/context/AuthContext.jsx` -- token persistence, `authFetch` auto-logout on 401
- [x] `frontend/src/pages/LoginPage.jsx` + `api/authClient.js` -- Login page and its API client
- [x] `backend/tests/test_auth_login.py`, `test_auth_service.py` -- login, rate limiting, protected-route token validation

**Acceptance Criteria:**
- Given valid credentials on the Login page, when authentication succeeds, then a JWT is issued and sent in the `Authorization` header on every subsequent request.
- Given credentials that don't match an account, when authentication fails, then a clear error returns and no session is established.
- Given a request carrying a JWT, when a protected endpoint handles it, then `user_id` is resolved server-side from the token — never trusted from client input.
- Given a JWT that is expired, malformed, or absent, when a protected endpoint is called, then the request is rejected with 401 before any data access occurs.

## Design Notes

The six pitfalls a 2026-08-09 review of the pre-restart GraphMind codebase's auth layer left unresolved (no rate limiting, a weakly-typed JWT algorithm, `db.py` bypassing central config, SQLAlchemy `echo=True` left on, enumeration-revealing signup/login responses, tests running against the live Neon database) directly shaped this story and Story 1.3 before it. 1.3 closed four of the six; this story closes the remaining two that specifically needed a login endpoint to exist first — rate limiting and enumeration-revealing responses (both message content and timing). This context lived only in a pre-implementation review note, not in `epics.md` itself, which is why it's recorded here rather than left implicit in the code comments alone.

`get_current_user` (`dependencies.py`) is deliberately route-layer wiring, not business logic — kept separate from `service.py` so it's reusable as `Depends(get_current_user)` across every future protected route in every later module, without those modules needing to know anything about JWT internals.

The rate limiter is explicitly in-process and per-`(ip, email)`, not distributed — correct for a single-process MVP deployment, and its own docstring says so rather than silently assuming it. `client_ip` is read from `request.client.host`, which resolves to a reverse proxy's own IP once actually deployed behind one — a real limitation at the time this story shipped, later corrected by Story 1.5's `TRUSTED_PROXY_HOSTS` (see this file's provenance note; that fix is `spec-1-5`'s, not this story's).

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including `test_auth_login.py`'s rate-limiting and token-validation cases
- `npm run build` (from `frontend/`) -- expected: clean. No dedicated frontend test file existed for `LoginPage`/`AuthContext` at the time this story shipped (see provenance note) — frontend coverage for this flow at ship time is build-clean plus the backend endpoint tests; `LoginPage.test.jsx`/`AuthContext.test.jsx` exist in the current tree but belong to a later commit's scope, not this spec's.

**Manual checks (if no CLI):**
- Register an account, log in with the correct password, confirm a JWT is returned and `GET /auth/me` succeeds with it. Attempt login with a wrong password and with a nonexistent email; confirm both return the identical generic message. Attempt 6 logins for the same email within a minute and confirm the 6th returns 429. Call a protected route with no token, a malformed token, and an expired token; confirm 401 in all three cases.
