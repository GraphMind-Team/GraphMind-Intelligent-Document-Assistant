---
title: 'Measure answer accuracy and refusal correctness in one command'
type: 'feature'
created: '2026-08-17'
status: 'ready-for-dev'
review_loop_iteration: 0
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-6-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** GraphMind has no repeatable, numeric way to prove answer accuracy and refusal correctness — quality is judged by impression, and OD-3's placeholder ≥80% SM-1 target has never been checked against a real baseline.

**Approach:** A standalone script (`backend/scripts/eval_harness.py`) that ingests a small git-tracked fixture corpus into the QA account, runs a 15–20 question set (factual / synthesis / unanswerable) through `ask_question` scoped to those fixtures (no HTTP/UI), and prints accuracy, unanswerable-refusal-rate, and answerable-refusal-rate as numbers.

## Boundaries & Constraints

**Always:**
- Call `ask_question`/`upload_document`/`ingest_document` directly — never HTTP or the frontend.
- Pass fixture UUIDs as `ask_question`'s `document_ids` — never `[]` (scopes to the whole QA library, pulling in prior manual-QA uploads).
- Run against real Weaviate/Neo4j/OpenRouter/Postgres — the DoD gate. Missing env vars fail loudly.
- Reuse the QA account (`essinkabg@gmail.com`, `backend/.env`) — no throwaway accounts.
- Eval set: 15–20 pairs in a git-tracked file, spanning factual / synthesis / unanswerable.
- Report accuracy and refusal rate as plain numbers, never pass/fail. Answerable-question refusal rate reported separately (SM-C1). Header always includes model id, timestamp, question count (non-deterministic LLM).
- A refusal is only `empty_reason == "refusal"`; `no_documents`/`empty_scope`/`no_answer` are distinct, never scored as refusals.

**Ask First:**
- If accuracy lands off the informal 80% expectation, don't rewrite OD-3/SM-1 in `epics.md` — report the number, ask how to record it.

**Never:**
- Mock the LLM, Weaviate, or Neo4j to fabricate a passing run.
- Implement Story 6.2 (cross-tenant proof) — out of scope.
- Score a `generate_answer` 503 as a refusal — log as a run error, excluded from both metrics.
- Silently re-drive `ingest_document` on a fixture stuck mid-pipeline — abort with a clear error (Story 2.3's no-safety-net gap).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Factual/synthesis question | Support in 1 (factual) or 2+ (synthesis) docs, `document_ids`-scoped | `empty_reason is None`; text matches `must_contain` (`all`/`any`) → correct else incorrect | N/A |
| Refusal on an answerable question | Factual/synthesis question, model refuses anyway | `empty_reason == "refusal"` | Incorrect for SM-1 *and* feeds SM-C1's numerator — the case that metric exists to catch |
| Unanswerable question | Not factually supported by any fixture | `refusal` is correct; `no_answer` logged separately, not a violation; `empty_scope` shouldn't happen, abort | Any actual answer (non-empty segments) is an SM-2 violation |
| LLM wrapper failure mid-run | `generate_answer` raises 503 | Logged `error`, run continues | Report shows error count separately |
| Re-running the harness | Fixture `duplicate`/`reingested` | Re-ingest only if not `Ready`/not stuck; poll with timeout | No duplicate rows/passages |

</frozen-after-approval>

## Code Map

- `backend/app/chat/service.py:25` -- `ask_question(...) -> AskResponse` (`schemas.py:66-93`); `empty_reason`: 81 `no_documents`/`empty_scope`, 96 `refusal` (pre-LLM), 180 `no_answer`; 503 on wrapper exhaustion
- `backend/app/shared/data_access/weaviate_client.py:319-324` -- `search_passages`' `near_vector`: `limit=TOP_K_PASSAGES`, no query-time distance cutoff
- `backend/app/shared/data_access/session.py:47-49` -- `get_session_factory()`; mirror `rebuild_graph_with_provenance.py:126-131`; user via `auth/repository.py:16` `get_user_by_email`
- `backend/app/documents/service.py:150,294` -- `upload_document(...) -> (Document, "created"|"duplicate"|"reingested")`; `ingest_document(document_id, *, session_factory=None)`
- `backend/app/shared/models.py:53-56` -- status: `Uploaded/Extracting/Graphing/Ready/Failed`
- `backend/app/shared/llm_client/__init__.py:143` -- `RELEVANCE_THRESHOLD = 0.75`, relevant iff `distance <= threshold`

## Tasks & Acceptance

**Execution:**
- [ ] `backend/scripts/eval_fixtures/*.md` -- 2-3 short fixture docs, checkable facts + synthesis material -- reproducible corpus, independent of prior manual QA state
- [ ] `backend/scripts/eval_questions.json` -- 15-20 `{id, category, question, expected_answer, must_contain, match, document_filenames}` entries -- the eval set (FR-13, NFR-6)
- [ ] `backend/scripts/eval_harness.py` -- resolve QA user; per fixture: upload, ingest if needed, poll with timeout, abort on `Failed`/stuck; run questions via `ask_question` scoped to fixture ids; classify per I/O matrix; print header + metrics -- single-command entry point (FR-13)
- [ ] `backend/tests/test_eval_harness.py` -- unit-test scoring/classification against fake `AskResponse`, one case per I/O-matrix row (5 rows) -- no live services

**Acceptance Criteria:**
- Given the evaluation set, when inspected, then it holds 15–20 pairs spanning factual, synthesis, and unanswerable
- Given the harness, when run via `python -m scripts.eval_harness`, then one command executes the set through `ask_question` directly, no HTTP/UI
- Given a completed run, then accuracy and refusal rate print as numbers, not pass/fail, with model/timestamp/count
- Given a completed run, then refusal rate on answerable questions prints separately (SM-C1)
- Given the first baseline run, then the report states measured SM-1 accuracy plainly, for a human to resolve OD-3

## Spec Change Log

## Design Notes

Scoring is deterministic: `must_contain` matches case-insensitively against segment text (`all`/`any` per question). Keep entries narrow to avoid false positives.

## Verification

**Commands:**
- `cd backend && python -m scripts.eval_harness` -- expected: prints header + the three metrics + error count; exits 0
- `cd backend && pytest tests/test_eval_harness.py -q` -- expected: all pass

**Manual checks:**
- `backend/.env` has DB/Weaviate/Neo4j/OpenRouter credentials populated
