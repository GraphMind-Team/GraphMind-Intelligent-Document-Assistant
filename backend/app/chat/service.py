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
from app.shared.llm_client import ChatCompletionError, generate_answer
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
    never an exception. This is the precise separation AC12 requires: the
    zero-passages path and the LLM-wrapper-failure path never share a
    status code or a branch (AD-3/AD-6).

    Forward-compatibility note for Story 3.2 (not built here): the
    relevance-threshold short-circuit AD-6 describes belongs right after
    `search_passages` returns and before `generate_answer` is called --
    exactly where the `if not passages:` branch sits below, which 3.2
    will extend to also check each passage's `.distance` against OD-2's
    (still-unset) threshold.

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
        # FR-10 refusal (that's Story 3.2's job, gated on a relevance
        # threshold this story doesn't have).
        return AskResponse(segments=[], empty_reason="no_documents")

    try:
        answer = generate_answer(question, passages)
    except ChatCompletionError as exc:
        logger.warning("Chat generation failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Answer generation is temporarily unavailable. Please try again.",
        ) from exc

    document_ids = {p.document_id for p in passages}
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
        citations: list[CitationResponse] = []
        # (chapter, document_filename) pairs already added to this segment
        # -- two different chunks from the same chapter of the same
        # document (routine at TOP_K_PASSAGES=8, or a model repeating a
        # passage_number like [1, 1]) must render as one chip, not two
        # identical ones sitting side by side. Order-preserving: first
        # occurrence wins the citation's position in the rendered list.
        seen_citations: set[tuple[str, str]] = set()
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
            citation_key = (source.chapter, filename)
            if citation_key in seen_citations:
                continue
            seen_citations.add(citation_key)
            citations.append(CitationResponse(chapter=source.chapter, document_filename=filename))
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
