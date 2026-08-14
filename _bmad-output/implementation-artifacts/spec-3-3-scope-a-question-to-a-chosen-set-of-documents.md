---
title: 'Story 3.3: Scope a question to a chosen set of documents'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'e172cff'
provenance: 'authored-before-implementation'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 3.1 built `DocumentsScopePanel` as a deliberately static, read-only list (its own header comment: checkboxes/select-all/filter are "explicitly Story 3.3's job"). Today `AskRequest` carries only `question`, and `search_passages` filters Weaviate on `user_id` alone — every question searches the user's entire library, with no way to narrow it. A user with a dozen contracts uploaded has no way to ask "what does the Q2 vendor agreement say about refunds" without the answer's retrieval pulling in passages from every other document too.

**Approach:** `AskRequest` gains an optional `document_ids` list (empty = search everything, per FR-11's stated default). `search_passages` ANDs a `Filter.by_property("document_id").contains_any(document_ids)` onto its existing `user_id` filter when the list is non-empty — the same `&`-combined-filter shape `delete_passages_for_document` already uses, so out-of-scope passages are excluded at the Weaviate query itself, never at the application layer after the fact (no citation can ever surface from a passage the query didn't return). The frontend adds interactivity to the existing panel: per-document checkboxes (unchecked by default, OD-6), a "Select all" control limited to Ready documents (UX-DR10), a client-side filter over the panel's own list only (OD-5 — never a library-wide search), and a legible note when nothing is checked so an all-unchecked state reads as "asking across everything," not "nothing selected." Selected ids live in a new `ChatScopeContext` (AD-5 names "chat document-scope" explicitly as context-owned state), shared between the panel and `ChatPage`'s submit handler.

## Boundaries & Constraints

**Always:**
- `document_ids` empty or omitted means "search all of the user's documents" — the exact FR-11 default, unchanged from Story 3.1's behavior in that case.
- Scope filtering happens once, at the Weaviate query (`search_passages`), not as a second application-layer filter over citations afterward — the query itself is the only thing standing between an out-of-scope passage and a citation, so there's exactly one place this guarantee can break, not two that could drift apart.
- No ownership validation on `document_ids` before it reaches `search_passages`. The existing `Filter.by_property("user_id").equal(user_id)` filter is ANDed with the document-id filter, not OR'd or applied separately — so a foreign or deleted id in the list simply matches nothing server-side; it can never widen retrieval to another tenant's passages. This is a deliberate reuse of the tenancy mechanism `search_passages`'s own docstring already documents for the unscoped case, not a gap to close with a second, redundant ownership check.
- A checkbox toggle applies immediately — no separate "apply"/"save scope" step. The context's `selectedDocumentIds` at the moment `handleSubmit` runs is what's sent; nothing buffers or debounces it (UX-DR9).
- Only documents at `status === "Ready"` are selectable. Every other status renders its checkbox `disabled`, with the status visible inline (the existing `StatusPill` already renders it as real text) and also present in the checkbox's own `aria-label`, not only as sighted-only inline text (UX-DR9/UX-DR27).
- The panel's filter input narrows which rows of the already-fetched document list are rendered, by filename substring, client-side only. It never calls a search/list endpoint itself, and never touches `selectedDocumentIds` — a document filtered out of view stays selected if it was (OD-5, UX-DR10 as amended).
- "Select all" scopes every `Ready` document from the full fetched list, regardless of what the filter input currently hides (UX-DR10's literal "every Ready document," not "every visible Ready document").
- An all-unchecked panel state renders a visible, legible note that the question will search everything — not merely "nothing selected" (OD-6).

**Ask First:** none outstanding.

**Never:**
- No library-wide document search from the panel's filter input — that remains out of v1 scope per OD-5's resolution of the earlier §6.2 conflict.
- No change to the refusal (relevance-threshold) branch's logic — scope only changes which passages are retrieval candidates in the first place; once passages exist, refusal/citation logic is exactly Story 3.2's, untouched.
- No polling/refetch of the document list from the scope panel in this story — `retainOnly` (the selection-pruning helper on `ChatScopeContext`) exists as a safety net for a future refetch, not because one exists today. `ChatScopeProvider` lives inside `ChatPage`, so navigating away and back already resets the selection to empty by unmounting the provider — there is no live bug this closes yet.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No documents checked | `document_ids` omitted or `[]` | Retrieval searches all of the user's documents (Story 3.1's existing behavior, unchanged) | N/A |
| Subset checked | `document_ids` = a non-empty list of the user's own document ids | `search_passages` ANDs `document_id.contains_any(...)` onto `user_id.equal(...)`; only passages from those documents are retrieval candidates | N/A |
| Checked documents have no matching passages | Non-empty `document_ids`, `search_passages` returns `[]` | 200, `segments: []`, `empty_reason="empty_scope"` — distinct from `"no_documents"`, since the library isn't actually empty, the scope just excluded everything relevant | N/A |
| Empty library, no scope | `document_ids` omitted/`[]`, `search_passages` returns `[]` | 200, `segments: []`, `empty_reason="no_documents"` (Story 3.1, unchanged) | N/A |
| Foreign/stale id in `document_ids` | A document id not owned by the current user (or since deleted) | Matches nothing — the `user_id` AND-filter excludes it; never a 403/404, never leaks another tenant's passages | N/A |
| Non-Ready document in the panel | `status` in `Uploaded`/`Extracting`/`Graphing`/`Failed` | Checkbox rendered `disabled`, status shown inline (StatusPill) and in `aria-label` | N/A |
| Filter text typed | Any string | Visible `<li>` rows narrow to filename matches; `selectedDocumentIds` unchanged, including for now-hidden rows | N/A |
| "Select all" clicked | Any filter state | Every `Ready` document (from the full list, not the filtered view) becomes selected | N/A |
| Oversized `document_ids` | Client sends more than 200 ids | 422 (Pydantic `max_length` validation) — defensive cap, not a measured value | FastAPI's default validation-error envelope |

</frozen-after-approval>

## Code Map

- `backend/app/chat/schemas.py` -- edit: `AskRequest.document_ids`, `AskResponse.empty_reason` gains `"empty_scope"`
- `backend/app/chat/routes.py` -- edit: pass `request.document_ids` through
- `backend/app/chat/service.py` -- edit: `document_ids` param, `empty_scope` vs `no_documents` branch
- `backend/app/shared/data_access/weaviate_client.py` -- edit: `search_passages` gains optional `document_ids`, ANDed `contains_any` filter
- `backend/tests/test_weaviate_client.py` -- edit: document_ids filter coverage
- `backend/tests/test_chat_ask_route.py` -- edit: scope-threading, default, and empty_scope-vs-no_documents coverage
- `frontend/src/context/ChatScopeContext.jsx` -- new: `selectedDocumentIds`, `toggleDocument`, `selectAll`, `retainOnly`
- `frontend/src/context/ChatScopeContext.test.jsx` -- new
- `frontend/src/pages/ChatPage.jsx` -- edit: split into `ChatPage` (provider wrapper) + `ChatPageContent`, threads `selectedDocumentIds` into `askQuestion`
- `frontend/src/pages/ChatPage.scope.test.jsx` -- new
- `frontend/src/pages/ChatPage.test.jsx` -- edit: one added `empty_scope` notice case
- `frontend/src/api/chatClient.js` -- edit: `askQuestion` gains `documentIds` param
- `frontend/src/api/chatClient.test.js` -- edit: `document_ids` body coverage
- `frontend/src/components/chat/DocumentsScopePanel.jsx` -- edit: checkboxes, Select all, filter input, legible all-unchecked note
- `frontend/src/components/chat/DocumentsScopePanel.test.jsx` -- edit: replaces the stale "no checkboxes" test
- `frontend/src/components/chat/ChatMessage.jsx` -- edit: `NOTICE_COPY.empty_scope`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/chat/schemas.py` -- `document_ids` field, `empty_scope` literal
- [x] `backend/app/chat/routes.py` -- threaded through
- [x] `backend/app/chat/service.py` -- scoped retrieval, four-way `empty_reason` branch
- [x] `backend/app/shared/data_access/weaviate_client.py` -- `document_ids` filter
- [x] backend tests (5 new: 2 in `test_weaviate_client.py`, 3 in `test_chat_ask_route.py`; `pytest`: 207 passed)
- [x] `frontend/src/context/ChatScopeContext.jsx`
- [x] `frontend/src/pages/ChatPage.jsx` split + `chatClient.js`
- [x] `frontend/src/components/chat/DocumentsScopePanel.jsx` interactivity
- [x] `frontend/src/components/chat/ChatMessage.jsx` -- `empty_scope` copy
- [x] frontend tests (new: `ChatScopeContext.test.jsx`, `ChatPage.scope.test.jsx`; extended: `chatClient.test.js`, `DocumentsScopePanel.test.jsx`, `ChatPage.test.jsx`; `npm test`: 132 passed; lint/build clean)
- [x] manual verification against the real dev servers

**Acceptance Criteria:** (mirrors the story's own Gherkin in `epics.md`)
- Given I open the Chat page, when the documents-in-scope panel loads, then no document is pre-checked (OD-6).
- Given no document is checked, when I ask a question, then retrieval runs against all of my documents per FR-11's default, and the panel communicates this legibly (OD-6, FR-11).
- Given I check a subset of documents, when I ask a question, then retrieval considers only passages from those documents, and passages outside the selected scope never appear as citations (FR-11).
- Given a document that has not reached Ready, when it appears in the scope panel, then its checkbox is disabled with the status noted inline and exposed programmatically via `aria-label` (UX-DR9, UX-DR27).
- Given the "Select all" affordance, when I use it, then every Ready document is brought into scope at once (UX-DR10).
- Given the document filter control, when I type in it, then it filters only the selectable list within the scope panel, never the document library (OD-5, UX-DR10 as amended).
- Given I toggle a document's checkbox, when the change registers, then it applies immediately with no separate apply step, and governs the scope of the next question (UX-DR9).

## Verification

**Commands:**
- `pytest` (from `backend/`) -- 207 passed, including 5 new scoping tests.
- `npm test -- --run` / `npm run lint` / `npm run build` (from `frontend/`) -- 132 passed; lint clean (only the pre-existing `only-export-components` fast-refresh warnings shared with `AuthContext.jsx`/`ThemeContext.jsx`); build clean.

**Manual checks -- completed against the real backend/frontend dev servers, real Weaviate, real Neo4j, real Postgres (account: `essinkabg@gmail.com`, which already carried `story32_verify_doc.md`, Ready, from Story 3.2's own verification):**
- Chat page with one Ready document: scope panel loaded with the checkbox unchecked and "Asking across all 1 document." shown -- OD-6 confirmed live, not just in tests.
- Asked "What is the refund window for TechCorp Supplies?" with nothing checked -- 200, real cited answer ("...30 days from the delivery date.", `Ch. Chapter 1: Refund Policy, story32_verify_doc.md`) -- confirms the default (search-everything) path is unaffected by this story's changes.
- Checked the one Ready document (note updated to "1 of 1 selected." immediately, no reload) and asked a second question -- request scoped correctly; got `empty_reason="no_answer"` (the document's real content didn't answer that particular question) rather than an error, confirming scoped retrieval reaches the backend and behaves like any other retrieval, not a degenerate path.
- Uploaded a second real document (`hr_handbook.md`) to reach a live non-Ready state: while `Graphing`, its checkbox rendered `disabled` with `aria-label="hr_handbook.md — not available yet (Graphing)"` -- confirmed via direct DOM inspection, not just accessible-name matching in tests.
- Filter input: typing a substring narrowed the visible `<li>` rows to matching filenames only; clearing it restored both rows -- confirmed via the DOM, dispatching a real `input` event through React's controlled-input value setter (a plain `.value =` assignment doesn't reach React's change detection, which is a testing-tool detail worth knowing, not a product bug).
- "Select all": selected only the Ready document, left the `Graphing` one untouched and its checkbox still unable to be checked even by a scripted event dispatched directly at it (bypassing normal browser click semantics) -- see the fix below.
- **One real finding from manual verification, fixed before sign-off:** the disabled-checkbox branch in `DocumentsScopePanel.jsx` was rendering an *uncontrolled* `<input type="checkbox" disabled>` (no `checked` prop). A scripted `dispatchEvent(new MouseEvent('click'))` aimed directly at it in the sandboxed verification browser toggled it to `checked: true` -- a real user's mouse/keyboard can't reach a disabled control this way, but relying on that instead of the component itself enforcing it was an unnecessary gap. Fixed by making it controlled (`checked={selectedDocumentIds.includes(doc.id)}`, always `false` in practice since `retainOnly` prevents a non-Ready id from ever entering the selection, plus a no-op `onChange` to satisfy React's controlled-input contract) -- re-verified live afterward: the same scripted dispatch against the disabled checkbox now has no effect, and "Select all" continues to select only the Ready document.
- Cleanup: `hr_handbook.md`'s Postgres row and Weaviate passages were removed after verification (via `delete_passages_for_document` and a direct `DELETE`) so the shared test account is left as it was found. Its few Neo4j entities were deliberately **not** removed -- entities merge on `(name, type, user_id)` with no per-document tag (AD-4), so there is no safe query to remove only one document's contribution without risking `story32_verify_doc.md`'s own shared entities; that gap is exactly what Story 2.7 (delete a document) is meant to close.
- Not manually re-verified live: the `empty_scope` `empty_reason` itself (constructing a live scope that retrieves literally zero passages isn't easily reproducible without a purpose-built document) and dark-mode rendering of the new checkbox/filter UI -- both covered by automated tests instead (`test_ask_scoped_to_documents_with_no_passages_returns_empty_scope_not_no_documents`; the new UI reuses existing `StatusPill`/token classes with no new colors introduced, so no new dark-mode-specific risk).

