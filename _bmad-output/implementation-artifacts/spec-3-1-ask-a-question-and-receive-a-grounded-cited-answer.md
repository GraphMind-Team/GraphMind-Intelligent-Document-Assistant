---
title: 'Story 3.1: Ask a question and receive a grounded, cited answer'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 3
context: []
baseline_commit: 'ea1be89d085bac13c10880bd671c548af5faab82'
provenance: 'reconstructed-after-implementation'
---

> **Provenance — read this before trusting the Boundaries below.**
>
> This spec was authored on 2026-08-14, *after* Story 3.1 shipped (`e26e1ef`, 2026-08-13) and after three review passes on it. Every other spec in this directory was written before its story was built; this one was not. Story 3.1 was implemented directly against `epics.md`'s acceptance criteria, and `deferred-work.md` recorded the missing file as a gap to close — this is that closure.
>
> The distinction matters, and is not a formality. The Boundaries section below is **reconstructed** from three sources — `epics.md`'s Story 3.1 acceptance criteria, the shipped code's own comments, and the three review passes' findings — so it describes what the story turned out to be bound by, not decisions a human approved in advance. Nothing here was negotiated before implementation, so nothing here carries the authority a genuinely frozen Boundaries section does. Treat it as an accurate record, not as a mandate that was honoured.
>
> Why that caveat is load-bearing: the concrete cost of this file's absence was UX-DR21. Story 3.1's review re-tuned the citation-chip contrast without first checking that `spec-1-2`'s Boundaries line 24 recorded it as a documented, human-accepted deviation. Closing it was still the right call (see the Spec Change Log), but the tension had to be reconciled across four documents afterwards instead of surfacing up front. A retro-spec that quietly presented itself as frozen would invite exactly the same error in the opposite direction — a future story treating these reconstructed lines as approved decisions and declining to revisit them.

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 2 ends with documents fully ingested — passages in Weaviate, entities in Neo4j, status `Ready` — and nothing that reads any of it. The `chat` module is an empty router from Story 1.1, `shared/data_access/weaviate_client.py` has only write/delete paths (its own docstring names a future reader function that doesn't exist yet), and `shared/llm_client/` knows only entity extraction. A user can fill their library and ask nothing.

**Approach:** The first read path end to end. `POST /chat/ask` embeds the question, vector-searches the user's own passages through the shared DAL, generates a segmented answer through the shared LLM wrapper, and resolves each segment's passage references into `{chapter, document_filename}` citations. The Chat page renders the thread, the citation chips, and the documents-in-scope panel. Retrieval always covers all of the user's documents; the relevance threshold and the scope selection are the next two stories.

## Boundaries & Constraints

**Always:**
- `shared/llm_client/` is the sole path to OpenRouter (AD-6) — `chat/` never constructs an OpenRouter client or issues an HTTP call to it. Chat generation gets its own public function, its own exception type, and its own independently-tuned timeout/retry budget, sharing no base class with extraction's — a future change to one must not silently move the other.
- Retrieval goes through `shared/data_access/` (AD-2). The vector search is filtered by a `user_id` resolved server-side from the JWT via `get_current_user`, never from anything in the request body (FR-2). Postgres reads use `user_scoped_select`, never a hand-written `select(Document).where(...)`.
- Every claim-bearing segment reaching the frontend carries at least one citation, and each citation names a specific document *and* a passage-level location, not merely a document-level source (FR-9). Enforced **in code** after the model responds — an out-of-range passage reference is dropped, a segment left with none is dropped entirely. Never trusted from the prompt alone, mirroring extraction's OD-1 enforcement precedent.
- The citation chip renders exactly `Ch. {chapter}, {document_filename}`, uses the citation token pair, and is a semantic inline element (`<cite>`), programmatically distinguishable from ordinary answer text rather than a bare styled `<span>` (UX-DR3, UX-DR28). Non-interactive — no click handler, role, or tabIndex.
- An arriving answer is announced through an `aria-live="polite"` region or equivalent, and turns carry semantic structure beyond alignment and bubble shape (UX-DR24).
- Layout is a two-column grid: flexible chat window + fixed 260px scope panel, 20px gutter; the composer is one row whose input and Ask button share a height (UX-DR9). Both fixed-width columns (this panel plus the shell's 220px sidebar) must reflow without horizontal scroll at 200% zoom (WCAG 1.4.4, UX-DR28).
- Bubbles follow UX-DR5 — user right/primary fill/sharp trailing corner, assistant left/surface fill/sharp leading corner — and the robot mascot is CSS shapes, small, left-aligned, 5px overlap on the composer, `aria-hidden`.
- An LLM-wrapper failure (timeout, retry exhaustion, OpenRouter error) surfaces as an ordinary service error per AD-3 — a 503 — and is never rendered as an answer, and never dressed up as the product's "I don't know" refusal (AD-6).

**Ask First:** none outstanding. OD-2 (the numeric relevance threshold) is genuinely open, but it belongs to Story 3.2 and is not this story's decision to make or pre-empt.

**Never:**
- No relevance threshold and no refusal path — FR-10 is Story 3.2. The zero-passage case here is a *degenerate library*, not a refusal, and must not be rendered as one (UX-DR15 has no design yet).
- No scope checkboxes, no "select all", no filter, no all-vs-subset retrieval logic — FR-11 is Story 3.3. The panel is a read-only list.
- No jump-to-source from a citation — explicitly out of v1 scope, which is why the chip is non-interactive.
- No conversation history sent to the model. Each question is answered from its own retrieval alone.
- No graph read or visualization — Epic 4.
- No change to the chip's `Ch. {chapter}, {document_filename}` text format. If the underlying data is too coarse, fix the data carried in the API, not the format UX-DR3 fixes.
- No re-tuning of a design token without first checking whether `spec-1-2`'s Boundaries record it as an accepted deviation. (Violated by this story's own review — see the Spec Change Log.)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal answer | Question, library with relevant `Ready` documents | 200, segments each with ≥1 `{chapter, document_filename, chunk_indexes}` citation | N/A |
| Empty / not-yet-ingested library | Vector search returns zero passages | 200 with `empty_reason="no_documents"`, `segments: []` — never an exception, never a refusal | N/A |
| Model finds nothing answerable | Passages found, model returns `{"segments": []}` | 200 with `empty_reason="no_answer"` — a distinct outcome from `no_documents`, rendered differently | N/A |
| Segment loses every citation | All its source documents deleted since indexing | That segment is dropped; if none survive, `empty_reason="no_answer"` | N/A |
| Cited document deleted / not owned | Filename lookup returns nothing for a `document_id` | That citation is dropped — never a fabricated filename, never a crash | N/A |
| Model cites an out-of-range passage | e.g. `passage_numbers: [9]` against 3 passages | That number is dropped; the segment survives on its valid ones | Warning logged |
| LLM fails after retries | Timeout / 5xx / 429 exhausted / malformed response | 503 with a plain detail — never an answer, never a refusal | Logged; frontend shows a distinct service banner |
| Non-retryable provider failure | 4xx other than 429 (bad key, bad request) | Immediate 503, no retry spent | Logged |
| Blank or over-length question | `"   "` or >2000 chars | 422 (FastAPI's own validation shape, no custom envelope per AD-3) | Input's `maxLength` prevents the over-length case reaching the backend at all |
| Single oversized passage | One passage alone exceeds the prompt budget | Included anyway — a zero-passage prompt is unanswerable by construction and still costs a real call | See Design Notes for the honest cost |
| Model repeats a passage number | `passage_numbers: [1, 1]` | One citation, one chunk index — the merge is over distinct source chunks, not mentions | N/A |
| Two chunks, same chapter | Routine at `TOP_K_PASSAGES=8` | One chip, but both chunk indexes retained in the payload | N/A |
| Cross-tenant retrieval result | Account B's request naming account A's document | Citation dropped, filename never resolved — proven by test, not by assumption | N/A |

</frozen-after-approval>

## Spec Change Log

Story 3.1 shipped before this file existed, so these entries are reconstructed from the branch's commit history and the review rounds' own findings. They are recorded here because the reasoning is load-bearing and was otherwise only discoverable by reading code comments.

- **Trigger:** First review pass on the shipped implementation (`a0acad0`, 2026-08-13).
- **Citations deduplicated:** two chunks from the same chapter of the same document (routine at `TOP_K_PASSAGES=8`) rendered as two identical chips side by side. Merged on `(chapter, document_filename)`, order-preserving.
- **Error handling tightened and silent truncation logged:** the prompt-budget truncation was invisible, making "why wasn't this document cited" indistinguishable from the model not finding it relevant.
- **KEEP:** every boundary above.

- **Trigger:** Second review pass (`7c09a17` and `d08ab7f`, 2026-08-13), covering contrast, focus behaviour, and the retrieval budget.
- **UX-DR21 closed — the entry this whole file exists because of.** The review flagged the citation-chip pair's 3.22:1 light-mode contrast as a defect and re-tuned `--citation-text` to `#3064C6` (4.62:1) **without first checking** that `spec-1-2`'s Boundaries recorded `#4A7FE0` as a documented, human-accepted AA deviation from 2026-08-11. Closing it was still correct — `epics.md`'s Epic 3 implementation notes always scoped UX-DR21 as open for closure here, so the 2026-08-11 acceptance was a decision to unblock Story 1.2, never a permanent one. But the check should have come first, and the reconciliation across `epics.md`, `DESIGN.md`, `spec-1-2` and the code happened afterwards (`cdb4c6b`) instead. This is the concrete cost of a missing spec file, recorded here so it reads as a process failure with a known cause rather than an unexplained token change.
- **`_MAX_PROMPT_CHARS` 6000 → 12000:** measured against the real chunker, the old budget let only 3 of 8 retrieved passages (English) or 2 of 8 (Bulgarian) reach the model, systematically discarding the back half of retrieval on almost every question.
- **`AnswerResult.included_passages` added:** citation resolution now keys off the exact budget-trimmed list the prompt was built from, not the full retrieval. Previously correct only because the trimming happens to drop from the tail — a future change to that selection could otherwise misattribute a citation to the wrong document, wrongly and plausibly, invisible to every existing test.
- **Focus retained through a pending request:** the composer input uses `readOnly` and the Ask button `aria-disabled` rather than native `disabled`, which drops keyboard focus to `<body>` with no reliable moment to restore it. Double-submit protection is unaffected — the `isAsking` guard in the submit handler always covered it.
- **NFR-1 deviation recorded in `deferred-work.md`:** p95 < 8s is knowingly not met (see Design Notes). Previously discoverable only by reading `shared/llm_client`'s inline comments, unlike every other accepted gap in this project.
- **KEEP:** everything above.

- **Trigger:** Third review pass (`18e5913`, 2026-08-14) — a read-only audit against the acceptance criteria, which surfaced two gaps that the full green test suite could not have revealed.
- **Tenancy had no test that could fail (the significant one):** the DAL test asserted only `"filters" in call_kwargs`, and every service-level test stubbed `search_passages` with `lambda *a, **k:` — so neither a swapped filter property nor a wrong `user_id` would have been caught, on the one AC where that matters most (FR-2/AD-2). Now asserts `filters.target`/`.value` at the DAL, plus a captured-args test proving the authenticated account's own id reaches `search_passages`.
- **FR-9 was degrading to document-level, and the first fix over-corrected:** `chapter` degenerates to `parsing.py`'s `"Full Document"` for any PDF without an outline — the common case — so every citation in such a document rendered identically, which is exactly the document-level-only source FR-9 forbids. Fixed by carrying chunk identity in the API (not by changing the chip, whose format UX-DR3 fixes). The first attempt used a scalar `chunk_index`, which the `(chapter, document_filename)` merge then reduced to the *first* contributing chunk — making the payload claim one specific chunk supported a segment when several did, more precise than the data actually was. Now `chunk_indexes: list[int]`, built through an insertion-ordered dict so first-occurrence-wins positioning is unchanged.
- **Startup warmup moved off the request path, then off the startup path:** `embed_texts` lazily constructs and, on a cold instance, downloads (~120MB) the fastembed model, and `ask_question` was the first caller paying that inline — the one path with no margin left inside the 130s client timeout. Warming it in `lifespan` fixed that but introduced a worse failure: inline, that download holds the app before `lifespan` yields, so uvicorn serves nothing and the platform health check can time out on a cold free-tier boot, turning a latency fix into a deploy failure. Now a named `_warm_embedding_model` on a daemon thread; `model.py`'s singleton is already double-checked-locking, so a request arriving mid-warmup shares the one instance.
- **A test that was falsely green, kept as a warning:** the first version of the non-blocking warmup test asserted from inside the stubbed `embed_texts`. `_warm_embedding_model` swallows every exception by design, so the assertion was eaten and the test passed *while the app blocked* — verified against an inline warmup. The signal has to be observed from outside, which the kept version does. Recorded because the falsely-green shape is the more natural one to write, and someone will be tempted to simplify back to it.
- **Accessibility gaps closed:** an sr-only `"You:"`/`"GraphMind:"` sender cue (UX-DR24 asks for structure beyond alignment and bubble shape, and a screen reader received none of UX-DR5's visual cues, so two turns read as one undifferentiated stream); `role="log"` + `tabIndex` + `aria-label` on the message list (Chrome 127+ makes an overflow scroller keyboard-focusable on its own, Firefox and Safari do not, leaving a keyboard-only user unable to scroll back through a long thread).
- **Oversized-passage fallback:** `_select_passages_within_budget` always includes at least the first passage — a single passage exceeding the budget alone (250 whitespace-split "words" against text with none) otherwise left a zero-passage prompt that still spent a real call and could only return `passage_count=0`. The honest cost is recorded in Design Notes.
- **Minor:** `maxLength={2000}` mirroring `AskRequest.max_length`; a fallback for an unrecognized `empty_reason`; `_parse_and_validate_answer` returns `list[AnswerSegment]` rather than a half-populated `AnswerResult`; `document_ids` built from `included_passages`.
- **KEEP:** everything above.

## Code Map

- `backend/app/chat/schemas.py` -- new: `AskRequest` (strip + length bounds), `AskResponse`/`AnswerSegmentResponse`/`CitationResponse`, `empty_reason` literal
- `backend/app/chat/routes.py` -- edit: `POST /chat/ask` on the Story 1.1 empty router, `Depends(get_current_user)`
- `backend/app/chat/service.py` -- new: `ask_question` — embed → search → degenerate-zero-passage branch → generate → resolve citations → assemble
- `backend/app/chat/repository.py` -- new: `get_filenames_for_documents` via `user_scoped_select` (AD-2)
- `backend/app/shared/data_access/shapes.py` -- edit: `WeaviateSearchResult` (no `user_id`, no `embedding`, carries `distance` for 3.2)
- `backend/app/shared/data_access/weaviate_client.py` -- edit: `search_passages` — the reader function this module's docstring anticipated; `TOP_K_PASSAGES`
- `backend/app/shared/llm_client/__init__.py` -- edit: `generate_answer`, `AnswerSegment`/`AnswerResult`, `ChatCompletionError`, prompt builder, budget selection, parse/validate — separate from extraction's budget and exception type
- `backend/app/main.py` -- edit: `chat_router` registration; `_warm_embedding_model` on a daemon thread in `lifespan`
- `backend/.env.example` -- edit: `OPENROUTER_CHAT_MODEL`, independent of extraction's `OPENROUTER_MODEL`
- `frontend/src/api/chatClient.js` -- new: `askQuestion`, timeout/network relabelling, `isServiceError` for 503
- `frontend/src/pages/ChatPage.jsx` -- edit: two-column grid, thread, live region, composer
- `frontend/src/components/chat/ChatMessage.jsx` -- new: user/assistant/notice/thinking bubbles, sr-only sender cue
- `frontend/src/components/chat/CitationChip.jsx` -- new: `<cite>`, exact UX-DR3 format, non-interactive
- `frontend/src/components/chat/DocumentsScopePanel.jsx` -- new: read-only list + status pills
- `frontend/src/components/chat/RobotMascot.jsx` -- new: CSS shapes, `aria-hidden`
- `frontend/src/index.css` -- edit: `--citation-text` (UX-DR21 closure), robot shadow tokens with dark overrides
- `backend/tests/test_chat_ask_route.py` -- new: auth, 422 validation, both `empty_reason` outcomes, the exact 503 point, citation resolution/dedup/chunk indexes, tenancy
- `backend/tests/test_chat_generation.py` -- new: retry matrix, parse/validate enforcement, budget behaviour
- `backend/tests/test_weaviate_client.py` -- edit: `search_passages` — filter target/value, mapping, default limit
- `backend/tests/test_startup_warmup.py` -- new: warmup runs, swallows failure, does not block startup, uses a daemon thread
- `frontend/src/**/*.test.{js,jsx}` -- new/edit: `chatClient`, `ChatPage`, `CitationChip`, `DocumentsScopePanel`, `RobotMascot`

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/chat/schemas.py` -- request/response shapes, `empty_reason`'s three-way distinction
- [x] `backend/app/chat/routes.py` -- `POST /chat/ask`, `user_id` never from the body
- [x] `backend/app/chat/service.py` -- the orchestration, and the single point where a 503 is raised
- [x] `backend/app/chat/repository.py` -- tenancy-scoped filename resolution
- [x] `backend/app/shared/data_access/weaviate_client.py` + `shapes.py` -- `search_passages`, `WeaviateSearchResult`
- [x] `backend/app/shared/llm_client/__init__.py` -- `generate_answer` and its own retry/parse/validate path -- AD-6
- [x] `backend/app/main.py` -- router registration; non-blocking embedding warmup (review addition)
- [x] `frontend/src/api/chatClient.js` -- 503 flagged distinctly from every other failure
- [x] `frontend/src/pages/ChatPage.jsx` + `components/chat/*` -- layout, thread, chip, panel, mascot
- [x] `frontend/src/index.css` -- UX-DR21 closure, robot shadow tokens
- [x] backend tests -- route, generation, DAL, startup warmup
- [x] frontend tests -- client, page, chip, panel, mascot

**Acceptance Criteria:**
- Given a submitted question, when retrieval runs, then it goes through `shared/data_access/` and is filtered by the `user_id` resolved from the JWT — proven by a test that fails if the wrong id is passed.
- Given retrieved passages, when the answer is generated, then the call goes through `shared/llm_client/` and `chat/` never touches OpenRouter directly.
- Given a generated answer, when it is returned, then every segment carries at least one citation naming a document and a passage-level location; an uncited segment never reaches the frontend.
- Given a citation, when it renders, then it is a `<cite>` reading exactly `Ch. {chapter}, {document_filename}`, non-interactive, using the citation token pair.
- Given a new assistant message, when it arrives, then it is announced through a polite live region and its sender is programmatically identifiable, not conveyed by alignment alone.
- Given the LLM wrapper fails, when the failure surfaces, then it is a 503 — never an answer, never a refusal.
- Given an empty library, when a question is asked, then a 200 with `empty_reason="no_documents"` returns, visually distinct from both an answer and a future refusal.
- Given 200% browser zoom on a laptop viewport, when the three-column result reflows, then there is no horizontal scrolling or clipping.

## Design Notes

`TOP_K_PASSAGES = 8` — large enough that a question spanning documents can pull from more than one, small enough to keep the prompt short. A tunable default, not an architectural commitment; 3.2 may revisit it alongside its threshold.

`_MAX_PROMPT_CHARS = 12000` budgets only the assembled passage block — not the instruction scaffolding, and not the question (bounded separately at 2000 chars). Both sit on top as unaccounted reserve. Passages are dropped whole from the tail, never truncated mid-passage, since half a sentence is worse context than one fewer whole passage. The one exception is the first passage, always included even when it alone exceeds the budget: the alternative is a zero-passage prompt that still costs a real call and can only return `passage_count=0`. The honest cost of that exception — an over-budget prompt may 4xx on context length, which correctly surfaces as a non-retryable 503 reading "try again" for something retry can never fix — is recorded in the code. It remains the better trade than a guaranteed-useless 200, and the real fix is capping chunk size in characters upstream in `documents/parsing.py`.

Chat generation's timeout/retry budget (`45s`, 2 attempts) is deliberately different from extraction's (`120s`, 3 attempts), not a copy-paste: extraction runs in a background task with nobody waiting, chat does not.

**NFR-1 (p95 < 8s) is knowingly not met.** The free-tier default model took ~32s against a one-sentence prompt, so worst case across both attempts is ~120s (45s + up to 30s of a 429's own `Retry-After` + 45s). A timeout tuned to 8s would fail the happy path almost every time, defeating the story. `OPENROUTER_CHAT_MODEL` is the intended fix once a faster model is chosen; the deviation is recorded in `deferred-work.md` rather than papered over, and no test asserts NFR-1, so nothing in CI will flag it as a regression.

The embedding model is warmed on a daemon thread at startup rather than inline, because on a cold free-tier instance with an ephemeral filesystem the model cache does not survive a boot and the download would block the app before it accepts traffic.

Retrieval quality note, not a defect and not this story's call: the embedding model is `paraphrase-multilingual-MiniLM-L12-v2`, a symmetric-similarity model chosen in Story 2.3 for Bulgarian support. Asymmetric question-to-passage retrieval is typically better served by a model trained for it. Relevant to answer quality here; owned by Epic 6's measurement work, not by a change in this story.

## Verification

**Commands:**
- `pytest` (from `backend/`) -- expected: all pass, including the four new/edited test files
- `npm test -- --run` / `npm run lint` / `npm run build` (from `frontend/`) -- expected: clean

**Manual checks (if no CLI):**
- With real `OPENROUTER_API_KEY` and Weaviate credentials, and at least one `Ready` document, ask a question and confirm: the answer renders with `Ch. …` chips, the chips are `<cite>` elements, a screen reader announces the arriving answer with a sender cue, and the scope panel lists documents with status pills.
- Ask with an empty library and confirm the `no_documents` notice is plain text, not a bubble that could be mistaken for a refusal.
- Zoom to 200% and confirm the three-column layout reflows to one column with no horizontal scroll.
