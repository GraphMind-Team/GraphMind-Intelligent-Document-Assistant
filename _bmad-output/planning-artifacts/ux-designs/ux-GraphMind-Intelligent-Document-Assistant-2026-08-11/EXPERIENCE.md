---
title: GraphMind
status: final
created: 2026-08-11
updated: 2026-08-11
sources:
  - _bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/prd.md
  - _bmad-output/planning-artifacts/prds/prd-GraphMind-Intelligent-Document-Assistant-2026-08-11/addendum.md
---

# GraphMind — Experience Spine

Web app, single surface, dark mode in scope for v1. `DESIGN.md` is the visual identity reference (Theme 4 — Bold High-Contrast, light softened to baby-blue, dark as the Soft Dark variant); this spine is the experience — behavior, structure, state, interaction. No UI system named; layout is bespoke (sidebar shell + table/panel patterns), not inherited from a component library.

## Foundation

Web app only, responsive for desktop-first use (document review and chat composition are desk-bound tasks). No named UI system — GraphMind's shell (sidebar + main) and components (tables, modals, chat thread, chip panels) are bespoke, styled per `DESIGN.md`. Light mode is default; dark mode ships in v1 as a user-selectable preference (not a system-detected default) — see User Settings. Every authenticated page shares one persistent left-sidebar shell; only Login and Registration are outside it.

## Information Architecture

| Surface | Reached from | Purpose |
|---|---|---|
| Login | App open (unauthenticated) / "Log in" link | Authenticate into the workspace |
| Registration | Login page "Register" link | Create an account |
| Documents | Sidebar (default landing page post-login) | List, upload, inspect, delete documents |
| Document Detail | Documents row click | Metadata, chapter breakdown, delete + confirm |
| Chat | Sidebar | Ask grounded questions, scoped to selected documents |
| Graph Preview | Sidebar | Read-only view of the user's unified knowledge graph |
| User Settings | Sidebar | Profile, password, theme, account deletion |
| Exit | Sidebar (bottom) | Log out, return to Login |

Sidebar order (top to bottom): User Settings, Documents, Chat, Graph Preview, Exit — Exit is visually separated from the other four (bottom-anchored), since it's a destructive-adjacent, session-ending action rather than a content surface. Upload is a modal reached from Documents, not a standalone route. No drawer, no secondary nav; modal stacks one level deep (e.g. Upload modal never opens another modal on top of itself).

→ Composition reference: [key-screens-light.html](mockups/key-screens-light.html) · [key-screens-dark.html](mockups/key-screens-dark.html) (all 8 core screens, both modes). Spine wins on conflict.

## Voice and Tone

Microcopy. Brand voice and aesthetic posture live in `DESIGN.md` (Brand & Style).

| Do | Don't |
|---|---|
| "No supporting evidence found in your documents for this question." | "Sorry, I don't know that! 🤷" |
| "Delete this document? Its passages will be removed from search immediately. Entities already merged into your Knowledge Graph from this document will remain and may still influence future answers." | "Are you sure? This can't be undone!" |
| "5 documents · 4 ready, 1 processing" | "You're all caught up! 🎉" |
| "Uploaded", "Extracting", "Graphing", "Ready", "Failed" (FR-4 vocabulary, used verbatim) | Cute/vague substitutes ("Working on it…", "Almost there!") |
| Plain, declarative, specific about *why* (especially around deletion boundaries and refusals — trust is the product). | Hedging, apologetic filler, exclamation marks, emoji as substance rather than a rare accent (sidebar icons are the one accepted exception, per the mock). |

[ASSUMPTION: no explicit brand-voice document exists in sources beyond the mock's copy; the table above extrapolates from copy actually used in `.working/key-screens-theme4-bold.html` plus the PRD's trust-first framing (§1, FR-10).]

## Component Patterns

Behavioral. Visual specs live in `DESIGN.md.Components`.

| Component | Use | Behavioral rules |
|---|---|---|
| Sidebar nav item | All authenticated pages | Exactly one item shows the `active` state, matching current page. Exit is bottom-anchored, separated from the four content items. |
| Document table row | Documents | Row shows title, type, status pill, upload date, trashcan icon. Clicking the row (outside the trash icon) opens Document Detail. Trashcan is a separate hit target — clicking it does not navigate, it initiates delete (see State Patterns / confirm flow). |
| Status pill | Documents table, Document Detail, Chat doc-scope panel | Renders one of exactly five states per FR-4: Uploaded, Extracting, Graphing, Ready, Failed. Only "Ready" documents are selectable in Chat's document panel — all other states render their checkbox disabled with the status visible inline (e.g. "(processing)"), matching the mock's `NDA_Draft_Rev2.pdf (processing)` treatment. |
| Upload modal | Triggered by Documents' "Upload" button | Dropzone (drag-and-drop + click-to-browse) accepts PDF/MD/HTML. Each queued file shows filename, size (or "Queued" pre-start), and its own progress bar — files upload/progress independently, not as one blocked batch. Modal closes only on explicit Cancel or after all queued files finish (success or reject); closing does not cancel in-flight uploads. On close, Documents list refreshes to show new rows in "Uploaded" status. |
| Document Detail panel | Document row click | Shows title, status, upload date, file type/size, chapter count, passages-indexed count, and full chapter list (name + passage count per chapter) — populated only once ingestion reaches "Ready"; earlier states show the metadata fields as pending/unavailable rather than blank. Delete button opens an inline confirm box (see State Patterns), not a separate modal. |
| Chat message bubble | Chat thread | User messages right-aligned, filled with `{colors.primary}`-family fill, rounded with a sharp trailing corner. Assistant messages left-aligned, `{colors.surface}`-toned, rounded with a sharp leading corner (mirror of user bubble) — the asymmetric corner is the sender cue, not just alignment. |
| Citation chip | Inline within assistant bubbles | Renders as `Ch. {chapter}, {document_filename}` (e.g. "Ch. 4, Vendor_Agreement_2026.pdf"), visually distinct from surrounding text via `{colors.citation}` background per FR-9's "traceable to at least one citation" requirement — every claim-bearing sentence carries at least one. Non-interactive in v1 (clickable jump-to-source is explicitly out of scope, PRD §6.2). |
| Document search bar | Chat, above/outside the chat window | Searches the user's document library to add documents to session scope; distinct from the read-only "documents in scope" panel on the right. Includes a "Select all" affordance that scopes the session to every Ready document at once (FR-11 default is all documents; this is the explicit UI equivalent). |
| Documents-in-scope panel | Chat, right side of chat window | Lists chips per selected/selectable document with a checkbox; unchecking removes a document from the active question's retrieval scope (FR-11). Non-Ready documents appear checkbox-disabled with status noted inline, per Status pill rule above. |
| Chat composer row | Chat, bottom of chat window | Single row: text input + "Ask" send button, both rendered at identical height, vertically centered against each other — not stacked, not mismatched heights. The robot mascot sits above-left of this row with a 5px overlap onto the row's top edge (per memlog decision), decorative and non-interactive (`aria-hidden`). |
| Graph canvas | Graph Preview | Read-only node-link diagram; no click-to-query, no drag-to-rearrange, no editing in v1 (PRD §4.5, memlog). Nodes represent entities, edges represent relationships, scoped to the authenticated user's graph only. |
| Settings card | User Settings | Four independent cards, per PRD §4.7: Profile, Change Password, Appearance (theme toggle, FR-15), Delete Account (danger zone, FR-16, visually separated via `{colors.danger}`-tinted border/background). Each card saves independently — saving Profile does not require touching Password. |
| Theme toggle | User Settings → Appearance | Two-state switch (Light / Dark), FR-15. Selecting a theme applies it immediately app-wide and persists it to the account across sessions; it is not a per-session/browser-only or OS-auto-detected preference. |
| Delete Account | User Settings → danger zone | FR-16. Requires an explicit confirm step (same danger-zone pattern as document delete, FR-8) before permanently removing the user's documents, vector entries, Knowledge Graph data, and account record; user is logged out immediately on confirm. No recovery/undo window in v1. |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Empty document library | Documents | No mock exists for this state. [ASSUMPTION] Table area shows a single-column message ("No documents yet.") plus the Upload button remains primary-actionable — do not invent full visual treatment, defer to DESIGN.md/implementation. |
| Uploaded / Extracting / Graphing | Documents table, Document Detail, Chat doc panel | Status pill shows the exact stage per FR-4. Document is visible everywhere but not selectable in Chat's scope panel (checkbox disabled) until "Ready." Document Detail's metadata fields (chapters, passage counts) are pending/unavailable, not fabricated with zeros. |
| Ready | Documents table, Document Detail, Chat doc panel | Full metadata available; selectable in Chat scope; deletable. |
| Failed | Documents table, Document Detail | **Open gap** — no mock exists for this state. Per FR-4, a Failed document must show a human-readable reason and must not silently drop from the list. [ASSUMPTION: flagged, not designed] the failure reason's exact placement/visual treatment (inline in the row vs. only in Document Detail) is undecided — needs a dedicated mock before build. |
| Delete confirmation | Document Detail (primary), Documents row trash icon | Clicking Delete/trash does not delete immediately — it reveals an inline confirm box stating the deletion boundary in plain language (vector passages removed immediately; graph entities persist, per FR-8) with Cancel / Confirm Delete actions. This applies whether delete is initiated from the table row or the detail panel. |
| Chat: grounded answer | Chat thread | Assistant bubble contains ≥1 citation chip per claim-bearing sentence (FR-9). This is the default/success state and the product's core trust mechanic. |
| Chat: refusal ("I don't know") | Chat thread | **Open gap** — no mock exists for this specific bubble state. Per FR-10, when retrieval finds no adequate evidence, the assistant must return an explicit refusal rather than a generated guess. [ASSUMPTION: flagged, not designed] it should visually read as categorically different from a grounded answer (not just an answer bubble with zero citation chips, which could be misread as "answered, just untraceable") — needs a dedicated mock; do not ship the refusal as a bare text bubble indistinguishable from a low-confidence normal answer. |
| Upload in progress | Upload modal | Each file row shows independent progress; "Queued" precedes byte progress for files not yet started. Modal remains open until user cancels or all files resolve. |
| Modal open | Any modal (Upload today; delete-confirm is inline, not modal) | Background is not interactive while modal is open (standard overlay); Escape/Cancel closes without side effects for not-yet-started uploads. |
| Loading (page-level) | Any authenticated page on first load | [ASSUMPTION] no skeleton/spinner pattern specified in sources — defer exact treatment to implementation, but the shell (sidebar) should render immediately even if page content is still loading, since sidebar navigation must stay usable. |

## Interaction Primitives

- Click/tap to act — no drag-and-drop required beyond the Upload modal's dropzone (which also supports click-to-browse as a non-drag fallback).
- Row click (Documents table) opens Document Detail; the trash icon is a separate, smaller hit target that does not trigger navigation.
- Checkbox toggle (Chat scope panel, Select all) is immediate/optimistic — no separate "apply" step; retrieval scope for the *next* question reflects current checkbox state.
- Composer submission: Enter key or clicking "Ask" both submit the current question (standard text-input submit convention); [ASSUMPTION] no keyboard shortcut system beyond this is specified in sources — GraphMind is not positioned as a keyboard-first power-user tool the way some reference products are.
- Destructive actions (document delete, account delete) always require an explicit confirm step — never a single click to destroy data. This is stricter than "Drift trusts the user" reference posture, because GraphMind's PRD explicitly calls out the delete/graph-persistence boundary as something users must not be surprised by (FR-8).
- **Banned:** silent/instant deletes without confirmation, clickable citation chips that jump to source (explicitly deferred, PRD §6.2), drag-to-reorder anywhere, modal-on-modal stacking.

## Accessibility Floor

Behavioral. Visual contrast lives in `DESIGN.md`.

- [ASSUMPTION] WCAG 2.2 AA as the floor across the web surface — not specified in sources, but a reasonable default for a portfolio-stage product with no stated accessibility exemption.
- Status pills (Uploaded/Extracting/Graphing/Ready/Failed) must not rely on color alone — always paired with the text label, per the mock's existing pattern (badge text + tinted background, not a bare color dot).
- Citation chips must be programmatically distinguishable from surrounding answer text (not just visually) so screen-reader users can identify where a claim's evidence is cited, not just sighted users.
- The refusal state (once designed — see open gap above) must be announced distinctly from a normal answer to assistive tech, not merely styled differently for sighted users.
- Disabled checkboxes (non-Ready documents in Chat's scope panel) must expose their disabled reason (e.g. via `aria-label` incorporating the status) rather than only showing "(processing)" as visual-only text.
- Delete confirmation actions (Cancel / Confirm Delete) must be reachable and clearly labeled via keyboard and screen reader — this is the product's one truly irreversible-feeling action (documents) alongside account deletion, so it cannot depend on hover or pointer-only affordances.
- Tab order on every page follows visual reading order (sidebar → page heading → primary content → secondary panels), consistent with the shell's fixed left-to-right layout.
- Focus rings must remain visible against both light and dark theme backgrounds — themeable, not hardcoded to one palette (relevant because dark mode is in scope for v1).

## Key Flows

### Flow 1 — First trustworthy answer (Elena, onboarding a new project's documents)

1. Elena logs in and lands on Documents.
2. She clicks Upload; the Upload modal opens with a dropzone.
3. She uploads 3 documents; each queues with its own progress bar.
4. The modal closes once uploads finish; the 3 new documents appear in the table with "Uploaded" status.
5. She clicks one document to open Document Detail — metadata (chapters, passage counts) populates once ingestion reaches "Ready"; she notes the trashcan delete option and the confirm-before-delete pattern without using it yet.
6. She sorts the Documents table by most recent to confirm her newest upload is on top.
7. She visits Graph Preview and sees a read-only node-link diagram of entities/relationships extracted so far.
8. In Chat, she uses "Select all" in the documents-in-scope panel to include every Ready document, then asks "which vendors are mentioned across these documents and what do they supply?"
9. **Climax:** The answer synthesizes across multiple documents via graph traversal — not a single-document lookup — listing vendors named in one contract whose relationships (e.g. "supplies") are drawn from entities merged into her unified Knowledge Graph from several different source files at once. Each claim carries an inline citation chip (e.g. "Ch. 4, Vendor_Agreement_2026.pdf") naming the specific chapter/document it came from, but the answer itself only exists because GraphMind connected facts *across* those documents — something a single-document search or a per-file citation list couldn't produce. She doesn't need to open any of the source PDFs to trust it.

Failure/edge branch (per PRD UJ-1): if Elena asks about something absent from her corpus, the assistant returns the explicit refusal state (open gap, flagged above) instead of a fabricated answer — this is a designed product behavior, not an error state to be minimized.

### Flow 2 — Deleting a stale document (Marcus, re-uploading a corrected contract)

1. Marcus opens Documents, finds the outdated contract.
2. He clicks its trashcan icon (or opens Document Detail and clicks Delete).
3. An inline confirm box appears, stating plainly that passages are removed from search immediately but graph entities derived from the document persist.
4. He confirms; the document disappears from the table and from future Chat scope/citations immediately.
5. **Climax:** Marcus understands the deletion boundary — he isn't later surprised that a deleted document's entities still surface in an unrelated answer — and re-uploads the corrected version with full trust in the system's honesty about its own limits.

## Open Gaps

Flagged explicitly per instruction — do not treat these as designed, and do not build from invented visuals:

1. **Refusal ("I don't know") chat bubble** — FR-10 requires it; no mock exists. Needs a dedicated visual/behavioral design pass before implementation, distinct enough from a grounded-answer bubble to avoid being misread as "answered, just uncited."
2. **Failed ingestion state** — FR-4 requires a human-readable reason shown without dropping the document from the list; no mock exists. Placement (row-inline vs. detail-only) undecided.
3. **Empty document library state** — no mock exists; a reasonable default is assumed above but not designed.