---
id: SPEC-GraphMind
companions:
  - glossary.md
  - ../../planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/EXPERIENCE.md
  - ../../planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md
sources:
  - ../../planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md
  - ../../planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/addendum.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# GraphMind

## Why

Information relevant to a question is typically scattered across many documents, and when an AI assistant answers, users can't verify the claim, so they don't trust it. GraphMind treats citation and honest refusal as the product's core promise: a user should never need to open the source document themselves to trust an answer. Two retrieval strategies work together toward that — vector search over passages for semantic questions, and a per-user knowledge graph for relational questions that require traversing connections rather than matching text. This is a portfolio project for a two-person team, built in a fixed 20-day window as a course deliverable, with the explicit intent to keep evolving it afterward.

## Capabilities

- **CAP-1 Authentication & Tenancy Isolation**
  - **intent:** A visitor can create an account and log in; every subsequent read/write to the vector index and knowledge graph is filtered by `user_id` server-side, independent of any client-supplied value.
  - **success:** Passwords are stored hashed (bcrypt_sha256); a valid session is a JWT sent with every request. Two test accounts cannot retrieve each other's documents, citations, or graph data through any endpoint.

- **CAP-2 Document Ingestion**
  - **intent:** A user uploads a PDF, Markdown, or HTML file (via file picker or drag-and-drop, with independent per-file progress); the system parses it into metadata-tagged passages, embeds them, and in parallel extracts entities/relationships merged into the user's single unified knowledge graph. The user can see each document's ingestion state, and unchanged content is not reprocessed.
  - **success:** Unsupported formats are rejected before processing starts. Each document shows one of Uploaded/Extracting/Graphing/Ready/Failed, with Failed carrying a human-readable reason and not silently dropping from the list. Re-uploading a byte-identical file (by content hash) does not re-run extraction, embedding, or LLM calls. Newly extracted entities that match existing graph entities merge rather than duplicate.

- **CAP-3 Document Library**
  - **intent:** A user can list, inspect, and delete their own documents.
  - **success:** The document list shows every document owned by the authenticated user and none owned by any other user; opening one shows ingestion status, upload date, and chapter breakdown. Deleting a document removes it and its passages/embeddings from the vector index immediately; knowledge-graph entities derived from it are not retroactively pruned, and the UI states that boundary plainly at delete time.

- **CAP-4 Grounded Chat Q&A**
  - **intent:** A user asks a question in plain language; the system retrieves relevant passages and/or traverses the knowledge graph and answers only from that evidence with citations, or explicitly refuses when evidence is inadequate. The user can scope a question to all of their documents or a chosen subset.
  - **success:** Every claim-bearing sentence in an answer is traceable to at least one citation naming a specific document + passage. Below a defined relevance threshold, the system short-circuits before the generation call and returns an explicit refusal rather than a guess. Passages outside the selected document scope never appear as citations; default scope is all of the user's documents.

- **CAP-5 Knowledge Graph View**
  - **intent:** A user can visually explore their own unified knowledge graph as an interactive node-link diagram.
  - **success:** The view renders entities and relationships as a node-link diagram scoped to the authenticated user's `user_id`; no other user's graph data is queryable or renderable from this view.

- **CAP-6 Evaluation Harness**
  - **intent:** Answer quality is measured objectively via a fixed evaluation set spanning single-source factual, cross-document synthesis, and unanswerable (expected refusal) questions, runnable with a single command.
  - **success:** The harness invokes the service layer directly (not through the UI) and reports accuracy on answerable questions and refusal-rate on unanswerable ones as numeric output, not just pass/fail. The evaluation set contains 15–20 question/expected-answer pairs, authored incrementally as ingestion becomes functional.

- **CAP-7 Account & Appearance Settings**
  - **intent:** A user can switch between light and dark appearance as a manually chosen, persisted preference, and can permanently delete their own account.
  - **success:** The chosen theme persists across sessions and every screen, including auth pages, renders correctly in both themes. Account deletion requires an explicit confirmation step; on confirm, the user's documents, vector index entries, knowledge-graph data, and account record are removed and the user is logged out.

## Constraints

- Per-user tenancy isolation is a launch blocker, not a bug to triage later: any cross-tenant leak stops release. Enforced server-side at the query layer on both Weaviate and Neo4j, never only in the UI.
- Hybrid retrieval — Weaviate vector index plus a per-user unified Neo4j knowledge graph — is non-negotiable: vector search handles semantic questions, graph traversal handles relational ones, and neither alone satisfies the trust bet.
- All managed services must run on free tiers (Weaviate Cloud, Neo4j AuraDB, OpenRouter, Neon Postgres, Vercel Hobby, Render free web service) so the project is reproducible by any reviewer at zero cost; ingestion content-hash dedupe exists specifically to protect this.
- Fixed 20-day delivery window with a 2-developer team drives KISS/YAGNI throughout: feature-based modular monolith over layered/hexagonal architecture, minimal auth schema (no password reset/email verification), no staging environment, exact-match-only entity resolution, React Context over Redux.
- The refusal behavior (CAP-4) is a required safety guardrail against fabricated claims presented as fact, not an optional nicety — it must short-circuit before any generation call.

## Non-goals

- No cross-tenant collaboration, sharing, or team workspaces — each account's documents are visible only to that account.
- No proactive/unprompted insights (e.g. contradiction detection across a user's documents), no correction-feedback loop that improves extraction over time, and no user-editable correction of extracted entities/relationships.
- No reference-counted/provenance-aware graph deletion — deleting a document clears its vector passages but does not retroactively prune graph entities derived from it.
- No answer confidence badge/score display — explicitly rejected during scoping.
- No chapter-level filtering in Chat — scoping is document-level only; chapters remain metadata visible in Document Detail.
- No query history (question + answer + scope + citation snapshot) — deferred to v2.
- Not a general-purpose chatbot — GraphMind never answers from the LLM's general knowledge when the corpus doesn't support an answer; this is the core differentiator.
- No clickable citations that jump to source, no conversational memory/follow-ups, no suggested follow-ups, no document search/filtering, no project/category grouping beyond chapters, no hybrid BM25+vector search, no raw-context inspection panel, no conversation export, no account-deletion recovery/undo window, no live entity/relationship preview post-ingestion, no natural-language querying over the graph.

## Success signal

The system passes the course Definition of Done: every in-scope capability functions end-to-end and is demonstrable; every chat answer shows at least one concrete source reference; a user cannot retrieve another user's documents (verified with two test accounts, zero cross-tenant leakage); the evaluation harness runs with a single command and reports a numeric accuracy figure. Concretely: answerable-question accuracy on the evaluation set reaches ≥80%; the system refuses 100% of genuinely unanswerable evaluation questions without fabricating; and refusal rate on answerable questions does not rise as a side effect of chasing refusal correctness (over-refusing is as much a failure as fabricating).

## Assumptions

- Numeric accuracy target for SM-1 (≥80%) is a placeholder pending a real evaluation-set baseline.
- No password reset or email verification in v1, to protect the 20-day timeline.

## Open Questions

- Exact entity/relationship type list for extraction (FR-5) is unresolved — flagged to architecture, still open.
- Whether the delete/graph-persistence tension (CAP-3) needs a stronger v1 mitigation (e.g. a more prominent warning) or is acceptable as-is for a portfolio-stage product.
- UX open gaps: the refusal chat-bubble's visual/behavioral design, the Failed-ingestion-state placement, and the empty-document-library state have no mocks and need a dedicated design pass before implementation.
