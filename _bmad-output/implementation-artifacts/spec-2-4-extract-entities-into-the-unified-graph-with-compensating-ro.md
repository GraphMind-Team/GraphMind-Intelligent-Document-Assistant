---
title: 'Story 2.4: Extract entities into the unified graph with compensating rollback'
type: 'feature'
created: '2026-08-13'
status: 'in-review'
review_loop_iteration: 1
context: []
baseline_commit: '0e37045523e87ed8379d2f376d26720b56636383'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.3 leaves every document parked at `Extracting` forever — nothing calls an LLM, nothing writes to Neo4j, and neither `shared/llm_client/` nor a Neo4j client exists yet anywhere in the codebase. `Graphing`/`Ready` are unreachable statuses.

**Approach:** Add the first real `shared/llm_client/` (OpenRouter, AD-6) and the first real Neo4j client (`shared/data_access/neo4j_client.py`, mirroring `weaviate_client.py`'s pattern exactly), an extraction step constrained to OD-1's closed type set, and the Neo4j write with AD-1's compensating rollback. `ingest_document` (Story 2.3) extends: `Extracting` → parse/embed/write Weaviate (already built) → **`Graphing`** → extract + merge into Neo4j → **`Ready`**, or `Failed` with Weaviate cleanup on any failure in the Graphing step.

## Boundaries & Constraints

**Always:**
- `shared/llm_client/` is the sole path to OpenRouter (AD-6) — `documents/service.py` never imports an OpenRouter SDK directly. One function: given text + the OD-1 type sets, return parsed `{entities, relationships}` or raise. Retry on timeout/5xx (2 attempts total), consistent with `weaviate_client`/`embeddings` treating transient provider failures as retryable.
- Extraction constrained to the closed OD-1 sets — entities `Person`/`Organization`/`Project`/`Product`/`Location`; relationships `WORKS_AT`/`SUPPLIES`/`PART_OF`/`LOCATED_IN`/`RELATED_TO` (fallback). Enforced in code after the LLM responds, not trusted from the prompt alone — an out-of-vocabulary type is dropped with a warning log, not a document-level failure.
- One extraction call per document over its concatenated chapter text, bounded to a fixed character budget (Design Notes) — not per-passage. Truncation is for extraction only; Weaviate still holds every passage untruncated.
- `neo4j_client.py` mirrors `weaviate_client.py`: lazy double-checked-locking singleton (`get_neo4j_driver`), `close_neo4j_driver()` in `main.py`'s existing `lifespan`, one `write_entities_and_relationships(...)` function — the only one `documents/service.py` calls (AD-2).
- Entity merge is `MERGE` on exact `(name, type, user_id)` — matches merge into one node, near-matches ("TechCorp" vs "TechCorp Supplies") stay distinct (AD-4). Relationships `MERGE`d between two entity refs, typed, same `user_id` scope.
- Status extends 2.3's sequence: `Extracting` (set) → Weaviate write (built) → `Graphing` → extract + Neo4j write → `Ready`.
- Any Graphing-step failure (LLM after retries, or the Neo4j write) triggers the same rollback a Weaviate failure would: delete this document's Weaviate passages (`delete_passages_for_document`, already built), mark `Failed`. Reading AD-1's "Neo4j write fails → rollback" as covering the whole step — both failure points leave the identical broken state, needing identical cleanup.
- Retry-lock carries over unchanged: a document in `Extracting`/`Graphing` refuses retry; only `Failed` can (AD-1) — verify 2.3's existing guard already covers `Graphing`, added after that guard was written.
- `user_id` on every Neo4j write resolved server-side (AD-2), never client input.

**Ask First:** none outstanding — the one open decision (OD-1) was resolved by the human before this spec was written.

**Never:**
- No fuzzy/LLM-assisted entity merge — exact match only (AD-4), no exceptions.
- No graph read/query endpoint or visualization — Epic 4's job. This story only writes.
- No pruning of graph entities on document delete — explicitly deferred to Epic 2's own delete story (2.7) and stated there as a permanent boundary, not incidentally skipped here.
- No `failed_reason` column — Story 2.3 set this precedent (status-only, reason goes to the logger); Story 2.5 adds the column and the surfaced text. Don't invent one now.
- No chat/refusal-short-circuit logic in `shared/llm_client/` — that's Epic 3's addition to this same package when Chat is built; this story's client function has no concept of refusal.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal extraction | Document reaches `Extracting`, Weaviate write already succeeded | Status → `Graphing` → entities/relationships extracted and merged → `Ready` | N/A |
| No notable entities | LLM returns an empty entities/relationships list | Document still reaches `Ready` — an empty extraction is a valid outcome, not a failure | N/A |
| LLM call fails after retries | OpenRouter timeout/5xx, both attempts exhausted | Weaviate passages for this document deleted; status → `Failed` | Logged with the underlying error |
| Neo4j write fails | Driver/query error during the merge | Same as above: Weaviate cleanup, status → `Failed` | Logged with the underlying error |
| LLM returns an out-of-vocabulary type | e.g. `"type": "Event"` | That entity/relationship is dropped; extraction continues with the rest | Warning logged, not a document-level failure |
| Repeat entity across documents | Same user uploads two documents both mentioning "Maria Ivanova" (Person) | One graph node, referenced by both documents' extractions | N/A |
| Retry attempted mid-flight | Retry requested while status is `Extracting` or `Graphing` | Refused — retry only accepted from `Failed` | 4xx/plain detail, reusing 2.3's existing guard |

</frozen-after-approval>

## Spec Change Log

- **Trigger:** Direct human request ("what about the document view page, whee the pages and chapters are not yet shown" → "add in 2.4"), after confirming via grep that `Document`/`DocumentResponse` have no chapter/passage-count fields at all — this was deferred out of Story 2.2 and never picked up by 2.3 (which only built the Weaviate write path) or 2.4's original Code Map (which didn't touch `models.py`/`schemas.py`).
- **Amended:** One nullable JSON column, `Document.chapter_breakdown` (`dict[str, chapter_name] -> int passage_count`), populated once — from the `chunks` list already produced during the `Extracting` parse step — in the *same commit* that sets `status = "Ready"`. Never set on the `Extracting`/`Graphing`/`Failed` paths, so a `Failed` document keeps `chapter_breakdown = None` and the Detail page's existing "Pending, never a fabricated 0" rule (Story 2.2, UX-DR8) continues to cover it with no new branching. `DocumentResponse` exposes the raw dict as `chapter_breakdown: dict[str, int] | None`; `chapter_count` and `passages_indexed` are derived from it client-side (dict length, sum of values) rather than stored as separate redundant columns.
- **Deviation acknowledged:** Story 2.2's frozen spec said "No speculative `chapter_count`/`passage_count` columns" and named 2.3 as the story that would add them "when it has real data." 2.3 shipped without them. This amendment is that deferred column work, attached here instead because 2.4 is the first story where a document can actually reach `Ready`.
- **Why one JSON column, not two integers:** the epic context's UX spec calls for "a chapter list with per-chapter passage counts," not just two totals — a single `chapter, count` map covers both the summary numbers and the breakdown list from one source of truth, insertion-ordered to match reading order.
- **Why `sa.JSON`, not `postgresql.JSONB`:** `backend/tests/conftest.py` runs the suite against `sqlite:///:memory:`, which has no JSONB support; the generic `sa.JSON` type works on both SQLite and the real Postgres (Neon) database.
- **KEEP:** every already-approved boundary above (llm_client, neo4j_client, Graphing status step, AD-1 rollback scope, AD-4 exact-match merge) is unchanged by this amendment.

- **Trigger:** Three-layer adversarial review (blind-hunter, edge-case-hunter, verification-gap) after the implementation subagent's first pass, all tests green.
- **Real bug fixed:** `neo4j_client.write_entities_and_relationships`'s `entity_type_by_name` lookup was a flat `{name: type}` dict — a name appearing twice with two different types (AD-4's own docstring names this as legitimate, e.g. "Washington" the Person vs. "Washington" the Location) silently kept only the last-seen type, so a relationship naming that ambiguous entity could resolve against the wrong type and its Cypher `MATCH` would match zero rows, silently dropping the relationship with no warning (the existing warning path only covered the *absent* case, not the *ambiguous* one). Fixed: ambiguous names are now excluded from the lookup, and a relationship naming one is dropped through the same warning path as an absent name. New test: `test_write_entities_and_relationships_skips_a_relationship_whose_source_name_is_ambiguous`.
- **Hardening added:** `neo4j_client.ensure_ready()` (new), wired into `main.py`'s lifespan startup alongside the existing Weaviate `ensure_ready()`, creates a `(name, type, user_id)` uniqueness constraint on `:Entity`. Without it, `MERGE` alone is only safe against a single writer — two background ingestion tasks racing to create the same not-yet-existing entity (realistic: Story 2.1 lets multiple files queue and process concurrently) could both create a node, breaking the "one graph node, not two" AC under concurrency. Best-effort, matching Weaviate's own startup treatment exactly: failure is logged, never fatal, since a Community-tier Neo4j deployment may not support composite uniqueness constraints at all.
- **Verification gap closed:** `chapter_breakdown`'s "preserves document reading order" claim was asserted only via dict `==`, which ignores key order in Python — the original test fixture's chapters also happened to already be alphabetical, so even an order-sensitive assertion against it couldn't have revealed a wrong (sorted) implementation. New test `test_chapter_breakdown_preserves_document_reading_order_not_sorted` uses chapters in reverse-alphabetical document order and asserts `list(...items())` directly.
- **Docstring/behavior mismatch fixed:** `extract_entities_and_relationships`'s docstring claimed callers "never see the underlying httpx/json exception directly," but a 4xx OpenRouter response raised a raw `httpx.HTTPStatusError`, unwrapped. Now wrapped in `ExtractionError` like every other failure path (`test_extract_a_4xx_response_is_not_retried` updated accordingly). Functionally harmless before this fix (`ingest_document`'s outer `except Exception` catches everything regardless) — fixed for the abstraction's own consistency, not because of an observed failure.
- **Investigated, not a bug:** the edge-case-hunter pass flagged a document with zero parsed chunks reaching the Graphing step with empty extraction text. Confirmed by reading `documents/parsing.py`: `parse_document` already raises `UnparseableDocument` (caught by `ingest_document`'s existing outer `except`, routing to `Failed` before Graphing is ever reached) whenever parsing yields zero chunks — AC1 of Story 2.3 requires "one or more passages". `chunks` is therefore guaranteed non-empty by the time the Graphing step runs; no code change needed.
- **Accepted, not fixed:** AD-4's exact-match/near-match `MERGE` tests (`test_neo4j_client.py`) verify the Cypher/params sent to a fake transaction recorder, not execution against a real Neo4j engine — there is no Neo4j service in this project's test setup. Logged in `deferred-work.md` rather than fixed here; the new uniqueness constraint above is a partial, database-level mitigation for the same underlying guarantee, not a replacement for an integration test.
- **KEEP:** everything from the first Spec Change Log entry above, and every already-approved boundary before it.

## Code Map

- `backend/app/shared/models.py` -- edit: `Document.chapter_breakdown` — nullable `sa.JSON` column
- `backend/alembic/versions/` -- new: migration adding `chapter_breakdown` to `documents`
- `backend/app/documents/schemas.py` -- edit: `DocumentResponse.chapter_breakdown: dict[str, int] | None`
- `backend/app/shared/llm_client/__init__.py` -- edit: first real implementation — `extract_entities_and_relationships(text) -> ExtractionResult`, OpenRouter call + retry + JSON parse/validate
- `backend/app/shared/data_access/neo4j_client.py` -- new: mirrors `weaviate_client.py` — driver singleton, `close_neo4j_driver()`, `write_entities_and_relationships(...)`
- `backend/app/shared/data_access/shapes.py` -- read-only reference: `Neo4jEntity`/`Neo4jRelationship` shape this story finally writes for real
- `backend/app/documents/service.py` -- edit: `ingest_document` extends past the Weaviate write — `Graphing` status, extraction call, Neo4j write, computes `chapter_breakdown` from `chunks`, `Ready`/`Failed`
- `backend/app/main.py` -- edit: `close_neo4j_driver()` added to `lifespan`, alongside the existing `close_weaviate_client()`
- `frontend/src/pages/DocumentDetailPage.jsx` -- edit: render real Chapters/Passages-indexed/chapter-breakdown values when `status === 'Ready'` and `chapter_breakdown` is present; unchanged "Pending" path for every other status
- `backend/tests/test_entity_extraction.py` -- new: type-set validation/dropping, empty-result handling
- `backend/tests/test_neo4j_client.py` -- new: mirrors `test_weaviate_client.py`'s shape — write, merge-on-exact-match, near-match stays distinct
- `backend/tests/test_documents_ingest_graphing.py` -- new: full `Extracting → Graphing → Ready` path (asserts `chapter_breakdown` populated), and both failure branches' rollback (asserts it stays `None`)
- `frontend/src/pages/DocumentDetailPage.test.jsx` -- edit: Ready-state case rendering real chapter/passage values

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/models.py` + new Alembic migration -- `chapter_breakdown` JSON column on `documents`
- [x] `backend/app/documents/schemas.py` -- `DocumentResponse.chapter_breakdown`
- [x] `backend/app/shared/llm_client/__init__.py` -- OpenRouter extraction call, retry, type-set validation -- AD-6, first real implementation
- [x] `backend/app/shared/data_access/neo4j_client.py` -- driver singleton + `write_entities_and_relationships` -- AD-2, mirrors `weaviate_client.py`; also `ensure_ready()` (review addition, see Spec Change Log) creating the `(name, type, user_id)` uniqueness constraint
- [x] `backend/app/main.py` -- wire `close_neo4j_driver()` and `ensure_ready()` into `lifespan` -- symmetric with the Weaviate client's lifecycle
- [x] `backend/app/documents/service.py` -- extend `ingest_document` with the Graphing step, its rollback branch, and `chapter_breakdown` computation on the `Ready` commit -- the story's core AC
- [x] `frontend/src/pages/DocumentDetailPage.jsx` -- Ready-state branch replacing "Pending" with real values
- [x] `backend/tests/test_entity_extraction.py` -- out-of-vocabulary dropping, empty result -- pins the closed-type-set guarantee
- [x] `backend/tests/test_neo4j_client.py` -- exact-match merge vs. near-match distinct, plus an ambiguous same-name-different-type case (review addition) -- pins AD-4
- [x] `backend/tests/test_documents_ingest_graphing.py` -- happy path + both failure branches, plus a reading-order-not-sorted case (review addition) -- pins AD-1's rollback for the Graphing step and `chapter_breakdown`'s all-or-nothing behavior and ordering
- [x] `frontend/src/pages/DocumentDetailPage.test.jsx` -- Ready-state rendering

**Acceptance Criteria:**
- Given a document whose Weaviate write already succeeded, when extraction runs, then every OpenRouter call goes through `shared/llm_client/` and `documents` never imports an OpenRouter SDK directly.
- Given extraction identifies entities/relationships, when they're written, then only OD-1's closed type set is ever persisted to Neo4j.
- Given two documents mention the same-named, same-typed entity, when both are ingested, then the graph holds one node, not two; a near-match name stays a distinct node.
- Given the Graphing step fails for any reason, when the failure is handled, then this document's Weaviate passages are deleted, it's marked `Failed`, and `chapter_breakdown` stays `None` — no orphaned partial state.
- Given a document in `Extracting` or `Graphing`, when a retry is attempted, then it's refused.
- Given a document reaches `Ready`, when Document Detail loads, then Chapters, Passages indexed, and the chapter breakdown list show real values, not "Pending".

## Design Notes

Extraction prompt asks for strict JSON: `{"entities": [{"name", "type"}], "relationships": [{"source", "target", "type"}]}`. A malformed response is a retryable failure (same 2-attempt budget as a transport error), not a crash.

Character budget for the concatenated chapter text: 12,000 chars (~3k tokens) — a conservative fit under free-tier context limits alongside the prompt itself. Not benchmarked against a real long document; flagged in `deferred-work.md` with the truncation caveat.

Cypher shape (illustrative): `MERGE (e:Entity {name: $name, type: $type, user_id: $user_id})`, relationships merged the same way between two entity refs, typed by `$relationship_type`.

`chapter_breakdown` is built with `collections.Counter` over `chunk.chapter for chunk in chunks` (already parsed for the Weaviate write, no re-parsing) — insertion order of first appearance is preserved into the JSON column and the API response, so the frontend list matches document reading order with no server-side sort.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the three new test files
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including the updated Detail test

**Manual checks (if no CLI):**
- With real `OPENROUTER_API_KEY`/`NEO4J_*` env vars set, upload a document and confirm it reaches `Ready`, that its entities appear as nodes in the Neo4j Aura console, and that Document Detail shows real Chapters/Passages-indexed numbers and a chapter breakdown list instead of "Pending".
