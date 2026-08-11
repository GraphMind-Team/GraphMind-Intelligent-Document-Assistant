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

FR-1: Account creation and login — a visitor can create an account and log in; passwords stored hashed (bcrypt_sha256); session represented as a JWT sent with every request. No password reset/email verification in v1.
FR-2: Server-side tenancy filtering — every read/write to the vector index and Knowledge Graph is filtered by `user_id` at the query layer, independent of any client-supplied value. Launch blocker, not best-effort.
FR-3: Upload and parse supported formats — a user can upload PDF, Markdown, or HTML files; unsupported formats rejected before processing; a parsed document produces Passages tagged with `document_id`, `chapter`, `chunk_index`.
FR-4: Ingestion status visibility — each document shows one of Uploaded / Extracting / Graphing / Ready / Failed; Failed includes a human-readable reason and is not dropped from the list.
FR-5: Entity/relationship extraction into the unified graph — extracted entities/relationships merge into the user's single Knowledge Graph; matching entities merge rather than duplicate; extraction scoped to a fixed entity/relationship type set.
FR-6: Ingestion dedupe — re-uploading a byte-identical file (content hash) does not re-run extraction or re-call the LLM/embedding API.
FR-7: List and inspect documents — a user views their document list (status, upload date) and can open one to see metadata/chapters; never sees another user's documents.
FR-8: Delete a document — deletes the document and its Passages/embeddings from the vector index immediately; Knowledge Graph entities/relationships derived from it are NOT retroactively pruned; UI states this boundary at delete time.
FR-9: Answer with structured citations — retrieves relevant Passages and/or traverses the Knowledge Graph, returns an answer with citations to specific supporting Passage(s); every claim-bearing sentence is traceable to ≥1 citation.
FR-10: Explicit refusal below evidence threshold — below a defined relevance threshold, the system short-circuits before the generation call and returns an explicit refusal.
FR-11: Document scoping for a question — a user can ask across all documents or a chosen subset; default scope is all documents; passages outside scope never appear as citations.
FR-12: Graph visualization — a user can view an interactive node-link visualization of their own Knowledge Graph, scoped to their `user_id`.
FR-13: Run the evaluation set and report metrics — a single command runs the Evaluation Set (15-20 Q/A pairs) against the live system via the service layer directly, reporting accuracy and refusal-rate numerically.
FR-14: Drag-and-drop upload with progress — files can be dropped onto the upload area or picked via file browser; each queued file shows independent progress; files upload independently rather than blocking as one batch.
FR-15: Light/dark theme preference — a user can switch between light and dark appearance from User Settings (manual toggle, no OS auto-detection); the choice persists across sessions; all screens render correctly in both themes.
FR-16: Account deletion — a user can permanently delete their own account via an explicit confirmation (danger-zone pattern); on confirmed deletion, documents, vector index entries, Knowledge Graph data, and the account record are removed and the user is logged out.

### NonFunctional Requirements

NFR-1 (Performance): Answer latency target p95 < 8s end-to-end (retrieval + generation), given free-tier LLM/hosting constraints.
NFR-2 (Capacity): Support documents up to 20MB; no hard cap on document count per user for v1.
NFR-3 (Browser support): Latest two versions of evergreen browsers (Chrome, Firefox, Edge, Safari); no legacy browser support.
NFR-4 (Reliability): All three managed services (Weaviate, Neo4j AuraDB, Neon Postgres) are external dependencies; a demo-time network outage risk exists with a fallback plan (offline-validated graph queries / local export).
NFR-5 (Security, binds FR-2/SM-3): Cross-tenant data leakage is a launch blocker, verified with two test accounts — not a bug to triage later.
NFR-6 (Evaluation quality): The Evaluation Set contains 15-20 question/expected-answer pairs, authored incrementally as ingestion becomes functional rather than all at once.
NFR-7 (Cost): All managed services run on free tiers by design (Weaviate, Neo4j AuraDB, OpenRouter, Neon) — zero-cost reproducibility is a constraint, not just a preference.
NFR-8 (Accessibility, from UX Accessibility Floor): WCAG 2.2 AA as the floor across the web surface; status/color must never be the sole signal; focus rings visible in both themes; tab order follows visual reading order.

**Success Metrics (acceptance targets — these are what the Evaluation Harness epic must actually prove):**

SM-1: Answerable-question accuracy on the Evaluation Set — target ≥80% [ASSUMPTION: placeholder pending a real baseline run]. Validates FR-9, FR-10, FR-13.
SM-2: Refusal correctness — the system refuses 100% of genuinely unanswerable questions in the Evaluation Set, with no confident fabrication. Validates FR-10, FR-13.
SM-3: Zero cross-tenant data leakage, verified with two test accounts. Validates FR-2. Tiered Primary (not Secondary) because tenancy isolation is a launch blocker.
SM-C1 (counter-metric, do not optimize): refusal rate on *answerable* questions must not rise as a side effect of chasing SM-2 — over-refusing is as much a failure as fabricating.

[Cross-check from the brainstorm reconciliation: SM-3's test must cover leakage *through the generated answer* — i.e. that the LLM's answer never blends another user's retrieved context — not only that a raw unauthorized query is blocked. These are subtly different failure modes and the PRD only names the second.]

### Additional Requirements

- No starter/greenfield template is specified by Architecture — Epic 1 Story 1 begins from scratch scaffolding for both `backend/` and `frontend/`. Per the addendum's risk register, Day 1 is scaffolding only, with no exploratory work scheduled that day.
- Feature-based (vertical-slice) modular monolith: four backend modules — `auth`, `documents`, `chat`, `kg` — each owning `routes.py` / `service.py` / `repository.py`; shared infra centralized in `shared/data_access/` and `shared/llm_client/`. Hexagonal/ports-and-adapters explicitly rejected (AD architecture spine, Design Paradigm).
- AD-1 — Ingestion consistency via compensating rollback (saga-lite): fixed write order (Weaviate then Neo4j); on Neo4j-write failure, the handler deletes the just-written Weaviate objects before marking the document `Failed`; the document's status row also acts as a retry lock (retry only permitted from `Failed`, never during `Extracting`/`Graphing`). **Ownership rule:** the `documents` module is the sole writer of a document's ingestion-status field — AD-9's cascade-delete path only ever performs a full cascade delete, never a partial or concurrent status mutation, so ingestion and account-deletion cannot race on that field.
- AD-2 — Tenancy enforcement via mandatory shared data-access layer: every Weaviate/Neo4j read/write goes through `shared/data_access/`; no module hand-writes raw queries. Fixed shape contracts: Weaviate passages (`chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`, no nested metadata dict); Neo4j entities (`name` + `type`, typed relationships between entity references). **Cypher-injection guardrail:** any future natural-language-to-Cypher querying (out of v1 scope) must have `user_id` injected server-side into the generated query and must never trust LLM-generated output for the tenancy filter — recorded now, before that feature is built.
- AD-3 — API contract: every FastAPI route declares a Pydantic `response_model`; all errors use `HTTPException(status_code, detail)` → single `{"detail": ...}` shape, no custom error envelope.
- AD-4 — Entity identity resolution is exact-string-match only in v1 (no fuzzy/LLM-assisted merge).
- AD-5 — Frontend shared state (auth/user, theme, chat document-scope) lives in React Context, not Redux.
- AD-6 — One shared LLM-client wrapper (`shared/llm_client/`) is the sole path to OpenRouter for both entity extraction (documents module) and answer generation (chat module); the refusal short-circuit (FR-10) happens before this wrapper is ever called; the `kg` module never calls it. **Single refusal source:** the `chat` module checks the retrieval relevance score *before* invoking the wrapper and returns the refusal directly if below threshold. The wrapper's own internal failures (timeout, retry exhaustion, OpenRouter error) are a categorically distinct failure mode, surfaced as a normal service error per AD-3 (e.g. `503`) — never dressed up as, or conflated with, the product's "I don't know" refusal.
- AD-7 — Deployment topology: frontend on Vercel Hobby (free); backend on Render free web service (750 instance-hrs/mo, 15-min idle spin-down, ~1 min cold start).
- AD-8 — Single deployed environment (local dev + one prod, no staging tier); secrets are environment variables only, never committed, managed via each host's native dashboard.
- AD-9 — Account deletion (FR-16) is a full cascade hard-delete through the same shared data-access layer as every other path, following the same compensating-rollback discipline as ingestion (AD-1) if a partial failure occurs across stores.
- Stack (pinned versions, verified Aug 2026): Python 3.12+, FastAPI 0.141.1, Pydantic v2, SQLAlchemy 2.0.51, Alembic 1.19.0 (Postgres/Neon migrations), weaviate-client 4.22.0, neo4j driver 6.2, React 19.2.x, Vite 8.2.1, Tailwind CSS, react-force-graph 1.48.2, JWT + bcrypt, OpenRouter (free tier).
- Definition of Done (addendum): all in-scope PRD §6.1 items function end-to-end and are demonstrable; every chat answer displays ≥1 concrete source reference; unanswerable questions produce an explicit refusal verified by the Evaluation Set; cross-tenant isolation verified with two test accounts; the evaluation script runs with a single command and reports a numeric accuracy figure.
- Risk-driven sequencing (addendum risk register): a short Cypher reference/query-pattern primer should be prepared early (team is unfamiliar with Cypher) before graph-write stories begin; entity-extraction scope must stay constrained to a small fixed type set to bound LLM extraction latency/imprecision; graph queries used in any live demo should be validated offline in advance with a local-export fallback.

**Out-of-scope guardrails (PRD §6.2 — what stories must NOT build):**

- Chapter-level filtered search — v1 document scoping is document-level only (FR-11); chapters stay as read-only metadata (citation chip text, Document Detail chapter list) and are never a user-facing filter control in Chat.
- Query history — no surface for past questions/answers/citation snapshots in v1 (deferred to v2 during UX design).
- Clickable citations that jump to or highlight the source passage — citation chips are non-interactive in v1.
- Answer confidence badge/score — explicitly rejected during brainstorming convergence, not merely deferred.
- Opt-in "explain this answer" reasoning trace; live entity/relationship preview post-ingestion; user-editable graph corrections; natural-language querying over the graph; reference-counted/provenance-aware graph deletion.
- Password reset / email verification (FR-1 assumption); account recovery or undo window after account deletion (FR-16).
- Document search/filtering across the library, and project/category grouping beyond chapters. **See Open Decision OD-5 — this collides with a UX component that is specified.**
- Hybrid BM25+vector search; raw-context inspection panel; conversation export; staging environment.

**Open decisions that block specific stories (must be resolved before or inside the story that needs them):**

- OD-1 — **Exact entity/relationship type list for extraction (FR-5).** Genuinely undecided (PRD §8 item 1, carried into the architecture spine's Deferred). Extraction prompts cannot be written until this fixed type set exists. Blocks the ingestion/extraction story.
- OD-2 — **FR-10 relevance threshold value.** The short-circuit *mechanism* is fixed by AD-6, but the numeric cutoff is an empirically-tuned config value living in the shared LLM-client wrapper, to be set during implementation/evaluation. Blocks refusal-behavior acceptance criteria.
- OD-3 — **Numeric accuracy target for SM-1.** Currently an 80% placeholder; confirm once the Evaluation Set exists and a baseline run is possible.
- OD-4 — **Whether the FR-8 delete/graph-persistence tension needs a stronger v1 mitigation** than the plain-language warning already specified. PM-level question, explicitly not architecture's to resolve.
- OD-5 — **RESOLVED (2026-08-11).** The Chat document search control is scoped down to a **filter over the documents-in-scope panel only** — it narrows the selectable list, it does not search the document library. This removes the conflict with PRD §6.2, which continues to hold library-wide document search/filtering out of v1 scope. UX-DR10 is amended accordingly.
- OD-6 — **RESOLVED (2026-08-11).** The documents-in-scope panel is **not pre-checked on load** — no document is selected by default. FR-11's stated default (all of the user's documents) still governs the *retrieval* behaviour: an empty selection means the question runs against all of the user's documents, it does not mean "no scope". **Consequence for the Epic 3 story:** an all-unchecked panel must be visibly legible as "asking across everything", otherwise it reads as "nothing selected" and the user cannot tell which is in effect.
- OD-7 — **RESOLVED (2026-08-11).** On a content-hash match the upload modal shows an explicit "already uploaded" message on that file's row and surfaces the existing document, rather than creating a second row. Nothing is reprocessed, no LLM or embedding call is made (FR-6). Note that dedupe is keyed on content hash, not filename: a byte-identical file under a different name is still a duplicate, and an edited file under the same name is a genuinely new document that dedupe never touches. Replacing a document by filename was considered and rejected as new scope beyond FR-6.

**Stale cross-references in source documents (documentation hazard — do not propagate into stories):**

- `addendum.md` references a non-existent "FR-18" for the account-deletion undo window; the final PRD's account deletion is FR-16.
- `addendum.md`'s risk mitigation "Two pages, utility-class styling, no visual polish in v1" (echoed in the architecture stack table's Tailwind row) predates and contradicts the finalized UX design, which specifies 8 screens and a full design-token system. The UX spines are later and authoritative.
- The `.memlog.md` files and `reconcile-prd.md` use an earlier FR numbering (drag-and-drop/theme/account-deletion as FR-16/17/18, graph viz as FR-14, eval harness as FR-15). Only the final `prd.md` numbering (FR-1…FR-16) is authoritative.

### UX Design Requirements

UX-DR1: Authenticated shell — fixed 220px left sidebar + fluid content area; sidebar item order top-to-bottom is User Settings, Documents, Chat, Graph Preview, with Exit bottom-anchored and visually separated (`margin-top:auto`); exactly one nav item shows the active state at a time.
UX-DR2: Light/dark theme tokens implemented app-wide per DESIGN.md's full color spec (light "softened baby-blue" + dark "Soft Dark" dimmed-charcoal variant, not near-black); every screen including auth pages renders correctly in both themes (realizes FR-15).
UX-DR3: Citation chip component — `{colors.citation}` background / `{colors.citation-text}` foreground, its own locked color identity (never restyled as a generic badge); renders inline in assistant chat bubbles as `Ch. {chapter}, {document_filename}`; also reused as the file-type icon tile in upload rows; must be programmatically distinguishable from surrounding text for screen readers, not just visually (realizes FR-9).
UX-DR4: Status pill component — exactly five states per FR-4's vocabulary verbatim (Uploaded/Extracting/Graphing/Ready/Failed); color+text pairing, never color alone; reused across Documents table, Document Detail, and Chat's document-scope panel.
UX-DR5: Chat bubble components — user bubble right-aligned `{colors.primary}` fill with a sharp trailing corner; bot bubble left-aligned `{colors.surface}` fill with a sharp leading corner (mirrored asymmetric radius as the sender cue); robot mascot rendered from CSS shapes, small, left-aligned, 5px overlap onto the chat input's top edge, `aria-hidden` (decorative, non-interactive).
UX-DR6: Upload modal — dropzone supporting both drag-and-drop and click-to-browse; each queued file shows filename, size/"Queued", and independent progress; modal closes only on explicit Cancel or once all queued files resolve (success or reject); closing never cancels in-flight uploads; Documents list refreshes to show new "Uploaded" rows on close (realizes FR-3, FR-14).
UX-DR7: Document table component — columns Title, Type, Status, Uploaded, trash-icon; row click (outside the trash icon) opens Document Detail; the trash icon is a separate hit target that does not navigate and instead opens the inline delete-confirm.
UX-DR8: Document Detail panel — title, status, upload date, file type/size, chapter count, passages-indexed count, and full chapter list; metadata fields show as pending/unavailable (not fabricated zeros) until ingestion reaches Ready; Delete opens an inline confirm box, not a separate modal.
UX-DR9: Chat layout — two-column grid: flexible (`1fr`) chat window + fixed 260px documents-in-scope panel with 20px gap; composer row is a single row (text input + "Ask" button at identical, vertically centered height, not stacked); documents-in-scope panel lists checkboxes per document, unchecking removes it from the next question's retrieval scope, and non-Ready documents render checkbox-disabled with the status noted inline and exposed via `aria-label` (realizes FR-11).
UX-DR10: Document search/"Select all" affordance above the Chat window — searches the library to add documents to session scope; "Select all" scopes the session to every Ready document at once, the explicit UI equivalent of FR-11's "default is all documents."
UX-DR11: Graph canvas component — read-only node-link diagram; nodes are absolutely positioned circles sized by entity prominence with a soft drop shadow and centered white label text; no click-to-query, drag-to-rearrange, or editing in v1; scoped strictly to the authenticated user's graph (realizes FR-12).
UX-DR12: Settings page — four independent cards (Profile, Change Password, Appearance/theme toggle, Delete Account) in a two-column grid; each card saves independently; the Delete Account card uses the `{colors.danger}`-tinted danger-zone border/background (realizes FR-15, FR-16).
UX-DR13: Toggle switch component — 40×22px pill track, border color off / primary color on, white thumb; used for the theme toggle on Settings.
UX-DR14: Delete confirmation pattern (documents and account) — always an explicit inline confirm step, never a single-click destroy; plain-language copy stating the deletion boundary (e.g. graph entities persisting after document delete, per the Voice & Tone table); Cancel/Confirm Delete both reachable and clearly labeled via keyboard and screen reader (realizes FR-8, FR-16).
UX-DR15: Refusal ("I don't know") chat bubble — OPEN GAP, no existing mock. Must be built as visually and semantically distinct from a grounded-answer bubble (not just a bubble with zero citation chips) and announced distinctly to assistive tech; needs a design decision at implementation time (realizes FR-10).
UX-DR16: Failed ingestion state — OPEN GAP, no existing mock. Must show a human-readable failure reason without dropping the row from the Documents list; exact placement (inline in row vs. Document Detail only) is undecided and needs a decision during implementation (realizes FR-4).
UX-DR17: Empty document library state — OPEN GAP, no existing mock. Assumed default: a single-column "No documents yet." message with the Upload button remaining primary-actionable; not to be over-designed beyond this assumption without a dedicated pass.
UX-DR18: Accessibility floor applied app-wide — WCAG 2.2 AA target; status pills and any status signal always pair color with a text label; focus rings visible against both theme backgrounds; tab order follows visual reading order (sidebar → heading → primary content → secondary panels).
UX-DR19: Microcopy/voice — plain, declarative, specific-about-why tone per the Voice & Tone Do/Don't table; FR-4's status vocabulary (Uploaded/Extracting/Graphing/Ready/Failed) used verbatim; no hedging, apology filler, or decorative emoji (sidebar icons are the one accepted exception).
UX-DR20: Modal pattern — centered, 520px max-width container on a dimmed diagonal-hatched backdrop (not a flat scrim); header/body/footer three-part structure with footer-right-aligned actions; modal stacks never go more than one level deep (no modal-on-modal).

**From the WCAG 2.2 AA accessibility review (`review-accessibility.md`). Three of its four light-mode contrast failures were fixed in the final DESIGN.md — primary darkened to `#3861A8` (6.10:1, verified), sidebar link text to `#E4ECFA`, status-pill text to `#0C7A47`/`#8A5200`. The items below are what remained unresolved or unspecified. Team decisions of 2026-08-11: UX-DR21 is an accepted deviation and ships as-is; UX-DR22 and UX-DR23 are to be fixed; UX-DR24 through UX-DR28 are all confirmed in v1 scope and each needs story coverage.**

UX-DR21: **Citation-chip contrast — ACCEPTED DEVIATION (2026-08-11), not to be fixed in v1.** `citation-text` `#4A7FE0` on `citation` background `#D1EEFE` computes to 3.22:1 against a 4.5:1 requirement (the chip renders at 11.5px/700, below the large-text exemption threshold). The team has decided to ship the light-mode citation pair as specified in DESIGN.md rather than re-tune it. **Recorded consequence:** NFR-8 declares WCAG 2.2 AA the floor for the product, and this is a knowing exception to that floor, on the component DESIGN.md itself calls "the single most important visual token in the product". It affects light mode only — dark mode's re-tuned pair (`#8FB0FF` on `#2A3557`, 5.63:1) already passes. No Definition-of-Done check tests accessibility, so nothing downstream will surface this again. Revisit if the product moves beyond portfolio stage.
UX-DR22: **Status-pill background tint tokens (BLOCKING, unspecified).** DESIGN.md specifies pill text colors for only two of the five FR-4 states and never gives the pill *background* tint any token value at all ("success tint background" is prose, not a value). All five states (Uploaded/Extracting/Graphing/Ready/Failed) need an explicit tint+text pair, each verified to clear 4.5:1.
UX-DR23: **Focus-ring token (BLOCKING, missing).** EXPERIENCE.md mandates focus rings visible and themeable across both palettes, but no `focus-ring`/`outline` token exists in DESIGN.md's colors or components, and neither mockup defines any `:focus`/`:focus-visible` rule. Needs a dedicated token distinct from `border`, clearing 3:1 non-text contrast against `bg`, `surface`, and `surface-dark`.
UX-DR24: Chat thread live region — the message list needs `aria-live="polite"` (or `role="log"`) so screen-reader users are announced when an assistant answer arrives; currently absent from both spines and the mocks. Each turn needs enough semantic structure to distinguish user from assistant beyond alignment and bubble shape.
UX-DR25: Modal accessibility contract — `role="dialog"` + `aria-modal="true"` + `aria-labelledby` pointing at the modal heading, an explicit focus trap, defined initial focus placement, and focus return to the triggering control on close (Cancel, Escape, or completion). None of these are currently stated as requirements.
UX-DR26: Inline delete-confirm accessibility — the confirm box is inline rather than modal, so it needs its own treatment: an announcement on appearance, programmatic association between the plain-language deletion-boundary text and the Confirm/Cancel buttons (so the warning is read *before* the action), defined focus movement on open, defined Escape behavior (currently undefined for the inline pattern), and focus return on close.
UX-DR27: Disabled-checkbox labeling — the Chat scope panel's non-Ready document checkboxes must carry their status programmatically (e.g. `aria-label="NDA_Draft_Rev2.pdf, processing, not yet selectable"` or a proper `<label>` association). The reference mock directly violates EXPERIENCE.md's own stated requirement here, rendering "(processing)" as an unassociated sibling `<span>`.
UX-DR28: Remaining accessibility items — citation chips need a semantic inline element (`<cite>` or a labelled span), not a bare styled `<span class="cite">`; status-pill text must be real DOM text, never a pseudo-element or icon-font glyph; graph canvas needs a stated keyboard-access position (node detail on hover requires a keyboard equivalent, or nodes must carry no interaction at all) and must not encode entity type by color alone; `prefers-reduced-motion` handling for progress/modal/theme transitions is unaddressed; the fixed 220px sidebar + fixed 260px chat panel layout needs a 200% zoom reflow check (WCAG 1.4.4), since nothing currently guards against horizontal scroll or clipping.

### FR Coverage Map

FR-1: Epic 1 — Account creation and login (bcrypt_sha256 hashing, JWT session).
FR-2: Epic 1 — Server-side `user_id` tenancy filtering, enforced structurally via the shared data-access layer (AD-2).
FR-3: Epic 2 — Upload and parse PDF/Markdown/HTML into tagged Passages.
FR-4: Epic 2 — Ingestion status ledger and its five-state vocabulary, surfaced across three UI surfaces.
FR-5: Epic 2 — Entity/relationship extraction merged into the unified per-user Knowledge Graph (exact-match merge, AD-4).
FR-6: Epic 2 — Content-hash dedupe preventing reprocessing of unchanged documents.
FR-7: Epic 2 — Document list and detail inspection.
FR-8: Epic 2 — Document deletion with the vector-removed / graph-persists boundary stated at delete time.
FR-9: Epic 3 — Grounded answers with structured citations to specific Passages.
FR-10: Epic 3 — Explicit refusal below the evidence threshold, short-circuited before the LLM call (AD-6).
FR-11: Epic 3 — Document scoping for a question (all documents by default, or a chosen subset).
FR-12: Epic 4 — Per-user Knowledge Graph node-link visualization.
FR-13: Epic 6 — Evaluation harness run by a single command, reporting accuracy and refusal-rate numerically.
FR-14: Epic 2 — Drag-and-drop upload with independent per-file progress.
FR-15: Epic 1 (primary) — design-token system, both palettes, ThemeContext and cross-session persistence, so every screen is built theme-aware from the start; **Epic 5 completes its UI surface** with the Appearance toggle control on Settings.
FR-16: Epic 5 — Account deletion as a full cascade hard-delete across Postgres, Weaviate, and Neo4j (AD-9).

All 16 FRs are mapped. FR-15 is the one requirement deliberately split across two epics, to avoid retrofitting theming onto every previously-built screen.

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
