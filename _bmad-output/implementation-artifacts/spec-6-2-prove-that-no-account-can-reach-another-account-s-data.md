---
title: 'Prove that no account can reach another account''s data'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
baseline_commit: '5d0de537e120e8a113388e441dd32e859556dd80'
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** No proof exists today that a live account can never reach another live account's data across every endpoint. The one existing cross-tenant chat test (`test_ask_cross_tenant_citation_is_dropped_not_leaked`) mocks `search_passages`, so it never exercises real Weaviate/Neo4j. More fundamentally, testing at the service layer (passing `current_user` in as an argument) proves only that the service+repo honor the value handed to them — it cannot catch a route missing `Depends(get_current_user)`, a route reading `user_id` from a query/body param instead of the JWT, a forged/tampered token that still passes, or a new endpoint added without scoping.

**Approach:** A standalone script (`backend/scripts/isolation_proof.py`) driving the real FastAPI app in-process via `TestClient(app)` (no dependency overrides — real Postgres/Weaviate/Neo4j/OpenRouter, same live-services target as `eval_harness.py`'s `get_session_factory`), authenticated with real JWTs from `/auth/login` for two real accounts. This is a deliberate deviation from Epic 6's general "service layer, not HTTP" convention: 6.2's purpose is proving the auth boundary itself, which calling service functions directly cannot do.

## Boundaries & Constraints

**Always:**
- Drive every protected endpoint through `TestClient(app)` with real `Authorization: Bearer <jwt>` headers obtained from real `/auth/register` + `/auth/login` calls — never call service functions with a manually constructed `current_user`.
- No `dependency_overrides` on `get_db_session` and no stubbed ingestion — real Postgres (Neon)/Weaviate/Neo4j/OpenRouter throughout; missing env vars fail loudly.
- Route-enumeration check: walk `app.routes`, and for every `APIRoute` other than `/auth/register`, `/auth/login`, `/health`, `/docs`, `/openapi.json`, assert `get_current_user` appears in its dependency tree (`route.dependant.dependencies`, recursively). Catches any future endpoint added without auth scoping.
- Account A = existing QA account (`essinkabg@gmail.com`). Account B = a second, permanent, git-documented QA account (fixed email `essinkabg+qa2@gmail.com`, password from `ISOLATION_QA2_PASSWORD` env var). Registration is idempotent: `POST /auth/register`, on `409` fall back to `/auth/login` — never fails because the account exists, never recreated per run.
- Cover every protected endpoint for blocked cross-tenant access: `auth/me` (get/patch/theme/password), `documents` (list/get/delete), `chat/ask`, `kg/graph`.
- Give each account a fixture document containing an unmistakable, invented per-account token, PLUS one entity with the *same name* across both fixtures (e.g. an invented vendor name) — this stresses Neo4j scoping specifically, since name-based dedup is the one thing that could blend same-named entities if `user_id` filtering ever slipped.
- Run the blending check bidirectionally (A must not see B's token, B must not see A's token) across both `/chat/ask` (passages + answer/citation text) and `/kg/graph` (node/relationship names and ids).
- Forged-token perimeter check: against *every* protected route found by the route enumeration (not just one endpoint — `DELETE /auth/me` takes no target id, so "A deletes B" isn't expressible there; this is a `get_current_user`-wide check, not a cross-tenant one), send two invalid tokens and assert 401 on all of them, each hitting a genuinely different branch of `get_current_user`/`decode_access_token`: (a) invalid-signature token, built by `jwt.encode` with a deliberately wrong secret — must fail inside `decode_access_token`'s `except jwt.PyJWTError` branch; (b) a validly-signed token for a nonexistent user — build it with the real `create_access_token(uuid.uuid4())` (same secret/algorithm the app reads from `JWT_SECRET`/`JWT_ALGORITHM`, never hardcoded), so signature verification *passes* and the 401 must come from `repository.get_user_by_id` returning `None`. If both tokens were built the same way this would test one branch twice while appearing to cover two.
- `DELETE /auth/me` is reported as "N/A by construction" for cross-tenant isolation, not "covered" or "not covered" — the endpoint takes no target parameter, so a caller can only ever delete the account named by their own valid token; there is no cross-tenant surface to prove.
- Fixture re-run idempotency: `upload_document` is already idempotent by `(user_id, content_hash)` — a byte-identical re-upload returns the existing row with outcome `"duplicate"` or `"reingested"`, never a raw `IntegrityError`. The script must treat all three outcomes (`created`/`duplicate`/`reingested`) as success and poll for `Ready` status only when the returned document isn't already `Ready`; it must never delete-and-reupload or otherwise fight this existing contract. If a fixture is stuck (not `Ready`/not `Failed`) past a timeout, abort with a clear error rather than silently re-driving it (same rule as `eval_harness.py`).
- Any leak is a hard failure: print a per-endpoint/check pass/fail report, exit non-zero if any check fails, exit 0 only on zero leaks.

**Ask First:**
- If a real leak is found, do not attempt an inline fix — report it and ask how to proceed.

**Never:**
- Mock Weaviate, Neo4j, Postgres, or the LLM for the isolation assertions themselves, and never use the pytest `client`/`db_session` fixtures (`backend/tests/conftest.py`) — those are SQLite-backed with ingestion stubbed, the opposite of what this proof needs.
- Modify the existing mocked unit test (`test_ask_cross_tenant_citation_is_dropped_not_leaked`) — this script is a complementary live proof, not a replacement.
- Touch `yoanasb08@gmail.com` — unrelated real account, out of scope.
- Perform account B's happy-path self-delete — B is a permanent fixture, not disposable per-run.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| GET document cross-tenant | A's JWT, B's document id | 404, no leaked filename in body | Fail loudly if any field of B's document is returned |
| DELETE document cross-tenant | A's JWT, B's document id | 404, B's row untouched | Fail if B's row is deleted or any leak occurs |
| Route enumeration | Every registered `APIRoute` | Every route except the documented public allowlist has `get_current_user` in its dependency tree | Fail listing the unscoped route path if any is found |
| Chat/graph blending, both directions | A and B each hold a fixture with a unique token + a shared-name entity | Neither account's passages, answer text, citations, nor `/kg/graph` nodes/relationships contain the other account's unique token | Fail if either account's token appears in the other's results |
| Forged-token perimeter sweep | Wrong-secret token (fails `decode_access_token`'s signature check) and a real `create_access_token(uuid.uuid4())` token (passes signature, fails `get_user_by_id`), sent to every enumerated protected route | 401 on every route for both token types, via two distinct code branches | Fail listing the route if any accepts either forged token |
| Fixture re-upload on script re-run | Same fixture bytes uploaded a second time | `upload_document` returns `duplicate`/`reingested`, existing row reused, no `IntegrityError` | Script treats this as success, not failure; polls to `Ready` only if not already there |
| `DELETE /auth/me` | Real token, no target param exists | Reported "N/A by construction" — no cross-tenant surface, not exercised destructively | N/A |

</frozen-after-approval>

## Code Map

- `backend/tests/test_tenancy.py:13-22` -- `_register_and_login(client, ...)` pattern: real `/auth/register` + `/auth/login`, returns `access_token` — model for account A/B setup, but this script targets the real app (no `get_db_session` override)
- `backend/tests/conftest.py:59-75` -- pytest `client` fixture: SQLite + `get_db_session` override + stubbed ingestion — explicitly NOT reusable here; this script must build its own `TestClient(app)` with zero overrides
- `backend/app/main.py:165-168,175-176` -- router registration (`auth`, `documents`, `chat`, `kg`) and the one unauthenticated `/health` route — basis for the route-enumeration allowlist
- `backend/app/auth/dependencies.py:27` -- `get_current_user`: the dependency every protected route must carry
- `backend/app/documents/repository.py:40,49,99` -- `list_documents_for_user`, `get_document_for_user` (404 semantics), `delete_document_for_user`
- `backend/app/chat/service.py:25,66-68` -- `ask_question`; calls `search_passages(query_vector, str(current_user.id), ...)`
- `backend/app/shared/data_access/weaviate_client.py:310,343-352` -- `search_passages`: `Filter.by_property("user_id").equal(user_id)` server-side on `near_vector`
- `backend/app/shared/data_access/neo4j_client.py:430,471-554` -- `get_graph_for_user`: every Cypher `MATCH` filters `{user_id: $user_id}` — the layer the shared-entity-name fixture stresses
- `backend/app/auth/service.py:64` -- `register_user`; `.routes.py:31,50,108` -- register/login/delete-me routes (`:108` takes no target param — basis for the "N/A by construction" report line)
- `backend/app/auth/service.py:40,93-97,110-118,121-131` -- `JWT_ALGORITHM`, `_jwt_secret()` (reads `JWT_SECRET`), `create_access_token` (reuse directly for the nonexistent-`sub` token), `decode_access_token` (the two branches the two forged tokens must each hit: `except jwt.PyJWTError` vs. a valid `sub` that `get_user_by_id` can't resolve)
- `backend/app/auth/dependencies.py:27-39` -- `get_current_user`: signature check happens before the `get_user_by_id` DB lookup — confirms the two forged-token variants are genuinely different code paths, not the same rejection twice
- `backend/app/documents/service.py:150-229` -- `upload_document`'s three-state `created`/`duplicate`/`reingested` contract, keyed on `(user_id, content_hash)` — already idempotent across re-runs, do not fight it
- `backend/app/shared/data_access/session.py:47` -- `get_session_factory()` (used only if the script needs a raw DB check, e.g. confirming account state after a forged-token attempt)
- `backend/scripts/eval_harness.py:76,86-94,145` -- env-var override pattern, `REQUIRED_ENV_VARS`, `_validate_env` — mirror for this script's live-service preflight

## Tasks & Acceptance

**Execution:**
- [ ] `backend/scripts/isolation_fixtures/*.md` -- one fixture doc per account: a unique invented token each, plus one entity with an identical name across both -- makes token blending and Neo4j name-dedup leakage both detectable by exact match
- [ ] `backend/scripts/isolation_proof.py` -- build `TestClient(app)` with zero overrides; resolve/register accounts A and B idempotently; ingest fixtures via real upload, treating `duplicate`/`reingested` outcomes as success on re-runs; enumerate `app.routes` for auth-dependency coverage; drive every protected endpoint for cross-tenant blocked-access; run the bidirectional chat+graph blending check; sweep every enumerated route with both forged-token variants (wrong-secret; real `create_access_token` for a nonexistent user); report `DELETE /auth/me` as N/A by construction; print per-check pass/fail report; exit non-zero on any leak -- single-command full-coverage proof (epic-6 DoD gate)
- [ ] `backend/tests/test_isolation_proof.py` -- light unit coverage of the report/pass-fail classification against fake responses (secondary to the live script itself; keep small) -- no live services

**Acceptance Criteria:**
- Given both QA accounts, when run via `python -m scripts.isolation_proof`, then every protected endpoint is exercised through the real API layer (real JWTs, no service-layer shortcuts) for cross-tenant blocked-access and reported pass/fail
- Given the route enumeration, when compared against the app's registered routes, then any route lacking `get_current_user` outside the documented public allowlist is flagged as a failure
- Given each account's fixture (unique token + shared-name entity), when the bidirectional blending check runs, then neither account's chat answers, passages, nor `/kg/graph` output contain the other account's token
- Given the forged-token sweep, when the wrong-secret token and the real-`create_access_token`-with-nonexistent-user token are each sent to every enumerated protected route, then all return 401, via two genuinely distinct code branches
- Given the fixture upload is re-run against an already-`Ready` document, then the script proceeds without error, treating `duplicate`/`reingested` as success
- Given `DELETE /auth/me` takes no target parameter, then the report states it as N/A by construction rather than covered or not covered
- Given any leak is detected, then the script exits non-zero and the report names the failing endpoint/check
- Given a clean run, then the report states plainly that zero leaks were found across all covered endpoints

## Spec Change Log

## Design Notes

`TestClient` runs `BackgroundTasks` synchronously to completion before returning (see `conftest.py:133-151`'s comment on the same behavior) — so fixture uploads via `TestClient(app)` complete real ingestion (parsing/embedding/Weaviate/Neo4j writes) before the next call, no polling loop needed unlike `eval_harness.py`'s direct-service-call path. Login/register are rate-limited (5/min) on the real app; the script's idempotent register-or-login pattern must not spam `/auth/register` on every run.

## Verification

**Commands:**
- `cd backend && python -m scripts.isolation_proof` -- expected: per-endpoint/check report, final "0 leaks found" line, exit 0; exit 1 if any leak
- `cd backend && pytest tests/test_isolation_proof.py -q` -- expected: all pass

**Manual checks:**
- `backend/.env` has DB/Weaviate/Neo4j/OpenRouter credentials populated
- `ISOLATION_QA2_PASSWORD` set; second QA account (`essinkabg+qa2@gmail.com`) registered or auto-registered on first run

## Suggested Review Order

**Entry point & why API-layer testing, not service-layer**

- Start here: the full run in one place -- auth, fixture ingest, every check, the report.
  [`isolation_proof.py:827`](../../backend/scripts/isolation_proof.py#L827)

- The module docstring: why this script drives real JWTs through `TestClient(app)` instead of calling service functions directly, unlike `eval_harness.py`.
  [`isolation_proof.py:1`](../../backend/scripts/isolation_proof.py#L1)

**Route enumeration (the auth-boundary check no cross-tenant test alone can catch)**

- Recursively expands FastAPI's private `_IncludedRouter` wrapper -- the one fragile dependency the whole check rests on.
  [`isolation_proof.py:206`](../../backend/scripts/isolation_proof.py#L206)

- The route-count floor added in review: aborts loudly instead of silently checking a near-empty route set if that ducktyping ever breaks.
  [`isolation_proof.py:153`](../../backend/scripts/isolation_proof.py#L153)

- `_find_unscoped_routes`: the actual "every protected route has `get_current_user`" assertion.
  [`isolation_proof.py:249`](../../backend/scripts/isolation_proof.py#L249)

**Forged-token perimeter sweep (two genuinely distinct rejection branches)**

- The two token builders -- wrong-signature vs. validly-signed-but-nonexistent-user -- and why they must differ.
  [`isolation_proof.py:270`](../../backend/scripts/isolation_proof.py#L270)

- The sweep itself, including the review-round fix distinguishing a legitimate 429 from an accepted forged token.
  [`isolation_proof.py:326`](../../backend/scripts/isolation_proof.py#L326)

**Cross-tenant checks: auth/me family (mutate-and-revert, review-round fixes live here)**

- The theme false-positive fix: captures A's theme *before* B's PATCH, the bug all three review layers caught independently.
  [`isolation_proof.py:557`](../../backend/scripts/isolation_proof.py#L557)

- The password check fix: proves account A's real stored password is untouched via a live re-login, not just that A's already-issued JWT still works.
  [`isolation_proof.py:599`](../../backend/scripts/isolation_proof.py#L599)

- `DELETE /auth/me`'s "N/A by construction" reporting -- why this endpoint has no cross-tenant surface at all.
  [`isolation_proof.py:920`](../../backend/scripts/isolation_proof.py#L920)

**Cross-tenant checks: documents and bidirectional blending**

- Blocked GET/DELETE against the other account's fixture document.
  [`isolation_proof.py:697`](../../backend/scripts/isolation_proof.py#L697)

- The chat/graph blending checks -- the shared-entity-name fixture design is what makes the graph check meaningful.
  [`isolation_proof.py:747`](../../backend/scripts/isolation_proof.py#L747)

- The fixtures themselves: same vendor name, different contract terms and contact, per account.
  [`isolation_fixture_account_a.md:1`](../../backend/scripts/isolation_fixtures/isolation_fixture_account_a.md#L1)

**Peripherals**

- Fixture re-upload idempotency: treats `duplicate`/`reingested` as success, never fights `upload_document`'s own contract.
  [`isolation_proof.py:389`](../../backend/scripts/isolation_proof.py#L389)

- New unit coverage added in the review round: fake-client doubles proving the theme/password/rate-limit fixes actually work.
  [`test_isolation_proof.py:1`](../../backend/tests/test_isolation_proof.py#L1)

- Env var docs for the two real QA-account passwords this script (uniquely) needs.
  [`.env.example:85`](../../backend/.env.example#L85)
