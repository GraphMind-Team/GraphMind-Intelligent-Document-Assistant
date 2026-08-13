---
title: 'Story 2.1: Upload documents with drag-and-drop and per-file progress'
type: 'feature'
created: '2026-08-13'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'f11102123795405f6352b2081bd06e2a10f89de3'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `documents` module is still an empty Story-1.1 stub. There's no `documents` table, no upload path, and the Documents page is a placeholder — nothing exists for a user to get files into GraphMind.

**Approach:** Add the `documents` table (Alembic migration, minimal columns this story needs — later stories `ALTER` it incrementally rather than guessing fields now), a validating upload endpoint, and an upload modal with drag-and-drop + click-to-browse into one dropzone, independent per-file progress, and format/size rejection. No parsing/indexing/extraction here — files land in `Uploaded` status and stay there; Story 2.3 does the parsing.

## Boundaries & Constraints

**Always:**
- `documents` table columns (this story only): `id` (uuid pk), `user_id` (fk → users, indexed), `filename`, `file_type` (`pdf`/`markdown`/`html`), `file_size_bytes`, `status` (the five-value FR-4 vocabulary, stored verbatim: `Uploaded`, `Extracting`, `Graphing`, `Ready`, `Failed` — this story only ever writes `Uploaded`), `content` (raw file bytes, Postgres `bytea` via SQLAlchemy `LargeBinary`), `created_at`.
- Format allowlist: `.pdf`, `.md`, `.markdown`, `.html`, `.htm` (by extension and a matching `Content-Type` check) — anything else rejected with a clear reason before any row is written. Files over 20MB rejected with a reason naming the 20MB limit. Validate before any DB write, not after.
- Upload endpoint accepts one file per request (frontend fires one request per queued file, in parallel) — makes each row's progress genuinely independent, not synthetic.
- `user_id` on every written row comes only from `get_current_user` (never client-supplied), per AD-2 — reuse `auth/dependencies.py`, no new pattern.
- Upload modal: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at its heading, focus trapped inside while open, initial focus placed deliberately (the dropzone or first actionable control), focus returned to the Upload button on close. Background not interactive while open (UX-DR25).
- Real per-file progress via `XMLHttpRequest`'s upload `progress` event (not `fetch`, which has no upload-progress API) — each row shows its own filename, size (or "Queued" before it starts), and its own progress bar; a slow file never blocks others (parallel `XMLHttpRequest`s, not sequential).
- Modal closes only via explicit Cancel or once every queued file has resolved (success or error) — closing never cancels in-flight uploads. On close, the Documents list refetches.
- List endpoint/view is minimal — just enough to prove a row appears post-upload; full list/detail UI is Story 2.2's job.

**Ask First:** Storing raw file bytes as Postgres `LargeBinary` rather than an external object store (S3/R2/etc.) — no blob-storage decision exists anywhere in the architecture docs. This keeps the story zero-new-infra and fits the project's free-tier-only constraint, but it's a real architectural choice with a real ceiling (Neon's free tier has a storage cap) that whoever reviews this should explicitly sign off on, not discover later.

**Never:**
- Do not parse, chunk, embed, or write anything to Weaviate/Neo4j in this story — `status` never moves past `Uploaded` here. That's Story 2.3.
- Do not implement content-hash dedupe — that's Story 2.6; uploading the same file twice creates two rows for now.
- Do not build Document Detail (click-through, chapter list, delete) — that's Story 2.2/2.7. This story's list view only needs to prove rows exist with the right status.
- Do not add a document-count cap per user (explicitly unbounded per epics.md).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid file, drag-drop | A `.pdf` under 20MB dropped on the dropzone | Row appears, progress animates to 100%, document row created with `status=Uploaded` | N/A |
| Valid file, click-to-browse | Same file picked via file input | Identical outcome to drag-drop — both paths accept files equally (FR-14) | N/A |
| Unsupported format | A `.docx` file | Rejected before any request is sent; row shows a plain-language reason | Reason names the supported formats |
| Oversized file | A 25MB `.pdf` | Rejected before any request is sent | Reason names the 20MB limit |
| Multiple files, one slow | 3 files queued, one large | Each row's progress is independent; the two smaller files finish while the large one is still uploading | N/A |
| Modal closed mid-upload | User clicks Cancel while a file is still uploading | In-flight upload continues to completion; modal closes; list refreshes once closed | N/A |
| Cross-tenant check | Account B lists documents | Only B's own uploaded rows appear, never account A's | N/A (re-verifies SM-3 against real documents per epics.md) |

</frozen-after-approval>

## Code Map

- `backend/alembic/versions/` -- new migration: `documents` table per Boundaries
- `backend/app/shared/models.py` -- edit: add `Document` ORM model
- `backend/app/documents/routes.py` -- edit: `POST /documents` (upload), `GET /documents` (minimal list for this story)
- `backend/app/documents/service.py` -- edit: format/size validation, row creation
- `backend/app/documents/repository.py` -- edit: `create_document`, `list_documents_for_user` (via `shared/data_access/tenancy.py`'s `user_scoped_select`)
- `backend/app/documents/schemas.py` -- new: `DocumentResponse`, mirrors `auth/schemas.py`'s pattern
- `frontend/src/pages/DocumentsPage.jsx` -- edit: replace placeholder with Upload button + minimal table + modal trigger
- `frontend/src/components/UploadModal.jsx` -- new: dialog, dropzone, per-file progress rows
- `frontend/src/api/documentsClient.js` -- new: `uploadDocument` (XHR-based, progress callback), `listDocuments` — mirrors `authClient.js`'s `formatDetail` error pattern

## Tasks & Acceptance

**Execution:**
- [x] `backend/alembic/versions/` -- migration creating `documents` table -- schema this story and 2.2+ build on
- [x] `backend/app/shared/models.py` -- `Document` model -- ORM counterpart to the migration
- [x] `backend/app/documents/schemas.py` -- `DocumentResponse` -- AD-3 `response_model` compliance
- [x] `backend/app/documents/repository.py` -- `create_document`, `list_documents_for_user` -- tenancy-scoped via `user_scoped_select`
- [x] `backend/app/documents/service.py` -- format/size validation (reject before DB write), orchestrates repository call -- keeps validation out of the route layer
- [x] `backend/app/documents/routes.py` -- `POST /documents` (multipart upload, `Depends(get_current_user)`), `GET /documents` -- the two endpoints this story needs
- [x] `frontend/src/api/documentsClient.js` -- `uploadDocument(file, onProgress)` via XHR, `listDocuments()` via `authFetch` -- real progress events
- [x] `frontend/src/components/UploadModal.jsx` -- dialog a11y (trap/labelledby/initial-focus/return-focus), dropzone, per-file rows -- satisfies AC1/AC2/UX-DR25
- [x] `frontend/src/pages/DocumentsPage.jsx` -- Upload button, minimal table, wires the modal -- proves the end-to-end flow

**Acceptance Criteria:**
- Given the Upload modal is open, when it renders, then it's centered, 520px max-width, dimmed diagonal-hatched backdrop, header/body/footer with right-aligned footer actions, and no second modal can open on top of it.
- Given several files are queued, when they upload, then each row shows independent filename/size/progress, and a slow file never blocks the others.
- Given an unsupported-format or oversized file, when it's added, then it's rejected with a clear, specific reason before any upload request is sent.
- Given uploads finish and the modal closes (Cancel or all-resolved), when it closes, then the Documents list refreshes with the new rows at `Uploaded` status, and any in-flight upload was not cancelled by the close action.
- Given two test accounts each with uploaded documents, when account B lists documents, then none of account A's documents appear.

## Design Notes

Migration is deliberately minimal — no `content_hash` (2.6), `failed_reason` (2.5), or chapter/passage counts (2.2/2.3); each lands via its own later migration rather than being guessed now. `UploadModal.jsx` fires one `XMLHttpRequest` per queued file concurrently, not a sequential queue — that's what makes "a slow file doesn't block the others" literally true.

## Verification

**Commands:**
- `alembic upgrade head` (from `backend/`) -- expected: `documents` table created
- `pytest` (from `backend/`) -- expected: all pass, including new upload/validation/tenancy tests
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: all clean

**Manual checks (if no CLI):**
- Drag-and-drop and click-to-browse both work for the same dropzone.
- Tab through the open modal: focus stays trapped inside; Escape or Cancel returns focus to the Upload button.

## Suggested Review Order

**Upload validation (backend)**

- Format/content-type validated before any body read; size enforced via bounded chunked read rather than post-hoc, closing a DoS-shaped gap review caught (an oversized body no longer gets fully buffered before rejection).
  [`service.py:63`](../../backend/app/documents/service.py#L63)

- The bounded read loop itself, and the ordering (`validate_format` → `_read_bounded` → `validate_size`) that makes the above true.
  [`routes.py:34`](../../backend/app/documents/routes.py#L34)

- Content-Type comparison normalizes parameters/case before matching — closes a real false-rejection bug (`"text/plain; charset=utf-8"` failing an exact-string match against `"text/plain"`).
  [`service.py:52`](../../backend/app/documents/service.py#L52)

**Tenancy & storage**

- `user_id` resolved only from `get_current_user`, matching the pattern `test_tenancy.py` already proved in Story 1.5.
  [`repository.py:21`](../../backend/app/documents/repository.py#L21)

- The `documents` table migration — minimal columns, `content` as `LargeBinary` per the approved "Ask First" decision.
  [`8a1c4f6b2d3e_create_documents_table.py:21`](../../backend/alembic/versions/8a1c4f6b2d3e_create_documents_table.py#L21)

**Upload modal (frontend)**

- Auto-close now requires at least one success, not just "everything settled" — closes a real bug where an all-rejected batch vanished before the user could read why.
  [`UploadModal.jsx`](../../frontend/src/components/UploadModal.jsx)

- Dialog a11y: focus trap, initial focus, return-focus-on-unmount, Escape-to-close.
  [`UploadModal.jsx`](../../frontend/src/components/UploadModal.jsx)

- `listDocuments` now rejects a non-array 2xx body instead of silently handing `DocumentsPage` a `null` that would crash on `.map`.
  [`documentsClient.js`](../../frontend/src/api/documentsClient.js)

**Peripherals**

- New format/content-type/empty-file/tenancy test cases added during review.
  [`test_documents_upload.py`](../../backend/tests/test_documents_upload.py)
