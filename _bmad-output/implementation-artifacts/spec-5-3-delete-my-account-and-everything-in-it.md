---
title: 'Story 5.3: Delete my account and everything in it'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '395e46e3af9019dcf3fcf276d98705e3bb970963'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Delete Account danger-zone card ships inert (Story 5.1) — its button is `aria-disabled` and no-ops — and no backend path exists to remove a user's Postgres rows, Weaviate objects, or Neo4j entities. A user who wants to leave has no way to have their data genuinely removed.

**Approach:** Add `DELETE /auth/me`, backed by new user-scoped delete functions in `weaviate_client.py`/`neo4j_client.py` and a Postgres cascade (all owned `documents` rows, then the `users` row) run through the shared DAL, ordered so both external stores are cleared before the single Postgres commit — mirroring `documents/service.py::delete_document`'s existing fixed delete order. Wire the existing `DeleteAccountCard.jsx` shell with a real two-step inline confirm (mirroring `DocumentCard.jsx`'s precedent), and call `logout()` on success.

## Boundaries & Constraints

**Always:**
- Delete order mirrors `delete_document`: Weaviate (`delete_passages_for_user`) → Neo4j (`delete_entities_for_user`) → Postgres (all `documents` rows, then the `users` row) → one `db.commit()`. Never commit Postgres before both external-store deletes succeed.
- New `user_id`-only functions live in `weaviate_client.py` and `neo4j_client.py` (AD-2) — no raw Weaviate filter or Cypher added under `auth/`.
- If any owned document is outside `_DELETABLE_STATUSES` (`{"Ready", "Failed"}`, `documents/service.py:557`), raise `HTTPException(409)` and delete nothing — same guard `delete_document` already applies, for the same reason: a mid-ingestion background task could otherwise write into a store whose rows for this user are being (or have just been) wiped.
- Both new store-delete functions must be idempotent (match-zero-rows on a re-run), matching `delete_passages_for_document`/`prune_document_from_graph`'s existing contract, so a retry after partial failure is safe.
- `DeleteAccountCard.jsx` gets `DocumentCard.jsx`'s confirm state machine: `isConfirming`/`isDeleting`/`error` local state, inline `role="alert"` box (no modal), focus moves to Cancel on open, Escape and Cancel both close it, a failed request re-enables the box for retry.
- On a successful `DELETE /auth/me` (204), the frontend calls `AuthContext`'s `logout()` and navigates to `/login`.
- No re-authentication (password re-entry) step — the AC's specify only an explicit UI confirmation, not credential re-verification.

**Ask First:** none anticipated. If a genuine ambiguity surfaces beyond what's specified here, halt and ask rather than guessing.

**Never:**
- No password re-confirmation, no email confirmation link, no soft-delete or undo window (v1 scope).
- No `ON DELETE CASCADE` added to the `documents.user_id` FK — deletion stays explicit, application-level.
- Do not reuse `wipe_all_entities_and_relationships` (global, script-only, `neo4j_client.py:384`) for this.
- Do not loop per-document calling `documents/service.py::delete_document` — that would re-run one Weaviate/Neo4j call per document; the new user-scoped functions clear each store in one call.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Confirm delete, no documents | Authenticated user, zero owned documents | 204; `users` row gone; frontend logs out, redirects to `/login` | N/A |
| Confirm delete, N Ready/Failed documents | All owned documents in `_DELETABLE_STATUSES` | Weaviate passages + Neo4j entities for all deleted; all `documents` rows + `users` row deleted in one commit | N/A |
| Document mid-ingestion | One owned document is `Uploaded`/`Extracting`/`Graphing` | 409, nothing deleted; confirm box shows the error and stays open | `HTTPException(409, detail=...)` |
| Unauthenticated | No/invalid bearer token | 401 | AD-3 shape |
| External-store delete fails | `delete_passages_for_user` or `delete_entities_for_user` raises | 500 surfaced; no Postgres commit; all rows intact and retry-safe | Exception bubbles; regression-tested |
| Rapid double-click confirm | Second click while `isDeleting` | Second click inert (`aria-disabled`-style guard); exactly one request fires | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/shared/data_access/weaviate_client.py` -- add `delete_passages_for_user(user_id)`, mirrors `delete_passages_for_document` (line 190) but filters on `user_id` alone
- `backend/app/shared/data_access/neo4j_client.py` -- add `delete_entities_for_user(user_id)`: `MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e`, sibling to `wipe_all_entities_and_relationships` (line 384) but user-scoped and request-path-safe
- `backend/app/documents/repository.py` -- add `delete_all_documents_for_user(db, user_id) -> int`, bulk `delete()` statement scoped to `user_id`, no commit; sits beside `delete_document_for_user` (line 99)
- `backend/app/auth/repository.py` -- add `delete_user(db, user_id) -> None`, `db.delete` on the `User` row, no commit; sits beside `update_user_password` (line 47)
- `backend/app/auth/service.py` -- add `delete_account(db, current_user)`: imports `_DELETABLE_STATUSES` from `app.documents.service` (safe direction — `documents/` never imports `auth/`) to guard, then runs the ordered cascade and `db.commit()`
- `backend/app/auth/routes.py` -- add `DELETE /auth/me`, `status_code=204`, `Depends(get_current_user)`, sits beside `change_password` (line 90)
- `backend/tests/test_auth_delete_account.py` -- new: covers I/O matrix above
- `frontend/src/api/settingsClient.js` -- add `deleteAccount(authFetch)`, alongside `updateTheme`
- `frontend/src/components/settings/DeleteAccountCard.jsx` -- rewrite: real confirm state machine (mirrors `DocumentCard.jsx`), calls `deleteAccount` then `logout()` (`AuthContext`) + `navigate('/login')`
- `frontend/src/components/settings/DeleteAccountCard.test.jsx` -- new, styled on `AppearanceCard.test.jsx`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/data_access/weaviate_client.py` -- `delete_passages_for_user` -- enables per-user Weaviate wipe
- [x] `backend/app/shared/data_access/neo4j_client.py` -- `delete_entities_for_user` -- enables per-user graph wipe
- [x] `backend/app/documents/repository.py` -- `delete_all_documents_for_user` -- bulk Postgres cleanup of owned documents
- [x] `backend/app/auth/repository.py` -- `delete_user` -- Postgres user-row delete
- [x] `backend/app/auth/service.py` -- `delete_account` -- orchestrates ordered cascade + mid-ingestion guard
- [x] `backend/app/auth/routes.py` -- `DELETE /auth/me` -- wires route, 204
- [x] `backend/tests/test_auth_delete_account.py` -- covers I/O matrix (happy path 0/N docs, 409, 401, partial-failure retry-safety)
- [x] `frontend/src/api/settingsClient.js` -- `deleteAccount` -- API call
- [x] `frontend/src/components/settings/DeleteAccountCard.jsx` -- real confirm UI + wiring
- [x] `frontend/src/components/settings/DeleteAccountCard.test.jsx` -- confirm state machine + success/error paths

**Acceptance Criteria:**
- Given the Delete Account danger zone, when I click to delete, then nothing is deleted yet and an explicit confirm step appears, matching the document-delete precedent (FR-16, UX-DR14)
- Given the cascade, when it runs, then it goes through the same shared data-access layer as every other path, not a special-cased raw-query path (AD-9, AD-2)
- Given the confirmation step, when a keyboard or screen-reader user reaches it, then Cancel and Confirm are both reachable and clearly labelled, neither depending on hover or a pointer-only affordance (UX-DR14, UX-DR26)
- Given the deletion completes, when it finishes, then I am logged out immediately

## Spec Change Log

## Design Notes

- The mid-ingestion guard imports `_DELETABLE_STATUSES` from `documents/service.py` rather than redefining it, keeping the deletable-status set single-sourced. `documents/` has no import of `auth/` today, so `auth/service.py -> documents/service.py` introduces no cycle.
- `delete_all_documents_for_user` is a single bulk-delete statement, not a loop over `delete_document_for_user` per row — same reasoning as the "Never" rule against looping `delete_document`: one statement does the same Postgres work as N.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- 274 passed.
- `npm test -- --run` (from `frontend/`) -- 241 passed. `npm run lint` -- clean, apart from the four pre-existing `only-export-components` fast-refresh warnings noted in Story 5.2's spec.

**Manual checks -- against the real dev servers and real Postgres (Neon), QA account `story-5-3-qa@example.com`:**
- Clicked "Delete Account": inline confirm box appeared, focus moved to Cancel, nothing deleted yet.
- Clicked Cancel: box collapsed, focus returned to the "Delete Account" button -- caught and fixed a real bug here that the unit tests (jsdom) missed: `.focus()` was being called synchronously in the same handler that hid the button via a `display:none`-toggling class, so a real browser (unlike jsdom) refused the focus and it fell through to `<body>`. Fixed with a deferred `useEffect` keyed on `isConfirming` instead of a same-tick `.focus()` call; re-verified in-browser afterwards (focus lands back on the button).
- Re-opened, clicked "Delete My Account": `DELETE /auth/me` returned 204 (observed via network log), immediately redirected to `/login`.
- Attempted to log back in with the same credentials: `POST /auth/login` returned 401 "Invalid email or password", confirming the Postgres `users` row is genuinely gone and the session ended.
- Did not re-verify Weaviate/Neo4j cleanup manually against real instances (the QA account had no uploaded documents in this pass) -- that path is covered by `test_delete_account_with_deletable_documents_removes_everything_in_one_commit` (backend, mocked store calls asserted) and the dedicated `delete_passages_for_user`/`delete_entities_for_user` unit tests in `test_weaviate_client.py`/`test_neo4j_client.py`, not by a real-instance manual check.

### Review loop (blind-hunter, edge-case-hunter, verification-gap)

Three review layers ran against the diff. All surviving findings triaged to `patch` (auto-fixed here, no spec renegotiation needed); the rest were rejected as already-decided frozen-spec boundaries (no re-auth, no undo window, no typed confirmation), exact mirrors of already-shipped precedent in `DocumentCard.jsx`/`delete_document` (the ARIA structure, the logged-not-raised partial-Weaviate-failure handling, the TOCTOU on the status guard, the no-Postgres-commit-failure-handling gap), or not grounded in this codebase (no ORM child-table cascades exist to bypass; no blob/file storage layer exists to orphan).

Fixed:
- **`auth/repository.py::delete_user` crashed on a concurrent double-delete.** Two `DELETE /auth/me` calls for the same account (two tabs, a retry) could race: the loser's `db.get(User, user_id)` returns `None` after the winner already committed, and `db.delete(None)` raised. Now a clean no-op. Regression-tested directly (`test_repository_delete_user_is_a_no_op_when_the_row_is_already_gone`) and at the route level (`test_delete_account_second_concurrent_call_is_a_clean_401_not_a_500`).
- **`_DELETABLE_STATUSES` was a leading-underscore "private" constant reused across a module boundary** (`documents/service.py` -> `auth/service.py`). Promoted to `DELETABLE_STATUSES` (public), updated at both call sites.
- **`deleteAccount`'s real fetch/error-handling body was never executed by any test** -- both `settingsClient.test.js` (no `deleteAccount` coverage existed) and `DeleteAccountCard.test.jsx` (mocks the whole module) skipped over the actual implementation. Added a `describe('deleteAccount', ...)` block to `settingsClient.test.js` mirroring `updateTheme`/`changePassword`'s own tests plus a 204-no-`json()`-call test mirroring `documentsClient.test.js`'s `deleteDocument` precedent.
- **The user-directed `bg-white` on the trigger button was a dark-mode regression** (a solid white rectangle against the dark card, unlike every other themed element on the page). Confirmed with the human this wasn't the intended visual and switched to `bg-card-bg` (theme-aware, matches the card). Verified both themes in-browser after a clean reload -- light `#FFFFFF`, dark `#262B35`, both correct.

Re-ran verification after fixes: `pytest` -- 276 passed (was 274). `npm test -- --run` -- 245 passed (was 241). `npm run lint` -- clean.

## Suggested Review Order

**Cascade orchestration (entry point)**

- The fixed delete order and the mid-ingestion guard -- everything else in this story exists to serve this function.
  [`service.py:162`](../../backend/app/auth/service.py#L162)

- The route that triggers the cascade -- thin by design, all logic lives in the service function above.
  [`routes.py:108`](../../backend/app/auth/routes.py#L108)

**New store-scoped delete primitives**

- Weaviate: user-scoped sibling to the existing per-document delete, same idempotent logged-not-raised contract.
  [`weaviate_client.py:228`](../../backend/app/shared/data_access/weaviate_client.py#L228)

- Neo4j: unlike the global `wipe_all_entities_and_relationships`, this one is safe for request-serving code.
  [`neo4j_client.py:384`](../../backend/app/shared/data_access/neo4j_client.py#L384)

- Postgres: a single bulk `DELETE`, not a loop, for the same reason the store-scoped functions above exist.
  [`documents/repository.py:128`](../../backend/app/documents/repository.py#L128)

- The status set shared across the module boundary with `delete_document` -- promoted public during review.
  [`documents/service.py:560`](../../backend/app/documents/service.py#L560)

**Concurrency hardening (from review)**

- Guards a real double-delete race: the loser of two concurrent `DELETE /auth/me` calls now no-ops instead of crashing.
  [`auth/repository.py:53`](../../backend/app/auth/repository.py#L53)

**Frontend confirm + wiring**

- The confirm state machine, mirroring `DocumentCard.jsx`'s precedent; the deferred-focus effect here fixes a real browser bug jsdom couldn't catch.
  [`DeleteAccountCard.jsx:15`](../../frontend/src/components/settings/DeleteAccountCard.jsx#L15)

- Cascade trigger and outcome handling -- success logs out and navigates, failure re-opens the box for retry.
  [`DeleteAccountCard.jsx:73`](../../frontend/src/components/settings/DeleteAccountCard.jsx#L73)

- The API client call, previously untested end-to-end -- review caught that every test mocked past this function's real body.
  [`settingsClient.js:60`](../../frontend/src/api/settingsClient.js#L60)

**Tests (peripheral)**

- The route-level I/O matrix: happy paths, the 409 guard, retry-safety after a partial failure, and the concurrency regression.
  [`test_auth_delete_account.py:1`](../../backend/tests/test_auth_delete_account.py#L1)

- The confirm-box interaction coverage, including the double-click and focus-return regressions.
  [`DeleteAccountCard.test.jsx:1`](../../frontend/src/components/settings/DeleteAccountCard.test.jsx#L1)
