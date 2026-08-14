"""Chat module business logic (Story 3.1).

Orchestrates the grounded-answer flow: embed -> search -> (degenerate
zero-passage case) -> generate -> resolve citations -> assemble. Any data
access here goes through `app.shared.data_access` / `app.chat.repository`
rather than talking to Postgres/Weaviate/Neo4j directly (AD-2).
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.chat import repository
from app.chat.schemas import AnswerSegmentResponse, AskResponse, CitationResponse
from app.shared.data_access.weaviate_client import TOP_K_PASSAGES, search_passages
from app.shared.embeddings import embed_texts
from app.shared.llm_client import RELEVANCE_THRESHOLD, ChatCompletionError, generate_answer
from app.shared.models import User

logger = logging.getLogger(__name__)


def ask_question(db: Session, current_user: User, question: str) -> AskResponse:
    """Embed -> search -> (degenerate zero-passage case) -> generate ->
    resolve -> assemble.

    `question` arrives already validated non-blank/length-bounded by
    `AskRequest` (chat/schemas.py) -- no manual check here.

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
    called -- no generation call is made at all, per AD-6.

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
    query_vector = embed_texts([question])[0]
    passages = search_passages(query_vector, str(current_user.id), limit=TOP_K_PASSAGES)

    if not passages:
        # AC12's degenerate case: an effectively-empty library. NOT the
        # FR-10 refusal below -- an empty library and a library that has
        # documents but none relevant enough are distinct outcomes, and
        # the frontend renders them differently.
        return AskResponse(segments=[], empty_reason="no_documents")

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
        return AskResponse(segments=[], empty_reason="refusal")

    try:
        answer = generate_answer(question, passages)
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
        return AskResponse(segments=[], empty_reason="no_answer")

    return AskResponse(segments=segments)
