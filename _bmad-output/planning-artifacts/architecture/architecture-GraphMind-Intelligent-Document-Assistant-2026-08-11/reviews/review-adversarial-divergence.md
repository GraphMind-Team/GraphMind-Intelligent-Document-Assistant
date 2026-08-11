---
name: review-adversarial-divergence
type: architecture-review
target: architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md
method: adversarial two-developer divergence construction
created: '2026-08-11'
---

# Adversarial Divergence Review — GraphMind Architecture Spine

## Method

Constructed two independently-built units one level below the spine — the `documents` module (Developer A) and the `chat` module (Developer B) — each written to obey every AD literally, with no direct coordination beyond what the spine text pins down. Looked for shared-data shape clashes, dual ownership of one entity/row, conflicting mutation paths, and boundaries loose enough for two compliant-but-different implementations.

## Verdict

**FAIL — the spine is under-specified at exactly its three riskiest seams (AD-1, AD-2, AD-6).** It correctly forces both developers through shared modules (DAL, LLM client), which prevents the *obvious* failure (raw queries bypassing tenancy). But "goes through a shared function" is not the same guarantee as "agrees on what that function returns," "agrees on write order," or "agrees on failure semantics" — and the spine pins none of the latter. Five concrete divergences were constructed below that satisfy every AD as literally written yet produce incompatible or racy systems.

## Divergence Scenarios

### 1. DAL chunk-shape mismatch (AD-2) — HIGH
Spine gives only one example DAL signature (`get_documents(user_id, ...)`) and never pins the shape of a retrieved chunk record. Dev A (`documents`) writes ingestion chunks with `chapter`/`chunk_index` nested inside a `metadata` dict Weaviate property; Dev B (`chat`) independently writes `search_chunks(user_id, query_embedding, top_k)` assuming flat top-level `chapter`/`chunk_index` fields per the Consistency Conventions table. Both go exclusively through `shared/data_access/`, both filter by `user_id` — AD-2 is fully satisfied — yet citations break at runtime because no schema contract exists between the writer and reader of the same Weaviate object.

### 2. Duplicate refusal paths (AD-6 / FR-10) — HIGH
AD-6 places the refusal short-circuit "before the generation call reaches" `shared/llm_client/`, i.e. outside the wrapper. Nothing stops the wrapper's own retry/timeout-failure handling (built by whoever owns `shared/`) from also synthesizing a "couldn't answer" fallback message inside a 200 response when OpenRouter calls exhaust retries. Now two independently justifiable refusal paths exist — chat/service.py's threshold-based refusal (FR-10, likely a defined response shape) and the LLM wrapper's own failure-fallback (undefined shape, AD-3 only governs `HTTPException` error paths, not in-band success-envelope fallbacks) — with different wording/detection contracts for the frontend to distinguish.

### 3. Ingestion write-order and concurrency gap (AD-1) — MEDIUM-HIGH
AD-1 says the handler "deletes whatever the first write already committed" but never states whether Weaviate or Neo4j is written first, and AD-2's DAL contract says nothing about locking. Two equally-compliant orderings (Weaviate-then-Neo4j vs. Neo4j-then-Weaviate) are both valid readings of the rule, so a rollback implementation built against one order is silently wrong if a re-upload/retry races a concurrent rollback delete of the same `document_id` — no invariant serializes ingestion attempts per document.

### 4. Neo4j node/property contract undefined between writer and reader (AD-2/AD-4) — MEDIUM
AD-4 pins merge semantics (exact string match) but not node labels or property keys. `documents/service.py` could persist entities as `(:Entity {name, user_id, document_id})`; `kg/service.py`'s Cypher construction (built independently, per the Capability Map's "governed by AD-2" only) could assume typed labels (`:Person`, `:Organization`) or a `label` property instead. Both comply with AD-2 (DAL-only access) and AD-4 (exact-match merge), yet the graph-visualization endpoint returns empty or malformed graphs against real ingested data.

### 5. Two mutators of the document status ledger (AD-1 / AD-2 / FR-16) — MEDIUM
AD-1 implicitly assigns the `documents` status ledger to the `documents` module, but AD-2 requires *all* modules to reach Postgres only via the shared DAL — which means nothing in the spine prevents `auth`'s account-deletion flow (FR-16) from calling a DAL function that deletes/mutates document rows directly, independent of and uncoordinated with the ingestion state machine (`Uploaded → Extracting → Graphing → Ready|Failed`). A deletion mid-`Extracting` races the ingestion handler's own status writes with no ownership rule resolving the conflict.

## File Path

`c:\Users\yoana\Sirma Academy\GraphMind-Intelligent-Document-Assistant\_bmad-output\planning-artifacts\architecture\architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11\reviews\review-adversarial-divergence.md`
