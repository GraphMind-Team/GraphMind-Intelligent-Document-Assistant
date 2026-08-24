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

from app.chat import repository
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
from app.shared.models import ChatMessage, Document, User

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
    question: str,
    document_ids: list[uuid.UUID],
    *,
    use_history: bool = True,
    use_router: bool = True,
) -> AskResponse:
    """Route -> (embed -> search) or (fetch document structure) ->
    (degenerate zero-passage case) -> generate -> resolve -> assemble.

    `question` arrives already validated non-blank/length-bounded by
    `AskRequest` (chat/schemas.py) -- no manual check here. `document_ids`
    (Story 3.3/FR-11) arrives as whatever the client sent, unvalidated for
    ownership -- `search_passages`/`fetch_passages_for_documents`'s own
    `user_id` filter is what keeps a foreign/stale id from ever widening
    retrieval, so no extra check is needed here.

    History threading (Story 3.4/FR-17): before routing, this fetches the
    bounded recent-turn window (`HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS`,
    `shared/llm_client`) from this account's own persisted `ChatMessage`
    rows. An empty window (a fresh conversation) makes `history=[]`,
    identical to the pre-3.4 call shape.

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
    if use_history:
        history = bound_chat_history(
            _pair_messages_into_turns(
                repository.get_recent_turn_messages(db, current_user.id, HISTORY_MAX_TURNS)
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
        return _finish(db, current_user, question, AskResponse(segments=segments))

    if plan.intent == "document_overview":
        return _answer_document_overview(db, current_user, question, document_ids, scoped_ids, history)

    return _answer_factual(db, current_user, question, plan.search_query, scoped_ids, history)


def _answer_factual(
    db: Session,
    current_user: User,
    question: str,
    search_query: str,
    scoped_ids: list[str],
    history: list[ChatHistoryTurn],
) -> AskResponse:
    """The `"factual"` branch (Story 3.1/3.2/3.3, `search_query` rewrite
    added Story 3.5): embed -> search -> refusal short-circuit -> generate
    -> resolve.

    `search_query` is the retrieval embedding text (Story 3.5's router
    rewrite, or the bare `question` when the router had nothing to
    resolve or was skipped); `question` itself is what `generate_answer`
    is called with (so the answer's phrasing/language matches what the
    user actually typed, not the rewritten form) and what gets persisted.
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
        return _finish(db, current_user, question, AskResponse(segments=[], empty_reason=reason))

    if not any(p.distance is not None and p.distance <= RELEVANCE_THRESHOLD for p in passages):
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
        return _finish(db, current_user, question, AskResponse(segments=[], empty_reason="refusal"))

    try:
        answer = generate_answer(question, passages, history=history)
    except ChatCompletionError as exc:
        logger.warning("Chat generation failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Answer generation is temporarily unavailable. Please try again.",
        ) from exc

    return _resolve_generated_answer(db, current_user, question, answer)


def _answer_document_overview(
    db: Session,
    current_user: User,
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
        return _finish(db, current_user, question, AskResponse(segments=[], empty_reason=reason))

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
        return _finish(db, current_user, question, AskResponse(segments=[], empty_reason="no_answer"))

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

    return _resolve_generated_answer(db, current_user, question, answer)


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
    db: Session, current_user: User, question: str, answer: AnswerResult
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
        # outcome, distinct from "no_documents"/"empty_scope".
        return _finish(db, current_user, question, AskResponse(segments=[], empty_reason="no_answer"))

    return _finish(db, current_user, question, AskResponse(segments=segments))


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


def _finish(db: Session, current_user: User, question: str, response: AskResponse) -> AskResponse:
    """Persists this turn's two rows -- the user's question, then the
    resulting assistant message -- and returns `response` unchanged.

    Called at every `ask_question` return point that reaches this far,
    which by construction is every path except the `ChatCompletionError`
    -> 503 path above (that one raises before ever calling this -- see
    this function's own module docstring and the story's I/O matrix:
    "never persisted as a message, never rendered as an answer").

    `response.segments` (a list of Pydantic `AnswerSegmentResponse`) is
    stored via `model_dump()` -- a plain JSON-serializable list of dicts,
    matching `ChatMessage.segments`' documented shape and exactly what
    `ChatHistoryMessageResponse.model_validate` expects to read back.

    `repository.save_message` flushes but never commits -- `get_db_session`
    (shared/data_access) doesn't auto-commit, so this function commits once
    after both rows are staged, mirroring `documents/service.py`'s own
    "service layer owns the transaction boundary" convention (e.g. its
    `upload_document` commits right after `repository.create_document`).
    """
    repository.save_message(
        db, ChatMessage(user_id=current_user.id, role="user", question=question)
    )
    repository.save_message(
        db,
        ChatMessage(
            user_id=current_user.id,
            role="assistant",
            segments=[segment.model_dump() for segment in response.segments],
            empty_reason=response.empty_reason,
        ),
    )
    db.commit()
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
    db: Session, current_user: User, cursor: str | None, limit: int | None
) -> ChatHistoryResponse:
    """`GET /chat/history` (Story 3.4/AD-10): a newest-first, cursor-
    paginated page of this account's single ongoing conversation.

    `user_id` is `current_user.id`, resolved server-side from the JWT via
    `get_current_user` (same as `ask_question`) -- never client-supplied,
    matching this route's own contract in the spec's Boundaries.

    `cursor` is checked with `is not None`, not truthiness -- an empty
    string (`?cursor=`) is a malformed cursor, not "no cursor supplied",
    and must 422 via `_decode_cursor` the same as any other malformed
    value, rather than silently restarting from the newest page.
    """
    resolved_limit = limit if limit is not None else _DEFAULT_HISTORY_PAGE_SIZE
    decoded_cursor = _decode_cursor(cursor) if cursor is not None else None
    rows, has_more = repository.list_messages_for_user(db, current_user.id, decoded_cursor, resolved_limit)
    next_cursor = _encode_cursor(rows[-1]) if has_more and rows else None
    return ChatHistoryResponse(
        messages=[ChatHistoryMessageResponse.model_validate(row) for row in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )
