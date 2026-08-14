---
title: 'Story 2.8: Prune orphaned graph entities when a document is deleted'
type: 'feature'
created: '2026-08-14'
status: 'ready-for-dev'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.7 shipped "delete a document" with graph entities/relationships deliberately left untouched (FR-8's original boundary). Confirmed live against the running app: `hr_handbook.md` was deleted (gone from Postgres and Weaviate), but its entities (`Employees`, `Manager`, `Paid vacation`, `Remote`, `Calendar year`) remain in Neo4j under the same `user_id`, and the `Entity` node schema carries only `(name, type, user_id)` — no document reference at all, so no query could ever have attributed or cleaned them up. Human decision: reverse this boundary (resolves OD-4).

**Approach:** Add `source_document_ids` (a list property) to every `Entity` node and every typed relationship, appended on each `MERGE` during ingestion (Story 2.4's write path). On document delete, remove that document's id from every node/relationship it contributed to; delete the node/relationship itself only once the list is empty — reference-counted, so an entity shared across documents survives as long as any contributor does. Because no existing graph data carries this attribution, ship with a one-time operational rebuild: clear Neo4j, re-extract every current `Ready` document.

## Boundaries & Constraints

**Always:**
- `write_entities_and_relationships` (`neo4j_client.py`) gains a required `document_id: str` parameter. Every `MERGE` sets `source_document_ids` via `coalesce(existing, []) + document_id` when not already present — idempotent against a document re-ingested twice (Story 2.6's reingest-on-Failed path already makes this a real scenario, not hypothetical).
- Relationships carry their own `source_document_ids`, independent of their endpoint entities' lists — a relationship and its two entities can, in principle, be pruned by different documents at different times; each list is authoritative only for itself.
- Prune order inside one transaction: relationships first (remove this document's id from any relationship's list; delete the relationship if now empty), then entities (same, then `DETACH DELETE` any entity now empty). Relationships are written only when both their named entities were present in the same extraction call (Story 2.4's existing resolution rule) — so an entity's and its relationships' `source_document_ids` for a given document are always added together, keeping the two prune passes consistent with each other by construction.
- New `prune_document_from_graph(document_id: str, user_id: str) -> None` in `neo4j_client.py` — the only new Neo4j entry point this story adds, called from `documents/service.py::delete_document` (Story 2.7) after the existing Weaviate-passage delete, before the Postgres row delete. Delete order stays Weaviate → Neo4j → Postgres row: each step commits to something only after the previous one succeeded, so a mid-failure never leaves a document row pointing at partially-cleaned stores.
- A no-op (never touches the driver) when neither list changes anything — mirrors `write_entities_and_relationships`'s existing empty-call short-circuit.
- The inline delete-confirm copy (`DocumentCard.jsx`, `DocumentDetailPage.jsx`, Story 2.7) changes from unconditionally claiming entities "remain and may still influence future answers" to stating plainly that entities/relationships unique to this document are removed, and only ones shared with another document survive.
- One-time rebuild: a standalone script (not part of app startup or any request path) that wipes all `Entity` nodes/relationships in Neo4j, then re-runs extraction (`extract_entities_and_relationships`) and the new provenance-aware write for every document currently at `status = "Ready"`. Destructive — requires an explicit confirmation flag to run, never runs implicitly.

**Ask First:** Running the rebuild script against the real Aura database is destructive (wipes graph data for every user) — HALT and get explicit human go-ahead before executing it for real, same as Story 2.6's real-database migration required.

**Never:**
- No change to `AD-4`'s exact-match merge identity — `(name, type, user_id)` stays the merge key; this story only adds provenance metadata alongside it, never changes what counts as "the same entity."
- No automatic/scheduled re-running of the rebuild — one-time, human-triggered, not a startup step or background job.
- No change to Weaviate or Postgres delete behavior (Story 2.7's existing order/logic there is untouched) — this story only inserts the new Neo4j prune step into that existing sequence.
- No soft "orphan" flag on graph nodes as an alternative to real deletion — the whole point is that dead information stops being queryable/visible, not marked-but-kept.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Entity unique to one document | Document deleted | Entity's `source_document_ids` becomes empty; node is deleted | N/A |
| Entity shared by two documents | One of the two deleted | Entity survives with the other document's id still in its list | N/A |
| Relationship shared by two documents | One deleted | Relationship survives; the other document's id remains in its list | N/A |
| Document re-ingested via Story 2.6's Failed-reingest path | Same document id writes twice | `source_document_ids` never gets a duplicate entry (idempotent append) | N/A |
| Document whose extraction produced zero entities | Delete | Prune step is a no-op, same as the empty-write short-circuit | N/A |
| Pre-rebuild legacy entity (no `source_document_ids` at all) | Any document deleted before the rebuild runs | `coalesce(..., [])` treats it as already-empty; never matched, never touched | N/A |
| Rebuild script run twice | Second run | Idempotent — wipes again, re-extracts the same current `Ready` documents, same end state (modulo any LLM non-determinism in extracted entities, an accepted characteristic of extraction itself, not new to this story) | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/shared/data_access/neo4j_client.py` -- edit: `write_entities_and_relationships` gains `document_id: str`; `_write_entities_and_relationships_tx`'s Cypher sets `source_document_ids` on both entity and relationship `MERGE`s; new `prune_document_from_graph(document_id, user_id)` + its transaction function
- `backend/app/documents/service.py` -- edit: `ingest_document`'s existing `write_entities_and_relationships(...)` call passes `document_id_str`; `delete_document` (Story 2.7) calls `prune_document_from_graph` after the Weaviate delete, before the Postgres row delete
- `frontend/src/components/DocumentCard.jsx`, `frontend/src/pages/DocumentDetailPage.jsx` -- edit: `DELETE_BOUNDARY_TEXT` (shared constant, Story 2.7) updated to the new wording
- `backend/scripts/rebuild_graph_with_provenance.py` -- new: one-time, human-triggered, requires an explicit `--yes` flag; wipes all `Entity` nodes/relationships, re-extracts + re-writes every `Ready` document with provenance
- `backend/tests/test_neo4j_client.py` -- edit: `write_entities_and_relationships` tests updated for the new required `document_id` param and `source_document_ids` assertions; new tests for `prune_document_from_graph` (unique-entity deleted, shared-entity survives, shared-relationship survives, idempotent double-prune, empty no-op)
- `backend/tests/test_documents_delete.py` -- edit: delete test(s) extended to assert the graph prune is invoked with the right `(document_id, user_id)`, and that a shared entity (fixture: two documents contributing the same entity) survives a single delete
- `backend/tests/test_documents_ingest_graphing.py` -- edit: existing ingestion tests updated for `write_entities_and_relationships`'s new required parameter
- `frontend/src/pages/DocumentDetailPage.test.jsx`, `frontend/src/components/DocumentCard.test.jsx` -- edit: confirm-box text assertions updated to the new copy

## Tasks & Acceptance

**Execution:**
- [ ] `neo4j_client.py` -- `document_id` param on `write_entities_and_relationships`, `source_document_ids` set on entity + relationship `MERGE` -- the story's write-side foundation
- [ ] `neo4j_client.py` -- `prune_document_from_graph(document_id, user_id)`, relationships-then-entities, reference-counted delete
- [ ] `documents/service.py` -- wire both: pass `document_id` on ingest, call prune on delete (after Weaviate, before the Postgres row)
- [ ] `DocumentCard.jsx` / `DocumentDetailPage.jsx` -- confirm-box copy update
- [ ] `backend/scripts/rebuild_graph_with_provenance.py` -- the one-time rebuild, gated behind an explicit confirmation flag
- [ ] `backend/tests/test_neo4j_client.py` -- write-path provenance assertions + full prune coverage
- [ ] `backend/tests/test_documents_delete.py` -- prune-is-called + shared-entity-survives coverage
- [ ] `backend/tests/test_documents_ingest_graphing.py` -- updated call-signature coverage
- [ ] Frontend confirm-box copy tests updated

**Acceptance Criteria:**
- Given an entity/relationship only one document ever contributed, when that document is deleted, then it is removed from the graph.
- Given an entity/relationship multiple documents contributed, when only one of those documents is deleted, then it remains.
- Given ingestion writes entities/relationships, when the write happens, then the contributing document's id is recorded on each.
- Given the graph has no attribution today, when the one-time rebuild runs, then every current `Ready` document's entities/relationships are rebuilt with provenance, and nothing already-orphaned survives untracked.
- Given the delete confirm box, when it renders, then its wording reflects reference-counted pruning, not an unconditional "entities remain."
- Given any Neo4j access this story adds, when it runs, then it goes through `neo4j_client.py` (AD-2) — no raw Cypher anywhere else.

## Design Notes

Cypher shape for the entity `MERGE` (illustrative): `MERGE (e:Entity {name: $name, type: $type, user_id: $user_id}) SET e.source_document_ids = CASE WHEN $document_id IN coalesce(e.source_document_ids, []) THEN coalesce(e.source_document_ids, []) ELSE coalesce(e.source_document_ids, []) + $document_id END`. Same shape for relationships, `SET` on `r` instead of `e`.

Prune shape (illustrative, relationships pass): `MATCH (:Entity {user_id: $user_id})-[r]->(:Entity {user_id: $user_id}) WHERE $document_id IN coalesce(r.source_document_ids, []) SET r.source_document_ids = [id IN r.source_document_ids WHERE id <> $document_id] WITH r WHERE size(r.source_document_ids) = 0 DELETE r` — then the same pattern for `Entity` nodes with `DETACH DELETE`. No relationship-type filter needed on the `MATCH` since the update targets the property, not the type.

The rebuild script re-runs real extraction (`extract_entities_and_relationships`) — one LLM call per current `Ready` document. Confirmed cheap at today's real data volume (3 `Ready` documents in the live system at the time this spec was written), consistent with the human's explicit choice of this approach over a per-document-diff alternative.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including new prune/provenance tests
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including updated confirm-box copy tests

**Manual checks (if no CLI):**
- Do NOT run `rebuild_graph_with_provenance.py` against the real Aura database without asking first (Ask First, above). Once approved: run it, confirm entity/relationship counts before/after are sane, then delete a document with a unique entity and confirm it disappears from a direct Neo4j query, while an entity shared with a surviving document does not.
