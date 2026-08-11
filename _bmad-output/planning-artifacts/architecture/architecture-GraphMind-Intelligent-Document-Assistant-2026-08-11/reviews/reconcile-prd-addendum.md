# Reconciliation Review: PRD + Addendum → Architecture Spine

**Scope:** GraphMind v1. Compares `prd.md` and `addendum.md` against `ARCHITECTURE-SPINE.md` for dropped, contradicted, or silently changed architecturally-relevant decisions.

## Method

Checked each of: feature module boundaries, request flows, security note, rejected hexagonal alternative, risk register items, stack choices, FR-4 status vocabulary, FR-5 identity resolution, FR-10 refusal threshold behavior — plus adjacent items surfaced while cross-referencing (FR-16 data removal, graph viz library, entity type list tension).

## Correctly Represented / Inherited

- **Feature module boundaries** — `auth`, `documents`, `chat`, `kg` map cleanly to PRD §4.1–4.5; eval (FR-13) correctly modeled as a standalone script per addendum; Settings (FR-15/16) correctly split across `auth` (account deletion) and frontend `context/` (theme), matching addendum's cross-cutting placement.
- **Request flows** — Ingestion, Q&A, and graph-viz flows in the spine match the addendum's flow descriptions. The addendum's unresolved Weaviate/Neo4j desync risk ("direction identified... not yet a committed design") is *resolved* by AD-1's saga-lite rollback — correct, forward progress, not a contradiction.
- **Rejected hexagonal alternative** — reproduced near-verbatim in the Design Paradigm section, same rationale (fixed stack, fixed end date, indirection cost).
- **FR-4 status vocabulary** — AD-1 uses the exact `Uploaded → Extracting → Graphing → Ready | Failed` vocabulary from FR-4, no drift.
- **FR-5 identity resolution** — PRD left this an open ASSUMPTION ("exact-match, fuzzy-match, or LLM-assisted... left to architecture"). Spine's AD-4 resolves it decisively (exact-match only, with a concrete example). This is architecture doing its job, not a gap.
- **FR-10 refusal short-circuit mechanism** — AD-6 correctly places the short-circuit before the LLM wrapper is reached; structural seed's `chat/service.py` comment echoes FR-10 directly.
- **Stack choices** — core stack (FastAPI, Weaviate, Neo4j AuraDB, Neon, OpenRouter, React/Vite/Tailwind, JWT+bcrypt) matches addendum's table, with versions added. Weaviate sandbox 14-day auto-expiry is new information the spine adds (verified via research) and correctly flagged under Deferred — a genuine improvement, not a contradiction.
- **FR-8 delete/graph-persistence tension** — PRD's open question (§8 item 3) is explicitly and correctly left unresolved in the spine's Deferred section as a "product/PM-level" question, not silently dropped.
- **Entity/relationship type list (FR-5)** — correctly carried forward into Deferred as a genuine open item, matching PRD §8 item 1.

## Gaps Found

1. **FR-16 account-deletion data-removal completeness — dropped, not deferred.** PRD explicitly flags this as `[ASSUMPTION: ... left to architecture]` (§4.7 FR-16) — i.e., architecture was asked to decide how account deletion cascades across Postgres, Weaviate, and Neo4j. The spine gives account deletion no AD (no equivalent of AD-1's rollback/compensating-action pattern for the deletion path) and does not list it in the Deferred section either, unlike the entity-type-list and SM-1/FR-8 items that *were* properly carried into Deferred. This is the clearest silent drop: the PRD asked architecture to own a decision, and the spine neither makes the decision nor acknowledges it's still open.

2. **Post-MVP server-side Cypher injection note — dropped from spine entirely.** Both PRD (§4.1 FR-2 consequence: "Where natural-language graph querying exists post-MVP, the `user_id` constraint is injected server-side... never trusted from LLM output") and the addendum's dedicated Security Note repeat this guidance twice, signaling it's considered important enough to state outside the general AD-2 tenancy rule. The spine's AD-2 covers current-state tenancy enforcement but never mentions this forward-looking constraint, and it isn't listed in Deferred alongside the other genuinely-open items (NL graph querying itself *is* correctly listed as post-MVP backlog in the addendum, but the specific security constraint on its future implementation isn't echoed anywhere in the spine). Low urgency since NL querying is out of scope for v1, but PRD/addendum treated this as a load-bearing security guardrail worth stating twice, and the spine states it zero times.

3. **Graph visualization library unspecified in spine.** Addendum's stack table names `react-force-graph / vis-network` for FR-12's node-link rendering. The spine's Stack table and Structural Seed (`frontend/src/pages/` — "Graph" view) omit any library choice — the only stack row silently absent from an otherwise complete table. Minor, but it's the one addendum-stack decision that didn't make it across.

4. **FR-10 relevance threshold value is unaddressed and unacknowledged.** PRD FR-10 requires a "defined relevance threshold" below which the system refuses. AD-6/structural-seed correctly capture *where* the check happens (before the LLM call) but never state what the threshold is, how it's computed (e.g., cosine-similarity cutoff, top-k score floor), or where it's configured — and unlike the entity-type-list and SM-1 numeric-target open items, this isn't listed in the Deferred section either. It's an open decision that fell through without being flagged as open.

5. **Minor tension: entity-type-list "already constrained" vs. "genuinely unresolved."** The addendum's risk register states the mitigation for imprecise/slow extraction is "extraction scope constrained to a small fixed entity-type set" (present tense, implying it's already decided), while the PRD (§8) and the spine's own Deferred section both treat the actual type list as still open. Not a hard contradiction — the *fact* that scope will be constrained is decided, only the *contents* of the list are open — but the addendum's phrasing reads as more settled than the spine treats it, worth a one-line clarification if either doc is revised.

## Summary Table

| Item | Status |
|---|---|
| Feature module boundaries | Represented |
| Request flows | Represented (desync risk resolved forward via AD-1) |
| Security note (current-state tenancy) | Represented (AD-2) |
| Security note (post-MVP Cypher injection) | **Dropped** |
| Rejected hexagonal alternative | Represented |
| Risk register (desync, dedupe-cost, sandbox expiry) | Represented / resolved |
| Stack choices | Represented, except graph-viz library |
| FR-4 status vocabulary | Represented exactly |
| FR-5 identity resolution | Resolved (AD-4) |
| FR-5 entity type list | Correctly deferred |
| FR-10 short-circuit mechanism | Represented (AD-6) |
| FR-10 threshold value | **Unaddressed, not flagged as open** |
| FR-16 data-removal completeness | **Dropped (not resolved, not deferred)** |
