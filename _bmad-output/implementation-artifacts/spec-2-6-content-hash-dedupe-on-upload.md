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
- `backend/app/documents/repository.py` -- edit: `get_document_by_content_hash(db, user_id, content_hash) -> Document | None`, mirrors `get_document_for_user`'s tenancy-scoped pattern; `claim_failed_document_for_reingest(db, document_id) -> bool`, an atomic conditional `UPDATE ... WHERE status = 'Failed'` (the retry lock for the reingest path)
- `backend/app/documents/service.py` -- edit: `upload_document` computes the hash, checks for an existing match first (branching on `Failed` vs. not), returns `(document, UploadOutcome)` where `UploadOutcome = Literal["created", "duplicate", "reingested"]`; catches `IntegrityError` on the create-race case
- `backend/app/documents/schemas.py` -- edit: `DocumentResponse.is_duplicate: bool = False`
- `backend/app/documents/routes.py` -- edit: `upload_document` route unpacks `(document, outcome)`, branches on all three outcomes (200 for `duplicate`/`reingested`, 201 for `created`; `background_tasks.add_task(...)` scheduled for `created` and `reingested`, never for `duplicate`) (needs a `response: Response` param)
- `frontend/src/components/UploadModal.jsx` -- edit: `startUpload` branches on `is_duplicate`; new `'duplicate'` row status added to `isSettled()` but deliberately *excluded* from the auto-close "good enough to close" gate (kept `'success'`-only after the auto-close bug fix); new render branch showing "Already uploaded" + a `Link` to the existing document, `role="status"`, guarded against a missing `documentId`
- `backend/tests/test_documents_upload.py` -- edit: new tests for hash-match (same/different filename), edited-content non-match, no-ingestion-on-duplicate, cross-user isolation, the concurrent-create race, the reingest-on-Failed-match path, the no-reingest-on-Ready-match path, and the concurrent-reingest race
- `backend/tests/test_documents_repository.py` -- new: `get_document_by_content_hash` tenancy scoping; `claim_failed_document_for_reingest` wins/loses/clears-stale-chapter_breakdown/unknown-id
- `backend/tests/test_content_hash_migration.py` -- new: the migration's backfill loop computes the correct sha256 per existing row, plus the pre-existing-collision `RuntimeError` guard -- added during the matrix audit, closing the "pre-migration document re-uploaded" row
- `frontend/src/components/UploadModal.test.jsx` -- edit: duplicate-response row rendering; auto-close behavior for a lone duplicate, an all-duplicate batch, a mixed duplicate+error batch (all now correctly stay open), a mixed duplicate+success batch (still auto-closes), and Cancel dismissing an all-duplicate batch

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
- [x] `backend/app/documents/repository.py` + `service.py` -- `claim_failed_document_for_reingest`, three-outcome `UploadOutcome`, reingest-in-place on a `Failed` match (post-merge fix)
- [x] `frontend/src/components/UploadModal.jsx` -- exclude `'duplicate'` from the auto-close gate so the message is actually visible (post-merge fix, from a real user bug report)

**Acceptance Criteria:**
- Given a byte-identical re-upload (any filename), when processed, then no second row is created, no parse/embed/LLM call is made, and the response identifies the existing document.
- Given a content-hash match, when the upload modal updates that file's row, then it shows an explicit "already uploaded" message and links to the existing document.
- Given an edited file re-uploaded under its original filename, when checked, then its hash differs and it is ingested as genuinely new.
- Given two concurrent uploads of the identical new file, when the race is resolved, then exactly one document row exists and neither request 500s.
- Given a document uploaded before this story shipped, when re-uploaded byte-identical, then it is still recognized as a duplicate (backfilled hash).
- Given pre-existing `(user_id, content_hash)` collisions in the database when the migration runs, then it fails loudly with a clear, actionable error naming the colliding rows, and never creates the unique index over data that would violate it.
- Given a `Failed` document, when its exact bytes are re-uploaded, then it is reset to `Uploaded` and re-ingested in place — no second row, ingestion scheduled same as a fresh upload.
- Given a single duplicate (or all-duplicate) upload batch, when the request resolves, then the modal stays open with "Already uploaded" visible until the user explicitly dismisses it, rather than auto-closing before it can be read.

## Spec Change Log

- **Trigger:** Three-layer adversarial review (blind-hunter, edge-case-hunter, verification-gap) after the implementation subagent's first pass, all tests green.
- **Deploy-blocking, found and fixed:** edge-case-hunter flagged that the migration's `op.create_index(..., unique=True)` would fail if any pre-existing `(user_id, content_hash)` collision already existed in the data — checked directly against the real Neon database rather than left theoretical, and confirmed: it already held exactly one such collision (two byte-identical `notes.md` test-upload rows, both `Failed`, from earlier manual verification). Applying the migration as originally written would have failed with a raw, confusing driver-level `IntegrityError`. Fixed: the migration now runs a `GROUP BY user_id, content_hash HAVING COUNT(*) > 1` check after the backfill and before the unique index, raising a clear `RuntimeError` naming the colliding rows if any are found — it deliberately never deletes or merges rows itself, since that's a data decision requiring a human with the specific ids in hand. The one real colliding row was deleted by the human (not by this workflow) after being shown the exact ids/dates/content; the migration was then applied cleanly and verified against Neon (`alembic current` == head, `content_hash` and `ix_documents_user_id_content_hash` both present). New test: `test_upgrade_raises_and_never_creates_the_unique_index_when_collisions_exist`.
- **Defensive fix:** the backfill's `hashlib.sha256(row.content)` would raise `TypeError` on a `None` value. `content` is `nullable=False` at the model level so this shouldn't be reachable, but the fix is one line (`row.content or b""`) and matches this codebase's established "shouldn't happen but the fix is cheap" precedent (Story 2.5).
- **Accessibility fix:** the duplicate-row message had no live-region role, unlike the sibling error case's `role="alert"` — a screen-reader user got no notification when a row settled into "Already uploaded". Fixed with `role="status"` (polite, not urgent — `alert` stays reserved for the error case).
- **Defensive fix:** `<Link to={`/documents/${row.documentId}`}>` would have rendered `/documents/undefined` if a resolved body's `id` were ever missing — unreachable via the real backend (a non-optional field on `DocumentResponse`) but flagged independently by two reviewers; now guarded, falling back to plain "Already uploaded" text with no link.
- **Investigated, not fixed here:** re-uploading a `Failed` document's exact bytes is treated identically to any other duplicate (`is_duplicate: true`, no re-ingestion) — raised independently by blind-hunter and edge-case-hunter. Not a regression (no retry mechanism exists anywhere in this codebase yet), so this doesn't break a working path, but it does close off the one thing a user might intuitively try. Logged in `deferred-work.md` for whenever a retry story is built, rather than decided here — the correct behavior (retry-in-place vs. current behavior vs. something else) is a product decision, not a bug fix.
- **Investigated, not fixed here:** a lone duplicate upload (the common single-file case) auto-closes the modal as soon as the request resolves, before a user has a realistic chance to see or click the "Already uploaded" link — only reachable in a mixed batch. Matches the spec exactly as written; logged in `deferred-work.md` as a UX gap for whenever the modal is next touched, not treated as a defect in this story.
- **KEEP:** every already-approved boundary above — hash-before-create ordering, the `(document, is_duplicate)` return shape, the DB-level unique-index race guard, and the additive `is_duplicate` field — none altered by this entry.

- **Trigger:** A second, independent human-requested review (after the story was already committed) corrected a claim in the entry above, then a real user bug report against the running app found a second, related defect.
- **Correction to the record:** the "Investigated, not fixed here" entry above claimed re-uploading a `Failed` document "was never a working retry path this story could have broken." That is false, and the review that produced it didn't check the baseline. At the pre-2.6 commit (`a120f93`), `POST /documents` unconditionally created a new row and called `background_tasks.add_task(service.ingest_document, ...)` for every upload, including a re-upload of a previously-failed file — so a byte-identical re-upload *was* a working, if informal, retry: a fresh row, a fresh pipeline run, a real chance to succeed the second time. Story 2.6 silently removed that path by routing every hash match — including one against a `Failed` document — into the no-op duplicate branch. That is a regression, not a pre-existing gap, and the epic already treats `Failed` as an expected, often-transient state (Story 2.4's 429-retryable fix exists for exactly this reason).
- **Bug fixed (the regression above):** a hash match against a `Failed` document is no longer treated as a plain duplicate. `repository.claim_failed_document_for_reingest` atomically flips it back to `Uploaded` (conditional `UPDATE ... WHERE status = 'Failed'`, so two concurrent re-uploads of the same failed document can't both claim it — the loser correctly falls back to `"duplicate"`), clears `failed_reason` and `chapter_breakdown`, and `service.upload_document` now returns one of three outcomes — `"created"`, `"duplicate"`, `"reingested"` — instead of the `is_duplicate` boolean this spec originally specified. This narrows the frozen Boundaries line "On a match: no new row, `document.status`/`content`/everything else untouched... status code 200" — that line now holds only for a match against a *non*-`Failed` document; a `Failed` match still creates no new row (NFR-7 still holds — retrying a failed attempt is not the duplicated work NFR-7 forbids) but does reset status and schedule ingestion, same as `"created"`. `is_duplicate` in the API response stays `false` for `"reingested"`, since nothing was skipped. New tests: `test_upload_byte_identical_reupload_of_a_failed_document_reingests_in_place`, `test_upload_byte_identical_reupload_of_a_ready_document_does_not_reingest`, `test_claim_failed_document_for_reingest_loses_race_falls_back_to_duplicate`, plus four repository-level tests pinning the atomic claim (wins, clears a stale `chapter_breakdown` defensively, refuses a non-`Failed` row, and a not-found id).
- **Bug fixed (found by the user against the running app, not by any review layer):** a single-file duplicate upload — the common case — auto-closed `UploadModal` the instant the request resolved, so "Already uploaded" and its link were never visible; the earlier review round had flagged this exact defect and mis-triaged it as "matches the spec exactly as written, not a defect" rather than fixing it. Fixed: the auto-close gate's "at least one good-enough-to-close outcome" check no longer counts `'duplicate'` — a duplicate result is now treated like an error for auto-close purposes (informational, requires an explicit Cancel/Escape to dismiss) even though it remains a normal, expected, *settled* outcome, not a failure. A batch containing at least one genuinely new (`'success'`) upload alongside a duplicate still auto-closes, unchanged. New tests cover: a lone duplicate staying open, an all-duplicate batch staying open, a mixed duplicate+error batch staying open, a mixed duplicate+success batch still auto-closing, and Cancel still working to dismiss an all-duplicate batch.
- **Superseded:** the two "Investigated, not fixed here" bullets above and their corresponding `deferred-work.md` entries are resolved by this entry and have been removed from `deferred-work.md` — left in place above only as the append-only historical record of what the first review round concluded.
- **KEEP:** the hash-before-create ordering, the DB-level unique-index race guard, the additive `is_duplicate` field on `DocumentResponse`, and the migration/collision-guard work from the entry above — none altered by this entry.

## Design Notes

Migration backfill: iterate existing `documents` rows, `hashlib.sha256(row.content).hexdigest()`, `UPDATE` in place — cheap at this project's scale (no pagination needed), then `ALTER COLUMN content_hash SET NOT NULL` once every row has a value. Column added nullable first specifically so the backfill step itself doesn't violate a NOT NULL constraint mid-migration.

`service.upload_document`'s new return shape `(document, UploadOutcome)` (`Literal["created", "duplicate", "reingested"]`, narrowed from an earlier `is_duplicate: bool`) is this function's only breaking change — its only caller is the POST route, so no other module needs updating.

FastAPI status-code override: declare `response: Response` as a route parameter and set `response.status_code = 200` in the duplicate/reingested branches; the declared `response_model=DocumentResponse` still governs serialization regardless of which status code the handler sets.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including new hash-match/race/backfill tests
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including new UploadModal duplicate-row tests

**Manual checks (if no CLI):**
- Upload a file, then upload the exact same bytes again (rename allowed) — confirm the modal shows "Already uploaded" linking to the first document, and confirm in logs/DB that no second row, no embedding call, and no LLM call occurred.

## Suggested Review Order

**Dedupe core, including the three-outcome reingest fix (backend)**

- `upload_document`'s hash-before-create ordering, now branching on `Failed` vs. not before deciding the outcome.
  [`service.py:147`](../../backend/app/documents/service.py#L147), [`service.py:198`](../../backend/app/documents/service.py#L198), [`service.py:202`](../../backend/app/documents/service.py#L202)

- The atomic retry-lock claim — this is what makes reingest safe under concurrency, the same shape as AD-1's original retry lock.
  [`repository.py:51`](../../backend/app/documents/repository.py#L51)

- Tenancy-scoped hash lookup, reused for the pre-create check and the post-race re-query.
  [`repository.py:82`](../../backend/app/documents/repository.py#L82)

- The three-way status-code/scheduling branch in the route — `created`/`reingested` both schedule ingestion, only `duplicate` doesn't.
  [`routes.py:56`](../../backend/app/documents/routes.py#L56), [`routes.py:90`](../../backend/app/documents/routes.py#L90), [`routes.py:94`](../../backend/app/documents/routes.py#L94)

**Data model & migration (deploy-blocking issue found and fixed pre-merge — see Spec Change Log)**

- Column + composite unique index, the DB-level guard against the concurrent-upload race.
  [`models.py:97`](../../backend/app/shared/models.py#L97), [`models.py:106`](../../backend/app/shared/models.py#L106)

- Backfill + the pre-existing-collision safety check — confirmed against real production data.
  [`e1f5c8a2b4d7_add_content_hash_to_documents.py`](../../backend/alembic/versions/e1f5c8a2b4d7_add_content_hash_to_documents.py#L1)

**Frontend: the auto-close fix (found by a real user bug report, not by review)**

- `isSettled` still treats `'duplicate'` as terminal, but the auto-close gate now excludes it — the actual line that was wrong.
  [`UploadModal.jsx:20`](../../frontend/src/components/UploadModal.jsx#L20), [`UploadModal.jsx:105`](../../frontend/src/components/UploadModal.jsx#L105)

- The "Already uploaded" render branch itself (a11y role + defensive `documentId` guard).
  [`UploadModal.jsx:300`](../../frontend/src/components/UploadModal.jsx#L300)

**Tests**

- Reingest-on-Failed-match, no-reingest-on-Ready-match, and the concurrent-reingest race.
  [`test_documents_upload.py:507`](../../backend/tests/test_documents_upload.py#L507), [`test_documents_upload.py:590`](../../backend/tests/test_documents_upload.py#L590)

- Repository-level claim semantics (wins, refuses a non-`Failed` row, clears a stale `chapter_breakdown`, unknown id) and hash-lookup tenancy scoping.
  [`test_documents_repository.py:99`](../../backend/tests/test_documents_repository.py#L99), [`test_documents_repository.py:48`](../../backend/tests/test_documents_repository.py#L48)

- Hash-match/no-match/create-race/cross-user coverage on the real HTTP path.
  [`test_documents_upload.py:305`](../../backend/tests/test_documents_upload.py#L305), [`test_documents_upload.py:335`](../../backend/tests/test_documents_upload.py#L335), [`test_documents_upload.py:398`](../../backend/tests/test_documents_upload.py#L398), [`test_documents_upload.py:422`](../../backend/tests/test_documents_upload.py#L422), [`test_documents_upload.py:451`](../../backend/tests/test_documents_upload.py#L451)

- Migration backfill correctness and the collision-guard's `RuntimeError` path.
  [`test_content_hash_migration.py:77`](../../backend/tests/test_content_hash_migration.py#L77), [`test_content_hash_migration.py:141`](../../backend/tests/test_content_hash_migration.py#L141)

- Frontend: the auto-close regression tests — a lone duplicate staying open (the exact reported bug), an all-duplicate batch, a mixed duplicate+error batch, a mixed duplicate+success batch still closing, and Cancel still working.
  [`UploadModal.test.jsx:219`](../../frontend/src/components/UploadModal.test.jsx#L219), [`UploadModal.test.jsx:244`](../../frontend/src/components/UploadModal.test.jsx#L244), [`UploadModal.test.jsx:286`](../../frontend/src/components/UploadModal.test.jsx#L286), [`UploadModal.test.jsx:305`](../../frontend/src/components/UploadModal.test.jsx#L305)
