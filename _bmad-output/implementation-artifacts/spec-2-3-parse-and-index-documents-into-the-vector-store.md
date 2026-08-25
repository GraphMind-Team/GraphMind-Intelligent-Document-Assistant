---
title: 'Story 2.3: Parse and index documents into the vector store'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 4
context: []
baseline_commit: '26aa8883481fac7d26213cbd51a7cd4105268463'
provenance: 'reconstructed-after-implementation'
---

> **Provenance — read this before trusting the Boundaries below.**
>
> This spec was authored on 2026-08-14, a full epic after Story 2.3 shipped (`8702517`, merged during Epic 2) and after four review-round fixes on it. It is the **first** occurrence of the missing-spec-file gap in this project — the `deferred-work.md` entry recording it explicitly warned this would recur ("worth closing before 2.4 sets the same precedent"), and it did: Story 3.1 shipped without one too (see `spec-3-1`'s own provenance note, which cites this exact entry).
>
> The Boundaries section below is reconstructed from three sources — `epics.md`'s Story 2.3 acceptance criteria, the shipped code's own comments, and the four pre-merge review-round commit messages (`0562af0`, `a5e246e`, `f85f1d5`, `49a12d5`, `0e3523e`). It describes what the story turned out to be bound by, not decisions a human approved in advance. Nothing here was negotiated before implementation.
>
> **Scope note:** this spec describes Story 2.3 as it shipped — parsing, chunking, local embedding, and the Weaviate write, ending at `Extracting`. Every file this story touches was extended again by later stories (`Graphing`/`Ready`/`chapter_breakdown` by 2.4, `Failed`'s reason text and the polling widened past `Uploaded` by 2.4/2.5, `search_passages` by 3.1). Where the Code Map below names a file also owned by one of those specs, this file's claim on it is limited to what 2.3 itself put there — see each of those specs' own Code Map for what was layered on top.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.2 gives a document a row, a status, and a detail page — but `status` can only ever be `Uploaded`, because nothing reads the uploaded bytes. FR-9's grounded-answer promise (Epic 3) has nothing to retrieve from; the library is a list of inert files.

**Approach:** A background ingestion pipeline, kicked off right after upload responds: parse the document into chaptered text, chunk it, embed each chunk locally (no per-call cost, no external API in the hot path), and write the flat passage shape to Weaviate through the first real `shared/data_access/` vector-store client. Status advances `Uploaded` → `Extracting` and stays there — `Graphing`/`Ready` are Story 2.4's pipeline continuation, not this one's.

## Boundaries & Constraints

**Always:**
- Parsing produces one or more passages per document, each tagged `document_id`, `chapter`, `chunk_index` (FR-3). Every parser (PDF/Markdown/HTML) catches its own failure mode and raises `UnparseableDocument` rather than trusting that upload-time extension/content-type checks proved the bytes are what they claim to be.
- The Weaviate write goes through a shared repository function in `shared/data_access/` — no raw Weaviate query anywhere in the `documents` module (AD-2). The flat agreed shape (`chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`), no nested metadata dict.
- `user_id` is applied server-side on every passage write, from the row's own `document.user_id` (itself JWT-derived at upload time), never from client input (FR-2).
- Status advances `Uploaded` → `Extracting` at the start of ingestion, visible on the Documents table without a manual reload (FR-4) — polling, not push, is this story's mechanism.
- Ingestion runs as a `BackgroundTasks` job scheduled after the upload response is sent, not awaited inline — upload latency stays independent of parse/embed/write time.
- Any failure anywhere in parse/embed/write marks the document `Failed`, never leaves it stuck at `Extracting` — AD-1's retry-lock ("retry only from `Failed`") has no other way to ever unlock a row that failed mid-pipeline.
- Chunk size and embedding model are chosen together, not independently: the chunk word count must leave real headroom under the embedding model's token limit, including for Cyrillic text tokenizing denser than English under a shared multilingual vocabulary.
- The embedding model runs locally (fastembed/ONNX), not via a paid API — a hard zero-cost constraint (AD-8) this story is the first to actually exercise.
- `close_weaviate_client()` is wired into `main.py`'s `lifespan`, mirroring the session-factory pattern already established for Postgres.

**Ask First:** none outstanding at the time this spec was reconstructed.

**Never:**
- No entity/relationship extraction, no Neo4j write, no `Graphing`/`Ready` status — Story 2.4's continuation of this same pipeline, not this story's.
- No retrieval/search path — `search_passages` doesn't exist yet; this story only writes. (Added later, by Story 3.1.)
- Extracted chapter titles and body text are never rendered as HTML or Markdown anywhere downstream — plain text / React nodes only, never `dangerouslySetInnerHTML`. A malicious `.md`/`.html` upload's heading text becoming stored XSS is a standing constraint on every future consumer of this text, not just this story's own rendering (none — this story never renders extracted text itself).
- No magic-byte verification of uploaded content against its claimed `file_type` — extension/content-type checks happen once, at upload time (Story 2.1); this story's parsers must independently fail closed (raise `UnparseableDocument`) rather than assume the claim was honest.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal ingestion | A valid PDF/MD/HTML upload | `Uploaded` → `Extracting`; passages written to Weaviate | N/A |
| Corrupt or mislabeled file | Bytes don't parse as their claimed `file_type` | `Failed`, no passages written | Logged with the underlying error |
| Document deleted mid-flight | Background task runs after the row is gone | Silent no-op — not an error | N/A |
| Text before the first heading/bookmark | A PDF/MD with an abstract or lead-in before any heading | Kept as a leading `"Full Document"` chapter, not dropped | N/A (review-round fix, not the initial ship) |
| HTML comments | `<!-- internal note -->` in an uploaded `.html` file | Excluded from passages — never embedded, never citable | N/A (review-round fix) |
| Fenced code block containing a `#`-prefixed line | A bash snippet with `# install deps` inside a Markdown fence | Not treated as a heading/chapter boundary | N/A (review-round fix) |
| Large document | Thousands of chunks, up to the 20MB upload cap | Embedded and written in `PASSAGE_BATCH_SIZE` batches, not all held in memory at once | N/A (review-round fix — see Design Notes) |
| Partial batch write failure | A later batch's Weaviate write fails after earlier batches succeeded | Already-written passages for this document are best-effort deleted — no orphaned partial set for a later retrieval to read as complete | Logged; document marked `Failed` |
| Two uploads racing the collection's first-ever creation | Concurrent first uploads against a fresh Weaviate instance | Exactly one create succeeds; the other proceeds without erroring | N/A (review-round fix — see Design Notes) |
| Failed-recovery commit itself fails | DB connection drops during the very commit meant to record `Failed` | Caught, logged — does not crash the background task or leave an unhandled exception | Logged |
| Concurrent uploads racing first model/client construction | Two background tasks both hit a cold embedding model or Weaviate client | Lock-guarded singleton construction — only one instance is ever built | N/A (review-round fix — see Design Notes) |

</frozen-after-approval>

## Spec Change Log

Story 2.3 shipped before this file existed, so these entries are reconstructed from four pre-merge review-round commits. Recorded here because the reasoning was previously only discoverable by reading `git log`, not by reading a spec.

- **Trigger:** First review pass (`0562af0`).
- **Pre-heading text no longer silently dropped:** Markdown/PDF-outline chapter splitting discarded any text before the first heading/bookmark (abstracts, README lead-ins, title pages). Now kept as a leading `"Full Document"` chapter — the same label Story 3.1 later inherits as the degenerate case its own FR-9 chunk-traceability fix had to account for.
- **HTML comments excluded:** the same `isinstance(NavigableString)` check used for real text also matched bs4's `Comment`/`CData`/`Doctype`/`Declaration` subclasses, so internal notes and TODOs embedded in uploaded HTML were getting embedded and made citable. Excluded via `PreformattedString`.
- **KEEP:** every boundary above.

- **Trigger:** Second review pass (`a5e246e`, "harden polling, ingestion recovery, and Weaviate write path").
- **`DocumentsPage` polling bugs fixed:** a silent poll was clearing a visible error banner (`setError(null)` ran before the silent-poll check), and the attempt cap incremented after checking instead of before, firing one fewer fetch than `MAX_POLL_ATTEMPTS` promised.
- **Failed-recovery path hardened:** `ingest_document`'s rollback/status/commit sequence is itself now wrapped in try/except — if it throws too (plausible: the same DB connection that just caused the original failure), the row no longer gets stuck at `Extracting` with an unhandled exception silently escaping the background task.
- **`write_passages` hardened:** rejects a batch whose passages don't all share one `(document_id, user_id)` instead of trusting `passages[0]` for the delete filter; `insert_many` now batches instead of one unbounded call per document.
- **Embedding model construction race fixed:** `@lru_cache` doesn't serialize concurrent cache misses — two background tasks racing on first use could both construct a full model instance simultaneously. Replaced with an explicit lock around first construction.
- **KEEP:** everything above.

- **Trigger:** Third review pass (`f85f1d5`, "multilingual embeddings, Weaviate collection race, orphan cleanup").
- **Embedding model switched to multilingual:** `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 512-token limit), replacing an English-only model that silently truncated non-English (Bulgarian) text without ever raising — a document could ingest successfully while its embeddings were computed from text the model was never trained on. This also incidentally fixed truncation for English: the old model's 256-token limit was already under half of what a 400-word chunk produced. Chunk size dropped to 250 words / 40-word overlap to fit real headroom under the new 512-token budget.
- **`get_weaviate_client` singleton race fixed:** same root cause and same fix shape as the embedding-model race above — `@lru_cache` replaced with a lock-guarded singleton. `close_weaviate_client()` added for the `lifespan` shutdown call.
- **Collection creation race fixed:** moved to a one-time, best-effort app-startup call (`weaviate_client.ensure_ready`, never blocks boot) plus a process-level readiness flag and a race-tolerant `create()` — two concurrent first-ever uploads no longer both call `create()` with the loser failing for no real reason, and every subsequent batch stops re-checking `exists()` once confirmed.
- **Delete-then-insert failure visibility fixed:** `delete_many`'s result is now checked; a partial failure logs a warning instead of being silently swallowed.
- **Orphan cleanup added:** a batch failing partway through now triggers a best-effort delete of this document's already-written passages — without it, a failed document could leave an orphaned partial passage set that Epic 3's retrieval would later read as if it were complete.
- **Markdown heading detection fixed:** now skips fenced code blocks, so a `# install deps` comment inside a bash snippet is no longer mistaken for a chapter boundary.
- **`DocumentsPage` polling restart key fixed:** keyed on *which* documents are pollable, not just whether any are — previously a document stuck at `Uploaded` forever would permanently exhaust the poll budget for the rest of the session, starving a later genuine upload of its own budget.
- **Process note:** this same commit logged the missing `spec-2-3` file as deferred work and corrected `sprint-status.yaml`'s 2-2/2-3 states. That entry is what this file, written an epic later, finally closes.
- **KEEP:** everything above.

- **Trigger:** Fourth review pass (`49a12d5`, "embed and write passages in batches, not all chunks at once").
- **Memory ceiling fixed:** `ingest_document` was embedding every chunk of a document into one in-memory `vectors` list before the first passage ever reached Weaviate — for a large document (up to the 20MB cap, thousands of chunks), that is the whole document's worth of 384-dim vectors held simultaneously, a more likely OOM path on a 512MB instance than the `insert_many` batching already applied Weaviate-side.
- **`write_passages` split:** into `delete_passages_for_document` (called once per document) and an insert-only `write_passages` (called once per batch) — folding the delete into every batch call would have wiped out whatever the previous batch just inserted. `ingest_document` now loops chunks in `PASSAGE_BATCH_SIZE` groups, embedding and writing each batch before moving to the next.
- **KEEP:** everything above.

- **Trigger:** Fifth review pass (`0e3523e`, small — recorded for completeness).
- **Orphan-cleanup-during-failure fixed:** `ingest_document` now captures `document_id`/`user_id` as plain strings *before* the try block, instead of re-reading `document.id`/`document.user_id` inside the except handler — after a DB-caused failure those attributes can be expired and require a session that may itself be broken (the likely cause of the original failure), silently skipping the orphan-cleanup delete in exactly the case it matters most.
- **`close_weaviate_client()` also resets the collection-readiness flag** — that flag describes readiness over the *connection*, not the process, so a reopened connection after a close must re-confirm the collection exists.
- **KEEP:** everything above.

- **Trigger:** Direct human request on a later feature branch ("add DOCX and PPTX upload/parsing support", `1b3354f`) plus the two review rounds over it (`1f52a15`, `4b74d48`). Not a defect in 2.3 — this story's parsing contract was correct for the three formats that existed when it shipped — but `parse_document` is 2.3's, so its acceptance criterion is where the widened contract has to be recorded.
- **Acceptance criterion widened:** "Given an uploaded PDF, Markdown or HTML document" now also covers DOCX and PPTX. The criterion's substance is unchanged (one or more passages, each tagged `document_id`/`chapter`/`chunk_index`); only the set of inputs it ranges over grew. `_parse_docx` chapters on Word's built-in heading styles by locale-invariant `style_id`, `_parse_pptx` chapters per slide on the slide title; both walk tables as well as body text.
- **Chapter-with-no-body no longer dropped:** `_chunk_chapters` skipped any chapter whose body text was empty, which silently cost a title-only PPTX slide (a section divider) and a DOCX heading immediately followed by another heading — the chapter vanished from the index rather than degrading. Such a chapter is now indexed on its own title. The `"Full Document"` sentinel this story introduced (see the first Trigger above) is the deliberate exception: it is a placeholder, not a title anyone wrote, so an empty one still means "no extractable text" and is still dropped. A PPTX slide with neither title nor body falls back to that same sentinel for exactly this reason — otherwise an image-only deck would index as the contentless strings "Slide 1", "Slide 2", retrievable and citable with nothing behind them, while the equivalent image-only PDF correctly fails.
- **Zip-bomb guard added:** DOCX/PPTX are zip archives, so unlike this story's three original formats the 20MB upload cap bounds only the *compressed* size. `_check_zip_bomb` now measures each entry's real decompressed output in bounded chunks before python-docx/python-pptx open the file, capped at 200MB. It deliberately does not trust `ZipInfo.file_size` (attacker-controlled central-directory data), and reads against a `ZipInfo` copy whose declared size cannot truncate the measurement — `zipfile` applies that size to reads *after* inflating, so a guard reading entries normally measures the lie while the full payload is still materialized in memory.
- **KEEP:** everything above, and every boundary this story set on chunking, batching and the dual-store write path — none of it is format-specific.

- **Out of scope for this Change Log:** `d03f9f2` ("poll until a document is actually Ready") widened `DocumentsPage`'s polling past `Uploaded` and batched the Neo4j write path. That commit belongs to Story 2.4's review (already recorded in `spec-2-4`'s own Spec Change Log) — it fixes a regression 2.4 introduced against 2.3's own (then-correct) polling behavior, not a defect in 2.3 itself. Named here only so a reader diffing `DocumentsPage.jsx` against this spec isn't left looking for where that change came from.

## Code Map

- `backend/app/documents/parsing.py` -- new: `parse_document`, PDF (bookmark-aware)/Markdown (heading-aware, fence-safe)/HTML (comment-excluding) chapter splitting, chunking with overlap
- `backend/app/documents/service.py` -- edit: `ingest_document` — the background task; `Uploaded` → `Extracting`, parse/embed/batch-write, `Failed` on any exception with best-effort orphan cleanup
- `backend/app/documents/routes.py` -- edit: `upload_document` schedules `ingest_document` via `BackgroundTasks`, passing only `document.id`
- `backend/app/shared/data_access/shapes.py` -- edit: `WeaviatePassage` — the flat, no-nested-metadata shape
- `backend/app/shared/data_access/weaviate_client.py` -- new: lock-guarded singleton client, `ensure_ready()` (startup, best-effort), `write_passages`/`delete_passages_for_document`, `PASSAGE_BATCH_SIZE`
- `backend/app/shared/data_access/__init__.py` -- edit: exports `write_passages`
- `backend/app/shared/embeddings/model.py` -- new: lock-guarded singleton `fastembed` model, `embed_texts`
- `backend/app/main.py` -- edit: `lifespan` closes the Weaviate client on shutdown
- `backend/.env.example` -- edit: documents `WEAVIATE_URL`/`WEAVIATE_API_KEY` as required for real ingestion, optional for the test suite
- `backend/requirements.txt` -- edit: `pypdf`, `beautifulsoup4`, `fastembed`
- `frontend/src/pages/DocumentsPage.jsx` -- edit: polls briefly after upload so the `Uploaded` → `Extracting` transition is visible without a manual reload
- `backend/tests/test_documents_parse_and_index.py` -- new: parse/chunk/embed/write path, both failure branches
- `backend/tests/test_weaviate_client.py` -- new: write/delete, batching, collection-creation race tolerance
- `backend/tests/test_embeddings.py` -- new: model singleton, `embed_texts` shape
- `frontend/src/pages/DocumentsPage.test.jsx` -- edit: polling behavior, error-banner persistence through a silent poll

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/documents/parsing.py` -- PDF/Markdown/HTML parsing and chunking, chapter-aware
- [x] `backend/app/shared/data_access/shapes.py` -- `WeaviatePassage`
- [x] `backend/app/shared/data_access/weaviate_client.py` -- client singleton, `ensure_ready`, write/delete path, batching — AD-2
- [x] `backend/app/shared/embeddings/model.py` -- local multilingual embedding, lock-guarded singleton
- [x] `backend/app/documents/service.py` -- `ingest_document`, its `Failed` recovery path, batched embed/write, orphan cleanup
- [x] `backend/app/documents/routes.py` -- background-task scheduling on upload
- [x] `backend/app/main.py` -- Weaviate client lifecycle in `lifespan`
- [x] `frontend/src/pages/DocumentsPage.jsx` -- post-upload polling, error-banner and attempt-cap correctness
- [x] `backend/tests/test_documents_parse_and_index.py`, `test_weaviate_client.py`, `test_embeddings.py`
- [x] `frontend/src/pages/DocumentsPage.test.jsx`

**Acceptance Criteria:**
- Given an uploaded PDF, Markdown or HTML document, when parsing runs, then it produces one or more passages, each tagged with `document_id`, `chapter` and `chunk_index`.
- Given parsed passages, when they are written to the vector store, then the write goes through a shared repository function using the flat agreed shape, with no raw Weaviate query inside `documents`.
- Given a document begins parsing, when its status is updated, then it advances `Uploaded` → `Extracting`, visible on the Documents table without a manual reload.
- Given any passage write, when it executes, then `user_id` is applied server-side, never from client input.

## Design Notes

Chunking: ~250 words per chunk, ~40-word overlap between consecutive chunks (`CHUNK_OVERLAP_WORDS`, made public so `documents/service.py`'s later extraction-text concatenation, Story 2.4, can strip it back off rather than re-deriving the number). `chunk_index` is sequential across the whole document, not reset per chapter. Sized against the embedding model's 512-token input limit with real headroom for Cyrillic's denser tokenization under a shared multilingual vocabulary — getting this wrong is silent (the model truncates, doesn't fail), so an oversized chunk's tail is stored and citable but never actually seen by its own embedding.

Embedding runs via `fastembed` (ONNX Runtime), not `sentence-transformers`/`torch` — torch's install size (~800MB–1GB) and a loaded MiniLM's runtime footprint (~400–600MB RSS) don't comfortably fit Render's 512MB free-tier instance alongside everything else the process holds.

Deferred and recorded, not fixed here: Render's free tier has an ephemeral filesystem, so `fastembed`'s on-disk model-weight cache does not survive a restart/redeploy/spin-down — every cold instance pays a real download before its first embed call. (Story 3.1's own `_warm_embedding_model`, added an epic later, addresses the *within-request* symptom of this — moving the cost off `ask_question`'s hot path — but does not make the cache persist across a genuinely cold boot; the download still happens, just at startup instead of at first use.)

The Weaviate write path batches at two levels: `ingest_document` embeds and writes chunks in `PASSAGE_BATCH_SIZE` groups (bounding in-memory vector count for a large document), and `write_passages` itself batches `insert_many` calls in chunks of `PASSAGE_BATCH_SIZE` even within one call (bounding request size to Weaviate). `delete_passages_for_document` runs once per document, separately from `write_passages`, specifically so folding it into per-batch writes can't wipe out a prior batch's just-inserted passages.

Collection creation and the client singleton both moved from `@lru_cache`/bare check-then-create to explicit lock-guarded construction, after two independent review rounds found the same race shape twice (embedding model, then Weaviate client/collection) — `@lru_cache` does not serialize concurrent cache misses, so two background tasks racing on first use could each build a full instance.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the three new test files
- `npm test -- --run` (from `frontend/`) -- expected: clean, including `DocumentsPage.test.jsx`'s polling cases

**Manual checks (if no CLI):**
- With real `WEAVIATE_URL`/`WEAVIATE_API_KEY` set, upload a PDF, a Markdown file with a pre-heading abstract, and an HTML file with an embedded comment; confirm each reaches `Extracting`, and that the comment never appears as a citable passage in the Weaviate console. Upload a Bulgarian-language document and confirm its embeddings are non-degenerate (not silently truncated).
