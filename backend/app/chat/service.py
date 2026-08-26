"""Chat module business logic (Story 3.1; intent routing added Story 3.5).

Orchestrates the grounded-answer flow: route -> (embed -> search) or
(fetch document structure) -> (degenerate zero-passage case) -> generate
-> resolve citations -> assemble. Any data access here goes through
`app.shared.data_access` / `app.chat.repository` rather than talking to
Postgres/Weaviate/Neo4j directly (AD-2).
"""

import logging
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.chat import repository, sessions_repository, sessions_service
from app.chat.schemas import (
    AnswerSegmentResponse,
    AskResponse,
    ChatHistoryMessageResponse,
    ChatHistoryResponse,
    CitationResponse,
)
from app.shared.data_access.weaviate_client import (
    TOP_K_PASSAGES,
    fetch_passages_for_documents,
    search_passages,
)
from app.shared.llm_client import (
    HISTORY_MAX_TURNS,
    RELEVANCE_THRESHOLD,
    AnswerResult,
    ChatCompletionError,
    ChatHistoryTurn,
    QuestionPlan,
    bound_chat_history,
    generate_answer,
    resolve_question,
)
from app.shared.i18n.errors import localized_error
from app.shared.models import ChatMessage, ChatSession, Document, User

logger = logging.getLogger(__name__)

# Default page size for GET /chat/history when the client omits `limit`.
# The frontend never actually omits it (it always sends an explicit 3 or
# 10 per UX-DR29), so this only matters for a direct/undocumented API
# call -- kept modest for the same "never one unbounded blob" reasoning
# AD-10 states outright, not a measured value.
_DEFAULT_HISTORY_PAGE_SIZE = 20


def ask_question(
    db: Session,
    current_user: User,
    session_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID],
    *,
    use_history: bool = True,
    use_router: bool = True,
) -> AskResponse:
    """Resolve session -> route -> (embed -> search) or (fetch document
    structure) -> (degenerate zero-passage case) -> generate -> resolve ->
    assemble.

    `session_id` (multi-session chat) is resolved and ownership-checked
    first, via `sessions_service.get_session` -- a foreign or nonexistent
    id 404s before any routing/retrieval/generation work happens, the same
    IDOR-safe, resolve-then-scope convention `folders`/`documents` already
    use. Every history read/write below is scoped to this one session,
    never the account's other sessions.

    `question` arrives already validated non-blank/length-bounded by
    `AskRequest` (chat/schemas.py) -- no manual check here. `document_ids`
    (Story 3.3/FR-11) arrives as whatever the client sent, unvalidated for
    ownership -- `search_passages`/`fetch_passages_for_documents`'s own
    `user_id` filter is what keeps a foreign/stale id from ever widening
    retrieval, so no extra check is needed here.

    The exact 503 point: only the `except ChatCompletionError` branch
    below. Nothing else in this function ever raises 503 -- the
    zero-passages branch returns 200 with `empty_reason="no_documents"`,
    the refusal branch returns 200 with `empty_reason="refusal"`, neither
    is ever an exception. This is the precise separation AC12 requires:
    the zero-passages path, the refusal path, and the LLM-wrapper-failure
    path never share a status code or a branch (AD-3/AD-6) -- exactly one
    of the three can produce a given response, by construction of the
    branch order itself, not by an extra check.

    The refusal short-circuit (Story 3.2, FR-10/OD-2): if no retrieved
    passage's `.distance` clears `RELEVANCE_THRESHOLD`
    (`shared/llm_client`), this returns before `generate_answer` is ever
    called -- no generation call is made at all, per AD-6. History or not,
    that check still runs first (Story 3.4's own Boundaries) -- it never
    looks at the history window at all.

    History threading (Story 3.4/FR-17): before routing, this fetches
    the bounded recent-turn window (`HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS`,
    `shared/llm_client`) from this session's own persisted `ChatMessage`
    rows and folds it into three places -- `resolve_question`'s routing
    input (so a follow-up like "summarize it" resolves against the prior
    turn), the retrieval query text (prior *questions* only, per the
    Boundaries' "keeps the embedding focused on topical/entity words"
    reasoning) and `generate_answer`'s `history` param (full Q+A,
    citations stripped). An empty window (a fresh conversation) makes all
    of those identical to the pre-3.4 call shape -- `history=[]`,
    `search_passages(question, ...)` and `generate_answer(question,
    passages)` unchanged -- rather than merely behaviorally equivalent.
    Retrieval's `document_ids` scope is never touched by history: this
    turn's own `document_ids` argument is the only thing that ever
    widens/narrows what `search_passages` searches, exactly as before
    Story 3.4, even if an earlier turn in the same conversation used a
    different scope.

    Intent routing (Story 3.5): `resolve_question` classifies `question`
    (given `history`, for reference resolution) into one of three
    branches, and never raises -- a routing failure degrades to the
    `factual` branch with the bare original question, exactly pre-3.5
    behaviour, so a `resolve_question` outage is never a new way for
    `/chat/ask` to fail.

      - `"greeting"`: no retrieval, no threshold check, no generation
        call -- the router's own canned `reply` is rendered directly as
        a single `kind="prose"` segment.
      - `"document_overview"`: `_answer_document_overview` reads the
        scoped document(s) whole (`fetch_passages_for_documents`) rather
        than searching for a top-K nearest match; `RELEVANCE_THRESHOLD`
        never applies to this branch (see that function's own docstring
        for why).
      - `"factual"`: `_answer_factual`, the pre-3.5 flow -- unchanged
        except retrieval now embeds the router's `search_query` (a
        standalone rewrite of `question` with references resolved, e.g.
        "what about its budget?" -> "What is Project Aurora's budget?")
        instead of the old join of the last `HISTORY_MAX_TURNS` raw
        questions ahead of the current one. That join diluted the
        retrieval embedding with whatever unrelated questions preceded
        it in conversation, routinely pushing an otherwise-answerable
        follow-up's distance back above `RELEVANCE_THRESHOLD`; a
        self-contained rewrite embeds on the actual topic instead.
        `search_query == question` whenever the router found nothing to
        rewrite or was skipped (`use_router=False`), which keeps this
        identical to pre-3.5 behaviour in that case.

    `use_history=False` opts a caller out of the read half of history
    threading entirely: no window is fetched, and `history=[]` is passed
    to `resolve_question`/`generate_answer` exactly as it always was.
    `use_router=False` opts out of the routing call itself -- `resolve_
    question` is never invoked, and every question is answered by
    `_answer_factual` with `search_query=question` (no rewrite). Both
    exist for one caller -- `scripts/eval_harness.py`, Epic 6's
    measurement instrument (FR-13), which runs a 15-20 question set
    sequentially through this function against a single QA account. With
    history/routing on, question N's retrieval embedding would depend on
    prior questions and on a classification call this instrument was
    never calibrated against -- SM-1/SM-2/SM-C1 would no longer measure
    what OD-3's baseline measured. The harness measures single-question
    retrieval through the exact pre-3.4/pre-3.5 code path; it is not the
    instrument for OD-8's window size or the router's classification
    quality. Both default `True` -- every real request path keeps history
    and routing.

    Persistence (Story 3.4/AD-10): every return point below except a
    `ChatCompletionError` -> 503 path goes through `_finish`, which
    persists this turn's question and the resulting assistant message
    (whatever it is -- a real answer, a refusal, an empty-reason notice,
    or a greeting reply) as two `ChatMessage` rows. The 503 path is the
    one documented exception (this function's own I/O matrix): a
    generation failure is never persisted as a message and never rendered
    as an answer, so a retried question doesn't leave a phantom failed
    turn in the conversation history a reload would show.

    Capacity note: this is a sync `def` route, so FastAPI runs it in
    Starlette's anyio threadpool (a fixed-size worker pool, not the async
    event loop) -- `resolve_question`'s own call (never retried, capped at
    `_ROUTER_TIMEOUT_SECONDS`) plus `generate_answer`'s retry backoff
    (`time.sleep`, `shared/llm_client`) can together block whichever
    worker is running this request well past `generate_answer`'s own
    ~45-120s range, with that worker doing nothing else meanwhile. Fine at
    demo scale; under real concurrent load the threadpool's worker count
    becomes a hard ceiling on simultaneous in-flight chat questions, not
    just a latency number -- worth knowing before this is mistaken for a
    scaling bug found the hard way rather than a known, documented limit.
    """
    session = sessions_service.get_session(db, current_user, session_id)

    if use_history:
        history = bound_chat_history(
            _pair_messages_into_turns(
                repository.get_recent_turn_messages(db, current_user.id, session_id, HISTORY_MAX_TURNS)
            )
        )
    else:
        # Not merely an empty result -- the DB round-trip is skipped too,
        # so an opted-out caller's behaviour can't drift with whatever
        # happens to be persisted on its account.
        history = []

    if use_router:
        plan = resolve_question(question, history)
    else:
        # The router's own round-trip is skipped too, same reasoning as
        # `use_history=False` above -- an opted-out caller gets the bare
        # pre-3.5 factual flow, not a routing call it asked not to make.
        plan = QuestionPlan(intent="factual", search_query=question, reply=None)

    scoped_ids = [str(document_id) for document_id in document_ids]

    if plan.intent == "greeting":
        # No retrieval, no threshold, no generation call -- `resolve_
        # question` already validated `plan.reply` is non-blank whenever
        # `intent == "greeting"` (its own contract), so this is always
        # safe to render directly.
        segments = [AnswerSegmentResponse(text=plan.reply, citations=[], kind="prose")]
        return _finish(db, current_user, session, question, AskResponse(segments=segments))

    if plan.intent == "document_overview":
        return _answer_document_overview(
            db, current_user, session, question, document_ids, scoped_ids, history
        )

    return _answer_factual(
        db,
        current_user,
        session,
        question,
        plan.search_query,
        scoped_ids,
        history,
        routing_failure=plan.routing_failure,
    )


def _answer_factual(
    db: Session,
    current_user: User,
    session: ChatSession,
    question: str,
    search_query: str,
    scoped_ids: list[str],
    history: list[ChatHistoryTurn],
    *,
    routing_failure: str | None = None,
) -> AskResponse:
    """The `"factual"` branch (Story 3.1/3.2/3.3, `search_query` rewrite
    added Story 3.5): embed -> search -> refusal short-circuit -> generate
    -> resolve.

    `search_query` is the retrieval embedding text (Story 3.5's router
    rewrite, or the bare `question` when the router had nothing to
    resolve or was skipped); `question` itself is what `generate_answer`
    is called with (so the answer's phrasing/language matches what the
    user actually typed, not the rewritten form) and what gets persisted.

    `routing_failure` (see `QuestionPlan.routing_failure`) is set only
    when no router actually ran, so this branch was reached by fallback
    rather than by classification. It changes exactly one thing: what a
    *refusal* means. Retrieval and generation are unaffected -- searching
    the raw question is still the right thing to do with a question
    nobody could classify.
    """
    passages = search_passages(
        search_query, str(current_user.id), limit=TOP_K_PASSAGES, document_ids=scoped_ids or None
    )

    if not passages:
        # AC12's degenerate case, split in two by Story 3.3: an
        # effectively-empty library ("no_documents") vs. a non-empty scope
        # whose selected documents just have no matching passages
        # ("empty_scope") -- the library isn't empty in that second case,
        # so it must not read like it is. Neither is the FR-10 refusal
        # below -- a library/scope with nothing to retrieve and a
        # library/scope that has relevant-search candidates but none
        # relevant enough are distinct outcomes, and the frontend renders
        # all three differently.
        reason = "empty_scope" if scoped_ids else "no_documents"
        return _finish(db, current_user, session, question, AskResponse(segments=[], empty_reason=reason))

    if not any(p.distance is not None and p.distance <= RELEVANCE_THRESHOLD for p in passages):
        # A refusal asserts something specific and user-visible: "your
        # documents don't support this question." That claim is only
        # honest if the question was actually routed here. When the router
        # never ran, an overview request ("summarize every chapter")
        # arrives as a nearest-match search that nothing can clear the
        # threshold for -- so the refusal would be an artifact of the
        # outage, blaming the user's library for it. This is the observed
        # production failure, not a hypothetical: the provider's free tier
        # hit its daily cap, every routing call 429'd, and users were told
        # their documents contained no supporting evidence.
        #
        # Raised rather than returned, deliberately: this joins the
        # existing `ChatCompletionError` -> 503 path, which the story's I/O
        # matrix already exempts from persistence. A turn that failed for
        # an upstream reason must not be written into the conversation as
        # though it were an answer, or a reload would replay it as history.
        if routing_failure is not None:
            key = (
                "error.chat_rate_limited"
                if routing_failure == "rate_limited"
                else "error.chat_unavailable"
            )
            logger.warning(
                "Suppressing a refusal for an unrouted question (routing_failure=%s) -- "
                "the retrieval miss is not evidence about the user's documents",
                routing_failure,
            )
            raise localized_error(503, key, current_user.language)

        # FR-10/OD-2: not one retrieved passage is close enough to trust.
        # `distance is None` can't be verified as relevant, so it never
        # counts toward clearing the bar -- the only path through which an
        # all-`None` retrieval refuses rather than silently falling
        # through to `generate_answer` with unverified passages.
        if all(p.distance is None for p in passages):
            # Can't happen today -- `search_passages` always requests
            # distance metadata -- but if it ever did, every question
            # would silently refuse and look like a correctly working
            # system. Logged so that failure mode leaves a trace instead
            # of being indistinguishable from "genuinely no evidence."
            logger.warning("Refusing with no distance metadata on any retrieved passage")
        return _finish(db, current_user, session, question, AskResponse(segments=[], empty_reason="refusal"))

    try:
        answer = generate_answer(question, passages, history=history)
    except ChatCompletionError as exc:
        logger.warning("Chat generation failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Answer generation is temporarily unavailable. Please try again.",
        ) from exc

    return _resolve_generated_answer(db, current_user, session, question, answer)


def _answer_document_overview(
    db: Session,
    current_user: User,
    session: ChatSession,
    question: str,
    document_ids: list[uuid.UUID],
    scoped_ids: list[str],
    history: list[ChatHistoryTurn],
) -> AskResponse:
    """The `"document_overview"` branch (Story 3.5): a request for a
    summary, outline, or "what is this document about" answer, built from
    the scoped document(s)' full content and chapter structure rather
    than `search_passages`'s top-K nearest-match result.

    `RELEVANCE_THRESHOLD` never applies here: `fetch_passages_for_
    documents` is a retrieval, not a search (see that function's own
    docstring), so its results never carry a `distance` for the refusal
    check to apply to. A summary/outline request is either answerable
    from the document's own content or it isn't -- not a question that
    can fail to be "relevant enough" to itself the way a free-text search
    query can be to a nearest-match result.

    Document selection mirrors `_answer_factual`'s own scoping: an
    explicit `document_ids` scope means exactly those documents, an
    empty scope means every `Ready` document this account owns --
    both capped at `repository.MAX_OVERVIEW_DOCUMENTS` (newest first),
    so neither an over-wide explicit scope nor a large library can build
    an unbounded prompt (`repository.get_overview_documents`'s own
    docstring).
    """
    documents = repository.get_overview_documents(db, current_user.id, document_ids)
    if not documents:
        # Same degenerate split as `_answer_factual`'s own -- an empty
        # library vs. an explicitly-scoped selection that resolved to
        # nothing (e.g. a stale/foreign id, since `get_overview_documents`
        # is itself tenancy-scoped).
        reason = "empty_scope" if scoped_ids else "no_documents"
        return _finish(db, current_user, session, question, AskResponse(segments=[], empty_reason=reason))

    structure_text = _build_document_structure_text(documents)
    passages = fetch_passages_for_documents(
        [str(document.id) for document in documents], str(current_user.id)
    )
    if not passages:
        # The document(s) exist and are in scope, but Weaviate has no
        # passages for them (e.g. an explicitly-scoped not-yet-Ready
        # document, or an index/Postgres desync) -- distinct from "no
        # documents in scope" above; the library/selection isn't empty,
        # there's simply no source content to summarize. Matches the
        # existing "found something, nothing answerable" shape
        # `no_answer` already covers for the factual path.
        return _finish(db, current_user, session, question, AskResponse(segments=[], empty_reason="no_answer"))

    try:
        answer = generate_answer(
            question, passages, history=history, mode="overview", document_structure=structure_text
        )
    except ChatCompletionError as exc:
        logger.warning("Chat generation failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Answer generation is temporarily unavailable. Please try again.",
        ) from exc

    return _resolve_generated_answer(db, current_user, session, question, answer)


def _build_document_structure_text(documents: list[Document]) -> str:
    """`documents` (Story 3.5's `document_overview` intent) -> a plain-
    text outline block: for each document, its filename followed by its
    `chapter_breakdown` (chapter name -> passage count) as indented
    lines. A document whose `chapter_breakdown` is still `None` (not yet
    `Ready` -- reachable only when the caller explicitly scoped to it,
    per `repository.get_overview_documents`'s own docstring) contributes
    its filename with no chapter lines, never a fabricated outline (same
    "Pending, never a fabricated 0" rule `Document.chapter_breakdown`'s
    own docstring states).

    This is Postgres-derived text handed to `llm_client.generate_answer`
    as an opaque `document_structure` string -- `shared/llm_client` never
    queries Postgres itself (AD-2/AD-6), so building this string is this
    module's job, not that package's.
    """
    lines: list[str] = []
    for document in documents:
        lines.append(f"{document.filename}:")
        if document.chapter_breakdown:
            for chapter, count in document.chapter_breakdown.items():
                lines.append(f"  - {chapter}: {count} passages")
    return "\n".join(lines)


def _resolve_generated_answer(
    db: Session,
    current_user: User,
    session: ChatSession,
    question: str,
    answer: AnswerResult,
) -> AskResponse:
    """`generate_answer`'s structured result -> the persisted, citation-
    resolved `AskResponse` -- shared by `_answer_factual` and `_answer_
    document_overview`, since both call `generate_answer` and both need
    identical citation-resolution/no_answer treatment afterward.

    `kind="prose"` segments (Story 3.5) pass through as plain text with
    `citations=[]`, never dropped for lacking citations the way a
    `kind="grounded"` segment is below -- a prose segment carries no
    claim, so FR-9/AC6's citation guarantee was never a promise it made.
    Whether the answer as a whole actually said anything is checked
    afterward: `if not any(seg.citations for seg in segments)` -- an
    answer built entirely of prose (or of nothing at all) falls to
    `no_answer`, the same outcome an empty `answer.segments` always did,
    so prose can accompany a grounded answer but never substitute for one
    at these two intents (`ask_question`'s `"greeting"` branch is the one
    place unaccompanied prose is a valid, complete answer -- and it never
    reaches this function, since it never calls `generate_answer`).
    """
    document_ids = {p.document_id for p in answer.included_passages}
    filenames = repository.get_filenames_for_documents(db, current_user.id, document_ids)
    # 1-based, matches generate_answer's prompt numbering -- built from
    # `answer.included_passages` (the actual, budget-trimmed/sampled list
    # the prompt was built from), never a separate full retrieval list.
    passages_by_number = {i + 1: p for i, p in enumerate(answer.included_passages)}

    segments: list[AnswerSegmentResponse] = []
    for seg in answer.segments:
        if seg.kind == "prose":
            segments.append(AnswerSegmentResponse(text=seg.text, citations=[], kind="prose"))
            continue

        # (chapter, document_filename) -> the chunk indexes that supported
        # this segment under that pair. Two different chunks from the same
        # chapter of the same document (routine at TOP_K_PASSAGES=8, or a
        # model repeating a passage_number like [1, 1]) must render as one
        # chip, not two identical ones sitting side by side -- so they
        # merge into a single citation, but every contributing chunk is
        # kept in `chunk_indexes` rather than only the first (see
        # CitationResponse's own comment for why dropping the rest would
        # make the payload claim more precision than it has).
        #
        # A dict, not a set + parallel list: Python dicts preserve
        # insertion order, so first occurrence still wins the citation's
        # position in the rendered list, exactly as before.
        merged: dict[tuple[str, str], list[int]] = {}
        for number in seg.passage_numbers:
            source = passages_by_number.get(number)
            if source is None:
                # Already validated in llm_client -- defensive no-op here.
                continue
            filename = filenames.get(source.document_id)
            if filename is None:
                # Document deleted/inaccessible since indexing -- drop this
                # citation, never fabricate a filename.
                continue
            chunk_indexes = merged.setdefault((source.chapter, filename), [])
            # A model repeating the same passage_number twice must not
            # produce a duplicated index -- the merge is over distinct
            # source chunks, not over how often the model mentioned them.
            if source.chunk_index not in chunk_indexes:
                chunk_indexes.append(source.chunk_index)

        citations = [
            CitationResponse(
                chapter=chapter,
                document_filename=filename,
                chunk_indexes=chunk_indexes,
            )
            for (chapter, filename), chunk_indexes in merged.items()
        ]
        if not citations:
            # A segment that lost every citation (e.g. all its source
            # documents were deleted) is dropped entirely, not shown as an
            # uncited claim -- same AC6 guarantee llm_client's own
            # validation already enforces at the passage-number level.
            continue
        segments.append(AnswerSegmentResponse(text=seg.text, citations=citations, kind="grounded"))

    if not any(seg.citations for seg in segments):
        # The model returned segments: [] outright, every segment lost its
        # citations above, or the surviving segments are entirely prose --
        # either way, a passages-were-found-but-nothing-answerable
        # outcome, distinct from "no_documents"/"empty_scope". The
        # all-prose case is why this tests for a *cited* segment rather
        # than merely a non-empty `segments`: a response made only of
        # framing sentences carries no grounded claim, and returning it as
        # an answer would defeat exactly the FR-9/AC6 guarantee the
        # citation enforcement above exists to hold. No follow-up
        # suggestions either: they're a "what next" affordance for a real
        # answer, not for an empty-reason notice.
        return _finish(db, current_user, session, question, AskResponse(segments=[], empty_reason="no_answer"))

    return _finish(
        db,
        current_user,
        session,
        question,
        AskResponse(segments=segments, followup_questions=answer.followup_questions),
    )


def _pair_messages_into_turns(messages: list[ChatMessage]) -> list[ChatHistoryTurn]:
    """Chronological (oldest-first) `ChatMessage` rows -> completed
    `ChatHistoryTurn`s, pairing each `role="user"` row with the
    `role="assistant"` row immediately after it.

    Rows always arrive strictly alternating user/assistant in that order
    -- `_finish` below only ever persists a turn's two rows together, in
    the same request, so no partial/orphaned turn can exist between one
    call and the next. The `else: i += 1` branch is defensive only (a
    shape this codebase's own writer never produces), so a future writer
    bug surfaces as "history threading silently skips one row" rather
    than a crash that would take the whole question down with it.

    `answer` is `assistant_message.segments`' `text` fields joined with a
    space, citations stripped -- the Boundaries' "generation needs prior
    answer content, never the citations that grounded it" requirement.
    `assistant_message.segments` is `None`/`[]` for a refusal or an
    empty-reason notice turn, which folds to `""` here rather than
    fabricating placeholder answer text.
    """
    turns: list[ChatHistoryTurn] = []
    i = 0
    while i + 1 < len(messages):
        user_message, assistant_message = messages[i], messages[i + 1]
        if user_message.role == "user" and assistant_message.role == "assistant":
            answer_text = " ".join(
                segment.get("text", "") for segment in (assistant_message.segments or [])
            )
            turns.append(ChatHistoryTurn(question=user_message.question or "", answer=answer_text))
            i += 2
        else:
            i += 1
    return turns


def _finish(
    db: Session, current_user: User, session: ChatSession, question: str, response: AskResponse
) -> AskResponse:
    """Persists this turn's two rows -- the user's question, then the
    resulting assistant message -- against `session`, and returns
    `response` unchanged.

    Called at every `ask_question` return point that reaches this far,
    which by construction is every path except the `ChatCompletionError`
    -> 503 path above (that one raises before ever calling this -- see
    this function's own module docstring and the story's I/O matrix:
    "never persisted as a message, never rendered as an answer").

    `response.segments` (a list of Pydantic `AnswerSegmentResponse`) is
    stored via `model_dump()` -- a plain JSON-serializable list of dicts,
    matching `ChatMessage.segments`' documented shape and exactly what
    `ChatHistoryMessageResponse.model_validate` expects to read back.

    Also touches `session` (multi-session chat's auto-titling, decision
    #3): `sessions_repository.touch_session` bumps `session.updated_at`
    unconditionally and sets `session.title` from `question` only the
    first time, while it's still `None` -- see that function's own
    docstring. Truncates via `sessions_repository.derive_title` rather
    than a local `[:80].strip()` -- that's the one place the truncation
    length is defined, which is also what lets `edit_message` below
    recognize a still-auto-titled session without duplicating the same
    literal.

    `repository.save_message` flushes but never commits -- `get_db_session`
    (shared/data_access) doesn't auto-commit, so this function commits once
    after both rows and the session touch are staged, mirroring
    `documents/service.py`'s own "service layer owns the transaction
    boundary" convention (e.g. its `upload_document` commits right after
    `repository.create_document`).

    Stamps `response.message_id`/`response.user_message_id` with the
    assistant/user rows' own ids before returning -- see those fields'
    own docstrings for why both are always set by the time a response
    actually reaches the client.
    """
    user_message = repository.save_message(
        db, ChatMessage(user_id=current_user.id, session_id=session.id, role="user", question=question)
    )
    assistant_message = repository.save_message(
        db,
        ChatMessage(
            user_id=current_user.id,
            session_id=session.id,
            role="assistant",
            segments=[segment.model_dump() for segment in response.segments],
            empty_reason=response.empty_reason,
        ),
    )
    sessions_repository.touch_session(db, session, title=sessions_repository.derive_title(question))
    db.commit()
    response.message_id = assistant_message.id
    response.user_message_id = user_message.id
    return response


def _encode_cursor(message: ChatMessage) -> str:
    """`ChatMessage` row -> opaque pagination cursor (Story 3.4/AD-10):
    its own `(created_at, turn_role_rank, id)` tuple (see
    `repository.turn_role_rank`'s comment for why role, not just
    `created_at`+`id`, is part of this), serialized as
    `"<iso-timestamp>|<role-rank>|<uuid>"`. None of the three components
    can themselves contain `|`, so a `split(..., 2)` in `_decode_cursor`
    round-trips this exactly -- no need for a heavier encoding
    (base64/JSON) for a token this codebase never needs to hide the
    contents of, only to pass back verbatim.

    `role_rank` comes from `repository.turn_role_rank`, never a second,
    separately-hardcoded 0/1 rule here -- this module already imports
    `repository`, so there's no reason for this encoding and the SQL
    `_TURN_ROLE_RANK` ordering it anchors into to risk drifting apart.
    """
    role_rank = repository.turn_role_rank(message.role)
    return f"{message.created_at.isoformat()}|{role_rank}|{message.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, int, uuid.UUID]:
    """Inverse of `_encode_cursor`. `cursor` only ever arrives as a value
    this same endpoint issued as a prior response's `next_cursor` (the
    route's own contract) -- a malformed value is therefore a client bug,
    not a data condition to degrade gracefully from, so it 422s rather
    than silently falling back to "no cursor" (which would look like
    "start from the newest message again", a confusing, silent behavior
    change for a client that thought it was paging further back).

    The role-rank component is range-checked against
    `repository.VALID_TURN_ROLE_RANKS` (just `{0, 1}`) -- `int(...)`
    alone would happily parse `"7"` into a cursor that "decodes"
    successfully but anchors into `_TURN_ROLE_RANK`'s ordering nowhere
    any real row could ever sort to, producing silently wrong pagination
    instead of the same 422 every other malformed-cursor shape gets.
    """
    try:
        created_at_raw, role_rank_raw, id_raw = cursor.split("|", 2)
        created_at = datetime.fromisoformat(created_at_raw)
        role_rank = int(role_rank_raw)
        if role_rank not in repository.VALID_TURN_ROLE_RANKS:
            raise ValueError(f"role_rank out of range: {role_rank}")
        message_id = uuid.UUID(id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor.") from exc
    return created_at, role_rank, message_id


def get_history(
    db: Session, current_user: User, session_id: uuid.UUID, cursor: str | None, limit: int | None
) -> ChatHistoryResponse:
    """`GET /chat/sessions/{session_id}/history` (Story 3.4/AD-10;
    multi-session chat): a newest-first, cursor-paginated page of one of
    this account's chat sessions.

    `session_id` is resolved and ownership-checked first via
    `sessions_service.get_session` (404 on a foreign/nonexistent id),
    same as `ask_question`. `user_id` is `current_user.id`, resolved
    server-side from the JWT via `get_current_user` -- never
    client-supplied, matching this route's own contract in the spec's
    Boundaries.

    `cursor` is checked with `is not None`, not truthiness -- an empty
    string (`?cursor=`) is a malformed cursor, not "no cursor supplied",
    and must 422 via `_decode_cursor` the same as any other malformed
    value, rather than silently restarting from the newest page.
    """
    sessions_service.get_session(db, current_user, session_id)
    resolved_limit = limit if limit is not None else _DEFAULT_HISTORY_PAGE_SIZE
    decoded_cursor = _decode_cursor(cursor) if cursor is not None else None
    rows, has_more = repository.list_messages_for_user(
        db, current_user.id, session_id, decoded_cursor, resolved_limit
    )
    next_cursor = _encode_cursor(rows[-1]) if has_more and rows else None
    return ChatHistoryResponse(
        messages=[ChatHistoryMessageResponse.model_validate(row) for row in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )


def set_message_feedback(
    db: Session, current_user: User, message_id: uuid.UUID, rating: str | None
) -> ChatMessage:
    """`PUT /chat/messages/{message_id}/feedback`: sets (or, `rating=None`,
    clears) the thumbs-up/down rating on one of this account's own
    assistant messages.

    404s -- not 403 -- on a foreign/nonexistent id, same IDOR-safe
    convention `sessions_service.get_session` already uses, and also on a
    `role="user"` id: feedback exists only on the answer half of a turn
    (`ChatMessage.feedback`'s own docstring), so a question's id is just as
    "not a feedback-able message" as one that doesn't exist at all -- never
    a distinct error that would let a caller probe which id belongs to
    which role.
    """
    message = repository.get_message_for_user(db, current_user.id, message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(status_code=404, detail="Chat message not found.")
    message.feedback = rating
    db.commit()
    db.refresh(message)
    return message


def edit_message(
    db: Session,
    current_user: User,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    question: str,
    document_ids: list[uuid.UUID],
) -> AskResponse:
    """`POST /chat/sessions/{session_id}/messages/{message_id}/edit`:
    edits one of this account's own past questions in place -- discards
    that question and every turn after it (this session only), then asks
    the edited question fresh from there.

    Reuses `ask_question` entirely unchanged for the actual retrieval/
    generation/persistence work, rather than a second, parallel code
    path: once the trailing rows are deleted, `ask_question`'s own
    history fetch (`repository.get_recent_turn_messages`) naturally sees
    the truncated conversation, so an edited question behaves exactly
    like a brand-new one asked at that point -- not a special case that
    could quietly drift from `ask_question`'s own retrieval/refusal/
    generation/503 behavior.

    Deliberately does *not* commit the delete before re-asking. The
    delete is emitted into this request's open transaction, so every read
    below (including `ask_question`'s history fetch) already sees the
    truncated conversation -- committing here would buy nothing except an
    unrecoverable loss: if generation then fails, `ask_question` raises
    503 *after* the user's question and every following turn are already
    gone for good. Left uncommitted, `_finish` commits the delete and the
    new turn together, and anything that raises on the way there is
    rolled back explicitly below -- the edited-from conversation survives
    intact.

    The rollback is explicit rather than left to `get_db_session`'s own
    `db.close()` (which would also discard the uncommitted delete): this
    is the one guarantee this function exists to make, and it should not
    depend on which caller's session-teardown happens to run.

    Re-titling: if the edited question was the session's *first* message,
    the session's auto-title still reads the old text, and
    `sessions_repository.touch_session` only titles while `title` is
    `None`. Clearing it here (only when nothing precedes the edited
    message, and only while the title still matches
    `sessions_repository.derive_title` of the *old* question text -- a
    user's own rename is never thrown away) lets `_finish` re-derive the
    title from the edited question through that one existing code path.

    404s -- not 403 -- on a foreign/nonexistent session id (via
    `sessions_service.get_session`, same as `ask_question`) or message id,
    and on a `role="assistant"` id or a `message_id` from a *different*
    session: only a user's own question, in *this* session, can be
    edited -- never a distinct error that would let a caller probe which
    id belongs to which role/session.
    """
    session = sessions_service.get_session(db, current_user, session_id)
    message = repository.get_message_for_user(db, current_user.id, message_id)
    if message is None or message.session_id != session.id or message.role != "user":
        raise HTTPException(status_code=404, detail="Chat message not found.")

    was_first_message = repository.count_messages_before(db, current_user.id, session_id, message) == 0
    was_auto_titled = session.title == sessions_repository.derive_title(message.question)
    clears_title = was_first_message and was_auto_titled

    repository.delete_messages_from(db, current_user.id, session_id, message)
    if clears_title:
        session.title = None

    try:
        response = ask_question(db, current_user, session_id, question, document_ids)
    except Exception:
        db.rollback()
        raise
    response.session_retitled = clears_title
    return response
