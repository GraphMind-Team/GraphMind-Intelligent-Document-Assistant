
# GraphMind
 
**Intelligent Document Q&A with Knowledge Graphs**
 
Project 15 · AI & Data Track · Team of 2–3 · 20-day delivery window
 
---
 
## Overview
 
GraphMind is a document question-answering assistant that returns **grounded, cited answers** over a private collection of corporate documents. Every response is traceable to a specific passage in a specific document, and the system explicitly declines to answer when no supporting evidence exists in the indexed corpus.
 
The application combines two complementary retrieval strategies. Vector search over document passages handles semantic questions ("what does the specification say about the deployment process"). A lightweight knowledge graph handles relational questions ("which projects use React", "who works on Project X") — queries that require traversing connections across documents rather than matching similar text.
 
The deliverable is a two-page application: **Chat** and **Documents**, plus a knowledge graph view.
 
---
 
## Problem Statement
 
Information relevant to a single question is typically scattered across many documents. Two failure modes follow: people spend disproportionate time searching, and when an automated assistant does answer, users cannot verify the claim and therefore cannot trust it.
 
Generic LLM assistants make this worse by producing fluent answers with no provenance, and by fabricating answers rather than admitting a gap. GraphMind treats citation and explicit refusal as core product requirements rather than optional features.
 
---
 
## Goals
 
1. Answer questions over an ingested document corpus with an explicit citation for every claim.
2. Return a clear, explained "I don't know" when retrieval finds no adequate supporting evidence.
3. Extract entities and relationships (project → team → technology) into a queryable knowledge graph.
4. Enforce per-user data isolation, so each user queries only their own documents.
5. Measure answer quality with a reproducible evaluation set rather than subjective assessment.

---
 
## Scope
 
The following constitute the v1 deliverable. The project starts from an empty repository — no prior prototype or existing codebase.
 
| # | Requirement |
|---|---|
| 1 | Document ingestion (PDF/MD/HTML) → passages → embeddings → vector index |
| 2 | Retrieval with LLM-generated answers containing structured citations |
| 3 | Entity and relationship extraction into a knowledge graph |
| 4 | Chat interface displaying sources alongside each answer |
| 5 | Evaluation set (questions, expected answers, measured accuracy) |
| 6 | Explicit "I don't know" when evidence is insufficient |
| 7 | Per-user isolation (authentication + `user_id` filtering at query level) |
| 8 | Chapter-level document metadata with filtered search |
| 9 | Document listing, inspection, and deletion |
| 10 | Two-page application: Chat and Documents |
 
---
 
## Technology Stack
 
| Layer | Technology | Rationale |
|---|---|---|
| Backend API | FastAPI | Lightweight, fast to develop, native Python integration with the RAG pipeline |
| Vector database | ChromaDB | Local, free, minimal setup overhead for a team without dedicated infrastructure support |
| LLM provider | OpenRouter (free tier) | Sufficient capability at zero cost for the project's scale |
| Frontend | React + Vite + Tailwind CSS | Rapid development; optional shadcn/ui for prebuilt components |
| Authentication | Neon (Postgres) + JWT | Managed Postgres; standard bcrypt + JWT pattern, no custom cryptography |
| Graph database | Neo4j AuraDB (free tier) | Managed — no self-hosting overhead. Cypher expresses relational traversal directly, which SQL or JSON storage would require hand-written join logic to replicate |
| Graph visualization | react-force-graph / vis-network | Node-link rendering in the frontend |
| Entity extraction | LLM prompting via OpenRouter | spaCy considered as a fallback if extraction latency becomes a bottleneck |
| Evaluation | Python script (ragas optional) | Expected-vs-actual comparison with LLM-as-judge as an optional extension |
 
The stack satisfies the assignment's required foundation (Python · Vector DB · LLM API · React). All services used are free-tier, keeping the project reproducible by any reviewer without cost.
 
---
 
## Architecture
 
A modular monolith organised by feature rather than by technical layer. Each module owns its full vertical slice — HTTP routing, business logic, and data access — with layering applied *within* the module rather than across top-level directories.
 
```
Frontend (React) — Chat / Documents / Graph views
        │  REST + JSON, JWT in Authorization header
        ▼
Backend (FastAPI)
  ├─ auth module       → Neon Postgres (users, password hashes)
  ├─ documents module  → ChromaDB (write: chunks, embeddings, metadata)
  │                    → Neo4j AuraDB (write: entities, relationships)
  │                    → OpenRouter (entity extraction)
  ├─ chat module       → ChromaDB (read: filtered similarity search)
  │                    → OpenRouter (answer generation with citations)
  └─ kg module         → Neo4j AuraDB (read: Cypher queries for visualization)
```
 
This structure was chosen over a conventional layered architecture (`routers/`, `services/`, `repositories/`) for a specific reason: with 2–3 developers working in parallel over a compressed timeline, a layered structure forces every feature change to touch three or four shared directories, producing frequent merge conflicts. Feature-based modules align code ownership with team roles, so contributors work in largely disjoint areas of the repository.
 
A hexagonal / ports-and-adapters architecture was also considered and rejected. Its principal benefit — swapping infrastructure implementations behind stable interfaces — has no payoff here, since the stack is fixed by the assignment and the project has a defined end date. The additional indirection would cost development time without buying usable flexibility.
 
### Request Flows
 
**Document ingestion:** the client uploads a file with a JWT; the auth layer resolves `user_id`; the documents module parses the file, splits it into passages tagged with `user_id`, `document_id`, `chapter`, and `chunk_index`, generates embeddings, and writes to ChromaDB. In parallel, the text is passed through an extraction prompt and the resulting entities and relationships are written to Neo4j.
 
**Question answering:** the chat module embeds the question and runs a similarity search filtered by `user_id` and, optionally, `chapter`. If the top result falls below the relevance threshold, the system returns an explicit refusal without invoking the LLM — saving both latency and API budget. Otherwise the retrieved passages and the question are sent to the LLM, which returns an answer with structured citations.
 
**Graph visualization:** the kg module runs a Cypher query scoped to `user_id` and returns nodes and edges as JSON for client-side rendering.
 
### Security Note
 
User isolation is enforced server-side at the query layer, not in the UI. This applies to Cypher queries as well: where natural-language graph querying is added post-MVP, the `user_id` constraint is injected into the query server-side rather than relying on the language model to include it correctly in generated Cypher.
 
---
 
## Evaluation Approach
 
Answer quality is measured against a fixed evaluation set of 15–20 question/expected-answer pairs spanning three categories: single-source factual questions, cross-document questions requiring synthesis, and questions with no support in the corpus, where the expected behaviour is refusal.
 
Two metrics are reported: accuracy on answerable questions, and the refusal rate on unanswerable ones. The second metric is treated as equally important — a system that answers everything confidently is not a successful outcome for this product.
 
The evaluation harness invokes the service layer directly rather than through HTTP, keeping runs fast and independent of the frontend.
 
---
 
## Delivery Plan
 
Sequencing follows technical dependency rather than perceived priority: authentication must exist before anything filters by `user_id`; ingestion must exist before retrieval has anything to search.
 
| Days | Focus |
|---|---|
| 1 | Repository scaffolding, service connectivity verification, role assignment |
| 2–3 | Authentication: Postgres schema, signup/login, JWT issuance and validation |
| 4–6 | Ingestion pipeline: parsing, chunking with metadata, embeddings, ChromaDB writes |
| 7–9 | Retrieval, citation generation, refusal threshold logic |
| 10–11 | Documents page: list, inspect, delete |
| 12–14 | Chat page: question flow, source display, chapter filtering |
| 15–17 | Knowledge graph: extraction, Neo4j integration, visualization |
| 18–19 | Evaluation runs, remediation, end-to-end integration testing |
| 20 | Buffer and demonstration preparation |
 
Evaluation questions are drafted in parallel from Day 6 onward, once ingestion is functional, so that the evaluation phase is a measurement exercise rather than an authoring one.
 
---
 
## Key Risks
 
| Risk | Mitigation |
|---|---|
| No existing codebase means week one has no schedule slack | Day 1 is scaffolding only, with no exploratory work; each subsequent stage builds directly on the previous |
| Cypher is unfamiliar to the team | A short reference of core query patterns is prepared on Day 1; graph writes use a small fixed set of parameterised queries |
| LLM entity extraction may be imprecise or slow | Extraction scope is constrained to three entity types; a small dedicated evaluation sample validates extraction quality separately from answer quality |
| Three managed services introduce demo-time network dependency | Graph queries are validated offline in advance; a local export serves as a demonstration fallback |
| Authentication overruns its allocation and blocks user isolation | Minimal schema only — no password reset or email verification in v1 |
| Frontend consumes disproportionate time | Two pages, utility-class styling, no visual polish in v1 |
 
---
 
## Definition of Done
 
- All ten scope items function end-to-end and are demonstrable.
- Every chat answer displays at least one concrete source reference.
- Questions without corpus support produce an explicit refusal, verified by the evaluation set.
- A user cannot retrieve another user's documents, verified with two test accounts.
- The evaluation script runs with a single command and reports a numeric accuracy figure.
---
 
## Post-MVP Backlog
 
Prioritised by impact relative to effort.
 
**High priority**
- Clickable citations that open and highlight the source passage
- Answer confidence indicator
- Prompt-injection guardrails for ingested content
- Natural-language querying over the knowledge graph
- 
**Medium priority**
- Conversational memory for follow-up questions
- Suggested follow-up questions
- Drag-and-drop upload with progress indication
- Search and filtering within the document list
- Project/category grouping in addition to chapters
**Low priority**
  
- Hybrid search combining BM25 with vector retrieval
- Raw-context inspection panel
- Light/dark theme
- Conversation export to PDF/Markdown
- Migration to a paid AuraDB tier if the project continues beyond the course
---
 
## Team
 
| Area | Responsibility |
|---|---|
| Backend / RAG | Authentication, ingestion, retrieval, citations, evaluation |
| Knowledge Graph | Entity extraction, Neo4j integration, graph queries |
| Frontend | Chat, Documents, and Graph views |
 
With a team of two, knowledge graph work is shared between both contributors.
 
---
 
