# PRD Quality Review — GraphMind

## Overall verdict
This is a tight, honest PRD for its stakes: a 20-day, 2-dev portfolio project with a fixed stack. Trade-offs are named rather than hidden (graph-not-pruned on delete, no password reset, 80% target as placeholder), and the addendum split keeps the PRD itself lean without losing implementation traceability. The main risks are thin Done-ness bounds on a few "graceful"-flavored FRs, a Success Metrics set that leans heavily on one evaluation harness with no coverage of the "unified graph merges correctly across documents" claim, and light scope-honesty gaps in UJ-1's climax claim ("something a single-document search couldn't produce") that the FRs don't actually test.

## Decision-readiness — adequate
Real decisions are stated as decisions: graph entities are not pruned on document delete (§4.3, FR-8), password reset/email verification is cut (FR-1), the confidence badge is explicitly rejected rather than deferred-by-omission (§6.2). The `[NOTE FOR PM]` at FR-8 sits at a genuine tension (deleted-but-still-influential graph traces), not a safe checkpoint, and is escalated into Open Question 3 — a good closed loop. Open Question 1 (entity/relationship type list) and Open Question 2 (numeric SM-1 target) are genuinely open, not rhetorical.

### Findings
- **medium** Stack/architecture decisions are entirely pre-made and unexamined (addendum "Technology Stack") — Weaviate, Neo4j AuraDB, OpenRouter, FastAPI are stated as "confirmed" with one-line rationale each, but no trade-off given up is named (e.g., why Weaviate over a simpler pgvector-on-Neon setup given Postgres is already in the stack for auth). For a course brief this may be a fixed constraint, but the PRD doesn't say whether it was ever negotiable — worth one sentence confirming the stack is externally fixed by the assignment, not a PM choice, so a reader doesn't mistake it for an unexamined decision. *Fix:* Add a one-line note in the addendum's Technology Stack intro: "Vector DB, graph DB, and LLM provider are fixed by the course brief; not open PM decisions."

## Substance over theater — strong
No persona theater (two UJs, both load-bearing, each maps directly to a feature cluster). No innovation theater — the "trust via citation + refusal" thesis is specific and is not restated as generic differentiation copy. NFRs in §10 have real numbers (p95 < 8s, 20MB cap) rather than "the system shall be performant." Vision statement (§1) is specific to this product's mechanism (vector + graph dual retrieval) rather than swappable boilerplate.

## Strategic coherence — strong
Clear thesis: citation + honest refusal is the product, not a feature. Feature prioritization follows from it — FR-9/FR-10 (grounded answer + refusal) sit at the center, and auth/tenancy (§4.1) is called out as "the single most safety-critical feature" rather than boilerplate. SM-1/SM-2 measure the thesis directly (accuracy + refusal correctness), and a counter-metric (SM-C1) is present to prevent over-refusal gaming — this is exactly the pattern the rubric asks for. MVP scope reads as a "problem-solving" shape (accuracy/refusal-first) and the scope logic matches.

### Findings
- **low** SM-3 (zero cross-tenant leakage) is filed as a "Secondary" metric even though §4.1 calls tenancy isolation "the single most safety-critical feature" and a "hard security requirement... launch blocker." The Success Metrics tier doesn't match the stated severity elsewhere in the PRD. *Fix:* Promote SM-3 to Primary, or add a sentence in §7 explaining why a launch-blocking requirement is filed as secondary (e.g., "secondary only in the sense that it's binary pass/fail, not a scored metric").

## Done-ness clarity — adequate
Most FRs have genuinely testable consequences (FR-1, FR-2, FR-6, FR-8, FR-9, FR-10, FR-12 are all concrete and verifiable). A few are thinner:

### Findings
- **medium** FR-7 (List and inspect documents) and FR-11 (Document scoping) and FR-13 (Graph visualization) have no "Consequences (testable)" subsection at all, unlike every other FR in the document — inconsistent with the rest of §4's rigor. FR-13 in particular only tests the negative case ("no other user's graph data is queryable") but never states what "renders correctly" means (e.g., does it need to handle graphs above some node count without failing?). *Fix:* Add at least one testable consequence per FR, even a minimal one (e.g., FR-11: "A question scoped to a chosen subset only retrieves passages from documents in that subset — verified by a query returning zero hits for content outside scope").
- **low** FR-5's extraction consequence ("Newly extracted entities that match existing graph entities... merge rather than duplicate") depends on an identity-resolution method that is never specified even loosely (exact string match? embedding similarity? LLM judgment?) — this is flagged as an assumption for the *type list* but not for the *merge/match* mechanism itself, which is arguably the harder unsolved problem. *Fix:* Add an `[ASSUMPTION]` tag noting the identity-resolution method is deferred to architecture, parallel to the existing type-list assumption.

## Scope honesty — strong
Non-Goals (§5) does real work and doesn't just restate MVP boundaries. `[ASSUMPTION]` tags are present and correctly roundtrip into §9's index (verified below). `[NOTE FOR PM]` appears at the one real deferred tension. De-scoping in §6.2 is explicit and even sourced (brainstorming MoSCoW references, "explicitly rejected during convergence"), which is unusually honest — most PRDs bury rejected ideas rather than naming why they were rejected. Open-items density (3 Open Questions, 4 Assumptions, 1 NOTE) is proportionate for a portfolio-stage PRD that isn't being green-lit to a large team.

## Downstream usability — adequate
This PRD does feed architecture and story creation (confirmed by the addendum's existence and its architecture section). Glossary (§3) is present and terms are used consistently in spot checks (Passage, Entity, Relationship, Citation, Refusal all recur correctly). FR IDs are contiguous (FR-1 through FR-14, no gaps). UJs each have a named protagonist (Elena, Marcus).

### Findings
- **low** SM and FR cross-references are present ("Validates FR-9, FR-10, FR-14") but UJs are never explicitly cross-referenced back to the FRs that realize them beyond a single "Realizes FR..." sentence per feature section — a downstream story-writer would need to manually map UJ-1's five sub-steps (upload, status, query, cite, edge-case refusal) to FR-3/FR-4/FR-9/FR-10 rather than finding it stated. *Fix:* Optional for this scope tier — a small UJ-to-FR table would help but is not load-bearing given the team is the same two people who wrote both documents.

## Shape fit — strong
This is a small-team technical-capability PRD wearing UJ clothing appropriately — two UJs are enough to be load-bearing without turning into persona theater, and the PRD correctly treats itself as "hobby/portfolio" tier: rigor is light where it should be (no elaborate persona matrix, no market sizing) and firm where it must be (tenancy isolation treated as launch-blocking, refusal behavior treated as a guardrail in §11). The PRD/addendum split itself is a good shape decision — keeps decision content in the PRD and implementation-how in the addendum, which is exactly what the rubric wants to see distinguished.

## Mechanical notes
- Glossary term "Knowledge Graph" is used consistently; "graph" alone is used informally in a few places (§4.3, §6.2) but always in contexts where the referent is unambiguous — not true drift.
- ID continuity: FR-1 through FR-14 contiguous, no gaps or duplicates. UJ-1/UJ-2 contiguous. SM-1/SM-2/SM-3/SM-C1 contiguous with a clearly-marked counter-metric category.
- Assumptions Index roundtrip: all four inline `[ASSUMPTION: ...]` tags (FR-1, FR-5, SM-1, and the cross-cutting NFRs note) are indexed in §9, and all four §9 entries have a matching inline tag. Clean roundtrip.
- One `[NOTE FOR PM]` (FR-8) is present and is escalated into Open Question 3 — good closed loop, no dangling notes.
- Required sections for this stakes tier (Vision, Target User, Glossary, Features/FRs, Non-Goals, MVP Scope, Success Metrics, Open Questions, Assumptions Index, Cross-Cutting NFRs, Constraints) are all present.
