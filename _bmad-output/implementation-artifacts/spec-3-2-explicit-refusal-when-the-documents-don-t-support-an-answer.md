---
title: 'Story 3.2: Explicit refusal when the documents don''t support an answer'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'b1afd55'
provenance: 'authored-before-implementation'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 3.1 shipped the grounded-answer path end to end, but left two things unresolved on purpose: OD-2 (the numeric relevance-score cutoff FR-10 needs) had no value, and UX-DR15 (the refusal bubble) had no design. `WeaviateSearchResult.distance` is already retrieved and threaded through the whole pipeline, unread. Without this story, a question with no real support in the user's documents still gets a full generation call and whatever the model invents from weak passages — the "confident guess" FR-10 exists to prevent.

**Approach:** A short-circuit in `chat/service.py`, evaluated after `search_passages` returns and before `generate_answer` is called: if no retrieved passage's `.distance` clears a threshold, return a refusal immediately — no generation call, no OpenRouter spend. The threshold (`RELEVANCE_THRESHOLD = 0.75`) lives in `shared/llm_client/` per AD-6 and the story's own AC, even though only `chat/service.py` reads it, and is a measured value (see Design Notes), not a guess. The frontend renders the refusal as its own message role — a centered, symmetric-cornered bubble in a dedicated amber token pair, distinct from both the assistant bubble (color, shape, alignment) and the existing empty-state notice paragraph (a real bubble, not plain text) — with a screen-reader-only "Refusal: " prefix so it announces distinctly, not just looks distinct.

## Boundaries & Constraints

**Always:**
- The short-circuit sits strictly between `search_passages` returning and `generate_answer` being called (AD-6) — `generate_answer` must never be invoked when every passage fails the threshold. Proven by a test that asserts non-invocation, not just the response shape.
- `RELEVANCE_THRESHOLD` lives in `shared/llm_client/__init__.py`, not `chat/service.py` and not `weaviate_client.py`, per the AC's literal wording, even though `llm_client` itself never reads it.
- The refusal (`empty_reason="refusal"`) and the LLM-wrapper failure (`ChatCompletionError` → 503) stay on structurally separate branches that can never share an except-clause — exactly one source of refusal exists in the system (AD-6). A wrapper failure is never rendered as a refusal, and a refusal is never a 503.
- `distance is None` never counts toward clearing the threshold — a passage that can't be verified as relevant doesn't get to authorize an answer. If every passage lacks distance metadata, the system refuses and logs a warning (not silent), so that failure mode leaves a trace rather than looking like an ordinary, correctly-working refusal.
- Refusal is "any passage clears the bar," not "all passages clear it" — one relevant-enough passage among `TOP_K_PASSAGES` is enough to proceed exactly as Story 3.1 already does, unfiltered; this story does not filter the passage list handed to `generate_answer`.
- The refusal bubble is a real bubble (bg/border/corner), never the plain-paragraph `notice` treatment used for `no_documents`/`no_answer` — and never the assistant bubble's fill/shape either. Copy is fixed, plain, declarative, hardcoded in the frontend: "No supporting evidence found in your documents for this question." No apology, hedging, emoji, or substitute wording (UX-DR19).
- The refusal announces distinctly to screen readers via its own `sr-only` prefix ("Refusal: "), not merely different visible styling (UX-DR15/UX-DR24).

**Ask First:** none outstanding — OD-2's number and UX-DR15's design are both resolved by this story, not deferred further.

**Never:**
- No filtering of individual passages by relevance before they reach `generate_answer` — out of scope; the threshold check is a single any-passage gate, not per-passage pruning.
- No change to `no_documents`/`no_answer` behavior or copy — those stay exactly as Story 3.1 built them.
- No reuse of `--danger` for the refusal bubble — a refusal is correct, designed behavior, not an error (AD-6).
- No env-var override for `RELEVANCE_THRESHOLD` — matches the sibling `_CHAT_*` constants' plain-module-constant pattern; no config-class precedent exists in this codebase to extend.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No passage clears the threshold | Every retrieved passage's `distance > RELEVANCE_THRESHOLD` | 200, `segments: []`, `empty_reason="refusal"` — `generate_answer` never called | N/A |
| At least one passage clears it | Mixed distances, one `<= RELEVANCE_THRESHOLD` | Unaffected — full Story 3.1 flow, unfiltered passage list | N/A |
| Boundary | `distance == RELEVANCE_THRESHOLD` exactly | Counts as relevant (`<=`); generation proceeds | N/A |
| All distances `None` | Weaviate metadata missing on every passage (can't happen today) | Refuses (conservative default) | `logger.warning` |
| Empty library | Zero passages retrieved | `empty_reason="no_documents"` (Story 3.1, unchanged) — never conflated with `refusal` | N/A |
| LLM wrapper fails | Timeout/5xx/429 exhausted, generation was reached (threshold was cleared) | 503 (Story 3.1, unchanged) — never rendered as a refusal | Logged |

</frozen-after-approval>

## Code Map

- `backend/app/shared/llm_client/__init__.py` -- edit: `RELEVANCE_THRESHOLD` constant, measured and documented
- `backend/app/chat/service.py` -- edit: refusal short-circuit branch between `search_passages` and `generate_answer`
- `backend/app/chat/schemas.py` -- edit: `empty_reason` gains `"refusal"`
- `frontend/src/pages/ChatPage.jsx` -- edit: `handleSubmit` branches `empty_reason === 'refusal'` into its own message role
- `frontend/src/components/chat/ChatMessage.jsx` -- edit: new `role === 'refusal'` bubble, fixed UX-DR19 copy, `sr-only` prefix
- `frontend/src/index.css` -- edit: `--refusal-bg`/`--refusal-text` token pair (light + dark), `@theme inline` registration
- `backend/tests/test_chat_ask_route.py` -- edit: refusal-path tests (all-above-threshold, mixed, boundary, all-`None`)

## Tasks & Acceptance

**Execution:**
- [x] `backend/app/shared/llm_client/__init__.py` -- `RELEVANCE_THRESHOLD`, measured against real data
- [x] `backend/app/chat/service.py` -- the short-circuit branch, logging on the all-`None` edge case
- [x] `backend/app/chat/schemas.py` -- `empty_reason`'s third value
- [x] `frontend/src/pages/ChatPage.jsx` -- refusal routed to its own message role
- [x] `frontend/src/components/chat/ChatMessage.jsx` -- refusal bubble
- [x] `frontend/src/index.css` -- refusal token pair
- [x] backend tests -- refusal-path coverage including non-invocation proof (5 new tests, `pytest`: 181 passed)
- [x] frontend tests -- refusal bubble rendering + accessibility (1 new test, `npm test`: 110 passed; lint/build clean)

**Acceptance Criteria:** (mirrors the story's own Gherkin in `epics.md`)
- Given a question whose retrieval scores all fall below `RELEVANCE_THRESHOLD`, when processed, then the system returns an explicit refusal rather than an answer.
- Given the refusal path, when it triggers, then the short-circuit happens before `generate_answer` is invoked, and no generation call is made at all.
- Given OD-2 had no value, when this story is implemented, then a numeric cutoff is chosen, recorded, and lives as a configuration value in `shared/llm_client/`, not hardcoded in `chat/service.py`.
- Given the LLM wrapper's own internal failures, when they occur, then they surface as service errors (503), never as a refusal — exactly one source of refusal exists in the system.
- Given no mock existed for the refusal bubble, when this story is implemented, then it reads as categorically different from a grounded answer, not merely an answer bubble with zero citation chips.
- Given a refusal is returned, when a screen-reader user receives it, then it is announced distinctly, not merely styled differently.
- Given the refusal copy, when it renders, then it reads "No supporting evidence found in your documents for this question." with no apology, hedging, emoji, or cute wording.

## Design Notes

**`RELEVANCE_THRESHOLD = 0.75` — measured, not guessed.** Live check against this account's real Weaviate data (the only `Ready` document at measurement time: an English vendor/refund-terms document, 2 chunks) using the real embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) and the real `search_passages`:

| Question | Kind | Best-passage distance |
|---|---|---|
| "What is the refund window for TechCorp Supplies?" | on-topic | 0.162 |
| "Is there a refund policy for Northbridge Logistics?" | on-topic | 0.236 |
| "Who handles shipping for the Q2 rollout hardware?" | on-topic | 0.459 |
| "Какъв е срокът за връщане на стоки от TechCorp Supplies?" (Bulgarian) | on-topic | 0.182 |
| "What is the airspeed velocity of an unladen swallow?" | off-topic | 0.899 |
| "How do I bake a chocolate cake?" | off-topic | 1.061 |
| "What is the capital of France?" | off-topic | 1.094 |

The third row was checked, not assumed: the retrieved chunk's text states outright "Northbridge Logistics handles shipping for all Q2 rollout hardware," so 0.459 is a genuine on-topic match, not a false positive that would have narrowed the real gap. The Bulgarian row exists because the embedding model is multilingual specifically for this project's Bulgarian-document support, and cross-lingual question/passage pairs typically show systematically higher distance than monolingual pairs at the same meaning — worth checking rather than assuming, since it could have silently narrowed or inverted the gap. It did not: 0.182 sits inside the on-topic cluster, not near the boundary.

Clean separation results: worst on-topic distance 0.459, best off-topic distance 0.899 — a 0.44-wide gap. `0.75` sits inside it, biased toward the "don't wrongly refuse" side (0.29 margin above the worst on-topic case vs. 0.15 below the best off-topic case) — a genuinely answerable question being refused is worse than an occasional weak-but-attempted answer, matching FR-10's intent.

Caveat, carried forward rather than hidden: one document, mostly English (six of seven probes), two passages. Real signal, not a rubber-stamped guess, but still a small sample — flagged for re-measurement once Epic 6's evaluation set exists (SM-2/SM-C1), the same way `TOP_K_PASSAGES` and `_MAX_PROMPT_CHARS` were themselves re-tuned against real data after Story 3.1 shipped rather than left at their original guesses.

**Constant placement.** `RELEVANCE_THRESHOLD` lives in `shared/llm_client/__init__.py` even though that module never reads it — only `chat/service.py` does. This was raised explicitly during planning as a single-responsibility concern (the constant sits next to `distance`'s producer or consumer, not a module that ignores it). Resolved in favor of the AC's literal wording: OD-2 "lives as a configuration value in the shared LLM-client wrapper rather than being hardcoded in the chat service." AD-6 already frames `llm_client` as the single owner of every knob that decides whether/how an OpenRouter call happens (model, timeout, retries, prompt budget) — this constant is that same category of decision, made one step earlier than the others, which is the justification recorded here rather than left implicit.

**Refusal bubble tokens.** `--refusal-bg`/`--refusal-text` duplicate `--status-uploaded-{bg,text}`'s exact values (light: solid `#FBEFD6`/`#8A5200`, already documented as clearing 4.5:1; dark: `rgba(227,169,74,.16)`/`#E3A94A`, computed at ~4.99:1 against `--card-bg`, where the chat thread's messages render) rather than reusing the status token directly — this codebase treats color tokens as single-purpose so unrelated components can't drift into each other from an innocent-looking retint.

## Verification

**Commands:**
- `pytest` (from `backend/`) — expected: all pass, including the new refusal-path tests.
- `npm test -- --run` / `npm run lint` / `npm run build` (from `frontend/`) — expected: clean.

**Manual checks — completed against the real backend/frontend dev servers, real Weaviate, real Postgres:**
- Uploaded a real document (vendor/refund-terms content, the same one used for the Design Notes measurement) and asked "What is the airspeed velocity of an unladen swallow?" — the refusal bubble rendered: centered, amber (`bg-refusal-bg`), symmetric corners, distinct from both the user bubble and the prior empty-state notice shape. Response returned fast (no ~30s+ generation latency), and no OpenRouter call appears in the backend log for that request — confirms the short-circuit actually skips generation, not just that the response shape looks right.
- Asked "What is the refund window for TechCorp Supplies?" (on-topic), twice. First attempt: the threshold correctly let it through to `generate_answer` (no refusal), then hit the free-tier model's already-documented NFR-1 latency limitation (`ChatCompletionError` after 2 attempts, Story 3.1's known deviation, unrelated to this story) and rendered as the existing red service-error banner — never as a refusal, confirming the two failure modes stay visually and structurally distinct in a real run, not just in mocked tests. Second attempt succeeded outright: rendered "The refund window for TechCorp Supplies is 30 days from the delivery date." with a real `Ch. Chapter 1: Refund Policy, story32_verify_doc.md` citation chip — the existing cited-answer flow is confirmed unaffected by this story's new branch, not just inferred from it not refusing.
- Accessibility: page-text extraction of the rendered bubble showed the `sr-only` "Refusal:" prefix ahead of the visible copy, confirmed present in the accessible content while not visually rendered (screenshot shows only the sentence, no visible "Refusal:" label) — the distinct-announcement mechanism works as designed.
- Dark mode: switched the app to dark (`localStorage.theme = 'dark'`) and re-triggered a refusal. Computed styles on the live bubble: `background-color: rgba(227, 169, 74, 0.16)`, `color: rgb(227, 169, 74)` — exactly `--refusal-bg`/`--refusal-text`'s dark values, confirming the token pair resolves correctly at runtime through `@theme inline`, not just correct in source. `border-radius: 14px` uniform (symmetric, not the assistant bubble's asymmetric corner) and `font-weight: 500` also confirmed live.

Note on process: `POST /documents` initially 500'd (unrelated pre-existing bug on `main` — `documents.content_hash` was `NOT NULL` with nothing populating it; fixed upstream by Story 2.6, merged into this branch mid-review). Local Neo4j also needed a temporary `neo4j+ssc://` scheme swap in `backend/.env` (self-signed-cert issue, dev-only, reverted after) to let ingestion reach `Ready` instead of `Failed` — neither blocker was specific to this story's code.
