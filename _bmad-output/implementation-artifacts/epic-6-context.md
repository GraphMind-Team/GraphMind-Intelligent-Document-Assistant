# Epic 6 Context: Evaluation Harness

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The team needs objective, numeric proof — not impressions — that GraphMind answers accurately when the evidence supports it and refuses honestly when it doesn't, and that one user's data can never leak into another's results or answers. This epic delivers a single-command evaluation harness measuring answer accuracy and refusal correctness against a curated question set, plus a dedicated cross-tenant isolation proof covering both blocked raw queries and the subtler case of an LLM blending another user's retrieved context into a generated answer. Together these two stories are the project's Definition-of-Done gate.

## Stories

- Story 6.1: Measure answer accuracy and refusal correctness in one command
- Story 6.2: Prove that no account can reach another account's data

## Requirements & Constraints

- The harness runs as a single command and invokes the service layer directly rather than driving the UI or hitting HTTP routes, so it stays fast and independent of frontend state.
- It reports accuracy on answerable questions and refusal rate on unanswerable questions as numbers, never as pass/fail.
- The evaluation set holds 15–20 question/expected-answer pairs spanning three categories: single-source factual, cross-document synthesis, and unanswerable (refusal-expected). It is authored incrementally as ingestion becomes functional, not written in one batch at the end.
- Target metrics: ≥80% accuracy on answerable questions (placeholder — confirmed or replaced with a baseline-grounded figure in Story 6.1, resolving the open numeric-target decision); 100% refusal on genuinely unanswerable questions with no confident fabrication; refusal rate on *answerable* questions reported separately as a counter-metric so refusal-tuning can't silently cause over-refusal.
- Cross-tenant leakage is a launch blocker to be caught here, not triaged later. The isolation proof must exercise every endpoint with two real test accounts and must cover two distinct failure modes: a blocked raw query for another account's data, and the subtler case where a generated answer's text or retrieved context blends another account's content even though the direct query path is correctly enforced. Any leak found is a blocker.
- The isolation proof and the accuracy/refusal harness together are both part of the project's Definition of Done.

## Technical Decisions

- Architecturally the harness is a standalone script that invokes the service layer directly and consumes the existing response contracts (routes' Pydantic `response_model`s) rather than adding new ones.
- Primary entry point for answer/refusal evaluation: `ask_question(db: Session, current_user: User, question: str, document_ids: list[uuid.UUID]) -> AskResponse` in `backend/app/chat/service.py`. `AskResponse` (`backend/app/chat/schemas.py`) has `segments: list[AnswerSegmentResponse]` (each with `text` and `citations`) and `empty_reason: Literal["no_documents", "empty_scope", "no_answer", "refusal"] | None`. A refusal is `empty_reason == "refusal"` with empty `segments` — distinct from the other three empty-result cases, which the harness must not mistake for a refusal.
- The refusal short-circuit happens inside `ask_question` before the shared LLM wrapper is ever called; the relevance cutoff is `RELEVANCE_THRESHOLD` in `app/shared/llm_client/__init__.py` (currently 0.75). Wrapper failures (timeout/retry exhaustion/provider error) surface as exceptions, not as a refusal — the harness should treat those as errors, not as scored refusals.
- Document-related entry points for setting up evaluation/test-account corpora live in `backend/app/documents/service.py`: `upload_document(db, current_user, ...)`, `ingest_document(...)`, `list_documents(db, current_user)`, `get_document(db, current_user, document_id)`, `delete_document(db, current_user, document_id)`.
- DB sessions for a standalone script are obtained via `get_session_factory()` in `app/shared/data_access/session.py` (same pattern as the existing `backend/scripts/rebuild_graph_with_provenance.py`), not through the FastAPI request-scoped dependency.
- Existing convention for standalone operational scripts: `backend/scripts/` (a proper package with `__init__.py`), run manually via `python -m scripts.<name>` from `backend/`, never invoked automatically at startup or on a schedule. This is the established location/pattern to follow for the harness script.
- Test convention: pytest, with `backend/tests/` as a flat directory (no subfolders) of one file per feature slice, named `test_<module>_<feature>.py`, plus a shared `conftest.py` for fixtures. The evaluation harness is a distinct, separately-run tool, not itself a pytest suite, but should follow the same import/session conventions.
- All Weaviate/Neo4j access the harness triggers indirectly (via the service layer) already goes through `shared/data_access/`; the harness itself must not hand-write raw queries against either store.
- `user_id` is always resolved server-side from an authenticated context — the isolation proof must exercise this through real second test-account credentials, not by passing a forged `user_id` into repository/service calls directly.

## Cross-Story Dependencies

- Story 6.1 depends on ingestion (Epic 2) and grounded chat (Epic 3) being functional, since the evaluation set is authored incrementally as real documents and questions become answerable.
- The open SM-1 numeric-accuracy-target decision is resolved only once Story 6.1 produces a baseline run.
- Story 6.2 extends the cross-tenant isolation checks first done in Epic 1 (Story 1.5, initial two-account verification) and re-verified in Epic 2 (Story 2.2, against real documents) to full endpoint coverage plus the answer-level leakage case, which no earlier story tests.
- Both stories function as the project's final Definition-of-Done gate and are expected to run after the epics they depend on (2, 3) are otherwise complete.
