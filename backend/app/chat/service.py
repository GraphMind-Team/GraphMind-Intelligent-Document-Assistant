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
    # 1-based, matches generate_answer's prompt numbering.
    passages_by_number = {i + 1: p for i, p in enumerate(passages)}

    segments: list[AnswerSegmentResponse] = []
    for seg in answer.segments:
        citations: list[CitationResponse] = []
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
