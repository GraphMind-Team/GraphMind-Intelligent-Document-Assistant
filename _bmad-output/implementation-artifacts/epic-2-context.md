# Epic 2 Context: Document Ingestion & Library

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A user can upload documents, watch them move through ingestion to a queryable state, inspect what was extracted, and delete what is stale — understanding exactly what deletion does and does not remove. This is the highest-risk epic in the project: it owns the dual-store write path (vector index + knowledge graph) and its compensating rollback, and it is the only place where partial state across the two stores is possible. Getting the ingestion state machine and rollback discipline right here is a prerequisite for every later epic that reads ingested data (chat retrieval, graph visualization).

## Stories

- Story 2.1: Upload documents with drag-and-drop and per-file progress
- Story 2.2: Document library and detail view
- Story 2.3: Parse and index documents into the vector store
- Story 2.4: Extract entities into the unified graph with compensating rollback
- Story 2.5: Failed ingestion surfaced with a readable reason
- Story 2.6: Content-hash dedupe on upload
- Story 2.7: Delete a document with an honest deletion boundary

## Requirements & Constraints

- Supported formats are PDF, Markdown, and HTML only; unsupported formats are rejected with a clear reason before any processing starts, and files over 20MB are rejected with a reason naming the limit. There is no cap on document count per user.
- A successfully parsed document produces one or more passages, each tagged with `document_id`, `chapter`, `chunk_index`.
- Ingestion status is exactly five states, used verbatim everywhere it's shown: `Uploaded`, `Extracting`, `Graphing`, `Ready`, `Failed`. A Failed document stays in the list with a human-readable reason — it is never silently dropped.
- Entity/relationship extraction merges into one unified graph per user (not a graph per document); matching entities merge, non-matches stay distinct. Extraction is constrained to a fixed, closed type set: entity types `Person`, `Organization`, `Project`, `Product`, `Location`; relationship types `WORKS_AT`, `SUPPLIES`, `PART_OF`, `LOCATED_IN`, `RELATED_TO` (the last one is the fallback so extraction never needs a type outside this closed set).
- Re-uploading a byte-identical file (matched by content hash, not filename) does not create a second document row, does not re-parse, and makes no embedding or LLM call — this exists specifically to protect the project's zero-cost, free-tier-only constraint.
- The document list and detail view show only the authenticated user's own documents — verified with two real test accounts, not just a blocked-query check. This is a launch-blocking requirement, not best-effort.
- Deleting a document removes its passages/embeddings from the vector index immediately; graph entities/relationships derived from it are deliberately not pruned (avoids reference-counting complexity in a unified multi-document graph). The UI must state this boundary plainly at delete time, in declarative language with no apologetic filler. A deleted document must no longer appear in the library, in chat scope, or as a citation.
- Upload accepts both drag-and-drop and click-to-browse into the same dropzone; each queued file shows independent progress so a slow file never blocks the others.

## Technical Decisions

- **Ingestion consistency (saga-lite rollback):** write order is fixed — Weaviate first, then Neo4j. If the Neo4j write fails, the handler actively deletes the Weaviate objects just written for that document, then marks it `Failed` with a human-readable reason. No orphaned partial state may survive a failed ingestion. The document's status row doubles as a retry lock: retry is only accepted from `Failed`, never while `Extracting`/`Graphing` is in flight, so a retry can never race an in-progress rollback. The `documents` module is the sole writer of the ingestion-status field.
- **Mandatory shared data-access layer:** no module hand-writes raw Weaviate or Neo4j queries; every read/write goes through `shared/data_access/`. The Weaviate passage shape is flat — `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`, no nested metadata dict — since both the `documents` module (writer) and the `chat` module (reader, Epic 3) depend on this exact shape. The Neo4j shape is a minimal typed contract: entity `name` + `type`, relationship `type` between two entity references.
- **Entity/relationship type list is resolved (OD-1):** entities are limited to `Person`, `Organization`, `Project`, `Product`, `Location`; relationships are limited to `WORKS_AT`, `SUPPLIES`, `PART_OF`, `LOCATED_IN`, `RELATED_TO`. Extraction prompts in Story 2.4 must constrain the LLM to exactly this closed set — no open-ended vocabulary.
- **Entity identity resolution is exact-string-match only** in v1 — no fuzzy or LLM-assisted merge. Near-matches (e.g. "TechCorp" vs "TechCorp Supplies") intentionally remain distinct nodes.
- **All OpenRouter calls go through `shared/llm_client/`** — the `documents` module never calls OpenRouter directly. This is also the enforcement point that keeps entity extraction consistent with the refusal-short-circuit pattern used elsewhere.
- `user_id` on every passage/entity write is resolved server-side from the JWT, never trusted from client input.
- Module layout: the `documents` module owns `routes.py` / `service.py` / `repository.py`; parsing, chunking, dedupe, and ingestion + rollback orchestration live in `service.py`.
- **Resolved (OD-7):** on a content-hash match, no new row is created; the upload modal shows an explicit "already uploaded" message and surfaces the existing document. Dedupe keys on content hash only, never filename.

## UX & Interaction Patterns

- Upload modal follows the shared modal pattern: centered, 520px max-width, dimmed diagonal-hatched backdrop, header/body/footer with right-aligned footer actions, never stacked on another modal. Full dialog a11y required: `role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, deliberate initial focus, focus returned to the trigger on close.
- The modal closes only via explicit Cancel or once every queued file resolves; closing never cancels in-flight uploads, and the Documents list refreshes on close.
- Document table columns: Title, Type, Status, Uploaded date, trash icon. Clicking a row anywhere but the trash icon opens Document Detail; the trash icon is a separate hit target that never navigates.
- Document Detail shows title, status, upload date, file type/size, chapter count, passages-indexed count, and a chapter list with per-chapter passage counts once Ready. Before Ready, those fields show as pending/unavailable — never fabricated as zero.
- Status pills use one shared token pair (tint + text label) per state, color never standing alone, label as real selectable DOM text (not an icon-font glyph or pseudo-element). Only 2 of the 5 states (`ready`/success, `uploaded`/warning) have a concretely specified, AA-tuned text color in the design source; `extracting`/`graphing`/`failed` are described only as "extend the same pattern" (warning for in-progress, danger for failed) without a confirmed tuned value — confirm all five clear 4.5:1 contrast before shipping pill-rendering surfaces in this epic.
- Delete uses an inline confirm (not a modal), on both the table row and Document Detail. Its copy states plainly that passages are removed from search immediately and that already-merged graph entities remain and may still influence future answers. Its a11y: appearance is announced, the boundary text is programmatically tied to Confirm/Cancel so it's read before acting, focus moves into the box, Escape collapses it, focus returns to the triggering control on close.
- Two open UX gaps with no existing mock, decided as part of this epic's stories: how a Failed reason is placed (inline in the row vs. Detail-only — Story 2.5), and the empty-library state (assumed to be a plain "No documents yet." message with Upload still primary-actionable — Story 2.2).
- Voice throughout: plain, declarative, specific about why; no hedging, apology filler, or decorative emoji.

## Cross-Story Dependencies

- This epic builds on Epic 1's authenticated shell, JWT-derived `user_id` resolution, and the shared data-access layer scaffolding — ingestion and library stories assume those already exist.
- Within the epic, ingestion is a pipeline: 2.1 (upload) feeds 2.2 (library list); 2.3 (parse/index) must land before 2.4 (entity extraction/graph merge) and 2.6 (dedupe, which short-circuits before 2.3's parse step); 2.5 (failed-state surfacing) depends on the status vocabulary and rollback behavior established in 2.4; 2.7 (delete) depends on the vector-store write path from 2.3.
- OD-1 (the entity/relationship type list) is resolved, so Story 2.4's extraction-prompt work is unblocked.
- The Weaviate passage shape this epic writes (flat `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`) is a hard contract that Epic 3's chat/retrieval module reads — changing it here breaks that epic.
