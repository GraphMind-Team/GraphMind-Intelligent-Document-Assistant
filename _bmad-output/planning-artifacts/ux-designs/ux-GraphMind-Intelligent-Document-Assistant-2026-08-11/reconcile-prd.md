# PRD ↔ UX Spine Reconciliation

Checked against DESIGN.md + EXPERIENCE.md, all in-scope FRs (FR-1–FR-15).

## FR-by-FR

- **FR-1 (Account creation/login):** PASS — Login/Registration surfaces in EXPERIENCE.md IA table.
- **FR-2 (Server-side tenancy filtering):** NO UX REPRESENTATION — server-side/query-layer enforcement has no user-facing surface; expected, not a real gap, but flagged per instruction since neither doc mentions it even as an invariant note.
- **FR-3 (Upload and parse supported formats):** PASS — Upload modal dropzone explicitly accepts PDF/MD/HTML (Component Patterns).
- **FR-4 (Ingestion status visibility):** PASS — Status badge component renders all 5 states verbatim (Uploaded/Extracting/Graphing/Ready/Failed), used across three surfaces.
- **FR-5 (Entity/relationship extraction into unified graph):** PASS — Graph Preview surface renders the unified per-user entity/relationship graph.
- **FR-6 (Ingestion dedupe):** NO UX REPRESENTATION — content-hash dedupe is not mentioned anywhere in DESIGN.md or EXPERIENCE.md (no "already uploaded"/duplicate-detected state in Upload modal or State Patterns).
- **FR-7 (List and inspect documents):** PASS — Document table row + Document Detail panel.
- **FR-8 (Delete a document):** PASS — Delete confirmation state with plain-language deletion-boundary copy matches FR-8 exactly (vector removed immediately, graph persists).
- **FR-9 (Answer with structured citations):** PASS — Citation chip component + chat bubble rule ("≥1 citation chip per claim-bearing sentence").
- **FR-10 (Explicit refusal below threshold):** PARTIAL PASS — behaviorally addressed (Voice/Tone table, Flow 1 failure branch, Open Gaps #1) but explicitly flagged as an undesigned visual gap; conceptual representation exists, no mock.
- **FR-11 (Document scoping for a question):** PASS, with a soft tension — Documents-in-scope panel + "Select all" implement scoping, but PRD states default scope (when user doesn't choose) is *all* documents, while EXPERIENCE.md's Flow 1 has the user manually click "Select all" to reach that state, implying it isn't pre-selected by default. Worth confirming intent.
- **FR-12 (Chapter-level filtered search):** NO UX REPRESENTATION — chapters appear only as read display (citation chip text, Document Detail's chapter list); no interaction surface lets a user scope a question to a specific chapter within selected document(s) as FR-12 requires. Composability with FR-11 ("one document's one chapter") has no corresponding control.
- **FR-13 (Query history):** NO UX REPRESENTATION — no surface in the IA table, no component, no state pattern for viewing past questions/answers/citation snapshots anywhere in either document.
- **FR-14 (Graph visualization):** PASS — Graph Preview, read-only node-link diagram, scoped per user.
- **FR-15 (Run evaluation set / report metrics):** NO UX REPRESENTATION — CLI/service-layer feature by design (FR-15 explicitly says harness bypasses the UI); expected absence, not a defect.

## Contradictions Found

1. **Theming vs. PRD's explicit deferral.** PRD §6.2 Out of Scope for MVP lists "theming" among v2/v3 backlog items. EXPERIENCE.md ("dark mode ships in v1 as a user-selectable preference") and DESIGN.md (full "Soft Dark" palette, User Settings "Appearance" theme-toggle component) build dark mode/theming as an in-scope v1 feature. Direct scope contradiction.
2. **Drag-and-drop upload vs. PRD's explicit deferral.** PRD §6.2 lists "drag-and-drop upload with progress" as v2/v3 backlog (also addendum.md Medium priority backlog). EXPERIENCE.md's Upload modal Component Pattern specifies a dropzone "(drag-and-drop + click-to-browse)" with per-file progress bars as v1 behavior. Direct scope contradiction.
3. **Document search/filtering vs. PRD's explicit deferral (possible).** PRD §6.2 / addendum.md Medium priority list "document search/filtering" as out of scope for MVP. EXPERIENCE.md's Chat surface includes a "Document search bar" to add documents to session scope. This may be a narrower, legitimately different feature (session-scoping search vs. library-wide search/filter), but the naming and mechanism overlap enough to warrant a scope-boundary check.
4. **Account deletion not in PRD.** EXPERIENCE.md's User Settings includes a "Delete Account" danger-zone card. No corresponding FR or mention exists anywhere in prd.md or addendum.md (account lifecycle beyond creation/login is undefined there). This is UX scope invented beyond the PRD, not necessarily wrong, but unauthorized by the source doc.
5. **Password reset absence — consistent, not contradictory.** Noted for completeness: PRD's "no password reset/email verification" assumption (FR-1) does not conflict with EXPERIENCE.md's "Change Password" settings card, since that's an authenticated in-session change, not a forgot-password/reset flow. No action needed.

## Summary

- FRs with no UX representation at all: **5** — FR-2, FR-6, FR-12, FR-13, FR-15 (of which FR-2 and FR-15 are backend/CLI-only by design and not true UX gaps; FR-6, FR-12, and FR-13 are genuine gaps worth closing before build).
- Contradictions: **2 confirmed** (theming, drag-and-drop upload) + **1 possible** (document search/filtering) + **1 unauthorized scope addition** (account deletion).
