---
title: 'Folder grouping for the documents library'
type: 'feature'
created: '2026-08-21'
status: 'in-progress'
review_loop_iteration: 1
context: []
baseline_commit: '0bf192d6fab054a50be08d4398b61eec1b842ac2'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The document library is a single flat grid with no way to group related documents, so it gets harder to navigate as the number of uploads grows.

**Approach:** Add user-owned folders (name + pastel color) that documents can optionally belong to (one folder per document, or none/"Ungrouped"). A "Folders" section heading sits above a folder tile grid, above the existing document grid; selecting a tile filters the grid client-side, matching the page's existing client-side sort/filter convention. Folders are created/renamed/recolored/deleted inline via small icon actions on each tile. Documents can be moved into a folder three ways: a "⋮" overflow menu on each `DocumentCard` with a "Move to folder" submenu (existing folders + "Create new folder"); dragging one document card onto another creates a new folder (via the create-folder dialog, pre-filled) and puts both in it, or — if the target document already belongs to a folder — adds the dragged document to that folder instead; dragging a document card onto a folder tile moves it into that folder directly.

## Boundaries & Constraints

**Always:**
- Every folder repository query goes through `user_scoped_select` (AD-2), same as `documents/repository.py`.
- Folder `color` is a fixed vocabulary enforced in service code (mirrors `Document.status`), never a free-form client hex value.
- Deleting a folder never deletes its documents — `documents.folder_id` uses `ON DELETE SET NULL`; the row survives as ungrouped.
- `GET /documents` already returns the full per-user list; folder membership counts and folder-scoped filtering are computed **client-side** over that list (no new query param), matching `DocumentsPage.jsx`'s existing "sort/filter is client-side" rule.
- Cross-tenant or nonexistent folder id → 404 `"Folder not found."`, never 403 (matches `Document`'s IDOR convention).
- Dragging a document always reassigns *the dragged document* to the resulting/target folder (one folder per document still holds) — dropping never merges folders or moves more than the single dragged document.
- A drag-created folder still goes through the same `FolderModal` create flow (name + color chosen by the human) — never a silently auto-named/auto-colored folder with no human confirmation.
- Native HTML5 drag-and-drop (`draggable`, `onDragStart`/`onDragOver`/`onDrop`) only — no new dependency for it.

**Ask First:** If implementation reveals a genuine need for nested folders, a document in multiple folders, or moving more than one document per drag, HALT and ask before building it.

**Never:** Nested or multi-parent folders. Bulk multi-select move actions (drag is always exactly one document). A grid/list view toggle. Pinning/favoriting folders or documents. Free-text color picker.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Create folder | `{name: "Тестове", color: "mint"}` | 201, folder row returned | N/A |
| Empty name | `{name: "", color: "mint"}` | — | 400 |
| Invalid color key | `{name: "x", color: "#ff0000"}` | — | 400 |
| Assign document to folder | `PATCH /documents/{id} {folder_id: <own folder>}` | 200, document now shows that folder | N/A |
| Assign to another user's folder | `folder_id` belongs to a different account | — | 404 `"Folder not found."` |
| Delete folder with documents | `DELETE /folders/{id}`, 3 docs assigned | 204; those docs' `folder_id` becomes `null` | N/A |
| Unassign document | `PATCH /documents/{id} {folder_id: null}` | 200, document becomes ungrouped | N/A |
| Drag doc A onto ungrouped doc B | Both currently `folder_id: null` | Create-folder dialog opens pre-filled; on confirm, both A and B get the new `folder_id` | N/A |
| Drag doc A onto doc B already in a folder | B has `folder_id: F` | A is assigned `folder_id: F` directly, no dialog | N/A |
| Drag doc A onto a folder tile | Tile represents folder `F` | A is assigned `folder_id: F` directly | N/A |
| Drag doc A onto itself / drop outside any target | No valid drop target | No-op, no request sent | N/A |

</frozen-after-approval>

## Spec Change Log

- **Trigger:** Human feedback after the initial implementation shipped and passed review (screenshot of the shipped `DocumentCard` folder `<select>`, plus two follow-up chat messages).
- **Amended:** (1) "Unfiled" → "Ungrouped" terminology, everywhere it's user-facing. (2) Added a "Folders" section heading above the tile grid. (3) Replaced the native `<select>`-based folder assignment on `DocumentCard` with a "⋮" overflow menu ("Move to folder" listing existing folders + "Create new folder") — this reverses the original spec's "do not build a new dropdown/menu/popover component" boundary, which is now struck. (4) Added drag-and-drop: doc-onto-doc (creates a folder via the existing dialog, or adds to the target's existing folder), and doc-onto-folder-tile (moves directly).
- **Known-bad state avoided:** Shipping a feature the human explicitly said doesn't match what they want, without capturing why the original "no new menu primitive" boundary no longer holds — a future reader must not assume that boundary is still in force.
- **KEEP:** Everything about the backend (folders module, `PATCH /documents/{id}`, tenancy, color vocabulary, migrations) is unaffected and must survive re-derivation untouched — this round is frontend-interaction-only. The existing `FolderModal` create/edit dialog is reused as-is for the drag-created-folder path, not rebuilt.

## Code Map

- `backend/app/shared/models.py` -- add `Folder(Base)` (id/user_id/name/color/created_at); add `Document.folder_id` nullable FK, `ondelete="SET NULL"`.
- `backend/alembic/versions/21fe494be69e_add_email_verified_at_to_users.py` -- current head; new migration's `down_revision` chains from `'21fe494be69e'`.
- `backend/app/shared/data_access/tenancy.py` -- `user_scoped_select(model, user_id)`, reuse verbatim in new `folders/repository.py`.
- `backend/app/documents/{routes,service,repository,schemas}.py` -- structural template (thin routes → service raises `HTTPException` → repository pure `user_scoped_select`, no commits); 404 wording at `service.py:539`; `DocumentResponse` uses `ConfigDict(from_attributes=True)` (`schemas.py:16`).
- `backend/app/main.py:32,144` -- router registration pattern to copy for a new `folders_router`.
- `backend/tests/conftest.py` -- `db_session`/`client` fixtures; module builders style from `test_documents_repository.py`.
- `frontend/src/components/UploadModal.jsx` -- only dialog reference in the app: backdrop (`:9-18`), focus trap (`:113-141`), escape-to-close, focus capture/return (`:76-84`), `aria-labelledby` heading id pattern. Reuse this shape for the folder create/edit dialog.
- `frontend/src/components/DocumentCard.jsx:156-215` -- inline confirm-box pattern (no modal) to reuse for folder delete confirmation.
- `frontend/src/pages/DocumentsPage.jsx:21-32,155-169,249-276` -- `SORT_OPTIONS`-style native `<select>` convention; `visibleDocuments` client-side derivation to extend with folder filtering.
- `frontend/src/api/documentsClient.js` -- `authFetch`-first-param pattern, `formatDetail(data?.detail)` error shape (see `listDocuments`, `:80-98`); mirror for new `foldersClient.js` and a new `updateDocumentFolder`.
- `frontend/src/index.css:28-186,188-271` -- token convention: light value in `:root`, dark override (often translucent `rgba`) in `:root[data-theme="dark"]`; `--status-*-bg`/`-text` pairs are the closest existing pastel precedent to model `--folder-color-*` on.
- `frontend/src/context/ChatScopeContext.jsx` -- AD-5 precedent showing only *selection ids* belong in Context; the full list stays page-local. Folders list/active-filter stay local to `DocumentsPage.jsx`, passed down as props — no new Context needed.

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/models.py` -- add `Folder` model + `Document.folder_id` column -- new domain object + FK per Intent
- [x] `backend/alembic/versions/f3a8c1d9b6e2_create_folders_table_and_document_.py` -- `op.create_table('folders', ...)` + `op.add_column('documents', 'folder_id', ...)` in one migration -- both must land atomically for referential integrity
- [x] `backend/app/folders/{__init__,schemas,repository,service,routes}.py` -- new vertical-slice module: `POST/GET /folders`, `PATCH /folders/{id}`, `DELETE /folders/{id}`; color vocabulary constant in `service.py` -- mirrors `documents` module structure
- [x] `backend/app/main.py` -- register `folders_router` -- wire the new module in
- [x] `backend/app/documents/schemas.py` -- add `folder_id: uuid.UUID | None` to `DocumentResponse` -- expose membership to the client
- [x] `backend/app/documents/{routes,service,repository}.py` -- add `PATCH /documents/{document_id}` accepting `{folder_id: uuid.UUID | None}`, validating the target folder belongs to `current_user` when not null -- document-side of the assignment, owned by the module that owns `Document`
- [x] `backend/tests/test_folders_repository.py`, `test_folders_routes.py` -- cover the I/O matrix + tenancy (cross-account 404) -- new module needs its own coverage
- [x] `backend/tests/test_documents_*` -- extend for `folder_id` in response + the new PATCH endpoint (happy path, cross-tenant folder_id, unassign)
- [x] `frontend/src/api/foldersClient.js` -- `listFolders`/`createFolder`/`updateFolder`/`deleteFolder`, `authFetch`-first pattern -- client for the new module
- [x] `frontend/src/api/documentsClient.js` -- add `updateDocumentFolder(authFetch, documentId, folderId)` -- client for the PATCH endpoint
- [x] `frontend/src/index.css` -- add ~6-8 `--folder-color-*` pastel tokens, light + dark, following the `--status-*` formula -- palette for the color picker
- [x] `frontend/src/components/FolderModal.jsx` -- create/edit dialog (name input + pastel swatch picker), built on `UploadModal.jsx`'s dialog shape -- single dialog reused for both create and edit
- [x] `frontend/src/components/FolderGrid.jsx` -- tile grid ("All documents", "Unfiled", each real folder with color+name+count, "+ New folder"); per-tile edit/delete icon buttons, delete uses the inline-confirm shape -- the folder view itself
- [x] `frontend/src/components/DocumentCard.jsx` -- add a native `<select>` for folder assignment, calls `updateDocumentFolder` -- lets a document move folders from the card
- [x] `frontend/src/pages/DocumentsPage.jsx` -- fetch folders alongside documents; compute counts + active-filter client-side over `documents`; render `FolderGrid`; pass `folders` down to `DocumentCard` -- wires everything together
- [x] `frontend/src/components/FolderGrid.test.jsx`, `FolderModal.test.jsx` -- new component tests, `vi.spyOn(foldersClient, ...)` pattern
- [x] extend `DocumentCard.test.jsx`, `DocumentsPage.test.jsx` -- cover folder assignment + filtering

**Round 2 (human feedback, see Spec Change Log):**
- [x] `frontend/src/components/FolderGrid.jsx`, `DocumentsPage.jsx` -- rename all user-facing "Unfiled" strings to "Ungrouped" -- terminology change
- [x] `frontend/src/pages/DocumentsPage.jsx` -- add a "Folders" section heading above `FolderGrid` (small label/heading, matching the existing eyebrow/heading convention already used for "Your library" / "Documents") -- makes the section legible as its own area
- [x] `frontend/src/components/DocumentCard.jsx` -- remove the native `<select>` folder-assignment control; replace with a "⋮" icon button opening a small menu: "Move to folder" listing every folder name (calls `updateDocumentFolder`) plus a trailing "Create new folder" item (opens `FolderModal`, then assigns the newly created folder on success) -- this is the one new menu/popover primitive this project now has; keep it minimal (a plain absolutely-positioned list, `role="menu"`/`role="menuitem"`, Escape + outside-click to close, matching this project's existing focus-management conventions from `UploadModal`/`DocumentCard`'s confirm box) since nothing reusable exists yet to build on
- [x] `frontend/src/components/DocumentCard.jsx` -- make the card `draggable`; `onDragStart` stores the dragged document's id (e.g. `event.dataTransfer.setData('text/plain', document.id)`); `onDragOver`/`onDrop` on every *other* card: if the drop target already has a `folder_id`, PATCH the dragged document to that `folder_id` directly; if not, open `FolderModal` in create mode, and on successful create, PATCH *both* the dragged and target document to the new folder's id
- [x] `frontend/src/components/FolderGrid.jsx` -- each folder tile becomes a drop target (`onDragOver`/`onDrop`): dropping a dragged document id there calls `updateDocumentFolder(documentId, thatFolder.id)` directly, no dialog
- [x] extend `DocumentCard.test.jsx`, `FolderGrid.test.jsx`, `DocumentsPage.test.jsx` -- cover the "⋮" menu (list + create-new item), doc-onto-doc drag (both branches: creates dialog vs. direct-add-to-existing-folder), doc-onto-folder-tile drag, and the "Ungrouped" rename -- new interaction surface needs its own coverage; simulate HTML5 DnD via `fireEvent.dragStart`/`dragOver`/`drop` with a `dataTransfer` stub, matching Testing Library's documented DnD pattern

**Acceptance Criteria:**
- Given a user with no folders, when they open Documents, then they see a "Folders" heading, "All documents" and "Ungrouped" tiles (no empty folder tiles), and every document is Ungrouped.
- Given a user creates a folder and assigns a document to it, when they select that folder tile, then only that document shows in the grid, and the tile's count is 1.
- Given a user deletes a folder that has documents, when the delete completes, then those documents remain (now Ungrouped) and no data is lost.
- Given account B, when it requests `PATCH /documents/{account-A-doc-id}` or any folder endpoint with account A's folder id, then it gets 404, never account A's data.
- Given two ungrouped documents, when the user drags one onto the other, then the create-folder dialog opens, and confirming it assigns both documents to the new folder.
- Given a document and a folder tile, when the user drags the document onto the tile, then the document is assigned to that folder with no dialog.
- Given a document card, when the user opens its "⋮" menu, then they see every folder plus "Create new folder", and choosing one assigns it without a page reload.

## Design Notes

Color palette: pick ~6-8 named pastel keys (e.g. `rose`, `peach`, `sun`, `mint`, `sky`, `lilac`) as the enforced vocabulary — small enough to render as a one-row swatch picker in `FolderModal`, consistent with the existing `--status-*` two-tone (bg + text) token pattern, translucent-`rgba`-over-dark-bg in the dark theme per that same precedent.

## Verification

**Commands:**
- `cd backend && python -m pytest` -- expected: full suite green, including new `test_folders_*` and extended `test_documents_*`
- `cd frontend && npm test` -- expected: full suite green, including new `FolderGrid`/`FolderModal` tests
- `cd backend && alembic upgrade head` -- expected: migration applies cleanly against a throwaway/dev DB

**Manual checks (if no CLI):**
- Open Documents page in both light and dark theme; confirm folder swatches read as pastel (not vivid) and text stays legible in both.
