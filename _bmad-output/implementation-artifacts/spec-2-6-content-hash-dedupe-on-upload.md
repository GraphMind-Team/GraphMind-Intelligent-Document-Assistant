---
title: 'Story 2.6: Content-hash dedupe on upload'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'a120f93d1e8607ca6c4509a0c24eab27416dd904'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every upload today always creates a new `Document` row and always runs the full pipeline (parse, embed, LLM extraction), even for a byte-identical re-upload — burning free-tier LLM/embedding budget on work already done. `Document`'s docstring already anticipates this ("content_hash in 2.6") but the column doesn't exist yet.

**Approach:** Add `Document.content_hash` (sha256 of raw bytes), computed on every upload before any row is created. A hash match for the same user returns the *existing* document (200, `is_duplicate: true`) instead of creating a row or scheduling `ingest_document` — no parse, no embed, no LLM call. A DB-level unique `(user_id, content_hash)` constraint closes the same concurrent-duplicate race Story 2.4 closed for entities.

## Boundaries & Constraints

**Always:**
- Hash computed from raw bytes only (`hashlib.sha256(content).hexdigest()`), never filename — dedupe must survive a rename (AC3).
- The hash check happens in `service.upload_document`, before `Document(...)` is constructed and before `routes.py` calls `background_tasks.add_task(service.ingest_document, ...)` — a duplicate must never schedule ingestion, not just abort it partway.
- On a match: no new row, `document.status`/`content`/everything else untouched, response reuses the *existing* document's data via `DocumentResponse`, plus `is_duplicate: true`; status code 200, not 201 (nothing was created).
- On no match: unchanged behavior — new row, `content_hash` set at creation, 201, `is_duplicate: false`, ingestion scheduled as today.
- New Alembic migration: add `content_hash` (`String(64)`, nullable=True initially), backfill every existing row by hashing its already-stored `content` column (never re-derived from anything else — `content` is `nullable=False` today, so every row has bytes to hash), then alter to `nullable=False`. Existing documents become dedupe-eligible too, not just ones uploaded after this ships.
- Composite unique index on `(user_id, content_hash)` — the DB-level guard against two concurrent uploads of the same file both missing the pre-create lookup (mirrors Story 2.4's Neo4j uniqueness constraint for the identical race shape, this epic's `documents` module now allowing several files to upload concurrently since Story 2.1). On the rare `IntegrityError` from that race, `service.upload_document` rolls back, re-queries by hash, and returns the now-existing row as a duplicate — never lets the exception propagate as a 500.
- `DocumentResponse.is_duplicate: bool = False` — a new field, additive, doesn't change any existing response consumer.
- Frontend: `uploadDocument`'s existing 2xx-resolves/non-2xx-rejects contract is untouched (200 already resolves) — `UploadModal.startUpload`'s `.then` branches on the resolved body's `is_duplicate` into a new terminal row status `'duplicate'`, added to `isSettled()` and to the auto-close "at least one resolved-successfully" gate alongside `'success'`.
- Duplicate row shows "Already uploaded" and links to the existing document (`/documents/{id}`) — human decision already recorded (OD-7): surfaces the existing document, doesn't just say "skipped".

**Ask First:** none — OD-7 already resolved the UX shape; this spec's only new decision (response shape: reuse `DocumentResponse` + flag, not a separate schema or 409) follows directly from it and needs no further sign-off.

**Never:**
- No re-parse, no `embed_texts` call, no `extract_entities_and_relationships` call, no Neo4j write on a duplicate — the entire point (NFR-7).
- No fuzzy/near-duplicate matching (e.g. normalized whitespace, re-encoded PDFs with identical visible content) — exact byte-hash match only, consistent with AD-4's exact-match precedent elsewhere in this epic.
- No dedupe across users — hash lookup is always scoped by `user_id` (AD-2), mirroring every other tenancy-scoped query in `repository.py`.
- No change to `MAX_FILE_SIZE_BYTES`/format validation order — those still gate before hashing, unchanged from Story 2.1.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First upload of a file | New content hash for this user | New row created, `content_hash` set, 201, `is_duplicate: false`, ingestion scheduled | N/A |
| Byte-identical re-upload, same filename | Hash matches an existing document | No new row; 200, `is_duplicate: true`, body is the existing document | N/A |
| Byte-identical re-upload, different filename | Hash matches, filename differs | Same as above — matched on hash only, filename ignored | N/A |
| Edited file re-uploaded under the original filename | Content differs, hash differs | Ingested as a genuinely new document (AC4) | N/A |
| Two concurrent uploads of the identical new file (race) | Both requests miss the pre-create hash lookup | DB unique constraint rejects the second `INSERT`; that request rolls back, re-queries by hash, returns the first request's row as a duplicate | `IntegrityError` caught, never a 500 |
| Existing (pre-migration) document re-uploaded | Its `content_hash` was backfilled by the migration | Matches like any other document — dedupe works against pre-2.6 documents too | N/A |

</frozen-after-approval>

## Code Map

- `backend/alembic/versions/` -- new: adds nullable `documents.content_hash` (`String(64)`), backfills by hashing each row's `content`, then alters to `nullable=False`; adds unique index on `(user_id, content_hash)` — chains off `d4e9b1f3a7c2`
- `backend/app/shared/models.py` -- edit: `Document.content_hash: Mapped[str] = mapped_column(String(64), nullable=False)`
- `backend/app/documents/repository.py` -- edit: `get_document_by_content_hash(db, user_id, content_hash) -> Document | None`, mirrors `get_document_for_user`'s tenancy-scoped pattern (line ~36)
- `backend/app/documents/service.py` -- edit: `upload_document` (lines ~140-171) computes the hash, checks for an existing match first, returns `(document, is_duplicate)`; catches `IntegrityError` on the race case
- `backend/app/documents/schemas.py` -- edit: `DocumentResponse.is_duplicate: bool = False`
- `backend/app/documents/routes.py` -- edit: `upload_document` route (line 55) unpacks `(document, is_duplicate)`, sets `response.status_code = 200 if is_duplicate else 201` (needs a `response: Response` param), only schedules `background_tasks.add_task(...)` (line 88) when `not is_duplicate`
- `frontend/src/components/UploadModal.jsx` -- edit: `startUpload` (line 144) branches on `is_duplicate`; new `'duplicate'` row status added to `isSettled()` (line 19) and the auto-close success-gate (line 96); new render branch (~line 269) showing "Already uploaded" + a `Link` to the existing document
- `backend/tests/test_documents_upload.py` -- edit: new tests for hash-match (same/different filename), edited-content non-match, no-ingestion-on-duplicate, cross-user isolation, and the concurrent-upload race
- `backend/tests/test_documents_repository.py` -- new: `get_document_by_content_hash` tenancy scoping (cross-user hash collision never matches)
- `backend/tests/test_content_hash_migration.py` -- new: the migration's backfill loop computes the correct sha256 per existing row (`op` mocked; DDL calls aren't under test, only the hashing/UPDATE logic) -- added during the matrix audit, closing the "pre-migration document re-uploaded" row
- `frontend/src/components/UploadModal.test.jsx` -- edit: duplicate-response row rendering, `isSettled`/auto-close behavior with an all-duplicate batch

## Tasks & Acceptance

**Execution:**
- [x] Alembic migration -- `content_hash` column, backfill, `NOT NULL`, unique `(user_id, content_hash)` index
- [x] `backend/app/shared/models.py` -- `Document.content_hash`
- [x] `backend/app/documents/repository.py` -- `get_document_by_content_hash`
- [x] `backend/app/documents/service.py` -- hash-check-before-create, `(document, is_duplicate)` return, `IntegrityError` race handling -- the story's core AC
- [x] `backend/app/documents/schemas.py` -- `DocumentResponse.is_duplicate`
- [x] `backend/app/documents/routes.py` -- status-code branch, conditional `background_tasks.add_task`
- [x] `frontend/src/components/UploadModal.jsx` -- `'duplicate'` status, `isSettled`/auto-close update, "Already uploaded" + link render branch
- [x] `backend/tests/test_documents_upload.py` -- hash-match/no-match/race-condition coverage
- [x] Repository-level test -- cross-user hash isolation
- [x] `frontend/src/components/UploadModal.test.jsx` -- duplicate row rendering + settle/auto-close behavior
- [x] `backend/tests/test_content_hash_migration.py` -- migration backfill hashing correctness (matrix audit addition)

**Acceptance Criteria:**
- Given a byte-identical re-upload (any filename), when processed, then no second row is created, no parse/embed/LLM call is made, and the response identifies the existing document.
- Given a content-hash match, when the upload modal updates that file's row, then it shows an explicit "already uploaded" message and links to the existing document.
- Given an edited file re-uploaded under its original filename, when checked, then its hash differs and it is ingested as genuinely new.
- Given two concurrent uploads of the identical new file, when the race is resolved, then exactly one document row exists and neither request 500s.
- Given a document uploaded before this story shipped, when re-uploaded byte-identical, then it is still recognized as a duplicate (backfilled hash).
- Given pre-existing `(user_id, content_hash)` collisions in the database when the migration runs, then it fails loudly with a clear, actionable error naming the colliding rows, and never creates the unique index over data that would violate it.

## Spec Change Log

- **Trigger:** Three-layer adversarial review (blind-hunter, edge-case-hunter, verification-gap) after the implementation subagent's first pass, all tests green.
- **Deploy-blocking, found and fixed:** edge-case-hunter flagged that the migration's `op.create_index(..., unique=True)` would fail if any pre-existing `(user_id, content_hash)` collision already existed in the data — checked directly against the real Neon database rather than left theoretical, and confirmed: it already held exactly one such collision (two byte-identical `notes.md` test-upload rows, both `Failed`, from earlier manual verification). Applying the migration as originally written would have failed with a raw, confusing driver-level `IntegrityError`. Fixed: the migration now runs a `GROUP BY user_id, content_hash HAVING COUNT(*) > 1` check after the backfill and before the unique index, raising a clear `RuntimeError` naming the colliding rows if any are found — it deliberately never deletes or merges rows itself, since that's a data decision requiring a human with the specific ids in hand. The one real colliding row was deleted by the human (not by this workflow) after being shown the exact ids/dates/content; the migration was then applied cleanly and verified against Neon (`alembic current` == head, `content_hash` and `ix_documents_user_id_content_hash` both present). New test: `test_upgrade_raises_and_never_creates_the_unique_index_when_collisions_exist`.
- **Defensive fix:** the backfill's `hashlib.sha256(row.content)` would raise `TypeError` on a `None` value. `content` is `nullable=False` at the model level so this shouldn't be reachable, but the fix is one line (`row.content or b""`) and matches this codebase's established "shouldn't happen but the fix is cheap" precedent (Story 2.5).
- **Accessibility fix:** the duplicate-row message had no live-region role, unlike the sibling error case's `role="alert"` — a screen-reader user got no notification when a row settled into "Already uploaded". Fixed with `role="status"` (polite, not urgent — `alert` stays reserved for the error case).
- **Defensive fix:** `<Link to={`/documents/${row.documentId}`}>` would have rendered `/documents/undefined` if a resolved body's `id` were ever missing — unreachable via the real backend (a non-optional field on `DocumentResponse`) but flagged independently by two reviewers; now guarded, falling back to plain "Already uploaded" text with no link.
- **Investigated, not fixed here:** re-uploading a `Failed` document's exact bytes is treated identically to any other duplicate (`is_duplicate: true`, no re-ingestion) — raised independently by blind-hunter and edge-case-hunter. Not a regression (no retry mechanism exists anywhere in this codebase yet), so this doesn't break a working path, but it does close off the one thing a user might intuitively try. Logged in `deferred-work.md` for whenever a retry story is built, rather than decided here — the correct behavior (retry-in-place vs. current behavior vs. something else) is a product decision, not a bug fix.
- **Investigated, not fixed here:** a lone duplicate upload (the common single-file case) auto-closes the modal as soon as the request resolves, before a user has a realistic chance to see or click the "Already uploaded" link — only reachable in a mixed batch. Matches the spec exactly as written; logged in `deferred-work.md` as a UX gap for whenever the modal is next touched, not treated as a defect in this story.
- **KEEP:** every already-approved boundary above — hash-before-create ordering, the `(document, is_duplicate)` return shape, the DB-level unique-index race guard, and the additive `is_duplicate` field — none altered by this entry.

## Design Notes

Migration backfill: iterate existing `documents` rows, `hashlib.sha256(row.content).hexdigest()`, `UPDATE` in place — cheap at this project's scale (no pagination needed), then `ALTER COLUMN content_hash SET NOT NULL` once every row has a value. Column added nullable first specifically so the backfill step itself doesn't violate a NOT NULL constraint mid-migration.

`service.upload_document`'s new return shape `(document, is_duplicate)` is this function's only breaking change — its only caller is the POST route, so no other module needs updating.

FastAPI status-code override: declare `response: Response` as a route parameter and set `response.status_code = 200` in the duplicate branch; the declared `response_model=DocumentResponse` still governs serialization regardless of which status code the handler sets.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including new hash-match/race/backfill tests
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including new UploadModal duplicate-row tests

**Manual checks (if no CLI):**
- Upload a file, then upload the exact same bytes again (rename allowed) — confirm the modal shows "Already uploaded" linking to the first document, and confirm in logs/DB that no second row, no embedding call, and no LLM call occurred.

## Suggested Review Order

**Dedupe core (backend)**

- Hash-before-create ordering, race handling via `IntegrityError` — the mechanism the whole story hangs off.
  [`service.py:142`](../../backend/app/documents/service.py#L142), [`service.py:176`](../../backend/app/documents/service.py#L176), [`service.py:196`](../../backend/app/documents/service.py#L196)

- Tenancy-scoped hash lookup, reused both for the pre-create check and the post-race re-query.
  [`repository.py:51`](../../backend/app/documents/repository.py#L51)

- Status-code branch and the conditional `background_tasks.add_task` — where a duplicate is guaranteed to never schedule ingestion.
  [`routes.py:56`](../../backend/app/documents/routes.py#L56), [`routes.py:88`](../../backend/app/documents/routes.py#L88)

**Data model & migration (deploy-blocking issue found and fixed here — see Spec Change Log)**

- Column + composite unique index, the DB-level guard against the concurrent-upload race.
  [`models.py:97`](../../backend/app/shared/models.py#L97), [`models.py:106`](../../backend/app/shared/models.py#L106)

- Backfill + the pre-existing-collision safety check added during review — confirmed against real production data.
  [`e1f5c8a2b4d7_add_content_hash_to_documents.py`](../../backend/alembic/versions/e1f5c8a2b4d7_add_content_hash_to_documents.py#L1)

**Frontend rendering**

- `'duplicate'` terminal status, settle/auto-close gate, and the "Already uploaded" + link render branch (a11y role + defensive `documentId` guard added during review).
  [`UploadModal.jsx:20`](../../frontend/src/components/UploadModal.jsx#L20), [`UploadModal.jsx:284`](../../frontend/src/components/UploadModal.jsx#L284)

**Tests**

- Hash-match/no-match/race/cross-user coverage on the real HTTP path.
  [`test_documents_upload.py:305`](../../backend/tests/test_documents_upload.py#L305), [`test_documents_upload.py:335`](../../backend/tests/test_documents_upload.py#L335), [`test_documents_upload.py:398`](../../backend/tests/test_documents_upload.py#L398), [`test_documents_upload.py:422`](../../backend/tests/test_documents_upload.py#L422), [`test_documents_upload.py:451`](../../backend/tests/test_documents_upload.py#L451)

- Repository-level tenancy scoping.
  [`test_documents_repository.py:48`](../../backend/tests/test_documents_repository.py#L48)

- Migration backfill correctness and the collision-guard's `RuntimeError` path (matrix audit addition).
  [`test_content_hash_migration.py:77`](../../backend/tests/test_content_hash_migration.py#L77), [`test_content_hash_migration.py:141`](../../backend/tests/test_content_hash_migration.py#L141)

- Frontend duplicate-row rendering.
  [`UploadModal.test.jsx:181`](../../frontend/src/components/UploadModal.test.jsx#L181)
