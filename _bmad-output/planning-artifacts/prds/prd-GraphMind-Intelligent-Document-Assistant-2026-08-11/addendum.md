# GraphMind — Addendum

Technical-how, sizing/timeline data, and rejected-alternative rationale that supports the PRD but doesn't belong in it. Sourced from the course brief (Project 15) and the brainstorming session.

## Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | FastAPI | Lightweight, fast to develop, native Python integration with the RAG pipeline |
| Vector database | **Weaviate** | Confirmed choice (corrects an earlier ChromaDB mention in the original brief) |
| LLM provider | OpenRouter (free tier) | Sufficient capability at zero cost for the project's scale |
| Frontend | React + Vite + Tailwind CSS | Rapid development; optional shadcn/ui for prebuilt components |
| Authentication | Neon (Postgres) + JWT | Managed Postgres; standard bcrypt + JWT pattern, no custom cryptography |
| Graph database | Neo4j AuraDB (free tier) | Managed, no self-hosting overhead. Cypher expresses relational traversal directly |
| Graph visualization | react-force-graph / vis-network | Node-link rendering in the frontend |
| Entity extraction | LLM prompting via OpenRouter | spaCy considered as a fallback if extraction latency becomes a bottleneck |
| Evaluation | Python script (ragas optional) | Expected-vs-actual comparison; LLM-as-judge as an optional extension |

All services free-tier — reproducible by any reviewer at zero cost. Every row above (except the Weaviate correction) was externally fixed by the course assignment brief (Project 15), not chosen by the PM/team — noted here since the PRD otherwise presents rationale in a way that could read as an open product decision.

## Architecture

Modular monolith organized by feature, not technical layer. Each module owns its full vertical slice (routing, logic, data access).

```
Frontend (React) — Chat / Documents / Graph views
        │  REST + JSON, JWT in Authorization header
        ▼
Backend (FastAPI)
  ├─ auth module       → Neon Postgres (users, password hashes)
  ├─ documents module  → Weaviate (write: chunks, embeddings, metadata)
  │                    → Neo4j AuraDB (write: entities, relationships)
  │                    → OpenRouter (entity extraction)
  ├─ chat module       → Weaviate (read: filtered similarity search)
  │                    → OpenRouter (answer generation with citations)
  └─ kg module         → Neo4j AuraDB (read: Cypher queries for visualization)
```

**Why feature-based over layered (`routers/`, `services/`, `repositories/`):** with 2 developers on a compressed timeline, a layered structure forces every feature change to touch several shared directories, producing frequent merge conflicts. Feature modules align code ownership with contributor roles.

**Why not hexagonal/ports-and-adapters:** its main benefit — swapping infrastructure behind stable interfaces — has no payoff when the stack is fixed by the assignment and the project has a defined end date. The added indirection costs time without buying usable flexibility.

### Request Flows

**Ingestion:** client uploads with JWT → auth resolves `user_id` → documents module parses, splits into passages tagged `user_id`/`document_id`/`chapter`/`chunk_index`, embeds, writes to Weaviate. In parallel, text passes through an extraction prompt; resulting entities/relationships write to Neo4j.

**Q&A:** chat module embeds the question, runs similarity search filtered by `user_id` (and optionally `chapter`). Below the relevance threshold, returns refusal without invoking the LLM (saves latency + budget). Otherwise sends retrieved passages + question to the LLM, which returns an answer with structured citations.

**Graph visualization:** kg module runs a Cypher query scoped to `user_id`, returns nodes/edges as JSON.

### Security Note

User isolation is enforced server-side at the query layer, not the UI — including for Cypher. Where natural-language graph querying is added post-MVP, the `user_id` constraint is injected server-side rather than trusted from LLM-generated Cypher.


## Risk Register

| Risk | Mitigation |
|---|---|
| No existing codebase — week one has no schedule slack | Day 1 is scaffolding only, no exploratory work |
| Cypher unfamiliar to the team | Short reference of core query patterns prepared Day 1; graph writes use a small fixed set of parameterized queries |
| LLM entity extraction imprecise or slow | Extraction scope constrained to a small fixed entity-type set; small dedicated eval sample validates extraction separately from answer quality |
| Three managed services → demo-time network dependency | Graph queries validated offline in advance; local export serves as demonstration fallback |
| Authentication overruns its allocation, blocks user isolation | Minimal schema only — no password reset/email verification in v1. [UPDATED 2026-08-20: email verification pulled forward into scope as Story 1.6, after the v1 DoD gate closed and this allocation risk was no longer live — see `epics.md` Story 1.6. Password reset remains out of scope, unchanged.] |
| Frontend consumes disproportionate time | Utility-class styling against a fixed design-token set, bespoke components, no component library. [UPDATED 2026-08-11: the original mitigation read "two pages, utility-class styling, no visual polish in v1", which predates the finalized UX spines — those define 8 screens and a full token system. What now bounds frontend time is the fixed token set and the absence of a component library, not screen count.] |
| Cross-user data leakage (brainstorming reverse-brainstorm finding) | Server-side `user_id` filtering enforced at query layer in both databases (PRD §4.1) |
| Weaviate/Neo4j write desync on partial ingestion failure (brainstorming finding) | Direction identified: unified ingestion job status tracking both writes — not yet a committed design |
| Ingestion cost/latency spiral from reprocessing unchanged docs (brainstorming finding) | Content-hash dedupe (PRD FR-6) |

## Definition of Done

- All in-scope PRD §6.1 items function end-to-end and are demonstrable.
- Every chat answer displays at least one concrete source reference.
- Questions without corpus support produce an explicit refusal, verified by the Evaluation Set.
- A user cannot retrieve another user's documents, verified with two test accounts.
- The evaluation script runs with a single command and reports a numeric accuracy figure.

## Post-MVP Backlog (prioritized)

**High priority**
- Clickable citations that open and highlight the source passage
- Answer confidence indicator
- Prompt-injection guardrails for ingested content
- Natural-language querying over the knowledge graph

**Medium priority**
- Conversational memory for follow-up questions
- Suggested follow-up questions
- Search and filtering within the document list
- Project/category grouping in addition to chapters
- User-editable graph corrections (brainstorming)
- Opt-in "explain this answer" reasoning trace (brainstorming)
- Live entity/relationship preview post-ingestion (brainstorming)
- Proactive contradiction detection across a user's documents (brainstorming — Disney Method dreamer pass)
- Correction-feed extraction-quality diagnostics (brainstorming)

**Low priority**
- Hybrid search combining BM25 with vector retrieval
- Raw-context inspection panel
- Conversation export to PDF/Markdown
- Migration to a paid AuraDB tier if the project continues beyond the course
- Reference-counted/full graph deletion on document removal (brainstorming)
- Account deletion recovery/undo window (PRD §4.7 FR-16)

**Pulled forward into v1 (was backlog in the original course brief):**
- Drag-and-drop upload with progress indication → now PRD FR-14
- Light/dark theme → now PRD FR-15

**Newly deferred to v2 (was drafted for v1, scoped out during UX design):**
- Query history (question + answer + document scope + citation snapshot)

## Team

| Area | Responsibility |
|---|---|
| Backend / RAG | Authentication, ingestion, retrieval, citations, evaluation |
| Knowledge Graph | Entity extraction, Neo4j integration, graph queries |
| Frontend | Chat, Documents, and Graph views |

With a team of two, knowledge graph work is shared between both contributors. [NOTE: the course brief allows a team of 2–3; this project is deliberately scoped to a fixed 2-person team throughout this PRD and addendum — not a gap, an intentional narrowing.]
