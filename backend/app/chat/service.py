"""Chat module business logic (Story 3.1).

Orchestrates the grounded-answer flow: embed -> search -> (degenerate
zero-passage case) -> generate -> resolve citations -> assemble. Any data
access here goes through `app.shared.data_access` / `app.chat.repository`
rather than talking to Postgres/Weaviate/Neo4j directly (AD-2).
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
from app.shared.data_access.weaviate_client import TOP_K_PASSAGES, search_passages
from app.shared.llm_client import (
    HISTORY_MAX_TURNS,
    RELEVANCE_THRESHOLD,
    ChatCompletionError,
    ChatHistoryTurn,
    bound_chat_history,
    generate_answer,
)
from app.shared.models import ChatMessage, User

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
) -> AskResponse:
    """Embed -> search -> (degenerate zero-passage case) -> generate ->
    resolve -> assemble.

    `question` arrives already validated non-blank/length-bounded by
    `AskRequest` (chat/schemas.py) -- no manual check here. `document_ids`
    (Story 3.3/FR-11) arrives as whatever the client sent, unvalidated for
    ownership -- `search_passages`'s own `user_id` filter is what keeps a
    foreign/stale id from ever widening retrieval, so no extra check is
    needed here.

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

    History threading (Story 3.4/FR-17): before retrieval, this fetches
    the bounded recent-turn window (`HISTORY_MAX_TURNS`/`HISTORY_MAX_CHARS`,
    `shared/llm_client`) from this account's own persisted `ChatMessage`
    rows and folds it into two places -- the retrieval query text (prior
    *questions* only, per the Boundaries' "keeps the embedding focused on
    topical/entity words" reasoning) and `generate_answer`'s `history`
    param (full Q+A, citations stripped). An empty window (a fresh
    conversation) makes both of those identical to the pre-3.4 call
    shape -- `search_passages(question, ...)` and `generate_answer(question,
    passages)` unchanged -- rather than merely behaviorally equivalent.
    Retrieval's `document_ids` scope is never touched by history: this
    turn's own `document_ids` argument is the only thing that ever
    widens/narrows what `search_passages` searches, exactly as before
    Story 3.4, even if an earlier turn in the same conversation used a
    different scope.

    `use_history=False` opts a caller out of the *read* half of that
    threading entirely: no window is fetched, and the retrieval/generation
    calls are the exact pre-3.4 shapes. It exists for one caller --
    `scripts/eval_harness.py`, Epic 6's measurement instrument (FR-13),
    which runs a 15-20 question set sequentially through this function
    against a single QA account. With history on, question N's retrieval
    embedding becomes the previous three questions newline-joined ahead of
    its own -- four unrelated questions spanning different fixture
    documents, embedded as one vector -- so SM-1/SM-2/SM-C1
    would no longer measure what OD-3's 92.9% baseline measured, and
    persisted rows surviving between runs would make consecutive runs
    non-comparable to each other on top of that. The harness measures
    single-question retrieval, which is what OD-2's `RELEVANCE_THRESHOLD`
    was itself calibrated against; it is not the instrument for OD-8's
    window size. Default `True` -- every real request path keeps history.
    The *write* half is deliberately not gated: `_finish` still persists,
    so the "every path except 503 persists" invariant below holds for
    every caller without exception (the harness's own rows simply go
    unread, accumulating on the QA account the same way its ingested
    fixture documents already do -- see that script's own
    known-limitation note).

    Persistence (Story 3.4/AD-10): every return point below except the
    `ChatCompletionError` -> 503 path goes through `_finish`, which
    persists this turn's question and the resulting assistant message
    (whatever it is -- a real answer, a refusal, or an empty-reason
    notice) as two `ChatMessage` rows. The 503 path is the one documented
    exception (this function's own I/O matrix): a generation failure is
    never persisted as a message and never rendered as an answer, so a
    retried question doesn't leave a phantom failed turn in the
    conversation history a reload would show.

    Capacity note: this is a sync `def` route, so FastAPI runs it in
    Starlette's anyio threadpool (a fixed-size worker pool, not the async
    event loop) -- `generate_answer`'s retry backoff (`time.sleep`,
    `shared/llm_client`) blocks whichever worker is running this request
    for the full ~45s/attempt, up to ~120s worst case on a retry, with
    that worker doing nothing else meanwhile. Fine at demo scale; under
    real concurrent load the threadpool's worker count becomes a hard
    ceiling on simultaneous in-flight chat questions, not just a latency
    number -- worth knowing before this is mistaken for a scaling bug
    found the hard way rather than a known, documented limit.
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

    if history:
        # Design Notes: prior questions only, newest last, then the
        # current question -- keeps the embedding on-topic rather than
        # diluted with prior answer prose. Deliberately NOT built when
        # `history` is empty (see below) so a fresh conversation's
        # retrieval query is the exact pre-3.4 bare `question`, not
        # merely an empty join that happens to look the same.
        query_text = "\n".join(turn.question for turn in history) + "\n" + question
    else:
        query_text = question
    scoped_ids = [str(document_id) for document_id in document_ids]
    passages = search_passages(
        query_text, str(current_user.id), limit=TOP_K_PASSAGES, document_ids=scoped_ids or None
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

    # From `answer.included_passages`, not the full `passages` retrieval --
    # same reasoning as `passages_by_number` below: the budget-trimmed list
    # actually sent to the model is the source of truth for what this
    # answer can cite, so filename resolution shouldn't look up documents
    # that were never in play. Harmless either way today (a superset only
    # adds unused entries to `filenames`), but keeping the two aligned means
    # a future change to `_select_passages_within_budget` can't quietly
    # make them diverge.
    document_ids = {p.document_id for p in answer.included_passages}
    filenames = repository.get_filenames_for_documents(db, current_user.id, document_ids)
    # 1-based, matches generate_answer's prompt numbering -- built from
    # `answer.included_passages` (the actual, budget-trimmed list the
    # prompt was built from), never the full `passages` retrieval
    # returned. Using the full list would only happen to work today
    # because _select_passages_within_budget drops exclusively from the
    # tail; keying off included_passages instead means citation
    # resolution can't silently desync from generate_answer's own
    # selection, whatever it becomes.
    passages_by_number = {i + 1: p for i, p in enumerate(answer.included_passages)}

    segments: list[AnswerSegmentResponse] = []
    for seg in answer.segments:
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
        segments.append(AnswerSegmentResponse(text=seg.text, citations=citations))

    if not segments:
        # The model returned segments: [] outright, or every segment lost
        # its citations above -- either way, a passages-were-found-but-
        # nothing-answerable outcome, distinct from "no_documents".
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
