---
title: 'Story 2.7: Delete a document with an honest deletion boundary'
type: 'feature'
created: '2026-08-14'
status: 'in-review'
review_loop_iteration: 0
context: []
baseline_commit: 'e172cff0d884c4a39d66063bb0cd7682c50ea2cc'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Documents can be uploaded and ingested but never removed. `DocumentCard.jsx`'s trash button already exists (focusable, `aria-label="Delete {filename}"`) but is explicitly wired to nothing — its own comment says "that is Story 2.7." No `DELETE /documents/{id}` endpoint exists anywhere in the backend.

**Approach:** Add `DELETE /documents/{document_id}`, IDOR-safe (404, not 403, mirroring `get_document`), which deletes the document's Weaviate passages first, then hard-deletes the row — Neo4j entities/relationships are deliberately left untouched, a permanent boundary, not an oversight. Wire the trash button (and a new Delete control on Document Detail) to an inline confirm box — built from scratch, no modal, no existing component to reuse — that states the boundary plainly before acting.

## Boundaries & Constraints

**Always:**
- Delete order: `delete_passages_for_document` (Weaviate) first, then `db.delete(document)` + commit — if the Weaviate delete raises, nothing has been committed yet, the document still exists, and the user can safely retry. The reverse order would risk an orphaned Weaviate entry for a document that no longer exists in Postgres.
- `DELETE /documents/{document_id}` reuses `get_document_for_user`'s exact tenancy-scoped lookup (404 for both "no such document" and "not yours," indistinguishable by construction — AD-2's existing IDOR pattern, not a new one).
- Neo4j is never touched by delete — no query, no import of the Neo4j client into this path. This is FR-8's explicit, permanent boundary (avoids reference-counting complexity in a unified multi-document graph), not a deferred TODO.
- The inline confirm box states plainly, before any action: passages are removed from search *immediately*, and entities already merged into the graph from this document *remain* and may still influence future answers. Declarative wording, no "sorry," no hedging (FR-8, UX-DR19).
- Full inline-confirm a11y (UX-DR26): appearance announced (`role="alert"` on the box, matching this app's existing error-announcement pattern), the boundary text's `id` referenced via `aria-describedby` on both Confirm and Cancel, focus moves into the box on open (to Cancel — the safer default for a destructive action), Escape collapses back to the resting Delete control, focus returns to the control that opened it on any non-deleting close.
- On successful delete: `DocumentCard`'s parent (`DocumentsPage`) removes the row from its local list without a full refetch (matches Story 2.2's existing client-side sort/filter-only pattern); `DocumentDetailPage` navigates back to `/documents` (nothing left to show at that route).
- `documentsClient.deleteDocument(authFetch, documentId)` mirrors `getDocument`/`listDocuments`'s existing error-handling shape (`!response.ok` → `Error(formatDetail(data?.detail) || fallback)`), adapted for a 204 empty body.

**Ask First:** none — every open question (delete order, IDOR pattern, confirm-box a11y shape, Neo4j boundary) is already resolved by this epic's existing precedent or by epics.md's literal AC text.

**Never:**
- No soft-delete flag, no `deleted_at` column — a hard row delete. `Document` has no existing FK pointed at it from any other table (confirmed: only `User`/`Document` exist), so no cascade handling is needed.
- No Neo4j pruning of any kind on delete — explicitly out of scope, permanently (see Boundaries above).
- No confirm *modal* — UX-DR14 specifically calls for inline, not the shared modal pattern `UploadModal.jsx` uses.
- No change to chat/citation behavior — both already resolve documents live at query time (`chat/service.py` already handles a since-deleted document's missing filename by dropping the citation, not fabricating one), so a deleted document disappears from scope/citations with no code change in `chat/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Delete a document you own | Valid `document_id`, owned by caller | 204; row and its Weaviate passages gone; Neo4j entities untouched | N/A |
| Delete another account's document | Valid `document_id`, owned by someone else | 404 "Document not found." — same message as a nonexistent id | N/A |
| Delete a nonexistent document | Random/garbage-but-valid-UUID `document_id` | 404, identical to the "not yours" case | N/A |
| Delete a document with zero passages (e.g. still `Uploaded`, never reached `Ready`) | No Weaviate rows exist for it | Succeeds — `delete_passages_for_document` is already idempotent against zero rows | N/A |
| Trash-icon click on a card | Card in resting state | Inline confirm box replaces/augments the card content; nothing deleted yet | N/A |
| Escape while confirm box is open | Confirm box focused | Collapses back to resting state; focus returns to the trash button | N/A |
| Cancel click | Confirm box open | Same as Escape | N/A |
| Confirm click | Confirm box open | `DELETE` fires; row removed from the list on success | On failure: error shown, row stays, confirm box stays open for retry |
| Delete from Document Detail | Delete button clicked, then confirmed | Same backend call; on success, navigates to `/documents` | N/A |

</frozen-after-approval>

## Code Map

- `backend/app/documents/repository.py` -- edit: `delete_document_for_user(db, user_id, document_id) -> bool`, mirrors `get_document_for_user`'s tenancy-scoped lookup, then `db.delete(...)` (does not commit — caller owns the transaction, matching `create_document`'s existing convention)
- `backend/app/documents/service.py` -- edit: `delete_document(db, current_user, document_id) -> None`, raises `HTTPException(404)` on a missing/not-owned document (reusing the same lookup `get_document` already uses), raises `HTTPException(409)` if `document.status` is not `Ready`/`Failed` (Spec Change Log), calls `delete_passages_for_document` before the repository delete, commits
- `backend/app/documents/routes.py` -- edit: `DELETE /documents/{document_id}`, `status_code=204`, same `document_id: uuid.UUID` typed param and `Depends(get_current_user)` pattern as the existing by-id route
- `frontend/src/api/documentsClient.js` -- edit: `deleteDocument(authFetch, documentId)`, mirrors `getDocument`'s error-handling shape for a 204 response
- `frontend/src/components/DocumentCard.jsx` -- edit: trash button wired to local `isConfirming`/`isDeleting` state; inline confirm box replaces the card's lower content when confirming; `onDeleted(documentId)` prop called on success
- `frontend/src/pages/DocumentsPage.jsx` -- edit: passes `onDeleted` down to `DocumentCard`, removes the deleted id from local state on success (no refetch)
- `frontend/src/pages/DocumentDetailPage.jsx` -- edit: new Delete button + the same inline confirm pattern; `useNavigate()` back to `/documents` on success
- `backend/tests/test_documents_delete.py` -- new: own-document success (row + Weaviate both gone, Neo4j untouched), cross-user 404, nonexistent-id 404, zero-passages document succeeds (now a `Failed` document -- see Spec Change Log), 409 for every non-terminal status
- `frontend/src/api/documentsClient.test.js` -- edit: real `deleteDocument` coverage against a fake `authFetch`/`Response` (Spec Change Log)
- `frontend/src/components/DocumentCard.test.jsx` -- new: trash click shows confirm, Escape/Cancel collapse and return focus, Confirm calls `deleteDocument` and `onDeleted`, `aria-describedby`/`role="alert"` wiring
- `frontend/src/pages/DocumentDetailPage.test.jsx` -- edit: Delete button + confirm + successful-delete navigation to `/documents`
- `frontend/src/pages/DocumentsPage.test.jsx` -- edit: real end-to-end delete flow through `handleDeleted` (Spec Change Log)

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/documents/repository.py` -- `delete_document_for_user`
- [x] `backend/app/documents/service.py` -- `delete_document` (Weaviate-then-row order, Neo4j untouched) -- the story's core AC
- [x] `backend/app/documents/routes.py` -- `DELETE /documents/{document_id}`
- [x] `frontend/src/api/documentsClient.js` -- `deleteDocument`
- [x] `frontend/src/components/DocumentCard.jsx` -- inline confirm, full a11y wiring
- [x] `frontend/src/pages/DocumentsPage.jsx` -- local-list removal on delete
- [x] `frontend/src/pages/DocumentDetailPage.jsx` -- Delete button, inline confirm, post-delete navigation
- [x] `backend/tests/test_documents_delete.py` -- own/cross-user/nonexistent/zero-passages coverage, plus a delete-order invariant, a Weaviate-failure retry-safety test, a bytecode-level Neo4j-never-touched test, and 409-mid-ingestion coverage (Spec Change Log)
- [x] `frontend/src/api/documentsClient.test.js` -- real `deleteDocument` request/response coverage, not just mocks (Spec Change Log)
- [x] `frontend/src/components/DocumentCard.test.jsx` -- confirm interaction + a11y
- [x] `frontend/src/pages/DocumentDetailPage.test.jsx` -- Delete + navigation
- [x] `frontend/src/pages/DocumentsPage.test.jsx` -- real end-to-end delete through `handleDeleted` (Spec Change Log)

**Acceptance Criteria:**
- Given a document row or Document Detail, when the trash icon or Delete button is clicked, then nothing is deleted yet and an inline confirm box appears instead (UX-DR14).
- Given the inline confirm box, when it renders, then it states plainly that passages are removed from search immediately and that graph entities remain and may still influence future answers, with no apologetic filler (FR-8, UX-DR19).
- Given a confirmed deletion, when it executes, then the document row and its Weaviate passages/embeddings are gone, through the shared data-access layer (FR-8, AD-2).
- Given a confirmed deletion, when it executes, then Neo4j entities/relationships derived from that document are deliberately left untouched (FR-8).
- Given a deleted document, when the library or chat is next used, then it no longer appears in the list, in chat scope, or as a citation.
- Given the inline confirm box, when a screen-reader or keyboard user encounters it, then its appearance is announced, the boundary text is programmatically tied to Confirm/Cancel, focus moves into the box, Escape collapses it, and focus returns to the triggering control on close (UX-DR26).
- Given a document that is still `Uploaded`, `Extracting`, or `Graphing`, when a delete is attempted, then it is refused with 409 and neither the row nor any Weaviate passages are touched (Spec Change Log).

## Spec Change Log

- **Trigger:** Three-layer adversarial review (blind-hunter, edge-case-hunter, verification-gap) against the implementation diff, all originally-specified tests green.
- **Deploy-blocking behavioral gap, found and fixed:** the frozen I/O matrix's "Delete a document with zero passages (e.g. still `Uploaded`, never reached `Ready`)" row assumed a document sitting in a non-terminal status is safe to delete because it has no Weaviate rows yet. That is false whenever ingestion is actually in flight: `DocumentsPage.jsx`'s own `POLLABLE_STATUSES = ['Uploaded', 'Extracting', 'Graphing']` documents that `ingest_document` runs as a genuine concurrent `BackgroundTasks` job against the row while it holds one of those statuses -- writing Weaviate passages during `Extracting`, then Neo4j entities during `Graphing`. `delete_document`'s own `delete_passages_for_document` call runs at one instant; the background task keeps writing after it, orphaning fresh Weaviate passages under a document id that no longer exists in Postgres once the row-delete commits. That's exactly the "no orphaned partial state" failure AD-1's compensating-rollback design exists to prevent, reached from a direction the original matrix never considered (a *second* writer, not a failure in the delete path itself). Fixed: `service.delete_document` now checks `document.status` immediately after the existing `get_document` lookup and raises `HTTPException(409, "Document is still being processed and can't be deleted yet.")` for anything other than `Ready`/`Failed` -- the two statuses guaranteed to have no background task concurrently touching the row. This mirrors `claim_failed_document_for_reingest`'s existing retry-lock precedent (Story 2.6): only act on a document when no background task could be concurrently touching it. New tests: `test_delete_refuses_a_document_mid_ingestion_with_409` (row/passages provably untouched by a refused attempt) and `test_delete_refuses_every_non_terminal_status_with_409` (parametrized over `Uploaded`/`Extracting`/`Graphing`).
- **Narrows the frozen I/O matrix:** the "zero passages" row's premise ("e.g. still `Uploaded`, never reached `Ready`") no longer holds -- `Uploaded` is not a deletable status as of the fix above. The zero-passages case is now covered by a `Failed` document instead (also terminal, also frequently zero-Weaviate-rows -- e.g. a parse failure before indexing ever started), which is what `test_delete_a_document_with_zero_passages_still_succeeds` now sets up. The row's *conclusion* ("Succeeds -- `delete_passages_for_document` is already idempotent against zero rows") is unchanged; only which status demonstrates it changed.
- **Test gap, found and fixed:** every existing frontend test touching `deleteDocument` (`DocumentCard.test.jsx`, `DocumentDetailPage.test.jsx`) replaced it with `vi.spyOn(...).mockResolvedValue/mockRejectedValue` -- none exercised the real function body, so a broken `deleteDocument` (e.g. unconditionally calling `response.json()` on a bodyless 204) would still have shown all-green. Fixed: added a `describe('deleteDocument', ...)` block to `documentsClient.test.js`, mirroring the existing `getDocument` tests in the same file -- a fake `authFetch` returning a real `Response`, asserting the request URL/method, that a 204 resolves without reading a body, and that a non-2xx response throws the backend's `detail` message.
- **Test gap, found and fixed:** `DocumentsPage.jsx`'s `handleDeleted` (the function that actually filters a deleted id out of the grid) was never exercised by a real delete flow -- `DocumentCard.test.jsx` renders `DocumentCard` standalone with its own `vi.fn()` for `onDeleted`, which can't observe `DocumentsPage`'s real filter logic. Fixed: added a `DocumentsPage.test.jsx` test that mocks `deleteDocument` to resolve, renders two documents, drives one card's full confirm-to-Delete flow, and asserts only that document's card is gone while the other remains.
- **Polish, found and fixed:** `DELETE_BOUNDARY_TEXT` was defined verbatim in both `DocumentCard.jsx` and `DocumentDetailPage.jsx`, free to drift. Extracted to one shared constant in `frontend/src/utils/documentFormat.js`, imported by both.
- **Polish, found and fixed:** neither delete trigger (`DocumentCard`'s trash button, `DocumentDetailPage`'s Delete button) communicated its disclosure-toggle role via ARIA. Both now carry `aria-expanded={isConfirming}` (or that file's equivalent state variable).
- **Polish, found and fixed:** a successful delete from `DocumentCard` unmounted the row that held focus (the confirm box's Delete button), dropping focus to `document.body` with no announced landing place -- the one moment in this whole story a keyboard/screen-reader user most needed to stay oriented. `DocumentDetailPage` was already fine (it navigates away to a new focus context). Fixed: `DocumentsPage` passes its existing `uploadButtonRef` down; `handleDeleted` focuses it after removing the row from state.
- **Investigated, not fixed here (logged to `deferred-work.md`):** `delete_document_for_user`'s boolean return is never checked by its caller in `service.delete_document` -- accepted as idempotent-delete semantics (the preceding `get_document` call already guarantees the row exists moments earlier in the same transaction). The `db.commit()` after a successful Weaviate delete is unwrapped (a commit failure there would raise past the route with no compensating action) -- accepted, matches an existing precedented gap elsewhere in this codebase. A stale in-flight poll response can transiently reintroduce a just-deleted document to the grid for about one poll cycle -- self-corrects on the next poll, low severity. None of the three are acted on in this entry.
- **KEEP:** every already-approved boundary above -- the Weaviate-then-row delete order, the tenancy-scoped 404 pattern, the permanent Neo4j boundary, the inline-confirm a11y contract, and the client-side-only list update on success -- none altered by this entry beyond the narrowing described above.

## Design Notes

Confirm-box focus default: Cancel, not Confirm — the safer default for a destructive action when focus must land somewhere on open; no AC mandates this specifically, but it's the conventional and lower-risk choice, called out here since a future reader might otherwise assume Confirm.

`DocumentCard`'s confirm state is local (`useState` inside the card), not lifted to `DocumentsPage` — each card is independent, and the only cross-component need is a single `onDeleted(id)` callback for the parent to update its list, not shared confirm-open state.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the new delete test file
- `npm run build` / `npm run lint` / `npm test -- --run` (from `frontend/`) -- expected: clean, including new DocumentCard/DocumentDetailPage delete coverage

**Manual checks (if no CLI):**
- Delete a `Ready` document from the library grid, confirm it disappears from the list, from a chat's document-scope panel, and stops being cited by chat — while its entities are still visible wherever the Knowledge Graph would be inspected (Epic 4, not yet built — confirm via a direct Neo4j query instead).
