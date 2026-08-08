# GraphMind — Epics & Stories

Derived from [BR.md](BR.md). Organised by feature module, matching the modular-monolith architecture (auth / documents / chat / kg) so each epic maps to a team ownership area. Sequencing follows the Delivery Plan's dependency order: auth → ingestion → retrieval → documents UI → chat UI → knowledge graph → evaluation.

Story points are rough (1/2/3/5/8, Fibonacci-ish) for relative sizing only.

---

## Epic 1 — Authentication & Per-User Isolation
**Scope refs:** #7 · **Days:** 2–3 · **Owner:** Backend/RAG

Foundation epic — nothing that filters by `user_id` can be built before this lands.

### Dependencies (must be in place before Epic 1 work starts)

1. **Neon Postgres project provisioned** — connection string (host, db, user, password) available as an env var. External service, so this is the earliest possible blocker; request access/create the project on Day 1 (Epic 8.2 smoke test).
2. **Backend scaffolding exists** — a runnable FastAPI app (Epic 8.1) with an `auth` module directory to build into.
3. **Python package dependencies installed**, e.g.:
   - `fastapi`, `uvicorn` — API framework + dev server
   - `sqlalchemy` + `asyncpg` (or `psycopg2-binary` for sync) — Postgres access
   - `alembic` — schema migrations (or a plain SQL init script if skipping migrations for v1)
   - `passlib[bcrypt]` (or `bcrypt` directly) — password hashing
   - `python-jose[cryptography]` (or `pyjwt`) — JWT issuance/validation
   - `pydantic` / `pydantic-settings` — request validation + env config
   - `python-dotenv` — local env var loading
4. **`users` table schema defined and migrated** — must exist before 1.1 can write a signup row.
5. **JWT signing secret configured** (env var, not hardcoded) — must exist before 1.2 can issue tokens.
6. **A FastAPI dependency (`Depends(...)`) for "current user from JWT"** — the mechanism 1.3/1.4 hang off of; build it once, reuse across all protected routers (documents, chat, kg).

Dependency order: (1) Neon project → (4) schema → (3) packages installed → (1.1 signup) → (5) JWT secret → (1.2 login) → (6) auth dependency → (1.3, 1.4).

- **1.1** As a new user, I can sign up with an email and password so that I have an account.
  - Acceptance: password stored as bcrypt hash in Neon Postgres, never in plaintext or logs; duplicate email rejected with a clear error. (3)
  - **Sub-tasks:**
    1. Define `User` model/table: `id`, `email` (unique, indexed), `password_hash`, `created_at`.
    2. Write the migration (Alembic revision, or init SQL) and apply it to the Neon database.
    3. Define the Pydantic request schema for signup: `email: EmailStr`, `password: str` with a minimum-length validator.
    4. Implement password hashing on write (bcrypt via passlib) — never store or log the raw password.
    5. Implement `POST /auth/signup`: validate input → check for existing email → hash password → insert row.
    6. Return 409 (or 400) with a clear message on duplicate email, without confirming *which* field collided beyond "email already registered."
    7. Return a minimal success response (e.g. `user_id`, `email`) — no password hash in the response body, ever.
    8. Tests: successful signup persists a hashed (not plaintext) password; duplicate email is rejected; invalid email format / too-short password are rejected with 422.
- **1.2** As a registered user, I can log in and receive a JWT so that I can make authenticated requests.
  - Acceptance: valid credentials return a signed JWT with `user_id` claim; invalid credentials return 401 without leaking whether the email exists. (3)
  - **Sub-tasks:**
    1. Define the Pydantic request schema for login: `email: EmailStr`, `password: str`.
    2. Implement `POST /auth/login`: look up user by email, verify password against the bcrypt hash (constant-time compare via passlib, not manual `==`).
    3. On mismatch (email not found *or* password wrong), return the same generic 401 + message in both cases — don't let response shape/timing reveal whether the email exists.
    4. Decide and configure JWT parameters: signing algorithm (e.g. HS256), expiry (e.g. 24h), claims (`user_id`, `exp`, `iat`).
    5. Implement token issuance using the JWT secret from Epic 1 dependency #5 (env var, never hardcoded).
    6. Return the token in the response body (e.g. `{"access_token": ..., "token_type": "bearer"}`).
    7. Tests: correct credentials issue a decodable token containing the right `user_id`; wrong password, unknown email, and malformed request all return the same 401 shape.
- **1.3** As the backend, I reject any request to a protected endpoint that lacks a valid JWT so that unauthenticated access is impossible.
  - Acceptance: missing/expired/malformed token → 401; middleware applied uniformly across documents, chat, and kg routers. (2)
  - **Sub-tasks:**
    1. Implement a `get_current_user` FastAPI dependency: extract the `Authorization: Bearer <token>` header, decode/verify the JWT signature and expiry.
    2. Raise 401 (with `WWW-Authenticate: Bearer` header) on: missing header, malformed header, invalid signature, expired token.
    3. Wire this dependency into every route in the documents, chat, and kg routers (Epic 2/3/6) — no protected route should be reachable without it.
    4. Add a router-level (not per-route) dependency where possible so a new endpoint is protected by default rather than by remembering to add it.
    5. Tests: request with no header → 401; expired token → 401; tampered/invalid-signature token → 401; valid token → request proceeds.
- **1.4** As the system, I derive `user_id` from the JWT server-side (never from a client-supplied field) so that isolation cannot be bypassed by a malicious request body.
  - Acceptance: any `user_id` present in a request payload is ignored in favor of the token's claim. (2)
  - **Sub-tasks:**
    1. Have `get_current_user` (1.3) return a `user_id` value (or a `User` object) — this becomes the single source of truth for the rest of the request.
    2. Audit request/query Pydantic schemas across documents, chat, and kg modules to confirm none of them accept a client-supplied `user_id` field; remove any that do.
    3. Thread the dependency-derived `user_id` explicitly into every ChromaDB filter and Cypher query parameter (used later by Epics 2/3/6) rather than reading it off the request body.
    4. Test/document the attack case explicitly: a request body containing a spoofed `user_id` for a different account is ignored, and the response is scoped to the token's real owner.
- **1.5** As a developer, I have a minimal schema with no password reset or email verification so that auth doesn't overrun its time allocation.
  - Acceptance: explicitly out of scope per BR risk mitigation; documented as a v1 limitation. (1)
  - **Sub-tasks:**
    1. Confirm the `users` table has no columns for reset tokens, verification tokens, or verification status — keep the schema to `id`, `email`, `password_hash`, `created_at`.
    2. Do not implement `/auth/forgot-password`, `/auth/reset-password`, or `/auth/verify-email` routes.
    3. Add a short note (README or this doc) stating these are intentionally deferred, so it reads as a scoping decision rather than an oversight during review/demo.

---

## Epic 2 — Document Ingestion Pipeline
**Scope refs:** #1 · **Days:** 4–6 · **Owner:** Backend/RAG

- **2.1** As a user, I can upload a PDF, Markdown, or HTML file so that it becomes searchable.
  - Acceptance: all three formats parse without error on representative sample files; unsupported formats rejected with a clear message. (5)
- **2.2** As the system, I split ingested documents into passages tagged with `user_id`, `document_id`, `chapter`, and `chunk_index` so that retrieval can filter and cite precisely.
  - Acceptance: every chunk in ChromaDB carries all four metadata fields; chapter boundaries detected from document structure (headings) where present. (5)
- **2.3** As the system, I generate embeddings for each passage and write them to ChromaDB so that semantic search is possible.
  - Acceptance: embedding + chunk + metadata persisted atomically per document; partial-failure uploads don't leave orphaned chunks. (3)
- **2.4** As a user, I get feedback on ingestion success or failure so that I know whether my document is searchable.
  - Acceptance: upload response indicates success/failure and chunk count; failures return an actionable error. (2)
- **2.5** As the system, I trigger entity/relationship extraction in parallel with the embedding write so that ingestion produces both a vector index and knowledge-graph data from a single pass.
  - Acceptance: extraction failure does not block or roll back the vector-index write (independent failure domains). (3)

---

## Epic 3 — Retrieval, Citations & Refusal
**Scope refs:** #2, #6 · **Days:** 7–9 · **Owner:** Backend/RAG

Core product differentiator: every claim is grounded, and absence of evidence produces a refusal rather than a fabrication.

- **3.1** As a user, I can ask a question and receive an answer grounded in my documents so that I can trust the response.
  - Acceptance: question embedded, similarity search filtered by `user_id` (and optional `chapter`), top-k passages sent to the LLM with the question. (5)
- **3.2** As a user, I see structured citations attached to each claim in an answer so that I can verify it against the source.
  - Acceptance: every answer contains ≥1 citation referencing a specific document + passage; citation format is structured (not just prose mention). (5)
- **3.3** As a user, I receive an explicit "I don't know" when no passage clears the relevance threshold so that I am not misled by a fabricated answer.
  - Acceptance: below-threshold queries never reach the LLM (saves latency/budget per BR); refusal message explains that no supporting evidence was found. (3)
- **3.4** As the system, I enforce the `user_id` filter at the query layer (not just the UI) so that isolation holds even against a malicious client.
  - Acceptance: verified with two test accounts — user A's query never returns user B's passages, per BR Definition of Done. (2)
- **3.5** As a developer, I can tune the relevance threshold so that the refusal rate can be calibrated against the evaluation set.
  - Acceptance: threshold is a single configurable value, not hardcoded in multiple places. (1)

---

## Epic 4 — Documents Page
**Scope refs:** #8, #9, #10 · **Days:** 10–11 · **Owner:** Frontend + Backend/RAG

- **4.1** As a user, I can see a list of my uploaded documents so that I know what's in my corpus.
  - Acceptance: list scoped to the logged-in user only; shows filename, upload date, chapter count. (3)
- **4.2** As a user, I can inspect a document's details (chapters, chunk count) so that I understand what was indexed.
  - Acceptance: detail view reflects the metadata written at ingestion time (2.2). (2)
- **4.3** As a user, I can delete a document so that it's removed from my corpus.
  - Acceptance: deletion removes the document's chunks from ChromaDB and its nodes/relationships from Neo4j (or clearly documents any lag); deleted document no longer appears in chat citations. (3)
- **4.4** As a user, I can upload a new document from the Documents page so that ingestion is accessible without leaving the UI.
  - Acceptance: reuses the ingestion endpoint (2.1); shows upload progress/result inline. (2)

---

## Epic 5 — Chat Page
**Scope refs:** #4, #8, #10 · **Days:** 12–14 · **Owner:** Frontend

- **5.1** As a user, I can ask a question in a chat interface and see the answer rendered with its sources so that I can verify claims without leaving the page.
  - Acceptance: each answer displays at least one concrete source reference per BR Definition of Done. (5)
- **5.2** As a user, I can filter my question to a specific chapter so that I narrow retrieval to a known section.
  - Acceptance: chapter filter passed through to the retrieval query (3.1); optional — omitted means search-all. (2)
- **5.3** As a user, I can see previous questions and answers in the current session so that I have conversational context while I work.
  - Acceptance: session-scoped history (not persisted cross-session — conversational memory across sessions is post-MVP per BR backlog). (3)
- **5.4** As a user, I see a distinct visual treatment for refusal responses so that "I don't know" doesn't read like a normal answer.
  - Acceptance: refusal state is visually distinguishable (e.g. styling/icon), not just plain text indistinguishable from a real answer. (1)

---

## Epic 6 — Knowledge Graph
**Scope refs:** #3 · **Days:** 15–17 · **Owner:** Knowledge Graph (shared)

- **6.1** As the system, I extract entities and relationships (project → team → technology) from ingested text via LLM prompting so that relational questions become answerable.
  - Acceptance: extraction scope constrained to three entity types per BR risk mitigation; results written to Neo4j AuraDB scoped by `user_id`. (5)
- **6.2** As a user, I can ask a relational question ("which projects use React") and get an answer sourced from the graph rather than vector search so that connection-traversal questions are handled correctly.
  - Acceptance: kg module runs a parameterised Cypher query, not free-text-to-Cypher generation, for v1 (natural-language graph querying is post-MVP per BR backlog). (5)
- **6.3** As a user, I can view a node-link visualization of my knowledge graph so that I can explore relationships visually.
  - Acceptance: kg module returns nodes/edges as JSON scoped to `user_id`; rendered client-side with react-force-graph or vis-network. (5)
- **6.4** As the system, I inject the `user_id` constraint into every Cypher query server-side so that graph isolation doesn't depend on LLM-generated query correctness.
  - Acceptance: matches BR Security Note explicitly — constraint is never left to the language model to include. (2)
- **6.5** As a developer, I have offline-validated graph queries and a local export fallback so that a demo isn't blocked by Neo4j AuraDB network dependency.
  - Acceptance: fallback export tested at least once before demo day, per BR key risks. (2)

---

## Epic 7 — Evaluation Harness
**Scope refs:** #5 · **Days:** 6 (drafting, parallel) & 18–19 (execution) · **Owner:** Backend/RAG

- **7.1** As a developer, I have a fixed evaluation set of 15–20 question/expected-answer pairs spanning single-source, cross-document, and unanswerable categories so that answer quality is measured reproducibly.
  - Acceptance: set drafted starting Day 6, once ingestion is functional, so evaluation is measurement, not authoring, by Day 18. (3)
- **7.2** As a developer, I can run the evaluation harness with a single command and get a numeric accuracy figure so that quality is objectively trackable.
  - Acceptance: matches BR Definition of Done; harness invokes the service layer directly, not through HTTP. (3)
- **7.3** As a developer, I get a refusal-rate metric alongside accuracy so that over-confident answering on unanswerable questions is caught.
  - Acceptance: both metrics reported per run; refusal rate treated as equally important to accuracy, per BR Evaluation Approach. (2)
- **7.4** As a developer, I can act on evaluation results to remediate retrieval/threshold issues before demo day so that quality gaps are fixed, not just measured.
  - Acceptance: Days 18–19 include a remediation pass, not just a single measurement run. (3)

---

## Epic 8 — Repository Scaffolding & Service Connectivity
**Scope refs:** cross-cutting · **Days:** 1 · **Owner:** All

- **8.1** As a developer, I have a scaffolded repository with the feature-module structure (auth / documents / chat / kg) so that parallel work doesn't collide.
  - Acceptance: directories exist per the Architecture diagram; no shared `routers/`/`services/`/`repositories/` split. (2)
- **8.2** As a developer, I have verified connectivity to all three managed services (Neon Postgres, ChromaDB, Neo4j AuraDB) and OpenRouter so that later stages aren't blocked by infra surprises.
  - Acceptance: a smoke-test script/endpoint confirms each connection on Day 1, before any feature work starts. (2)
- **8.3** As a team, we have roles assigned (Backend/RAG, Knowledge Graph, Frontend) so that ownership is clear from Day 1.
  - Acceptance: matches BR Team table; KG work explicitly shared between both contributors on a 2-person team. (1)
- **8.4** As a developer, I have a short reference of core Cypher query patterns prepared so that unfamiliarity with Cypher doesn't slow down Epic 6.
  - Acceptance: reference covers the fixed set of parameterised queries the project will actually use. (1)

---

## Epic 9 — End-to-End Integration & Demo Readiness
**Scope refs:** Definition of Done · **Days:** 18–20 · **Owner:** All

- **9.1** As a team, we verify all ten scope items function end-to-end so that the deliverable is demonstrable.
  - Acceptance: manual pass through every BR Scope row. (3)
- **9.2** As a team, we verify user isolation holds across the full stack (vector search + graph) using two test accounts so that the isolation requirement in the Definition of Done is provably met.
  - Acceptance: account A cannot retrieve account B's documents, chat answers, or graph nodes. (2)
- **9.3** As a team, we have a rehearsed demo script with a fallback for network-dependent services so that a live demo isn't derailed by a managed-service outage.
  - Acceptance: local export fallback (6.5) exercised as part of the rehearsal. (2)

---

## Traceability: Scope → Epic

| BR Scope # | Requirement | Epic |
|---|---|---|
| 1 | Ingestion → passages → embeddings → vector index | Epic 2 |
| 2 | Retrieval with structured citations | Epic 3 |
| 3 | Entity/relationship extraction into KG | Epic 6 |
| 4 | Chat interface with sources | Epic 5 |
| 5 | Evaluation set | Epic 7 |
| 6 | Explicit "I don't know" | Epic 3 |
| 7 | Per-user isolation | Epic 1, Epic 3, Epic 6 |
| 8 | Chapter-level metadata + filtered search | Epic 2, Epic 5 |
| 9 | Document listing, inspection, deletion | Epic 4 |
| 10 | Two-page application | Epic 4, Epic 5 |

## Post-MVP Backlog (not scheduled — see BR.md for full list)

High-priority items likely to become epics in a v2 planning pass: clickable citations that open/highlight the source passage, answer confidence indicator, prompt-injection guardrails for ingested content, natural-language querying over the knowledge graph (superseding the fixed-Cypher approach in 6.2).
