---
title: 'Story 1.6: Verify my email address before I can log in'
type: 'feature'
created: '2026-08-20'
status: 'in-progress'
review_loop_iteration: 0
context: []
provenance: 'authored-before-implementation'
---

> **Scope amendment.** This story adds email verification, which `epics.md` FR-1, the PRD (§4.1, §6.2, Assumptions Index), the addendum's risk register, and `spec-1-3-account-registration.md` all previously declared explicitly out of v1 scope. All four documents now carry a superseded note pointing here, dated 2026-08-20. The `epics.md` precedent for pulling a deferred item forward once the v1 DoD gate closed is FR-17 (conversational memory, Story 3.4); this follows the same shape. Password reset remains out of scope — only email verification is pulled forward.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `POST /auth/register` (Story 1.3) creates a usable, immediately-loginable account from any syntactically valid email address, with nothing confirming the person registering actually controls that inbox. Anyone can register under someone else's address, and typo'd or throwaway addresses accumulate real documents and graph data with no way to reach the account owner.

**Approach:** A signed, single-purpose JWT (`typ: "email_verify"`, reusing the existing `JWT_SECRET` and `jwt.encode`/`jwt.decode` machinery already in `auth/service.py` — no new token table) is mailed on registration via a new `shared/email` module (stdlib `smtplib`, console-log fallback when `SMTP_HOST` is unset). `POST /auth/login` rejects an unverified account with 403 once `REQUIRE_EMAIL_VERIFICATION` (default on) is set. `POST /auth/verify-email` consumes the token and flips `users.email_verified_at`; `POST /auth/resend-verification` issues a fresh one without ever revealing whether the target email exists. Every account that predates this migration is grandfathered as verified via a backfill from `created_at`, so no existing account is locked out.

## Boundaries & Constraints

**Always:**
- `email_verified_at` is a nullable `DateTime`, not a boolean — records *when*, and `NULL` is the real, meaningful "never verified" state (not a placeholder awaiting a staged backfill the way `documents.content_hash` was).
- The verification token is a JWT signed with the same `JWT_SECRET` as the access token, distinguished only by a `"typ": "email_verify"` claim. `decode_access_token` rejects any token carrying a `typ` other than `None`; `decode_email_verification_token` rejects any token whose `typ` isn't exactly `"email_verify"`. Both directions are enforced — a verification token must never work as a bearer credential, and an access token must never pass as a verification token — because both are signed with the same secret and would otherwise be silently interchangeable.
- `POST /auth/verify-email` is POST, not GET — a GET link would be pre-fetched and burned by mail-scanner/link-preview bots before the human ever clicks it.
- Verifying an already-verified account is a success, not an error (idempotent) — a double-clicked link must not show a scary failure for something that isn't actually a problem.
- `POST /auth/resend-verification` returns the exact same response body regardless of whether the target email belongs to a real account, an already-verified account, or nothing at all — this endpoint must never become an account-enumeration oracle, matching `authenticate_user`'s existing generic-401 reasoning for login.
- Sending the verification email is a `BackgroundTasks` job scheduled from the route, exactly like `documents/routes.py`'s `ingest_document` — an SMTP round trip must not hold the 201/202 response open, and a mail outage must never turn an otherwise-successful registration into a 500. Both this task and `resend_verification`'s own background job open their own DB session via an injectable `session_factory` (mirroring `ingest_document`'s pattern) rather than reusing the request's `db`, which is already closed by the time a background task runs.
- `REQUIRE_EMAIL_VERIFICATION` defaults to `"true"` (verified-only login in production) but is read lazily per-call, the same pattern as `_access_token_expire_minutes`/`_jwt_secret` — never added to `main.REQUIRED_ENV_VARS`, since the app must still boot with no mail configured.
- Leaving `SMTP_HOST` unset/blank is a first-class, permanently supported mode, not a stub: `shared/email.send_email` logs the recipient, subject, and full body (including the verify link) instead of failing. Local dev and the whole backend test suite run this way by default.
- The migration backfills `email_verified_at = created_at` for every pre-existing row in the same migration that adds the column — never a separate follow-up step, and never left NULL for rows that predate this story.

**Ask First:** none outstanding — SMTP provider choice for production deployment is a deploy-checklist item (`deferred-work.md`), not a code decision this story blocks on.

**Never:**
- No password reset flow — still explicitly out of v1 scope, unchanged by this story.
- No new token table, no distributed rate-limiter, no queue/worker — this stays within the existing in-process `RateLimiter`/JWT/`BackgroundTasks` machinery, matching every other Epic 1 story's infra footprint.
- The `typ`-based cross-use guard is never implemented as "reject if `typ == "email_verify"`" on the access-token side alone — it must also reject any *other* unexpected `typ` value, not just the one this story happens to introduce, so a future third token kind doesn't reopen the same hole by accident.
- `resend_verification` never takes the request's `db: Session` directly as a background-task argument — that session is closed by the time the task runs; it must open its own via `session_factory`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Registration | Valid registration payload | 201 (unchanged), plus one verification email scheduled to the registered address | A send failure is logged, never surfaced to the 201 response |
| Login, unverified, flag on | Correct credentials, `email_verified_at IS NULL`, `REQUIRE_EMAIL_VERIFICATION` true | 403, distinct verify-your-email message | `{"detail": ...}` |
| Login, unverified, flag off | Same, `REQUIRE_EMAIL_VERIFICATION` false | 200 (unchanged pre-1.6 behavior) | N/A |
| Login, verified | `email_verified_at` set (real verify, or migration backfill) | 200 | N/A |
| Verify, valid unexpired token | POST `/auth/verify-email` | 200, `email_verified_at` set | N/A |
| Verify, already verified | Same token (or any valid token for that user), re-POSTed | 200, no error (idempotent) | N/A |
| Verify, garbage/expired/wrong-secret token | Malformed, expired, or mis-signed string | 400 | `{"detail": "This verification link is invalid or has expired."}` |
| Verify, access token used as a verification token | A real login-issued JWT | 400 (rejected by the `typ` check) | Same 400 as above |
| Protected route, verification token used as bearer | A real verify-email-issued JWT sent as `Authorization: Bearer ...` | 401 | `{"detail": "Not authenticated."}` |
| Resend, unknown email | Any syntactically valid email | 202, fixed body | N/A |
| Resend, unverified real email | Existing, unverified account | 202, fixed body, one email actually sent | N/A |
| Resend, already-verified email | Existing, verified account | 202, fixed body, no email sent | N/A |
| Resend, rate limit exceeded | 6th request within the window for one (IP, email) pair | 429 | `{"detail": "Too many verification email requests. Try again later."}` |
| Pre-1.6 account after migration | `email_verified_at` backfilled from `created_at` | Logs in normally under the flag | N/A |
| No SMTP configured | `SMTP_HOST` unset | Email body (including the link) logged to console instead of sent; request still succeeds | N/A |

</frozen-after-approval>

## Spec Change Log

- **Initial version**, authored ahead of implementation (no review round yet).

## Code Map

- `backend/app/shared/models.py` -- edit: `User.email_verified_at`
- `backend/alembic/versions/21fe494be69e_add_email_verified_at_to_users.py` -- new: adds the column, backfills every existing row from `created_at`
- `backend/app/shared/email/__init__.py` -- new: `send_email` (stdlib `smtplib`, console fallback)
- `backend/app/auth/service.py` -- edit: `EMAIL_VERIFICATION_TOKEN_TYPE`, `create_email_verification_token`, `decode_email_verification_token`, the `typ` guard added to `decode_access_token`, `send_verification_email`, `verify_email`, `resend_verification`, `_require_email_verification`, the gate added to `authenticate_user`
- `backend/app/auth/repository.py` -- edit: `mark_email_verified`
- `backend/app/auth/schemas.py` -- edit: `VerifyEmailRequest/Response`, `ResendVerificationRequest/Response`, `MeResponse.email_verified`
- `backend/app/auth/routes.py` -- edit: `register` schedules the verification email; new `POST /auth/verify-email`, `POST /auth/resend-verification`
- `backend/app/auth/rate_limiter.py` -- edit: `get_resend_verification_rate_limiter`
- `backend/.env.example` -- edit: `SMTP_*`, `REQUIRE_EMAIL_VERIFICATION`, `EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS`
- `backend/scripts/isolation_proof.py` -- edit: `PUBLIC_ALLOWLIST_PATHS` gains `/auth/verify-email`, `/auth/resend-verification`
- `frontend/src/api/authClient.js` -- edit: `verifyEmail`, `resendVerification`, `loginAccount` now attaches `error.status`
- `frontend/src/pages/VerifyEmailPage.jsx` -- new
- `frontend/src/App.jsx` -- edit: `/verify-email` route, outside both route guards
- `frontend/src/pages/RegisterPage.jsx` -- edit: check-your-inbox success state, resend action
- `frontend/src/pages/LoginPage.jsx` -- edit: 403 handling, resend action
- `backend/tests/conftest.py` -- edit: `REQUIRE_EMAIL_VERIFICATION` default, resend limiter added to the fixture, `_stub_outbound_email`, `client` fixture's `get_session_factory` patch for `resend_verification`'s background-task session
- `backend/tests/test_auth_email_verification.py` -- new
- `backend/tests/test_auth_login.py` -- edit: one pinning test for the flag-off default
- `backend/tests/test_documents_upload.py` -- edit: `_fresh_rate_limiters` tuple unpacking updated for the new limiter
- `backend/tests/test_isolation_proof.py` -- unaffected directly; covered by the `PUBLIC_ALLOWLIST_PATHS` update above
- `frontend/src/pages/VerifyEmailPage.test.jsx` -- new
- `frontend/src/pages/RegisterPage.test.jsx` -- new
- `frontend/src/pages/LoginPage.test.jsx` -- edit: 403/resend coverage

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/models.py` + migration -- `email_verified_at` column, backfilled
- [x] `backend/app/shared/email/__init__.py` -- outbound mail with console fallback
- [x] `backend/app/auth/service.py` + `repository.py` + `schemas.py` + `routes.py` + `rate_limiter.py` -- verification flow end to end
- [x] `backend/tests/test_auth_email_verification.py` + supporting `conftest.py`/`test_auth_login.py`/`test_documents_upload.py` edits
- [x] `frontend/src/pages/VerifyEmailPage.jsx` + `App.jsx` routing
- [x] `frontend/src/pages/RegisterPage.jsx` + `LoginPage.jsx` -- check-your-inbox and 403/resend states
- [x] `frontend/src/api/authClient.js` -- `verifyEmail`, `resendVerification`
- [x] Frontend test coverage for the three changed/new pages

**Acceptance Criteria:** see Story 1.6's Given/When/Then block in `epics.md` (Epic 1) — reproduced here for this file's own completeness:
- Given valid registration details, when the account is created, then a verification email is sent and registration still succeeds even if sending fails.
- Given an unverified account, when login is attempted with correct credentials, then it is rejected with 403 and a distinct message.
- Given a valid unexpired verification link, when opened, then the account is marked verified and can log in.
- Given an already-consumed link is re-opened, then it still succeeds harmlessly; an actually invalid/expired token shows a clear failure with a way to request a new link.
- Given a resend request for any email, then the response is identical regardless of whether the account exists or is already verified, and the endpoint is rate-limited per (IP, email).
- Given a pre-existing account, when the migration runs, then it is grandfathered as verified from its `created_at`.
- Given no SMTP is configured, when a verification email would be sent, then the link is logged to the console instead, with no request failure.

## Design Notes

The `typ` claim is the whole mechanism keeping the two token kinds from being interchangeable, since both are signed with the same `JWT_SECRET` and neither is stored server-side (no revocation list, no single-use tracking beyond `email_verified_at` itself being idempotent). Access tokens are minted with *no* `typ` claim at all rather than `"typ": "access"` — this is deliberate, not an oversight: every access token issued before this story shipped, and every hand-crafted token in the pre-existing test suite (`tests/test_auth_login.py`'s expired/wrong-secret token constructions), has no `typ` claim, and inventing one retroactively would either break those tokens or require a migration-of-tokens that doesn't otherwise exist for a stateless JWT scheme.

`REQUIRE_EMAIL_VERIFICATION` exists mainly to keep the pre-existing test suite honest without forcing every one of the ~80 `POST /auth/login` call sites across 15 test files to register-then-verify before they can log in — those tests aren't testing verification, and rewriting them to route through it would be pure churn unrelated to what they actually check. `tests/conftest.py` defaults it off suite-wide; `test_auth_email_verification.py` turns it on per-test via `monkeypatch.setenv` exactly where it's exercising the gate itself.

The migration backfill is not optional polish — without it, the very next login by either of the two permanent QA accounts (`essinkabg@gmail.com`, `essinkabg+qa2@gmail.com`, used by `scripts/isolation_proof.py` and `scripts/eval_harness.py`) would fail once `REQUIRE_EMAIL_VERIFICATION` defaults on, silently breaking both scripts on their next run with no code change of their own.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the new `test_auth_email_verification.py` file and the updated rate-limiter/isolation-proof tests
- `npm run lint && npm run test` (from `frontend/`) -- expected: clean
- `alembic upgrade head` / `alembic downgrade -1` / `alembic upgrade head` (from `backend/`) -- round-trips cleanly; confirms every pre-existing row is backfilled non-null after upgrade

**Manual checks:**
- With no `SMTP_HOST` set, register a new account, confirm the "check your inbox" panel, copy the `/verify-email?token=...` link out of the uvicorn console log, confirm login before clicking it returns the 403 verify-email message with a working resend, then open the link and confirm login succeeds afterward.
- Repeat with real SMTP credentials configured and confirm the email actually arrives.
- Confirm a pre-existing (pre-migration) account still logs in normally.
