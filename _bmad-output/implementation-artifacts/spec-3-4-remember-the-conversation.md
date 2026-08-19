---
title: 'Remember the conversation'
type: 'feature'
created: '2026-08-18'
status: 'done'
review_loop_iteration: 0
baseline_commit: '18195781e39e5f6abcd0e1b1d1528e2dbf721285'
context: ['{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Chat is fully stateless today — `ask_question` takes no history and persists nothing, so a follow-up like "what about its budget?" cannot resolve, and the thread vanishes on reload.

**Approach:** Persist every message per-user in a new Postgres table; feed a bounded recent window of prior turns into both retrieval and generation for follow-ups; serve history through a new paginated endpoint the Chat page uses to render progressively. One continuous conversation per user account — no multi-conversation/switcher concept exists or is being introduced.

## Boundaries & Constraints

**Always:**
- Persist one row per message (`ChatMessage`: `id`, `user_id` FK indexed, `role` `'user'|'assistant'`, `question` text (user rows), `segments` JSON + `empty_reason` (assistant rows), `created_at` server-default `now()`) — mirrors `Document`'s model shape, queried via `user_scoped_select`.
- History window for retrieval/generation is bounded: last 3 prior turns, capped at 2000 total characters (oldest turn dropped first if over budget) — a named constant in `shared/llm_client`, next to `RELEVANCE_THRESHOLD`, not hardcoded inline. Never grows unbounded regardless of conversation length.
- Retrieval query text = bounded window's prior **questions only** (not answers) + the current question — keeps the embedding focused on topical/entity words rather than diluting it with prior answer prose.
- Generation prompt = full bounded window (question **and** answer text, citations stripped) + the current question and passages — the LLM needs prior answer content to resolve references like "its".
- A fresh conversation with zero prior turns behaves identically to today's stateless flow.
- Retrieval always uses the **current** scope selection; history supplies conversational context only, never widens/narrows the document boundary, even if scope changed since an earlier turn.
- Refusal short-circuit (Story 3.2, AD-6) still runs before any generation call, history or not; `chat` still never calls OpenRouter directly.
- New `GET /chat/history` route: `cursor` (optional, a prior response's `next_cursor`) + `limit` params, returns messages newest-first, `has_more`/`next_cursor` in the response — same `Depends(get_current_user)`/`Depends(get_db_session)` shape as `POST /chat/ask`. `user_id` resolved server-side only.
- Frontend requests `limit=3` on initial load (UX-DR29); scrolling to the top of the thread requests further pages at `limit=10`; newly revealed messages do not re-trigger the existing `aria-live="polite"` region — that stays reserved for genuinely new incoming answers.
- Every new Weaviate/Postgres access goes through existing shared patterns (`user_scoped_select`, `search_passages`) — no hand-written raw queries.

**Ask First:**
- If the 2000-char/3-turn history budget visibly degrades answer quality or latency during manual verification, stop and ask before changing it rather than silently retuning.

**Never:**
- No multi-conversation model, conversation naming, or "new conversation" action — out of scope, not implied by anything in FR-17.
- No client-supplied `user_id` anywhere in the new route or persistence path.
- Don't mutate `generate_answer`'s existing `(question, passages)` call sites without threading history explicitly — no silent default/global history injection.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Follow-up within window | 2 prior turns, ambiguous follow-up ("what about its budget?") | History-augmented retrieval/generation resolves the reference correctly | N/A |
| History exceeds budget | 5th prior turn pushes total past 2000 chars | Oldest turn(s) dropped until under budget; newest 3 turns still bounded | N/A |
| Empty history | First-ever question for the account | Identical output to pre-3.4 stateless behavior | N/A |
| Scope changed mid-conversation | Turn 1 scoped to doc A, turn 2 (follow-up) scoped to doc B only | Turn 2 retrieves only from doc B; history still supplies conversational context | N/A |
| History fetch, no messages yet | New account, `GET /chat/history` | `messages: []`, `has_more: false` | N/A |
| History fetch, cursor exhausted | Scrolled to the very first message | `has_more: false`, `next_cursor: null` | N/A |
| Generation failure mid-history | `ChatCompletionError` on a history-augmented call | Same 503 path as today (AD-6) — never persisted as a message, never rendered as an answer | Existing `except ChatCompletionError` branch, unchanged shape |

</frozen-after-approval>

## Code Map

- `backend/app/shared/models.py` -- add `ChatMessage` model, same declarative pattern as `Document` (L42-112): Uuid PK w/ py-default, `user_id` FK indexed, `role`, `question`, `segments` (plain `JSON`, not JSONB — SQLite test compat), `empty_reason`, `created_at` server-default
- `backend/alembic/versions/` -- new revision (`alembic revision --autogenerate`, standard Alembic convention -- no documented command exists in-repo, inferred from `env.py`'s `target_metadata = Base.metadata`)
- `backend/app/chat/repository.py` -- add `save_message`, `list_messages_for_user` (paginated, `user_scoped_select(ChatMessage, user_id)` + cursor filter on `created_at`/`id`, `order_by(desc(created_at))`, mirrors `documents/repository.py:40-46`'s shape)
- `backend/app/chat/service.py` -- `ask_question` (L25-182): thread a fetched bounded history window into the retrieval query (L64 `embed_texts` call) and into `generate_answer` (L98); persist the user question and the resulting assistant message after assembly, inside the same function; preserve the existing zero-passages/refusal/generate branch separation exactly (L70-105) and the `answer.included_passages`-driven citation logic (L107-125)
- `backend/app/chat/schemas.py` -- add `ChatHistoryMessageResponse`, `ChatHistoryResponse` (`messages`, `next_cursor`, `has_more`)
- `backend/app/chat/routes.py` -- add `GET /history` (L18 `router` reuse; same `Depends` pair as the existing `/ask` route)
- `backend/app/shared/llm_client/__init__.py` -- `generate_answer` (L617) gains a `history` param; `_build_chat_system_prompt` (L609-614) / `_CHAT_SYSTEM_PROMPT_TEMPLATE` (L465-475) gains a history section, budgeted separately from `_MAX_PROMPT_CHARS` (L165, currently passage-only); new `HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS` constants beside `RELEVANCE_THRESHOLD` (L143)
- `frontend/src/api/chatClient.js` -- add `getChatHistory(authFetch, { cursor, limit })`, same `(authFetch, ...) => Promise` shape as `askQuestion` (L18)
- `frontend/src/pages/ChatPage.jsx` -- on mount, fetch `limit=3` page, seed `messages` (L34); add scroll-up handler on the existing message-list container (L103-110) that fetches `limit=10` pages and prepends; existing `aria-live` region (L103-110) must not fire for prepended history
- `backend/tests/test_chat_ask_route.py`, new `backend/tests/test_chat_history_route.py` -- coverage for the I/O matrix rows
- `frontend/src/pages/ChatPage.test.jsx`, new scroll/history test file -- initial-3, scroll-loads-more, no-aria-live-on-history-reveal

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/models.py` -- `ChatMessage` model -- persistence for FR-17/AD-10
- [x] `backend/alembic/versions/*` -- migration for the new table
- [x] `backend/app/chat/repository.py` -- `save_message`, `list_messages_for_user` (paginated)
- [x] `backend/app/shared/llm_client/__init__.py` -- `HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS` constants, history-aware prompt building, `generate_answer` gains `history` param
- [x] `backend/app/chat/service.py` -- history fetch + threading into retrieval/generation, persist question + answer
- [x] `backend/app/chat/schemas.py` -- history response schemas
- [x] `backend/app/chat/routes.py` -- `GET /chat/history`
- [x] backend tests covering the I/O matrix (all 7 rows) plus persistence round-trip
- [x] `frontend/src/api/chatClient.js` -- `getChatHistory`
- [x] `frontend/src/pages/ChatPage.jsx` -- initial history load, scroll-up pagination, `aria-live` exclusion for revealed history
- [x] frontend tests: initial-3-render, scroll-triggered load-more, aria-live not retriggered
- [x] manual verification against real dev servers (backend/Postgres/Weaviate/Neo4j/OpenRouter)

**Acceptance Criteria:** (mirrors Story 3.4's Gherkin in `epics.md`)
- Given a conversation with prior turns, when a follow-up is asked, then the bounded history window resolves references correctly (FR-17)
- Given the history window, when constructed, then it never exceeds 3 turns / 2000 characters
- Given zero prior turns, when a question is asked, then behavior matches pre-3.4 output exactly
- Given a scope change between turns, when a follow-up runs, then retrieval honors only the current scope
- Given a return visit, when the Chat page loads, then only the most recent 3 messages render initially, older ones revealed by scrolling up (UX-DR29)
- Given history is revealed by scrolling, when it renders, then the `aria-live` region does not fire

## Spec Change Log

- Cursor tuple widened from `(created_at, id)` to `(created_at, turn_role_rank, id)`. Discovered during implementation: a turn's `user` and `assistant` rows are both written inside one transaction (`chat/service.py::_finish` calls `save_message` twice, then commits once), and Postgres's `now()` (this table's `created_at` server_default) returns the *transaction's* start time, not the per-statement time — so both rows of every single turn share an identical `created_at`, always, not as a rare edge case. An `id`-only tiebreak (a random UUID) would then order a tied pair unpredictably, silently corrupting `_pair_messages_into_turns`'s strict user-then-assistant alternation assumption and the history endpoint's newest-first ordering. `turn_role_rank` (0 for `user`, 1 for `assistant`) is the actual correct tiebreak; `id` remains as a final tiebreak for the (shouldn't-happen) case of two rows sharing both timestamp and role. Verified against the real dev Postgres in manual testing: two real turns' rows did share one `created_at` each, and ordering/pagination were still correct.
- `backend/app/auth/service.py::delete_account` (Story 5.3) and `backend/app/chat/repository.py` (new `delete_all_messages_for_user`) — not in the original Code Map, but required: `chat_messages.user_id` is a `NOT NULL` FK into `users.id` with no `ON DELETE CASCADE`, so account deletion for a user with any persisted chat turns failed with a Postgres `ForeignKeyViolation`/500 (SQLite's test DB doesn't enforce FKs by default, so this was invisible to the pytest suite — caught only via manual verification against real Postgres, then fixed and given its own regression test in `test_auth_delete_account.py`).
- Post-implementation adversarial/edge-case/verification-gap review (blind-hunter, edge-case-hunter, verification-gap, diffed against `baseline_commit`) found 16 findings triaged as mechanically fixable, all applied: a shared `repository.turn_role_rank`/`VALID_TURN_ROLE_RANKS` replacing two independent hardcodings of the same tiebreak rule; a new composite index `ix_chat_messages_user_id_created_at_role_id` (migration `a6c5923523fa`, `ChatMessage.user_id`'s standalone index dropped as redundant) actually covering the `(user_id, created_at, role, id)` query shape instead of `user_id` alone; `GET /chat/history`'s cursor check switched from truthiness to `is not None` (an empty `?cursor=` now 422s instead of silently restarting from the newest page) plus a range check on the decoded role-rank component; persistence assertions added to the 3 `ask_question` paths that only had response-shape coverage; `limit` boundary tests (0, 51, the 50 edge); a multi-turn scope-change test; a direct unit test for `_pair_messages_into_turns`'s defensive non-alternating-shape branch; a history round-trip test for real citation data; and, on the frontend, both history fetches now surface failures through the same `error` banner `handleSubmit` already used (previously silent), a visible "Loading earlier messages…" indicator + `aria-busy` during a scroll-triggered fetch, a `hasSubmittedLiveQuestionRef` guard against the initial-load fetch overwriting an already-submitted live turn, a synchronous `isLoadingHistoryRef` guard against overlapping scroll-triggered fetches, and a `historyPrependToken`-keyed dedicated scroll-restore effect (replacing a shared boolean ref) so prepend-restore math can never misapply to a live-append update landing in the same render pass.

## Design Notes

History text formats: retrieval query = `"\n".join(prior_questions) + "\n" + current_question` (questions only, keeps embedding on-topic). Generation prompt section = `"Q: {q}\nA: {a}\n"` per turn, newest turn last, appended before the passage block in `_CHAT_SYSTEM_PROMPT_TEMPLATE`. Cursor pagination anchors on a `(created_at, turn_role_rank, id)` tuple (widened from the originally-planned `(created_at, id)` — see Spec Change Log), not raw offset — new messages only ever append at the newest end, so a cursor into older history never drifts even if new turns arrive concurrently. No pagination convention exists elsewhere in this codebase to match; this establishes the first one.

## Verification

**Commands:**
- `cd backend && pytest` -- expected: all pass, including new history/persistence tests
- `cd backend && alembic upgrade head` -- expected: migration applies cleanly against local Postgres
- `cd frontend && npm test -- --run && npm run lint && npm run build` -- expected: all pass

**Manual checks:**
- Ask a question, then a follow-up referencing "it"/"that" -- confirm the answer resolves correctly against real OpenRouter/Weaviate
- Reload the Chat page -- confirm only 3 most-recent messages render, scrolling up reveals more, no full-history flash
- Change scope between two turns of the same conversation -- confirm the follow-up respects the new scope, not the old one

## Suggested Review Order

**History threading -- why retrieval and generation get different content**

- Start here: fetches the bounded window, builds retrieval's questions-only text, threads both into search and generation, persists via `_finish`.
  [`service.py:46`](../../backend/app/chat/service.py#L46)

- Trims to 3 turns / 2000 chars, dropping oldest first -- the one place both budgets are actually enforced.
  [`llm_client/__init__.py:535`](../../backend/app/shared/llm_client/__init__.py#L535)

- Empty/`None` history renders as `""`, the structural guarantee a fresh conversation's prompt stays byte-identical to pre-3.4.
  [`llm_client/__init__.py:571`](../../backend/app/shared/llm_client/__init__.py#L571)

- `HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS` -- the placeholder values themselves, and why they sit here beside `RELEVANCE_THRESHOLD`.
  [`llm_client/__init__.py:167`](../../backend/app/shared/llm_client/__init__.py#L167)

**Persistence -- the two-row-per-turn model and its one un-persisted path**

- `_finish`: every return point routes through here except the 503 path, which the story's own I/O matrix requires never be persisted.
  [`service.py:283`](../../backend/app/chat/service.py#L283)

- `ChatMessage`: one table, two disjoint row shapes (`user`/`assistant`), no `conversation_id` -- one continuous thread per account by design.
  [`models.py:115`](../../backend/app/shared/models.py#L115)

- Pairs alternating rows into turns; the defensive non-alternating branch (now unit-tested) guards a shape the writer never produces.
  [`service.py:248`](../../backend/app/chat/service.py#L248)

- `turn_role_rank`/`VALID_TURN_ROLE_RANKS`: the single source of truth for the tiebreak the review round centralized (previously duplicated in `service.py`).
  [`repository.py:49`](../../backend/app/chat/repository.py#L49)

**Pagination -- the cursor contract (this codebase's first pagination convention)**

- `GET /chat/history`: cursor + limit params, same auth-dependency shape as `/ask`.
  [`routes.py:29`](../../backend/app/chat/routes.py#L29)

- `get_history`: resolves the default page size, decodes the cursor, assembles `next_cursor`/`has_more`.
  [`service.py:368`](../../backend/app/chat/service.py#L368)

- `_encode_cursor`/`_decode_cursor`: opaque `(created_at, turn_role_rank, id)` tuple, `is not None` cursor check and the role-rank range check both added in review.
  [`service.py:320`](../../backend/app/chat/service.py#L320)

- `list_messages_for_user`: keyset pagination on the same tuple, fetches one extra row to answer `has_more` without a COUNT query.
  [`repository.py:147`](../../backend/app/chat/repository.py#L147)

- `ChatHistoryResponse`/`ChatHistoryMessageResponse`: the two-shape duality surfaced verbatim rather than merged into one rendering concept.
  [`schemas.py:127`](../../backend/app/chat/schemas.py#L127)

**Frontend -- progressive reveal and the three races closed in review**

- Initial load, scroll-up pagination, and the `hasSubmittedLiveQuestionRef` guard against a late history fetch clobbering a just-submitted live turn.
  [`ChatPage.jsx:103`](../../frontend/src/pages/ChatPage.jsx#L103)

- `isLoadingHistoryRef`: the synchronous reentrancy guard closing the overlapping-scroll-event duplicate-prepend race.
  [`ChatPage.jsx:96`](../../frontend/src/pages/ChatPage.jsx#L96)

- `historyPrependToken`-keyed scroll-restore effect, replacing a shared boolean ref so it can't misfire against a live-append in the same render.
  [`ChatPage.jsx:182`](../../frontend/src/pages/ChatPage.jsx#L182)

- `loadOlderHistory`: the fetch itself, now surfacing failures through the same `error` state `handleSubmit` uses instead of a silent no-op.
  [`ChatPage.jsx:192`](../../frontend/src/pages/ChatPage.jsx#L192)

**Peripherals**

- The `chat_messages` table migration.
  [`4eb9644cd73d_create_chat_messages_table.py:1`](../../backend/alembic/versions/4eb9644cd73d_create_chat_messages_table.py#L1)

- The composite-index migration added in review, replacing the redundant single-column index.
  [`a6c5923523fa_replace_chat_messages_user_id_index_.py:1`](../../backend/alembic/versions/a6c5923523fa_replace_chat_messages_user_id_index_.py#L1)

- The account-deletion FK-cascade regression test -- a real bug the test suite's SQLite backend couldn't have caught on its own.
  [`test_auth_delete_account.py:347`](../../backend/tests/test_auth_delete_account.py#L347)

