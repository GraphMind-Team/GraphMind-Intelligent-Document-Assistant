---
title: 'Story 2.2: Document library and detail view'
type: 'feature'
created: '2026-08-13'
status: 'in-review'
review_loop_iteration: 0
context: []
baseline_commit: 'e7736fbb8ff073d22bd4d1c128b6ff9ed982bd63'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.1 left a deliberately minimal Documents table (four columns, no row interaction) and no way to inspect a single document. There is no by-id endpoint and no Detail view, so a user can see *that* something uploaded but nothing *about* it.

**Approach:** Build the real Documents table per the reference mockup (Title, Type, Status pill, Uploaded, trash icon), a row-click-through to a Document Detail panel at `/documents/:id`, and the `GET /documents/{id}` endpoint behind it. Extract the status pill into a shared component so Epic 3's chat scope panel reuses one implementation. No delete behavior (2.7), no parsing-derived data (2.3).

## Boundaries & Constraints

**Always:**
- `GET /documents/{document_id}` resolves through `user_scoped_select` (never a bare `db.get`) and returns **404, not 403**, for another account's document — a 403 confirms the id exists. This is the codebase's first by-id document endpoint, so its first IDOR surface; treat as tenancy-critical.
- Reuse `DocumentResponse`; never serialize `content` (raw bytes) or `user_id`.
- Card click opens Detail; the trash icon is a separate hit target that does **not** navigate (UX-DR7). It renders and is keyboard-focusable here, but has no delete action wired — that's Story 2.7.
- Status renders through one shared `StatusPill` using Story 1.2's `--status-*` token pairs: tint + text label together, never colour alone, label as real selectable DOM text — not a pseudo-element, icon font, or `aria-label`-only (UX-DR4, UX-DR28).
- Detail panel per the mockup's `.detail-panel`: centered, 640px max-width, `--card-bg`, 1px `--border`, 14px radius, 26px padding; heading 18px/700 in `--primary`; metadata a two-column grid of eyebrow-style key over value.
- Metadata with no data source yet (chapter count, passages-indexed, chapter list) renders as explicit "Pending" — **never fabricated as `0`** (UX-DR8). Every document is `Uploaded` here, so this is the only reachable path (see Ask First).
- Toolbar row above the table (mockup's `.toolbar`): a **Sort** select (Most recent / Title A–Z / Status) and a **Filter: type** select (All types / PDF / Markdown / HTML). Both applied **client-side** over the already-fetched list — no new query params, so no new server-side input surface (a client-supplied sort field interpolated into `order_by` is a classic injection vector; not introducing one). Both are real `<select>` elements with labels, not custom widgets.
- Empty library: plain "No documents yet." in the grid area, Upload still primary-actionable (UX-DR17). A filter that matches nothing shows a distinct "No documents match this filter." — not the same copy as a genuinely empty library.
- Detail is a nested route (`/documents/:documentId`), not in-page state — back-button and deep-link for free, and keeps Documents the single active sidebar item (UX-DR1).
- Document-derived text renders as plain React text children only — no `dangerouslySetInnerHTML`, no Markdown/HTML renderer (standing constraint in `deferred-work.md`; `filename` is attacker-controlled and `.md`/`.html` are ingestible).

**Ask First:** none outstanding — both open questions were resolved by the human before implementation (see Never, first two bullets).

**Never:**
- **No Ready-state Detail branch** — human-approved decision. Chapter count, passages-indexed, and the chapter list all come from Story 2.3's parsing; no document can *reach* `Ready` yet and no column holds those values. Build only the reachable pending path; 2.3 adds the columns and the Ready branch together when it has real data, rather than dormant code against a guessed shape. The epic's "Detail for a Ready document" AC is therefore accounted for here but not exercisable until 2.3 — that is expected, not a gap to close in this story.
- **No search input** — human decision: sort and filter only. OD-5 (document-search scope boundary) is an open decision landing in Epic 3; don't pre-empt it.
- No delete behavior — trash icon renders, does nothing yet (2.7).
- No parsing, chunking, embedding, or status advancement past `Uploaded` (2.3).
- No pagination — tracked in `deferred-work.md`; unbounded is fine at current volumes.
- No speculative `chapter_count`/`passage_count` columns (see the Ready-state bullet above).
- No server-side sort/filter params — client-side only, per the toolbar constraint above.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Library with documents | Account has 3 uploads | Grid shows one card per document: file-type tile, title, status pill, uploaded date, trash icon | N/A |
| Empty library | Account has 0 uploads | "No documents yet." in the grid area; Upload button still primary | N/A |
| Sort / filter | Sort by Title A–Z; filter type = PDF | Cards reorder / non-PDF cards hidden, client-side, no refetch | N/A |
| Filter matches nothing | Filter = HTML, account has only PDFs | "No documents match this filter." — distinct from the empty-library copy | N/A |
| Card click | Click anywhere on a card outside the trash icon | Navigates to `/documents/:id`, Detail renders | N/A |
| Trash icon click | Click the trash icon | Does **not** navigate; no delete occurs (2.7) | N/A |
| Detail, no parsed data | Document at `Uploaded` | Chapter/passage fields read "Pending", never `0` | N/A |
| Cross-tenant by-id | Account B requests account A's document id | **404**, no document data, no existence disclosure | 404 with a generic detail |
| Unknown / malformed id | Random uuid, or a non-uuid path segment | 404 (unknown uuid) / 422 (malformed uuid) | Plain `{"detail": ...}` per AD-3 |
| Deep link while logged out | Unauthenticated `GET /documents/:id` in browser | Redirected to `/login`, then back to the deep-linked document after login | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/documents/{repository,service,routes}.py` -- edit: `get_document_for_user` via `user_scoped_select`, 404-on-miss, `GET /documents/{document_id}`
- `backend/tests/test_documents_detail.py` -- new: happy path, cross-tenant 404, unknown id, auth required
- `frontend/src/components/StatusPill.jsx` -- new: five FR-4 statuses → 1.2 token pairs
- `frontend/src/pages/DocumentsPage.jsx` -- edit: card grid, toolbar, card click, empty/filtered-empty states; `components/DocumentCard.jsx` -- new
- `frontend/src/pages/DocumentDetailPage.jsx` -- new: detail panel, pending metadata
- `frontend/src/api/documentsClient.js` -- edit: `getDocument`; `frontend/src/App.jsx` -- edit: nested detail route
- Tests: `DocumentsPage.test.jsx` (edit), `DocumentDetailPage.test.jsx` + `StatusPill.test.jsx` (new)

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/documents/repository.py` -- `get_document_for_user` through `user_scoped_select` -- tenancy applied at the one chokepoint
- [x] `backend/app/documents/service.py` + `routes.py` -- `GET /documents/{document_id}`, 404 on miss -- the by-id endpoint Detail reads
- [x] `backend/tests/test_documents_detail.py` -- cross-tenant 404 (no existence leak), unknown id, auth required -- pins the new IDOR surface
- [x] `frontend/src/components/StatusPill.jsx` -- shared pill on 1.2's token pairs, text label always present -- UX-DR4/UX-DR28, reused by Epic 3
- [x] `frontend/src/pages/DocumentsPage.jsx` -- real table + row click + trash hit target + empty state + client-side sort/filter toolbar -- AC1/AC3/AC7/AC8
- [x] `frontend/src/pages/DocumentDetailPage.jsx` -- detail panel, pending metadata, back to library -- AC4/AC5
- [x] `frontend/src/api/documentsClient.js` + `App.jsx` -- `getDocument`, nested detail route -- wires the two together
- [x] Frontend tests for pill states, row-vs-trash click separation, empty state, and detail pending fields

**Acceptance Criteria:**
- Given documents exist, when the Documents page loads, then each card shows file type, title, status pill, uploaded date, and a trash icon.
- Given two accounts, when account B requests account A's document by id, then the response is 404 and discloses nothing about that document's existence.
- Given a document card, when I click it outside the trash icon, then Detail opens; clicking the trash icon does not navigate.
- Given a document with no parsed data, when Detail renders, then chapter/passage fields read as pending, never as `0`.
- Given an empty library, when the page loads, then "No documents yet." appears and Upload remains primary-actionable.
- Given any status pill, when it renders, then its label is real selectable text paired with its tint — never colour alone.
- Given the toolbar, when I change Sort or Filter, then the visible rows reorder/narrow client-side with no refetch, and a filter matching nothing reads differently from an empty library.

## Spec Change Log

- **Trigger:** Direct human request after seeing the implemented table ("I don't like how they are put in a table... is there a way that the docs are in a grid field and that each doc is represented as a rectangle file icon"), not a review finding.
- **Amended:** The library renders a responsive card grid instead of the mockup's `.doclist` table. Each card carries the same five facts the columns did — file type (as an icon tile), title, status pill, uploaded date, trash action. Toolbar, sort/filter, empty/filtered-empty states, click-through and trash-does-not-navigate behavior are all unchanged.
- **Deviation acknowledged:** this contradicts the epic's literal AC wording ("the table lists Title, Type, Status, Uploaded date and a trash icon per row") and DESIGN.md's `.doclist`/"Document table row" component. Recorded here so it reads as a deliberate human decision rather than drift. UX-DR7's *substance* (row click opens Detail; trash is a separate hit target that never navigates) is preserved exactly.
- **No new design tokens:** the file-icon tile reuses DESIGN.md's own `.file-icon` treatment (`--citation` fill, `--primary` text), which the design doc explicitly sanctions as the one non-citation-chip use of the citation token ("the file-type icon tile in upload rows").
- **Side effect worth keeping:** the grid retires the table's clipping problem structurally. The table needed an `overflow-x-auto` container because its min-content width exceeded the content area at 200% zoom; `auto-fill`/`minmax` simply reflows to fewer columns (verified: single 356px column at a 640px viewport, zero overflowing elements, no page-level horizontal scroll).
- **KEEP:** the backend by-id endpoint, its cross-tenant 404 tests, `StatusPill`, the Detail panel, and the client-side sort/filter are untouched by this change.

## Design Notes

Detail as a nested route is what makes the deep-link matrix row work for free: `ProtectedRoute` already stashes `location.state.from` and `LoginPage` already redirects back to it (Story 1.5), so an unauthenticated deep link to `/documents/:id` lands on the right document after login with no new code.

`StatusPill` is extracted rather than inlined because Epic 3's chat scope panel renders the same five states, and only 2 of 5 pill token pairs were originally specified — one component makes the rest verifiable in one place.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the new cross-tenant 404 tests
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: all clean

**Manual checks (if no CLI):**
- Click a row body vs. the trash icon: only the row body navigates.
- Tab through a row: the trash icon is reachable and does not trigger navigation on Enter/Space.
- Detail at 200% zoom: no horizontal scroll or clipping.
