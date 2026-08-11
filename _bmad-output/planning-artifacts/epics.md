---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md
  - _bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/EXPERIENCE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/review-accessibility.md
  - _bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/reconcile-prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/reviews/reconcile-prd-addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-GraphMind-Intelligent-Document-Assistant-2026-08-11/reviews/review-adversarial-divergence.md
---

# GraphMind-Intelligent-Document-Assistant - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for GraphMind-Intelligent-Document-Assistant, decomposing the requirements from the PRD, UX Design, Architecture, and the PRD Addendum into implementable stories.

## Requirements Inventory

### Functional Requirements

| ID | Requirement | Must be true |
|---|---|---|
| FR-1 | Account creation and login | bcrypt_sha256 hashing; JWT sent with every request; no password reset or email verification in v1 |
| FR-2 | Server-side tenancy filtering | `user_id` applied at the query layer on every read/write, never client-supplied. Launch blocker |
| FR-3 | Upload and parse PDF / MD / HTML | Unsupported formats rejected before processing; output is passages tagged `document_id`, `chapter`, `chunk_index` |
| FR-4 | Ingestion status visibility | Exactly five states: Uploaded / Extracting / Graphing / Ready / Failed. Failed shows a reason and stays in the list |
| FR-5 | Entity extraction into the unified graph | One graph per user; matching entities merge rather than duplicate; fixed type set |
| FR-6 | Ingestion dedupe | Byte-identical re-upload (content hash) triggers no re-parse, no embedding call, no LLM call |
| FR-7 | List and inspect documents | Own documents only; detail view shows metadata and chapters |
| FR-8 | Delete a document | Passages leave the vector index immediately; graph entities deliberately not pruned; UI states this at delete time |
| FR-9 | Answer with structured citations | Every claim-bearing sentence traceable to ≥1 citation; citations name a specific document *and* passage |
| FR-10 | Explicit refusal below threshold | Short-circuits before the generation call and returns an explicit refusal |
| FR-11 | Document scoping | All documents or a chosen subset; default is all; out-of-scope passages never appear as citations |
| FR-12 | Graph visualization | Interactive node-link view, scoped to own `user_id` |
| FR-13 | Evaluation harness | One command, service layer directly, 15–20 pairs; reports accuracy and refusal rate as numbers |
| FR-14 | Drag-and-drop upload with progress | Drop or browse; each file progresses independently, not as one blocking batch |
| FR-15 | Light/dark theme | Manual toggle, no OS detection; persists across sessions; every screen works in both |
| FR-16 | Account deletion | Explicit confirmation; removes documents, vector entries, graph data and account record; logs the user out |

### NonFunctional Requirements

| ID | Area | Target |
|---|---|---|
| NFR-1 | Performance | p95 < 8s end-to-end (retrieval + generation) |
| NFR-2 | Capacity | Documents up to 20MB; no cap on document count per user |
| NFR-3 | Browsers | Latest two of Chrome, Firefox, Edge, Safari; no legacy support |
| NFR-4 | Reliability | Three managed services are external dependencies; demo fallback is offline-validated graph queries plus a local export |
| NFR-5 | Security | Cross-tenant leakage is a launch blocker, verified with two test accounts — not a bug to triage later |
| NFR-6 | Evaluation quality | 15–20 question/answer pairs, authored incrementally as ingestion becomes functional |
| NFR-7 | Cost | All services on free tiers; zero-cost reproducibility is a constraint, not a preference |
| NFR-8 | Accessibility | WCAG 2.2 AA floor; never colour alone; focus rings visible in both themes; tab order follows reading order |

**Success Metrics** — what the Evaluation Harness epic must actually prove:

| ID | Target | Validates |
|---|---|---|
| SM-1 | ≥80% accuracy on answerable questions *(placeholder pending a baseline run)* | FR-9, FR-10, FR-13 |
| SM-2 | 100% refusal on genuinely unanswerable questions, no fabrication | FR-10, FR-13 |
| SM-3 | Zero cross-tenant leakage, verified with two test accounts | FR-2 |
| SM-C1 | Counter-metric: refusal rate on *answerable* questions must not rise while chasing SM-2 | Guards SM-2 |

SM-3's test must cover leakage *through the generated answer* — that the LLM never blends another user's retrieved context — not only that a raw unauthorized query is blocked. The PRD names only the second; these are different failure modes.

### Additional Requirements

**Architecture decisions.** Each is a rule stories must satisfy, not advice.

| ID | Rule |
|---|---|
| AD-1 | **Saga-lite ingestion.** Fixed write order Weaviate → Neo4j. On Neo4j failure, delete the just-written Weaviate objects, then mark the document `Failed` with a reason. The status row is also the retry lock: retry only from `Failed`, never during `Extracting`/`Graphing`. The `documents` module is the **sole writer** of the status field, so ingestion and account-deletion cannot race on it |
| AD-2 | **Tenancy via mandatory shared DAL.** All Weaviate/Neo4j access goes through `shared/data_access/`; no module hand-writes raw queries. Weaviate shape is flat: `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding` — no nested metadata dict. Neo4j shape: entity `name` + `type`, typed relationships. Any future NL-to-Cypher must inject `user_id` server-side, never trusting LLM output |
| AD-3 | Every route declares a Pydantic `response_model`; all errors are `HTTPException` → `{"detail": ...}`. No custom error envelope |
| AD-4 | Entity merge is **exact string match only** — no fuzzy or LLM-assisted merge in v1 |
| AD-5 | Frontend shared state (auth, theme, chat scope) lives in React Context, not Redux |
| AD-6 | **`shared/llm_client/` is the only path to OpenRouter.** The refusal short-circuit happens before it is ever called. Wrapper failures (timeout, retry exhaustion, OpenRouter error) surface as ordinary service errors per AD-3 (e.g. `503`) — **never** as the product's "I don't know". `kg` never calls it |
| AD-7 | Frontend on Vercel Hobby; backend on Render free (15-min idle spin-down, ~1 min cold start) |
| AD-8 | Local dev plus one prod environment, no staging. Secrets via environment variables only, never committed |
| AD-9 | Account deletion is a full cascade hard-delete through the same shared DAL, with AD-1's rollback discipline if one store fails partway |

**Also binding:**

- **No starter template exists** — Epic 1 Story 1 scaffolds `backend/` and `frontend/` from scratch. Day 1 is scaffolding only, no exploratory work.
- **Module layout:** vertical-slice modular monolith — `auth`, `documents`, `chat`, `kg`, each owning `routes.py` / `service.py` / `repository.py`. Hexagonal/ports-and-adapters explicitly rejected.
- **Stack (pinned, verified Aug 2026):** Python 3.12+, FastAPI 0.141.1, Pydantic v2, SQLAlchemy 2.0.51, Alembic 1.19.0, weaviate-client 4.22.0, neo4j 6.2, React 19.2.x, Vite 8.2.1, Tailwind, react-force-graph 1.48.2, JWT + bcrypt, OpenRouter.
- **Definition of Done:** every §6.1 item demonstrable end-to-end; every answer shows ≥1 source; unanswerable questions refuse, verified by the Evaluation Set; cross-tenant isolation verified with two accounts; evaluation runs in one command and reports a number.
- **Sequencing risks:** prepare a short Cypher primer before graph-write stories (team is unfamiliar with it); keep the extraction type set small; validate demo graph queries offline with a local-export fallback.

**Out of scope — what stories must NOT build (PRD §6.2):**

Chapter-level filtered search (chapters stay read-only metadata) · query history · clickable citations · answer confidence badge *(rejected outright, not deferred)* · "explain this answer" trace · live entity preview · user-editable graph corrections · NL querying over the graph · reference-counted graph deletion · password reset / email verification · account recovery after deletion · library-wide document search and category grouping *(see OD-5)* · hybrid BM25+vector · raw-context panel · conversation export · staging environment.

**Open decisions.** Each is tied to the story it blocks.

| ID | Status | Decision or blocker |
|---|---|---|
| OD-1 | 🔴 OPEN | **Entity/relationship type list (FR-5).** Blocks Story 2.4 — extraction prompts cannot be written without it |
| OD-2 | 🔴 OPEN | **FR-10 threshold value.** Mechanism fixed by AD-6; the number is resolved inside Story 3.2 and lives as config in the LLM wrapper |
| OD-3 | 🔴 OPEN | **SM-1 numeric target.** 80% is a placeholder; confirmed in Story 6.1 after a baseline run |
| OD-4 | 🔴 OPEN | Whether FR-8's delete/graph warning needs a stronger v1 mitigation. PM call, not architecture's |
| OD-5 | ✅ RESOLVED | Chat document search is a **filter over the scope panel only**, not library search. Removes the §6.2 conflict; UX-DR10 amended |
| OD-6 | ✅ RESOLVED | Scope panel **not pre-checked**. Empty selection still means all documents (FR-11 default) — and must visibly read that way, or it looks like "nothing selected" |
| OD-7 | ✅ RESOLVED | Hash match shows "already uploaded" and surfaces the existing document. No second row, no reprocessing. Keyed on content hash, not filename. Replace-by-filename rejected as scope beyond FR-6 |

**Stale references in source docs — do not propagate:** `addendum.md` cited a non-existent "FR-18" (account deletion is FR-16) and carried a "two pages, no visual polish" mitigation predating the UX design — both now corrected. The `.memlog.md` files and `reconcile-prd.md` still use an older FR numbering; only `prd.md`'s FR-1…FR-16 is authoritative.

### UX Design Requirements

| ID | Requirement |
|---|---|
| UX-DR1 | **Authenticated shell** — fixed 220px sidebar + fluid content. Order: User Settings, Documents, Chat, Graph Preview; Exit bottom-anchored and separated. Exactly one active item |
| UX-DR2 | **Theme tokens app-wide** — light "softened baby-blue" + dark "Soft Dark" (dimmed charcoal, not near-black). Every screen including auth pages works in both |
| UX-DR3 | **Citation chip** — own locked colour identity, never a generic badge. Renders `Ch. {chapter}, {document_filename}` inline in assistant bubbles; reused as the file-type tile in upload rows. Must be programmatically distinguishable, not just visually |
| UX-DR4 | **Status pill** — exactly the five FR-4 states verbatim. Colour + text always paired, never colour alone. Used in Documents table, Detail, and Chat scope panel |
| UX-DR5 | **Chat bubbles** — user right-aligned primary fill, sharp trailing corner; bot left-aligned surface fill, sharp leading corner. Robot mascot in CSS shapes, small, left-aligned, 5px overlap on the composer, `aria-hidden` |
| UX-DR6 | **Upload modal** — dropzone takes drag-and-drop *and* click-to-browse. Per-file name, size/"Queued", independent progress. Closes only on Cancel or once all files resolve; closing never cancels in-flight uploads; list refreshes on close |
| UX-DR7 | **Document table** — Title, Type, Status, Uploaded, trash icon. Row click opens Detail; the trash icon is a separate target that does not navigate |
| UX-DR8 | **Document Detail** — title, status, date, type/size, chapter count, passage count, chapter list. Fields show pending/unavailable until Ready, never fabricated zeros. Delete opens an inline confirm, not a modal |
| UX-DR9 | **Chat layout** — `1fr` chat window + fixed 260px scope panel, 20px gap. Composer is one row, input and Ask at equal height. Scope panel has per-document checkboxes; non-Ready ones disabled with status inline and in `aria-label` |
| UX-DR10 | **Scope filter + "Select all"** above the chat window. "Select all" scopes every Ready document at once. *(Amended by OD-5: filters the scope panel only, not the library)* |
| UX-DR11 | **Graph canvas** — read-only node-link diagram. Circles sized by entity prominence, soft shadow, centered white labels. No click-to-query, drag, or editing. Strictly own graph |
| UX-DR12 | **Settings page** — four independent cards (Profile, Change Password, Appearance, Delete Account) in a two-column grid. Each saves on its own. Delete Account uses the danger-tinted treatment |
| UX-DR13 | **Toggle switch** — 40×22px pill track, border off / primary on, white thumb. Used for the theme toggle |
| UX-DR14 | **Delete confirmation** (documents and account) — always an explicit inline confirm, never single-click destroy. Plain-language deletion boundary. Cancel/Confirm reachable by keyboard and screen reader |
| UX-DR15 | 🔴 **Refusal bubble — OPEN GAP, no mock.** Must be visually *and* semantically distinct from a grounded answer, not just a bubble with zero citations. Needs a design decision at implementation |
| UX-DR16 | 🔴 **Failed ingestion state — OPEN GAP, no mock.** Must show a readable reason without dropping the row. Placement (row-inline vs Detail-only) undecided |
| UX-DR17 | 🔴 **Empty library — OPEN GAP, no mock.** Assumed: "No documents yet." with Upload still primary-actionable. Do not over-design beyond this |
| UX-DR18 | **Accessibility floor** — WCAG 2.2 AA. Status never colour-only; focus rings visible in both themes; tab order = sidebar → heading → content → secondary panels |
| UX-DR19 | **Voice** — plain, declarative, specific about why. FR-4's status words verbatim. No hedging, apology filler, or decorative emoji (sidebar icons excepted) |
| UX-DR20 | **Modal pattern** — centered, 520px max-width, dimmed diagonal-hatched backdrop, header/body/footer with right-aligned actions. Never modal-on-modal |

**Accessibility review findings** (`review-accessibility.md`). Three of four light-mode contrast failures were already fixed in DESIGN.md — primary → `#3861A8` (6.10:1), sidebar text → `#E4ECFA`, pill text → `#0C7A47`/`#8A5200`. These remained:

| ID | Status | Requirement |
|---|---|---|
| UX-DR21 | ⚠️ **ACCEPTED DEVIATION** | **Citation-chip contrast ships as-is.** `#4A7FE0` on `#D1EEFE` = 3.22:1 against a 4.5:1 requirement (11.5px/700, no large-text exemption). Team decision 2026-08-11: do not re-tune. **Consequence:** a knowing exception to NFR-8's AA floor, on the token DESIGN.md calls the most important in the product. Light mode only — dark mode passes at 5.63:1. No DoD check tests accessibility, so nothing will surface this again |
| UX-DR22 | 🔴 BLOCKING | **Status-pill tint tokens unspecified.** Text colours exist for only 2 of 5 states; the background tint has no token value at all. All five need an explicit tint+text pair clearing 4.5:1 |
| UX-DR23 | 🔴 BLOCKING | **No focus-ring token.** EXPERIENCE.md mandates visible themeable focus rings, but no token exists and no mock defines any `:focus` rule. Needs a token distinct from `border`, clearing 3:1 against `bg`, `surface`, `surface-dark` |
| UX-DR24 | In scope | **Chat live region** — `aria-live="polite"` or `role="log"`, so an arriving answer is announced. Turns need semantic structure beyond alignment and bubble shape |
| UX-DR25 | In scope | **Modal a11y** — `role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, defined initial focus, focus return to the trigger on close |
| UX-DR26 | In scope | **Inline confirm a11y** — announced on appearance; boundary text programmatically tied to Confirm/Cancel so it is read *before* acting; defined focus movement, Escape behaviour, and focus return |
| UX-DR27 | In scope | **Disabled-checkbox labelling** — non-Ready documents must carry status programmatically. The mock violates EXPERIENCE.md's own rule, leaving "(processing)" in an unassociated sibling span |
| UX-DR28 | In scope | **Remaining items** — semantic element for citations, not a bare styled span; pill text as real DOM text; graph needs a stated keyboard position and must not encode type by colour alone; `prefers-reduced-motion`; 200% zoom reflow check on the fixed-width columns |

### FR Coverage Map

| FR | Epic | Where it lands |
|---|---|---|
| FR-1 | 1 | Registration and login — bcrypt_sha256, JWT session |
| FR-2 | 1 | Server-side `user_id` filtering, enforced structurally via the shared DAL |
| FR-3 | 2 | Upload and parse PDF/MD/HTML into tagged passages |
| FR-4 | 2 | Status ledger and its five-state vocabulary across three surfaces |
| FR-5 | 2 | Entity extraction merged into the unified graph, exact-match |
| FR-6 | 2 | Content-hash dedupe |
| FR-7 | 2 | Document list and detail |
| FR-8 | 2 | Deletion with the vector-removed / graph-persists boundary |
| FR-9 | 3 | Grounded answers with structured citations |
| FR-10 | 3 | Refusal below threshold, short-circuited before the LLM call |
| FR-11 | 3 | Document scoping |
| FR-12 | 4 | Node-link graph visualization |
| FR-13 | 6 | One-command evaluation harness |
| FR-14 | 2 | Drag-and-drop upload with per-file progress |
| FR-15 | **1 + 5** | Tokens, palettes, ThemeContext and persistence in Epic 1 so screens are built theme-aware; the Settings toggle completes it in Epic 5 |
| FR-16 | 5 | Account deletion as a full cascade across all three stores |

All 16 mapped. FR-15 is the only one split across epics — deliberately, to avoid retrofitting theming onto every screen at the end.

## Epic List

### Epic 1: Secure Access & App Foundation

A visitor can create an account, log in, and trust that their data is structurally isolated from every other user's. Establishes the scaffolding both later epics build on: the `backend/` and `frontend/` project skeletons from scratch (no starter template exists), the mandatory shared data-access layer that makes tenancy a structural guarantee rather than a convention, and the design-token system with both light and dark palettes.
**FRs covered:** FR-1, FR-2, FR-15 (foundation)

**Implementation notes:** Scaffolding is Story 1 — there is no starter template, and the addendum's risk register allocates Day 1 to scaffolding with no exploratory work. The shared DAL (AD-2) and its Weaviate/Neo4j shape contracts must be established here even though only the Postgres path is exercised by auth, because two developers work in parallel against those contracts from Epic 2 onward. Resolve all three blocking token gaps (UX-DR21 citation contrast, UX-DR22 status-pill tints, UX-DR23 focus ring) while the palette is being built, rather than discovering them per-component later. SM-3 is first verified here with two test accounts.

### Epic 2: Document Ingestion & Library

A user can upload documents, watch them move through ingestion to a queryable state, inspect what was extracted, and delete what is stale — understanding exactly what deletion does and does not remove.
**FRs covered:** FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-14

**Implementation notes:** The highest-risk epic. Carries AD-1's saga-lite consistency rule: fixed Weaviate-then-Neo4j write order, active compensating rollback of the Weaviate write on Neo4j failure, and the status row doubling as a retry lock. Ingestion and library are one epic because they share the same `documents/` module files and the same Documents page — splitting them would produce exactly the file-churn pattern the epic design principles forbid. **Blocked until OD-1 (the fixed entity/relationship type list) is decided** — extraction prompts cannot be written without it. OD-7 (dedupe UX) and UX-DR22 (pill tint tokens, if not closed in Epic 1) surface here.

### Epic 3: Grounded Chat Q&A

A user can ask a question in plain language against a chosen scope of their documents and receive an answer whose every claim is traceable to a specific passage — or an explicit, honest refusal when the evidence isn't there.
**FRs covered:** FR-9, FR-10, FR-11

**Implementation notes:** The product's core promise. AD-6 governs: the relevance-threshold check happens in `chat/service.py` *before* the shared LLM wrapper is invoked, and the wrapper's own failures (timeout, retry exhaustion, OpenRouter error) surface as ordinary service errors per AD-3 (e.g. 503) — never as the product's "I don't know". Open items landing here: OD-2 (threshold value), OD-5 (document search bar scope boundary), OD-6 (whether the scope panel is pre-checked), UX-DR15 (the refusal bubble has no mock and must be designed), UX-DR21 (citation chip contrast, if not closed in Epic 1).

### Epic 4: Knowledge Graph View

A user can visually explore the unified knowledge graph built from their own documents, seeing the entities and relationships that connect information across files.
**FRs covered:** FR-12

**Implementation notes:** Small and genuinely standalone — a pure `user_id`-scoped Cypher read through the DAL plus one frontend page. The `kg` module never touches the LLM wrapper. Depends on Epic 2 having populated the graph, but shares no files with it, so it can run in parallel with Epics 3 and 5. Watch the accessibility note in UX-DR28: entity type must not be encoded by node colour alone, and node interactivity (if any) needs a keyboard equivalent.

### Epic 5: Account & Appearance Settings

A user can manage their profile, change their password, switch the application's appearance, and permanently delete their account with full confidence about what is removed.
**FRs covered:** FR-16, plus the Appearance toggle surface completing FR-15

**Implementation notes:** Carries AD-9's full cascade hard-delete across Postgres, Weaviate, and Neo4j, through the same shared DAL as every other path, with the same compensating-rollback discipline as ingestion if a store fails partway. Sequenced after Epic 2 because there is nothing to cascade until documents and graph entities exist. The four Settings cards each save independently. Deletion is immediate and final — no recovery or undo window in v1.

### Epic 6: Evaluation Harness

The team can prove with numbers, in a single command, that GraphMind answers accurately when it can and refuses honestly when it cannot.
**FRs covered:** FR-13

**Implementation notes:** The Definition-of-Done gate. Invokes the service layer directly rather than going through the UI, so it stays fast and independent of frontend state. Measures SM-1 (answerable-question accuracy, ≥80% placeholder target), SM-2 (100% refusal correctness on genuinely unanswerable questions), and SM-C1 as a counter-metric guarding against over-refusal. Per NFR-6 the 15–20 question set is authored incrementally as ingestion becomes functional, not in one batch at the end. OD-3 (confirming the numeric SM-1 target) resolves here, once a baseline run is possible. SM-3's cross-tenant verification should include the answer-level leakage case, not only blocked raw queries.

## Epic 1: Secure Access & App Foundation

A visitor can create an account, log in, and trust that their data is structurally isolated from every other user's. This epic also lays the foundation every later epic builds on: the backend and frontend skeletons (there is no starter template), the design-token system with both palettes, and the shared data-access layer that makes tenancy a structural guarantee rather than a convention.

### Story 1.1: Running project skeleton

As a developer,
I want a backend and frontend skeleton that run and talk to each other,
So that every later story has a working place to add behaviour instead of re-deciding project structure mid-build.

**Acceptance Criteria:**

**Given** a clean checkout of the repository
**When** I follow the setup steps
**Then** the FastAPI backend starts locally and the React/Vite frontend dev server starts
**And** the frontend successfully calls a backend health endpoint and renders its response

**Given** the backend project structure
**When** I inspect it
**Then** the four feature-module directories `auth/`, `documents/`, `chat/`, `kg/` each exist with `routes.py`, `service.py`, `repository.py`
**And** `shared/data_access/` and `shared/llm_client/` exist as the only infrastructure paths, per the architecture's structural seed

**Given** any route added to the backend
**When** it returns a success response
**Then** it declares a Pydantic `response_model`
**And** every error path returns FastAPI's default `HTTPException` shape `{"detail": ...}`, with no custom error envelope (AD-3)

**Given** the version table in the architecture spine
**When** dependencies are installed
**Then** the pinned versions are used (FastAPI 0.141.1, Pydantic v2, SQLAlchemy 2.0.51, Alembic 1.19.0, weaviate-client 4.22.0, neo4j 6.2, React 19.2.x, Vite 8.2.1, react-force-graph 1.48.2)
**And** Python is 3.12 or newer

**Given** the project requires service credentials
**When** configuration is loaded
**Then** every secret comes from an environment variable
**And** no secret value is committed to the repository (AD-8)

### Story 1.2: Design-token foundation and dual-theme rendering

As a user,
I want the interface to render legibly and correctly in both light and dark appearance,
So that I can read answers and documents comfortably in long sessions without straining.

**Acceptance Criteria:**

**Given** the palette, typography, spacing and radius values specified in DESIGN.md
**When** the token system is configured
**Then** all light-mode and dark-mode values are available as named tokens
**And** no component hardcodes a raw hex value outside the token definitions

**Given** the citation chip's light-mode pair is a knowingly accepted deviation from the AA floor (UX-DR21)
**When** the citation tokens are configured
**Then** they use DESIGN.md's specified values unchanged (`#4A7FE0` on `#D1EEFE`)
**And** no re-tuning is attempted, so the decision is not silently reversed during implementation

**Given** the ingestion pipeline has five states
**When** the status-pill tokens are defined
**Then** each of Uploaded, Extracting, Graphing, Ready and Failed has an explicit background-tint and text-colour pair
**And** each pair clears 4.5:1 (UX-DR22)

**Given** EXPERIENCE.md requires focus rings visible and themeable across both palettes
**When** a focus-ring token is defined
**Then** it clears 3:1 non-text contrast against `bg`, `surface` and `surface-dark`
**And** it is visible on every interactive element in both themes (UX-DR23)

**Given** the application is rendering in one theme
**When** the theme is switched at runtime through the shared React Context (AD-5)
**Then** every rendered surface updates immediately
**And** no screen renders correctly in only one of the two themes

**Given** a user with `prefers-reduced-motion` set
**When** transitions or progress animations would play
**Then** they are suppressed (UX-DR28)

### Story 1.3: Account registration

As a visitor,
I want to create an account,
So that I can upload documents that only I can ever see.

**Acceptance Criteria:**

**Given** I am on the Registration page
**When** I submit valid credentials
**Then** an account is created
**And** my password is stored hashed with bcrypt_sha256, never in plaintext (FR-1)

**Given** no database schema exists yet
**When** this story is implemented
**Then** an Alembic migration creates only the `users` table
**And** no other table is created ahead of the story that needs it

**Given** I submit invalid or incomplete input
**When** the request is rejected
**Then** the error returns as `HTTPException` with a `{"detail": ...}` body
**And** the message is plain and declarative, with no apologetic filler or emoji (UX-DR19)

**Given** password reset and email verification are out of v1 scope
**When** registration is built
**Then** no reset or verification flow is implemented

**Given** the Registration page is outside the authenticated shell
**When** it renders
**Then** it displays correctly in both light and dark themes, like every other screen (UX-DR2)

### Story 1.4: Login and JWT session

As a registered user,
I want to log in and stay logged in across requests,
So that I can reach my own workspace without re-authenticating on every action.

**Acceptance Criteria:**

**Given** I submit valid credentials on the Login page
**When** authentication succeeds
**Then** a JWT is issued
**And** it is sent in the `Authorization` header on every subsequent request (FR-1)

**Given** I submit credentials that do not match an account
**When** authentication fails
**Then** I receive a clear error and no session is established

**Given** a request carrying a JWT
**When** a protected endpoint handles it
**Then** `user_id` is resolved server-side from the token
**And** no client-supplied user identifier is ever trusted for this (FR-2)

**Given** a JWT that is expired, malformed, or absent
**When** a protected endpoint is called
**Then** the request is rejected with a 401 before any data access occurs

### Story 1.5: Authenticated shell and tenancy-enforced data access

As a logged-in user,
I want a consistent navigation shell and a guarantee that my data is reachable only by me,
So that I can move around the product confidently knowing isolation is enforced by the system, not by the screen I happen to be on.

**Acceptance Criteria:**

**Given** I am authenticated
**When** I land in the application
**Then** the fixed 220px sidebar renders with User Settings, Documents, Chat and Graph Preview, and Exit bottom-anchored and visually separated
**And** exactly one nav item shows the active state, matching the current page (UX-DR1)

**Given** any read or write of user-owned data
**When** it is performed
**Then** it goes through a shared repository function in `shared/data_access/` with `user_id` applied server-side
**And** no feature module hand-writes a raw query against a data store (AD-2)

**Given** two developers will build the `documents` and `chat` modules in parallel from Epic 2 onward
**When** the shared data-access layer is established
**Then** the Weaviate passage shape (`chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`, flat, no nested metadata dict) and the Neo4j entity shape (`name` + `type`, typed relationships between entity references) are defined and documented
**And** the forward-looking rule that any future natural-language-to-Cypher query must have `user_id` injected server-side is recorded alongside them

**Given** two test accounts exist
**When** account B requests account A's account-scoped data by identifier through any endpoint
**Then** the request returns no data belonging to account A (first verification of SM-3; re-verified against documents in Epic 2)

**Given** I navigate any authenticated page with the keyboard
**When** I tab through it
**Then** focus order follows sidebar, then page heading, then primary content, then secondary panels
**And** the focus indicator is visible in both themes (UX-DR18)

**Given** I am authenticated
**When** I select Exit
**Then** my session ends and I am returned to the Login page

**Given** the shell's fixed 220px sidebar beside a fluid content area
**When** the browser is zoomed to 200% on a typical laptop viewport
**Then** content reflows without horizontal scrolling or clipping (WCAG 1.4.4, UX-DR28)
**And** no CSS `order` or `row-reverse` is applied to any layout carrying interactive content, so DOM order and visual order cannot silently diverge (UX-DR18)

## Epic 2: Document Ingestion & Library

A user can upload documents, watch them move through ingestion to a queryable state, inspect what was extracted, and delete what is stale — understanding exactly what deletion does and does not remove. This is the highest-risk epic: it carries the dual-store write path and its compensating rollback, and it is the only place where partial state across Weaviate and Neo4j is possible.

### Story 2.1: Upload documents with drag-and-drop and per-file progress

As a user,
I want to drop a batch of files onto the page and watch each one upload independently,
So that I can get a whole project's documents into GraphMind in one go without babysitting them one at a time.

**Acceptance Criteria:**

**Given** I am on the Documents page
**When** I open the Upload modal
**Then** it renders centered at 520px max-width on the dimmed diagonal-hatched backdrop with a header/body/footer structure and footer-right-aligned actions
**And** no second modal can open on top of it (UX-DR20)

**Given** the Upload modal is open
**When** I drop files onto the dropzone or click through to the file browser
**Then** both paths accept the files equally (FR-14)

**Given** several files are queued
**When** they upload
**Then** each row shows its own filename, its size or "Queued" before it starts, and its own progress indicator
**And** a slow file does not block the others from progressing (FR-14)

**Given** I add a file in an unsupported format
**When** it is validated
**Then** it is rejected with a clear, plainly-worded reason before any processing starts (FR-3, UX-DR19)

**Given** I add a file larger than 20MB
**When** it is validated
**Then** it is rejected with a reason naming the limit (NFR-2)

**Given** files have finished uploading
**When** the modal closes, whether by explicit Cancel or because every queued file resolved
**Then** the Documents list refreshes and the new rows appear with "Uploaded" status
**And** closing the modal does not cancel uploads already in flight (UX-DR6)

**Given** no document schema exists yet
**When** this story is implemented
**Then** an Alembic migration creates only the `documents` table, including the ingestion-status field using the FR-4 vocabulary verbatim

**Given** the modal is open
**When** a screen-reader or keyboard user interacts with it
**Then** it exposes `role="dialog"`, `aria-modal="true"` and `aria-labelledby` pointing at its heading, traps Tab within itself, places initial focus deliberately, and returns focus to the Upload button on close
**And** the background is not interactive while it is open (UX-DR25)

### Story 2.2: Document library and detail view

As a user,
I want to see everything I have uploaded and open any one of them for detail,
So that I know what GraphMind can actually answer from before I start asking.

**Acceptance Criteria:**

**Given** I have uploaded documents
**When** I open the Documents page
**Then** the table lists Title, Type, Status, Uploaded date and a trash icon per row (UX-DR7)

**Given** two test accounts each with documents
**When** account B loads the Documents page
**Then** not one of account A's documents appears, through this or any other endpoint (FR-7, SM-3 re-verified against real documents)

**Given** a document row
**When** I click it anywhere outside the trash icon
**Then** Document Detail opens
**And** clicking the trash icon does not navigate (UX-DR7)

**Given** Document Detail is open for a Ready document
**When** it renders
**Then** it shows title, status, upload date, file type and size, chapter count, passages-indexed count, and the full chapter list with a passage count per chapter (UX-DR8)

**Given** Document Detail is open for a document that has not reached Ready
**When** it renders
**Then** the metadata fields show as pending or unavailable
**And** they are never fabricated as zeros (UX-DR8)

**Given** any surface showing ingestion status
**When** a status renders
**Then** it uses the pill token pair defined in Story 1.2, pairing a text label with its tint, never colour alone
**And** the label is real selectable DOM text, not a pseudo-element or icon-font glyph (UX-DR4, UX-DR28)

**Given** I have uploaded nothing yet
**When** I open the Documents page
**Then** a plain "No documents yet." message appears in the table area
**And** the Upload button remains primary-actionable (UX-DR17)

### Story 2.3: Parse and index documents into the vector store

As a user,
I want my uploaded documents broken down and indexed,
So that a question can later find the specific passage that answers it rather than just the file it lives in.

**Acceptance Criteria:**

**Given** an uploaded PDF, Markdown or HTML document
**When** parsing runs
**Then** it produces one or more passages, each tagged with `document_id`, `chapter` and `chunk_index` (FR-3)

**Given** parsed passages
**When** they are written to the vector store
**Then** the write goes through a shared repository function in `shared/data_access/`
**And** it uses the flat agreed shape `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`, with no nested metadata dict
**And** no raw Weaviate query is written inside the `documents` module (AD-2)

**Given** a document begins parsing
**When** its status is updated
**Then** it advances from Uploaded to Extracting, and the change is visible on the Documents table (FR-4)

**Given** any passage write
**When** it executes
**Then** `user_id` is applied server-side from the JWT, never from a client-supplied value (FR-2)

### Story 2.4: Extract entities into the unified graph with compensating rollback

As a user,
I want the concepts and connections in my documents merged into one graph across all of them,
So that GraphMind can answer questions that require joining facts from several files, not just matching text in one.

**⚠ Blocked until OD-1 is decided** — the fixed entity/relationship type list must exist before extraction prompts can be written.

**Acceptance Criteria:**

**Given** a document whose passages are indexed
**When** entity and relationship extraction runs
**Then** every OpenRouter call goes through `shared/llm_client/`
**And** the `documents` module never calls OpenRouter directly (AD-6)

**Given** extraction runs
**When** it identifies entities and relationships
**Then** it is constrained to the fixed type set agreed in OD-1, not an open-ended vocabulary (FR-5)

**Given** an extracted entity whose name exactly matches an existing entity in my graph
**When** it is merged
**Then** the two become one node rather than duplicating
**And** near-matches such as "TechCorp" and "TechCorp Supplies" remain distinct nodes, since merge is exact-string-match only (AD-4)

**Given** the two ingestion writes
**When** they execute
**Then** the Weaviate write always happens first and the Neo4j write second, in that fixed order (AD-1)

**Given** the Neo4j write fails
**When** the failure is handled
**Then** the Weaviate objects just written for that document are actively deleted
**And** the document is then marked Failed with a human-readable reason
**And** no orphaned partial state survives the failed ingestion (AD-1)

**Given** ingestion progresses normally
**When** statuses advance
**Then** the document moves Extracting to Graphing to Ready (FR-4)

**Given** a document currently in Extracting or Graphing
**When** a retry of its ingestion is attempted
**Then** it is refused, because retry is permitted only from the Failed state
**And** a retry therefore can never race an in-flight rollback on the same document (AD-1)

**Given** the ingestion-status field
**When** any code path writes to it
**Then** that path is inside the `documents` module, which is its sole owner (AD-1)

### Story 2.5: Failed ingestion surfaced with a readable reason

As a user,
I want to see plainly when a document failed to process and why,
So that a file I uploaded never just quietly stops working without explanation.

**Acceptance Criteria:**

**Given** a document whose ingestion failed
**When** the Documents list renders
**Then** the document is still present in the list and is never silently dropped (FR-4)

**Given** no mock exists for this state
**When** this story is implemented
**Then** the placement of the failure reason — inline in the table row versus only in Document Detail — is decided and the decision recorded
**And** a human-readable reason is shown wherever that decision places it (FR-4, UX-DR16)

**Given** a Failed document
**When** its status pill renders
**Then** it uses the danger tint and text pair defined in Story 1.2, with the text label always present alongside the colour

**Given** a Failed document
**When** I retry its ingestion
**Then** the retry is accepted, since Failed is the one state a retry is permitted from (AD-1)

### Story 2.6: Content-hash dedupe on upload

As a user,
I want GraphMind to recognise a document it has already processed,
So that re-uploading the same file does not quietly burn the project's free-tier LLM budget doing identical work twice.

**Acceptance Criteria:**

**Given** I upload a file whose content hash matches one of my existing documents
**When** it is processed
**Then** no second document row is created, nothing is re-parsed, and no embedding or LLM call is made (FR-6)

**Given** a content-hash match
**When** the upload modal updates that file's row
**Then** it shows an explicit "already uploaded" message and surfaces the existing document (OD-7)

**Given** a byte-identical file uploaded under a different filename
**When** it is checked
**Then** it is still recognised as a duplicate, because dedupe is keyed on content hash and not on filename

**Given** an edited version of a document uploaded under its original filename
**When** it is checked
**Then** its hash differs, dedupe does not fire, and it is ingested as a genuinely new document

**Given** dedupe exists specifically to protect the zero-cost constraint
**When** a hash match occurs
**Then** no OpenRouter call and no embedding API call is made for that file (NFR-7)

### Story 2.7: Delete a document with an honest deletion boundary

As a user,
I want deleting a document to tell me exactly what it does and does not remove,
So that I am never later surprised to find a deleted document still shaping an answer.

**Acceptance Criteria:**

**Given** a document in the table or open in Document Detail
**When** I click the trash icon or the Delete button
**Then** nothing is deleted yet and an inline confirm box appears instead (UX-DR14)

**Given** the inline confirm box
**When** it renders
**Then** it states plainly that the document's passages are removed from search immediately, and that entities already merged into my Knowledge Graph from this document remain and may still influence future answers
**And** the wording is declarative and specific about why, with no apologetic filler (FR-8, UX-DR19)

**Given** I confirm the deletion
**When** it executes
**Then** the document and its passages and embeddings are removed from the vector index immediately, through the shared data-access layer (FR-8, AD-2)

**Given** I confirm the deletion
**When** it executes
**Then** Knowledge Graph entities and relationships derived from that document are deliberately not pruned (FR-8)

**Given** the deleted document
**When** I next view the library or ask a question
**Then** it no longer appears in the list, in chat scope, or as a citation

**Given** the inline confirm box appears
**When** a screen-reader or keyboard user encounters it
**Then** its appearance is announced, the deletion-boundary text is programmatically associated with the Confirm and Cancel buttons so the warning is read before the action, focus moves into the box, Escape collapses it back to the resting Delete control, and focus returns to the triggering control on close (UX-DR26)

## Epic 3: Grounded Chat Q&A

A user can ask a question in plain language against a chosen scope of their documents and receive an answer whose every claim is traceable to a specific passage — or an explicit, honest refusal when the evidence isn't there. This epic is the product's core promise; everything else exists to make it possible.

### Story 3.1: Ask a question and receive a grounded, cited answer

As a user,
I want to ask a question in plain language and see exactly where each part of the answer came from,
So that I can act on it without having to open the source documents myself to check.

**Acceptance Criteria:**

**Given** I am on the Chat page
**When** the layout renders
**Then** it is a two-column grid with a flexible chat window and a fixed 260px documents-in-scope panel, separated by a 20px gutter
**And** the composer is a single row whose text input and "Ask" button are the same height and vertically centered against each other (UX-DR9)

**Given** this page adds a second fixed-width column beside the shell's 220px sidebar
**When** the browser is zoomed to 200% on a typical laptop viewport
**Then** the three-column result still reflows without horizontal scrolling or clipping (WCAG 1.4.4, UX-DR28)

**Given** I have typed a question
**When** I press Enter or click "Ask"
**Then** either path submits the question

**Given** a submitted question
**When** retrieval runs
**Then** the question is embedded and passages are searched through `shared/data_access/`
**And** the search is filtered by the `user_id` resolved server-side from my JWT, never from a client-supplied value (AD-2, FR-2)

**Given** retrieval returns passages above the relevance threshold
**When** the answer is generated
**Then** the OpenRouter call goes through `shared/llm_client/`
**And** the `chat` module never calls OpenRouter directly (AD-6)

**Given** a generated answer
**When** it is returned
**Then** every claim-bearing sentence is traceable to at least one citation
**And** each citation references a specific document *and* passage, not merely a document-level source (FR-9)

**Given** a citation
**When** it renders inside an assistant message
**Then** it appears as a chip reading `Ch. {chapter}, {document_filename}`, using the citation token pair, visually distinct from the surrounding answer text
**And** it is non-interactive, since jump-to-source is explicitly out of v1 scope (UX-DR3)

**Given** a citation chip
**When** a screen-reader user encounters it
**Then** it is a semantic inline element such as `<cite>` or a labelled span, programmatically distinguishable from ordinary answer text rather than a bare styled `<span>` (UX-DR3, UX-DR28)

**Given** the chat thread
**When** a new assistant message arrives
**Then** it is announced through an `aria-live="polite"` region or equivalent, so a screen-reader user learns of the answer without manually re-navigating (UX-DR24)

**Given** messages in the thread
**When** they render
**Then** my messages are right-aligned with the primary fill and a sharp trailing corner, and assistant messages are left-aligned with the surface fill and a sharp leading corner, the asymmetric corner acting as the sender cue (UX-DR5)

**Given** the Chat page
**When** it renders
**Then** the robot mascot is drawn from CSS shapes, small and left-aligned, overlapping the composer's top edge by 5px
**And** it carries `aria-hidden`, being decorative and non-interactive (UX-DR5)

**Given** the LLM wrapper fails through timeout, retry exhaustion, or an OpenRouter error
**When** the failure surfaces
**Then** it is returned as an ordinary service error per AD-3, such as a 503
**And** it is never rendered as an answer, and never dressed up as the product's "I don't know" refusal (AD-6)

**Given** a question asked end to end
**When** latency is measured across retrieval and generation
**Then** p95 stays under 8 seconds (NFR-1)

### Story 3.2: Explicit refusal when the documents don't support an answer

As a user,
I want GraphMind to tell me plainly when my documents don't contain the answer,
So that I am never handed a confident guess I might act on.

**Acceptance Criteria:**

**Given** a question whose retrieval scores all fall below the defined relevance threshold
**When** it is processed
**Then** the system returns an explicit refusal rather than an answer (FR-10)

**Given** the refusal path
**When** it triggers
**Then** the short-circuit happens in the `chat` module *before* the shared LLM wrapper is invoked
**And** no generation call is made at all, saving both latency and free-tier budget (FR-10, AD-6)

**Given** the relevance threshold has no value yet
**When** this story is implemented
**Then** OD-2 is resolved: a numeric cutoff is chosen, recorded, and lives as a configuration value in the shared LLM-client wrapper rather than being hardcoded in the chat service

**Given** the LLM wrapper's own internal failures
**When** they occur
**Then** they surface as service errors and are never rendered as a refusal
**And** exactly one source of refusal exists in the system (AD-6)

**Given** no mock exists for the refusal bubble
**When** this story is implemented
**Then** the refusal is designed to read as categorically different from a grounded answer
**And** it is not merely an answer bubble with zero citation chips, which could be misread as "answered, just untraceable" (UX-DR15)

**Given** a refusal is returned
**When** a screen-reader user receives it
**Then** it is announced distinctly from a normal answer, not merely styled differently for sighted users (UX-DR15, UX-DR24)

**Given** the refusal copy
**When** it renders
**Then** it is plain and declarative, in the shape of "No supporting evidence found in your documents for this question."
**And** it carries no apology, hedging, emoji, or cute substitute wording (UX-DR19)

**Given** refusal is a designed product behaviour rather than a failure mode
**When** the team evaluates the system
**Then** it is measured as its own metric rather than treated as something to minimise at all costs (feeds SM-2 and SM-C1 in Epic 6)

### Story 3.3: Scope a question to a chosen set of documents

As a user,
I want to narrow a question to particular documents,
So that I can ask about one contract without the answer pulling in everything else I have uploaded.

**Acceptance Criteria:**

**Given** I open the Chat page
**When** the documents-in-scope panel loads
**Then** no document is pre-checked (OD-6)

**Given** no document is checked
**When** I ask a question
**Then** retrieval runs against all of my documents, per FR-11's stated default
**And** the panel communicates this legibly, so that an all-unchecked state reads as "asking across everything" rather than "nothing selected" (OD-6, FR-11)

**Given** I check a subset of documents
**When** I ask a question
**Then** retrieval considers only passages from those documents
**And** passages outside the selected scope never appear as citations (FR-11)

**Given** a document that has not reached Ready
**When** it appears in the scope panel
**Then** its checkbox is disabled with the status noted inline
**And** the checkbox exposes its disabled reason programmatically, for example an `aria-label` incorporating the status, rather than leaving "(processing)" as visual-only text (UX-DR9, UX-DR27)

**Given** the "Select all" affordance
**When** I use it
**Then** every Ready document is brought into scope at once (UX-DR10)

**Given** the document filter control above the panel
**When** I type in it
**Then** it filters only the selectable list within the scope panel
**And** it does not search the document library, since library-wide search remains out of v1 scope (OD-5, UX-DR10 as amended)

**Given** I toggle a document's checkbox
**When** the change registers
**Then** it applies immediately with no separate apply step
**And** it governs the scope of the *next* question I ask (UX-DR9)

## Epic 4: Knowledge Graph View

A user can visually explore the unified knowledge graph built from their own documents, seeing the entities and relationships that connect information across files. Small and genuinely standalone: a pure `user_id`-scoped Cypher read plus one page, sharing no files with the epics around it.

### Story 4.1: Explore the knowledge graph built from my documents

As a user,
I want to see the entities and connections GraphMind extracted from my documents,
So that I can understand what it actually knows before I decide how far to trust its answers.

**Acceptance Criteria:**

**Given** I have documents that reached Ready
**When** I open Graph Preview
**Then** an interactive node-link diagram renders, with entities as nodes and relationships as edges (FR-12)

**Given** the graph query
**When** it runs
**Then** it is a Cypher read issued through `shared/data_access/`, scoped to the `user_id` resolved server-side
**And** no other user's graph data is queryable or renderable from this view under any code path (FR-12, FR-2, AD-2)

**Given** the `kg` module
**When** it serves this view
**Then** it never calls the shared LLM wrapper, because graph visualization is a pure Cypher read (AD-6)

**Given** the graph canvas
**When** it renders
**Then** it uses the specified 480px height, background fill, border hairline and 14px radius
**And** nodes render as circles sized by entity prominence, with centered white label text and the specified soft drop shadow (UX-DR11)

**Given** v1 scope
**When** I interact with the canvas
**Then** the view is read-only: there is no click-to-query, no drag-to-rearrange and no editing (UX-DR11)

**Given** entity types are distinguished on the canvas
**When** they render
**Then** the distinction is not carried by node colour alone — a label, shape or icon conveys the same information (UX-DR28)

**Given** nodes reveal any detail on hover
**When** a keyboard user navigates the canvas
**Then** an equivalent way to reach that detail exists
**And** if nodes carry no interaction at all, that is stated explicitly rather than left ambiguous (UX-DR28)

**Given** I have no documents yet, or none that produced graph entities
**When** I open Graph Preview
**Then** the view says so plainly rather than rendering an empty canvas with no explanation

## Epic 5: Account & Appearance Settings

A user can manage their profile, change their password, switch the application's appearance, and permanently delete their account with full confidence about what is removed. Sequenced after Epic 2 because there is nothing to cascade until documents and graph entities exist.

### Story 5.1: Manage my profile and password

As a user,
I want a single place to see my account details and change my password,
So that I can keep my login current without needing a reset flow or anyone's help.

**Acceptance Criteria:**

**Given** I open User Settings
**When** the page renders
**Then** four independent cards appear in a two-column grid at 900px max width: Profile, Change Password, Appearance, and Delete Account (UX-DR12)

**Given** the four cards
**When** I save one of them
**Then** it saves on its own — saving Profile does not require touching Password (UX-DR12)

**Given** the Change Password card
**When** I submit a new password from my authenticated session
**Then** the password is changed
**And** this is an in-session change, not a forgot-password or reset flow, which remains out of v1 scope (PRD §4.7; FR-1 assumption)

**Given** a newly set password
**When** it is stored
**Then** it is hashed with bcrypt_sha256, exactly as at registration

**Given** the Delete Account card
**When** it renders
**Then** it carries the danger-tinted border and background, visually separated from the other three cards (UX-DR12)

**Given** any validation failure on these cards
**When** the error returns
**Then** it uses the `HTTPException` `{"detail": ...}` shape (AD-3)
**And** the message is plain and declarative (UX-DR19)

### Story 5.2: Choose light or dark appearance and have it remembered

As a user,
I want to pick the appearance I find comfortable and have GraphMind remember it,
So that it looks the way I want every time I return, not just for the current session.

**Acceptance Criteria:**

**Given** the Appearance card
**When** it renders
**Then** a two-state toggle switch appears with a 40×22px pill track, the border colour when off, the primary colour when on, and a white thumb (UX-DR13)

**Given** I select a theme
**When** the selection registers
**Then** it applies immediately across the whole application through the shared React Context, not through prop-drilling or a separate state library (FR-15, AD-5)

**Given** I select a theme
**When** I log out and log back in
**Then** my choice persists, stored against my account rather than only in this browser (FR-15)

**Given** v1 scope
**When** the theme is determined
**Then** it comes solely from my manual choice
**And** no OS-preference auto-detection is applied (FR-15)

**Given** both themes
**When** I move through the product
**Then** every screen renders correctly in each, including the Login and Registration pages
**And** no screen is light-only or dark-only (FR-15, UX-DR2)

### Story 5.3: Delete my account and everything in it

As a user,
I want deleting my account to genuinely remove everything,
So that I can leave without wondering what was quietly left behind in some store.

**Acceptance Criteria:**

**Given** the Delete Account danger zone
**When** I click to delete
**Then** nothing is deleted yet, and an explicit confirmation step appears, matching the document-delete precedent (FR-16, UX-DR14)

**Given** I confirm the deletion
**When** it executes
**Then** my Postgres rows, all of my Weaviate objects, and all of my Neo4j entities and relationships are hard-deleted (FR-16, AD-9)

**Given** the cascade
**When** it runs
**Then** it goes through the same shared data-access layer as every other path
**And** it is not a special-cased raw-query path (AD-9, AD-2)

**Given** the deletion partially fails across stores
**When** the failure is handled
**Then** it follows the same compensating-rollback discipline as ingestion
**And** a silent partial delete is never allowed to stand (AD-9, AD-1)

**Given** the account-deletion path
**When** it executes
**Then** it only ever performs a full cascade delete of all my rows at once
**And** it never partially or concurrently mutates a document's ingestion-status field, which remains solely owned by the `documents` module (AD-1, AD-9)

**Given** the deletion completes
**When** it finishes
**Then** I am logged out immediately

**Given** v1 scope
**When** the deletion is confirmed
**Then** it is immediate and final, with no recovery or undo window (FR-16)

**Given** the confirmation step
**When** a keyboard or screen-reader user reaches it
**Then** Cancel and Confirm are both reachable and clearly labelled
**And** neither depends on hover or a pointer-only affordance (UX-DR14, UX-DR26)

## Epic 6: Evaluation Harness

The team can prove with numbers, in a single command, that GraphMind answers accurately when it can and refuses honestly when it cannot. This is the Definition-of-Done gate for the whole project.

### Story 6.1: Measure answer accuracy and refusal correctness in one command

As a member of the build team,
I want one command that measures how often GraphMind answers correctly and how often it correctly refuses,
So that answer quality is a number we can act on rather than an impression we argue about.

**Acceptance Criteria:**

**Given** the evaluation set
**When** it is complete
**Then** it contains 15–20 question and expected-answer pairs
**And** they span three categories: single-source factual, cross-document synthesis, and unanswerable questions where refusal is the correct outcome (FR-13, NFR-6)

**Given** the evaluation set
**When** it is authored
**Then** it is built up incrementally as ingestion becomes functional, rather than written in one batch at the end of the project (NFR-6)

**Given** the harness
**When** I run it
**Then** a single command executes the whole set (FR-13)

**Given** the harness
**When** it executes
**Then** it invokes the service layer directly rather than driving the UI, so it stays fast and independent of frontend state (FR-13)

**Given** a completed run
**When** results are reported
**Then** accuracy on answerable questions and refusal rate on unanswerable ones are both reported as numbers, not as pass or fail (FR-13)

**Given** a run against the unanswerable category
**When** results are reported
**Then** the system refused 100% of them, with no confident fabrication (SM-2)

**Given** a completed run
**When** results are reported
**Then** the refusal rate on *answerable* questions is reported separately as a counter-metric
**And** improving refusal correctness cannot silently degrade the product by over-refusing without that showing up (SM-C1)

**Given** the first baseline run
**When** its numbers are known
**Then** OD-3 is resolved: the placeholder ≥80% target for SM-1 is either confirmed or replaced with a figure grounded in that baseline

### Story 6.2: Prove that no account can reach another account's data

As a member of the build team,
I want demonstrable proof that one account can never see another's data,
So that we ship against the PRD's single launch-blocking requirement rather than assuming it holds.

**Acceptance Criteria:**

**Given** two test accounts, each with their own uploaded documents
**When** account B exercises every endpoint in the product
**Then** no document, passage, citation, or graph element belonging to account A is ever returned (SM-3, FR-2)

**Given** account B asks a question whose answer would require account A's documents
**When** the answer is produced
**Then** account A's content appears neither in the retrieved context nor anywhere in the generated answer text (SM-3)

**Given** the verification
**When** it is designed
**Then** it covers both the raw-query path and the generated-answer path
**And** these are treated as two distinct failure modes, since an answer can blend another user's context even when direct queries are correctly blocked

**Given** any leak is found
**When** it is triaged
**Then** it is treated as a launch blocker rather than a bug to fix later (NFR-5)

**Given** the Definition of Done
**When** the project is assessed as complete
**Then** this verification is part of it, alongside the single-command evaluation run (addendum DoD)
