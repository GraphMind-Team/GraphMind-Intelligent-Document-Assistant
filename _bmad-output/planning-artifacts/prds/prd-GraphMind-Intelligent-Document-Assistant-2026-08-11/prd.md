---
title: GraphMind
created: 2026-08-11
updated: 2026-08-11
status: final

---

# PRD: GraphMind
*Intelligent Document Q&A with Knowledge Graphs — working title, confirmed as final product name.*

## 0. Document Purpose

This PRD defines the v1 (MVP) scope for GraphMind, a document Q&A assistant combining vector retrieval and knowledge-graph traversal. It is written for the two-person build team (both PM and implementers) and for downstream architecture/UX work. It synthesizes two prior inputs: a brainstorming session that established the product's trust-first core insight and MoSCoW priorities, and the original course assignment brief (Project 15, AI & Data Track) that fixed the technology stack, delivery timeline, and Definition of Done. Implementation detail — stack rationale, architecture diagram, day-by-day delivery plan — lives in `addendum.md`, not duplicated here. 

## 1. Vision

GraphMind answers questions over a user's private document collection with grounded, cited answers — and explicitly declines to answer when the documents don't support a claim. It exists because information relevant to one question is typically scattered across many documents: people burn time hunting for it, and when an AI assistant does answer, they can't verify the claim, so they don't trust it. GraphMind treats citation and honest refusal as the product's core promise, not an optional nicety.

Under the hood, two retrieval strategies work together: vector search over document passages answers semantic questions ("what does the spec say about deployment"), while a lightweight per-user knowledge graph answers relational questions that require traversing connections rather than matching text ("which projects use React"). The north star that shapes every scope decision below: a user should never need to open the source document themselves to trust the answer.

This is a portfolio project for the author and their teammate, built in a fixed 20-day window as a course deliverable, with the explicit intent to keep evolving it afterward.

## 2. Target User

### 2.1 Jobs To Be Done

- As someone holding a private collection of documents (personal, team, or organizational), I want to ask questions in plain language and get an answer I can verify, so I don't have to read every document myself.
- As a user, I want confidence that an assistant won't make something up when it doesn't actually know — a wrong-but-confident answer is worse than no answer.
- As a user, I want my documents kept separate from everyone else's, without having to think about it.

### 2.2 Non-Users (v1)

- No cross-tenant sharing or collaboration — v1 has no concept of a shared workspace or team-visible documents. Each account's documents are visible only to that account.
- Not built for real-time/streaming data sources (feeds, live APIs) — only static uploaded documents (PDF, Markdown, HTML).
- Not a general-purpose chat assistant — GraphMind refuses to answer from anything other than the user's own ingested corpus (§4.4).

### 2.3 Key User Journeys

- **UJ-1. Elena uploads a batch of project docs and asks a relational question.**
  - **Persona + context:** Elena, a consultant onboarding onto an unfamiliar project, has a folder of specs, contracts, and meeting notes.
  - **Entry state:** authenticated, on the Documents page, no prior uploads.
  - **Path:** She uploads five PDFs and two Markdown files. Each shows an ingestion status (Uploaded → Extracting → Graphing → Ready) so she knows when they're queryable. Once ready, she switches to Chat and asks "which vendors are mentioned across these documents and what do they supply?"
  - **Climax:** The answer lists vendors with inline citations to the specific passages, synthesized via graph traversal across multiple documents — something a single-document search couldn't produce.
  - **Resolution:** She trusts the answer enough to act on it without opening the source PDFs, and continues asking follow-up questions.
  - **Edge case:** She asks about a vendor not mentioned anywhere in her corpus — GraphMind explicitly responds that it found no supporting evidence, rather than guessing from general knowledge.

- **UJ-2. Marcus deletes an outdated document.**
  - **Persona + context:** Marcus re-uploads a corrected version of a contract and wants the stale one gone.
  - **Entry state:** authenticated, on the Documents page, viewing his document list.
  - **Path:** He selects the outdated document and deletes it.
  - **Climax:** It disappears from the library and from vector search results immediately; a confirmation explains that structural graph entities derived from it may persist (§4.3) so he isn't surprised later.
  - **Resolution:** Marcus re-uploads the corrected version and continues working, understanding the deletion boundary rather than assuming total erasure.

## 3. Glossary

- **Document** — A user-uploaded file (PDF, Markdown, or HTML) ingested into GraphMind. Belongs to exactly one User.
- **Passage (Chunk)** — A segment of a Document's text, the unit stored in the vector index with its embedding and metadata (`user_id`, `document_id`, `chapter`, `chunk_index`).
- **Chapter** — A chapter/section-level metadata tag on a Passage, used to scope search within a Document.
- **Knowledge Graph** — The per-User graph of Entities and Relationships extracted from all of that User's Documents combined into one unified structure (not per-document).
- **Entity** — A node in the Knowledge Graph (e.g. a project, person, technology) extracted from Document text.
- **Relationship** — A typed edge between two Entities in the Knowledge Graph (e.g. "uses", "works on").
- **Citation** — A structured reference from a generated answer back to the specific Passage(s) that support it.
- **Refusal** — GraphMind's explicit "I don't know" response, returned when retrieval finds no adequate supporting evidence for a question.
- **User** — An authenticated account. All Documents, the Knowledge Graph, and query history belong to exactly one User (tenancy boundary).
- **Query History** — The saved record of a User's past questions and answers, including which Documents were in scope and a snapshot of citations at the time asked.
- **Evaluation Set** — A fixed set of question/expected-answer pairs used to measure answer accuracy and refusal correctness.

## 4. Features

### 4.1 Authentication & Tenancy Isolation

**Description:** Every User authenticates before using GraphMind. All reads and writes to both the vector index and Knowledge Graph are filtered by `user_id` at the query layer — never only in the UI. This is the single most safety-critical feature: without it, one user's private documents could leak into another's answers.

**Functional Requirements:**

#### FR-1: Account creation and login
A visitor can create an account and log in. Realizes entry state for UJ-1, UJ-2.
**Consequences (testable):**
- Passwords are stored hashed (bcrypt_sha256), never in plaintext.
- A valid session is represented as a JWT sent with every subsequent request.
- ~~[ASSUMPTION: No password reset or email verification in v1 — matches course brief's minimal-schema direction to protect the 20-day timeline.]~~ *(Email verification pulled forward into scope, 2026-08-20, as Story 1.6 — same "pulled forward once the DoD gate closed" precedent as FR-17 below. Password reset remains out of v1 scope, unchanged. See `epics.md` Story 1.6.)*

#### FR-2: Server-side tenancy filtering
The system enforces `user_id` filtering on every read/write to the vector index and the Knowledge Graph, independent of any client-supplied value.
**Consequences (testable):**
- A user with two test accounts cannot retrieve another account's documents, citations, or graph data through any endpoint.
- Where natural-language graph querying exists post-MVP, the `user_id` constraint is injected server-side into the generated query, never trusted from LLM output.

**Feature-specific NFRs:**
- This is a hard security requirement, not best-effort: any cross-tenant leak is a launch blocker, not a bug to triage later.

### 4.2 Document Ingestion

**Description:** A user uploads a PDF, Markdown, or HTML file. The system parses it, splits it into Passages tagged with metadata, generates embeddings, and writes them to the vector index. In parallel, the text passes through entity/relationship extraction and is merged into the user's single unified Knowledge Graph — not a new graph per document. Realizes UJ-1's upload step.

**Functional Requirements:**

#### FR-3: Upload and parse supported formats
A user can upload PDF, Markdown, or HTML files.
**Consequences (testable):**
- Unsupported formats are rejected with a clear error before any processing starts.
- A successfully parsed document produces one or more Passages tagged with `document_id`, `chapter`, `chunk_index`.

#### FR-4: Ingestion status visibility
A user can see each document's ingestion state.
**Consequences (testable):**
- Each document shows one of: Uploaded, Extracting, Graphing, Ready, Failed.
- A Failed state includes a human-readable reason and does not silently drop the document from the list.

#### FR-5: Entity/relationship extraction into the unified graph
The system extracts entities and relationships from ingested text and merges them into the user's single Knowledge Graph.
**Consequences (testable):**
- Newly extracted entities that match existing graph entities merge rather than duplicate. [ASSUMPTION: identity-resolution mechanism (exact-match, fuzzy-match, or LLM-assisted) is unspecified and left to architecture.]
- Extraction is scoped to a constrained, fixed set of entity/relationship types [ASSUMPTION: exact type list — e.g. project/team/technology/person — to be finalized in architecture, not this PRD].

#### FR-6: Ingestion dedupe
The system avoids reprocessing a document whose content is unchanged.
**Consequences (testable):**
- Re-uploading a byte-identical file (by content hash) does not re-run extraction or re-call the LLM or embedding API.

#### FR-14: Drag-and-drop upload with progress
A user can upload files via drag-and-drop onto the upload area, in addition to a file picker, and sees per-file progress while files are queued and uploading. Realizes the Upload modal in UX EXPERIENCE.md.
**Consequences (testable):**
- The upload modal accepts files dropped anywhere in its dropzone as well as via click-to-browse.
- Each queued file shows its own progress indicator; files upload independently rather than blocking as one batch.
- [ASSUMPTION: pulled forward from the course brief's v2 backlog into v1 scope per UX decision during design — the mocked Upload modal specifies this behavior directly.]

**Out of Scope:**
- Live entity/relationship preview shown to the user immediately post-ingestion — deferred (§6.2).
- User-editable correction of extracted entities/relationships — deferred (§6.2).

### 4.3 Document Library

**Description:** A user can see, inspect, and delete their uploaded documents. Realizes UJ-2.

**Functional Requirements:**

#### FR-7: List and inspect documents
A user can view a list of their documents with status, upload date, and can open one to see its metadata/chapters.
**Consequences (testable):**
- The list shows every document owned by the authenticated user, and none owned by any other user.
- Opening a document displays its ingestion status, upload date, and chapter breakdown.

#### FR-8: Delete a document
A user can delete a document.
**Consequences (testable):**
- On delete, the document and its Passages/embeddings are removed from the vector index immediately.
- Knowledge Graph entities/relationships derived from that document are **not** retroactively pruned (avoids reference-counting complexity across a unified multi-document graph). The UI states this plainly at delete time so the boundary isn't a surprise.
- [NOTE FOR PM: this creates a trust tension worth revisiting — a deleted document's structural graph traces can still influence future answers even though the document itself is gone. Flagged as a candidate for a stronger deletion mode in v2 if it proves confusing in practice.]

### 4.4 Grounded Chat Q&A

**Description:** The core interaction. A user asks a question; the system answers only from retrieved evidence, with citations, or explicitly refuses. Realizes UJ-1.

**Functional Requirements:**

#### FR-9: Answer with structured citations
Given a question, the system retrieves relevant Passages (vector search) and/or traverses the Knowledge Graph, and returns an answer with citations to the specific supporting Passage(s).
**Consequences (testable):**
- Every claim-bearing sentence in an answer is traceable to at least one citation.
- Citations reference a specific document + passage, not just a document-level source.

#### FR-10: Explicit refusal below evidence threshold
When retrieval finds no adequate supporting evidence, the system returns an explicit "I don't know" rather than invoking the LLM to guess.
**Consequences (testable):**
- Below a defined relevance threshold, the system short-circuits before the generation call (saves latency/cost) and returns a refusal message explaining no supporting evidence was found.
- Refusal is measured as its own metric in the Evaluation Set (§7), not treated as a failure mode to minimize at all costs.

#### FR-11: Document scoping for a question
A user can choose to ask across all of their documents, or scope a question to a chosen subset.
**Consequences (testable):**
- Retrieval only considers passages from documents within the selected scope; passages outside the scope never appear as citations.
- Default scope (when the user doesn't choose) is all of the user's documents.

**Out of Scope:**
- Query history (question + answer + scope + citation snapshot) — deferred to v2 per user decision during UX design; no history surface in v1.
- Answer confidence badge/score display — deferred (§6.2).
- Opt-in "explain this answer" reasoning trace — deferred (§6.2).

### 4.5 Knowledge Graph View

**Description:** A user can visually explore their own unified Knowledge Graph.

**Functional Requirements:**

#### FR-12: Graph visualization
A user can view a node-link visualization of their Knowledge Graph, scoped to their own `user_id`.
**Consequences (testable):**
- The view renders entities and relationships as an interactive node-link diagram.
- No other user's graph data is queryable or renderable from this view.

**Out of Scope:**
- Natural-language querying of the graph ("ask the graph directly") — deferred (§6.2).

### 4.6 Evaluation Harness

**Description:** Answer quality is measured objectively rather than assessed subjectively, using a fixed Evaluation Set spanning three question categories: single-source factual, cross-document synthesis, and unanswerable (expected refusal).

**Functional Requirements:**

#### FR-13: Run the evaluation set and report metrics
A single command runs the Evaluation Set against the live system and reports accuracy on answerable questions and refusal-rate on unanswerable ones.
**Consequences (testable):**
- The harness invokes the service layer directly (not through the UI), so it stays fast and independent of frontend state.
- Output includes both metrics numerically, not just pass/fail.

**Feature-specific NFRs:**
- The Evaluation Set contains 15–20 question/expected-answer pairs, authored incrementally as ingestion becomes functional rather than all at once at the end.

### 4.7 Account & Appearance Settings

**Description:** A User Settings surface holding profile info, password change, an appearance (theme) preference, and account deletion. Added to v1 scope during UX design (dark mode was explicitly requested as a v1 requirement, and account deletion emerged as a natural counterpart to document deletion once the Settings surface was designed) — pulled forward from what the course brief's backlog treated as v2/undefined.

**Functional Requirements:**

#### FR-15: Light/dark theme preference
A user can switch between light and dark appearance from User Settings; the choice is a user-selectable preference, not automatic OS-detection.
**Consequences (testable):**
- The chosen theme persists across sessions for that user.
- All screens (auth pages included) render correctly in both themes — no screen is light-only or dark-only.
- [ASSUMPTION: pulled forward from the course brief's v2 backlog into v1 scope per explicit user decision during UX design; no OS-preference auto-detection in v1, manual toggle only.]

#### FR-16: Account deletion
A user can permanently delete their own account from User Settings.
**Consequences (testable):**
- Deletion requires an explicit confirmation step (danger-zone pattern, matching the document-delete confirmation precedent in FR-8).
- On confirmed deletion, the user's documents, vector index entries, Knowledge Graph data, and account record are removed; the user is logged out.
- [ASSUMPTION: exact data-removal completeness (e.g. whether Knowledge Graph entities shared via merge with future re-signups are handled) is left to architecture — no such multi-account merge scenario exists in v1 since accounts are isolated per §4.1.]

**Out of Scope:**
- Account recovery/undo window after deletion — deletion is immediate and final in v1.

## 5. Non-Goals (Explicit)

- GraphMind is not a general-purpose chatbot — it will not answer from the LLM's general knowledge when the corpus doesn't support an answer (this is the product's core differentiator, not a limitation to work around).
- Not building cross-tenant collaboration, sharing, or team workspaces in v1.
- Not building proactive/unprompted insights (e.g. contradiction detection across a user's documents) in v1 — identified as a strong v2 direction, not lost, just deferred.
- Not building a correction-feedback loop that improves extraction quality over time in v1.
- Not building reference-counted graph deletion (full provenance-aware pruning) in v1.

## 6. MVP Scope

### 6.1 In Scope
- Auth (signup/login, JWT), server-side per-user tenancy isolation across both databases.
- Document ingestion: PDF/MD/HTML → passages → embeddings → Weaviate; parallel entity/relationship extraction → unified per-user Neo4j graph.
- Content-hash dedupe on ingest.
- Document library: list, inspect, delete (vector store cleared, graph not pruned).
- Chat Q&A: grounded answers with citations, explicit refusal below evidence threshold, document scoping (all vs. chosen subset).
- Knowledge graph visualization view, scoped per user.
- Evaluation harness: 15–20 question set, accuracy + refusal-rate metrics.
- Drag-and-drop upload with per-file progress (FR-14).
- User Settings: profile, password change, light/dark theme preference (FR-15), account deletion (FR-16).

### 6.2 Out of Scope for MVP
- User-editable graph corrections *(v2 candidate — brainstorming "Could")*.
- Opt-in "explain this answer" reasoning trace *(v2 candidate — brainstorming "Could")*.
- Live entity/relationship preview immediately after ingestion *(v2 candidate — brainstorming "Could")*.
- Proactive contradiction detection across a user's documents *(v2 candidate, strong direction per Disney Method dreamer pass)*.
- Correction-feed extraction-quality diagnostics *(v2 candidate)*.
- Reference-counted/full graph deletion *(v2 candidate)*.
- Answer confidence badge/indicator *(explicitly rejected during brainstorming convergence — revisit only if user feedback demands it)*.
- Natural-language querying over the knowledge graph *(v2 candidate, noted security implication in §4.1)*.
- Chapter-level filtered search — v1 document scoping is document-level only (FR-11); chapters remain captured as metadata (§4.2 FR-3, visible in Document Detail) but are not user-filterable in Chat.
- Clickable citations that open/highlight the source passage inline, suggested follow-up questions, document search/filtering, project/category grouping beyond chapters, hybrid BM25+vector search, raw-context inspection panel, conversation export *(all v2/v3 backlog per course brief, prioritized in `addendum.md`)*.
- ~~Conversational memory/follow-ups~~ *(pulled forward into scope as FR-17, 2026-08-18, now that v1's Definition-of-Done gate — Epic 6 — is closed. Same precedent as FR-14/FR-15 being pulled forward from the v2 backlog earlier. See `epics.md`'s FR-17, OD-8, AD-10, UX-DR29.)*
- Account recovery/undo window after account deletion *(§4.7 FR-16)*.
- ~~Password reset / email verification~~ *(email verification pulled forward into scope as part of FR-1, 2026-08-20, Story 1.6; password reset remains out of scope, unchanged)* *[ASSUMPTION, §4.1 FR-1]*.

## 7. Success Metrics

**Primary**
- **SM-1**: Answerable-question accuracy on the Evaluation Set — target ≥80% [ASSUMPTION: numeric bar not specified in sources; adjust once the set is authored]. Validates FR-9, FR-10, FR-13.
- **SM-2**: Refusal correctness — the system refuses 100% of genuinely unanswerable questions in the Evaluation Set (no confident fabrication). Validates FR-10, FR-13.
- **SM-3**: Zero cross-tenant data leakage, verified with two test accounts per FR-2's consequence. Validates FR-2. Tiered Primary, not Secondary, because §4.1 treats tenancy isolation as a launch blocker, not a nice-to-have.

**Counter-metrics (do not optimize)**
- **SM-C1**: Refusal rate on *answerable* questions should not rise as a side effect of chasing SM-2 — over-refusing is as much a failure as fabricating. Counterbalances SM-2.

[As a portfolio project without live users yet, v1 success is course Definition of Done + demonstrable trust behavior; deeper engagement/retention metrics are deferred until there's a real usage phase post-course.]

## 8. Open Questions

1. Exact entity/relationship type list for extraction (FR-5) — constrained set needed before extraction prompts can be finalized; belongs to architecture, flagged here so it isn't lost.
2. Numeric accuracy target for SM-1 — currently an assumption; confirm once the Evaluation Set exists and a baseline run is possible.
3. Whether the delete/graph-persistence tension (FR-8 NOTE) needs a stronger v1 mitigation (e.g. a plain-language warning) or is acceptable as-is for a portfolio-stage product.

## 9. Assumptions Index

- ~~§4.1 FR-1 — No password reset or email verification in v1.~~ *(Superseded 2026-08-20: email verification shipped as Story 1.6, pulled forward once the DoD gate closed. Password reset remains a valid open assumption/out-of-scope item.)*
- §4.2 FR-5 — Exact extraction entity/relationship type list deferred to architecture.
- §4.2 FR-5 — Entity identity-resolution/merge mechanism deferred to architecture.
- §7 SM-1 — 80% accuracy target is a placeholder pending a real Evaluation Set baseline.
- Cross-cutting NFRs below (§10) — latency, size limits, and browser support are reasonable defaults, not sourced from either input document.
- §4.2 FR-14 — Drag-and-drop upload pulled forward from v2 backlog into v1 per UX decision.
- §4.7 FR-15 — Light/dark theme preference pulled forward from v2 backlog into v1 per explicit user decision; manual toggle only, no OS auto-detection.
- §4.7 FR-16 — Account deletion data-removal completeness left to architecture.

## 10. Cross-Cutting NFRs

- **Performance:** Answer latency target p95 < 8s end-to-end (retrieval + generation), given free-tier LLM/hosting constraints.
- **Capacity:**  Support documents up to 20MB and no hard cap on document count per user for v1, revisit if free-tier storage limits bite.
- **Browser support:**  Latest two versions of evergreen browsers (Chrome, Firefox, Edge, Safari); no legacy browser support.
- **Reliability:** All three managed services (Weaviate, Neo4j AuraDB, Neon Postgres) are external dependencies; a demo-time network outage risk exists and is tracked in `addendum.md`'s risk register with a fallback plan.

## 11. Constraints and Guardrails

- **Privacy:** Per-user tenancy isolation (§4.1) is the primary privacy guardrail — no document content, citation, or graph data crosses `user_id` boundaries under any code path.
- **Cost:** All managed services run on free tiers by design (Weaviate, Neo4j AuraDB free tier, OpenRouter free tier, Neon free tier) to keep the project reproducible by any reviewer at zero cost. Ingestion dedupe (FR-6) exists specifically to protect this constraint.
- **Safety:** The refusal behavior (FR-10) is itself a guardrail against fabricated claims being presented as fact — treated as a core requirement, not a nice-to-have.
