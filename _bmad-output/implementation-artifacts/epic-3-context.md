# Epic 3 Context: Grounded Chat Q&A

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A user can ask a question in plain language against a chosen scope of their documents and receive an answer whose every claim is traceable to a specific passage — or an explicit, honest refusal when the evidence isn't there. This is the product's core promise; every other epic exists to make it possible. The epic now also covers conversational memory: a user's follow-up questions resolve against recent prior turns instead of each question being answered in isolation, and prior conversation persists across reloads. FR-17 (memory) was added after the epic otherwise shipped and extends the same `chat` module end-to-end rather than becoming its own epic.

## Stories

- Story 3.1: Ask a question and receive a grounded, cited answer
- Story 3.2: Explicit refusal when the documents don't support an answer
- Story 3.3: Scope a question to a chosen set of documents
- Story 3.4: Remember the conversation

## Requirements & Constraints

- Every claim-bearing sentence in a generated answer must be traceable to at least one citation, and each citation names a specific document *and* passage — never merely a document-level source.
- When retrieved passages don't clear a relevance threshold, the system returns an explicit refusal instead of an answer, with no generation call made at all (saves latency and free-tier budget). The refusal is measured as its own metric (feeds Epic 6's SM-2/SM-C1), not treated as failure to minimize at all costs.
- The relevance threshold is resolved (OD-2): `RELEVANCE_THRESHOLD = 0.75` in `shared/llm_client/__init__.py`, tuned against real Weaviate retrieval distances and biased toward not refusing a genuinely answerable question. Flagged for re-measurement once Epic 6's evaluation set exists.
- A question can run against all of a user's documents (default) or a checked subset; the scope panel starts with nothing pre-checked, and an all-unchecked state must still read as "asking across everything," not "nothing selected" (OD-6). Out-of-scope passages never surface as citations. The scope filter box only filters the panel's document list, never library-wide search (OD-5).
- p95 end-to-end latency (retrieval + generation) should stay under 8 seconds (NFR-1). This is a **known, accepted gap in the current shipped state**, not yet met: the free-tier default chat model measured ~32s per real call (worst case ~120s across a retry), documented in `shared/llm_client`'s timeout/retry constants and `deferred-work.md`. No test asserts NFR-1. `OPENROUTER_CHAT_MODEL` exists as the escape hatch to a faster model but is unset by default.
- Conversational memory (FR-17, Story 3.4): a bounded, recent window of prior question/answer turns feeds both the retrieval query text and the generation prompt, so a follow-up like "what about its budget?" resolves correctly. The window must never grow unbounded — old turns fall out as new ones are added. A fresh conversation with no prior turns must behave identically to the stateless Stories 3.1–3.3 flow (empty window changes nothing).
- The window's exact size is an open decision (OD-8: turn count + character budget) — a placeholder pending measurement against real free-tier context limits and NFR-1 latency during implementation of Story 3.4. Whatever value is chosen must be recorded as configuration, not hardcoded, consistent with how OD-2's threshold was resolved.
- Conversation history is persisted per-user and fetched through a paginated endpoint (cursor/offset + limit) — never as one unbounded blob. On page load only the most recent 3 messages render; scrolling upward incrementally reveals older messages via the same paginated endpoint.
- History reflects the scope active at the time each turn was asked, but a *new* follow-up always retrieves against the *current* scope selection — history supplies conversational context only, never widens or narrows retrieval's document boundary.

## Technical Decisions

- **AD-6 governs the whole epic:** `shared/llm_client/` is the only path to OpenRouter; the `chat` module never calls it directly. The relevance-threshold check happens in `chat/service.py` *before* the wrapper is ever invoked — this is the refusal short-circuit, and it is the single source of a "refusal" in the system. The wrapper's own failures (timeout, retry exhaustion, OpenRouter error) are a distinct failure mode, surfaced as an ordinary service error per AD-3 (e.g. 503) — never rendered as an answer and never conflated with the refusal.
- **AD-2 governs retrieval and persistence tenancy:** all Weaviate/Neo4j access goes through `shared/data_access/`, with `user_id` resolved server-side from the JWT, never client-supplied. The Weaviate passage shape chat reads is fixed by Epic 2: flat `chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`. Note AD-2's literal mandate (and the DAL module's name) targets Weaviate/Neo4j specifically — it does not by itself cover Postgres. Postgres access in this codebase already has its own tenancy pattern (`shared/data_access/tenancy.py`'s `user_scoped_select` helper, used by `auth`/`documents`), which is the natural fit for AD-10's paginated conversation-history storage rather than inventing a new pattern.
- **AD-10 (new, added alongside FR-17):** chat history is paginated, never fetched as one blob. The history endpoint takes cursor/offset + limit; the frontend's progressive-reveal fetches older pages on demand as the user scrolls upward (UX-DR29).
- **Current `chat/service.py` architecture is stateless** — `ask_question(db, current_user, question, document_ids)` takes no conversation/session identifier and produces one self-contained answer per call: embed → search → (degenerate zero-passage case) → refusal-threshold check → generate → resolve citations → assemble. Story 3.4 changes this: the function (or its caller) needs a way to load/append the bounded recent-turn window and thread it into both the retrieval query text and the generation prompt, plus a place to persist each new turn. Any new signature or persistence call should preserve the existing branch separation the module already relies on — the zero-passages path, the refusal path, and the LLM-wrapper-failure path must remain mutually exclusive by construction, not by an added check.
- Route layer: `chat/routes.py` handles ask-question and scope selection; a new paginated history route belongs here for Story 3.4. All routes declare a Pydantic `response_model`; all errors are `HTTPException` → `{"detail": ...}` (AD-3).
- Frontend shared state (chat document-scope selection) lives in React Context (AD-5), not Redux.

## UX & Interaction Patterns

- Chat page is a two-column grid: flexible chat window + fixed 260px documents-in-scope panel, 20px gutter. Composer is a single row with input and "Ask" button at equal height.
- Citation renders as a chip reading `Ch. {chapter}, {document_filename}`, using the citation token pair, non-interactive (no jump-to-source in v1), and must be a semantic inline element (e.g. `<cite>` or labelled span) — not a bare styled `<span>` — so a screen reader can distinguish it from ordinary answer text.
- New assistant messages are announced via `aria-live="polite"` (or `role="log"`) so a screen-reader user learns of the answer without re-navigating. For Story 3.4: messages revealed by scrolling up into older history must **not** re-trigger this live region — it's reserved for genuinely new incoming answers, not paged-in history.
- Refusal bubble (UX-DR15, resolved Story 3.2): centered, symmetric-cornered, dedicated `--refusal-bg`/`--refusal-text` amber token pair distinct from both the assistant bubble fill and `--danger`, with a screen-reader-only "Refusal: " prefix so it announces distinctly from a normal answer — not merely an answer bubble with zero citations.
- Scope panel: per-document checkboxes, none pre-checked by default; non-Ready documents have a disabled checkbox with status noted inline and exposed via `aria-label` (not visual-only text). "Select all" brings every Ready document into scope at once. Checkbox toggles apply immediately with no separate apply step and govern only the *next* question asked.
- Progressive chat-history reveal (UX-DR29, Story 3.4): on load, only the most recent 3 messages render; scrolling upward incrementally reveals earlier messages via AD-10's paginated endpoint rather than fetching/rendering the full history at once.
- Voice throughout: plain, declarative, specific about why — no hedging, apology filler, or emoji. Refusal copy example shape: "No supporting evidence found in your documents for this question."

## Cross-Story Dependencies

- Story 3.2's refusal short-circuit is the single source of "I don't know" in the system and must remain that way after Story 3.4 adds history — a history-augmented query still hits the same threshold check before any generation call, history or not.
- Story 3.3's scope selection and Story 3.4's history interact directly: retrieval must always honor the *current* scope, even when earlier turns in the same conversation were asked under a different scope.
- Story 3.4 depends on Stories 3.1–3.3's stateless flow remaining behaviorally unchanged when no history exists — this is an explicit acceptance criterion, not just a nice-to-have.
- This epic depends on Epic 2's Weaviate passage shape (`chunk_id, document_id, user_id, chapter, chunk_index, text, embedding`) and Epic 1's JWT-derived `user_id` resolution and shared DAL scaffolding.
- Epic 6's evaluation harness (FR-13) invokes this epic's service layer directly and measures SM-1/SM-2/SM-C1 against it; OD-2's threshold value came from that harness's baseline run and is flagged for re-tuning as the evaluation set grows.
