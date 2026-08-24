"""Pydantic request/response models for the chat module (Story 3.1).

Mirrors `documents/schemas.py`'s pattern where applicable. Unlike that
module, `AskResponse` is hand-assembled by `service.py` rather than built
from an ORM row, so `from_attributes` isn't needed here.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    # Strips before validation, so a whitespace-only question fails
    # min_length automatically rather than needing a manual check in
    # service.py -- a blank/over-length question is a 422 (FastAPI's own
    # validation-error shape, no custom envelope per AD-3), not a 400.
    model_config = ConfigDict(str_strip_whitespace=True)

    # max_length is a defensive cap, not a measured value -- it mainly
    # exists so a pathological input can't dominate
    # shared/llm_client's own prompt-size budget.
    question: str = Field(min_length=1, max_length=2000)

    # Story 3.3/FR-11: empty (the default) means "search all of the user's
    # documents" -- unchanged from Story 3.1's only behavior. No ownership
    # check happens on these ids anywhere in the request path; the existing
    # user_id filter search_passages already applies is what keeps a
    # foreign/stale id from ever widening retrieval (see
    # weaviate_client.search_passages). max_length is a defensive cap, same
    # spirit as `question`'s above -- not a measured value.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class CitationResponse(BaseModel):
    chapter: str
    document_filename: str
    # Chunk-level traceability that survives even when `chapter` degenerates
    # to parsing.py's `_FULL_DOCUMENT_CHAPTER` ("Full Document") -- the
    # common case for a PDF with no bookmarks/outline, where every citation
    # in the document would otherwise render identically and be
    # indistinguishable from a document-level source (the outcome FR-9
    # forbids). Not rendered by the current chip (its `Ch. {chapter},
    # {document_filename}` format is fixed by UX-DR3, and jump-to-source is
    # out of this story's scope) -- carried in the API purely so that
    # traceability isn't lost before a future story needs it.
    #
    # A list, not a single `chunk_index`, because `service.py` merges
    # citations on `(chapter, document_filename)` so the chip renders once
    # rather than N identical times. With a scalar field that merge would
    # keep only the first contributing chunk, making the payload claim one
    # specific chunk supported the segment when in fact several did -- more
    # precise than the data actually is, and silently lossy. Ordered by
    # first appearance in the model's own `passage_numbers` (i.e. retrieval
    # order, nearest-first -- not sorted), deduplicated, and always
    # non-empty, since a citation only exists because a passage produced it.
    chunk_indexes: list[int]


class AnswerSegmentResponse(BaseModel):
    text: str
    citations: list[CitationResponse]
    # Story 3.5: "grounded" (default, pre-3.5 meaning -- every citation in
    # `citations` backs a claim in `text`) or "prose" (a conversational
    # aside -- a greeting, a short framing sentence -- with no claim and so
    # always an empty `citations`). Defaults to "grounded" so an
    # already-persisted `chat_messages` row (written before this field
    # existed) reads back with its original meaning intact, matching
    # `llm_client.AnswerSegment.kind`'s own default for the same reason.
    kind: Literal["grounded", "prose"] = "grounded"


class AskResponse(BaseModel):
    segments: list[AnswerSegmentResponse]
    # None when segments is non-empty. Distinguishes four otherwise-
    # identical-looking "nothing to show" cases so the frontend can render
    # four different things:
    #   "no_documents" -- search_passages returned zero results with no
    #                     scope requested (empty or not-yet-ingested
    #                     library)
    #   "empty_scope"  -- Story 3.3/FR-11: search_passages returned zero
    #                     results, but a non-empty document_ids scope WAS
    #                     requested -- the library isn't empty, the
    #                     selected documents just have no matching
    #                     passages (not yet Ready, or no relevant content).
    #                     Kept distinct from "no_documents" so a user with
    #                     a full library who scoped narrowly doesn't see
    #                     copy implying they have nothing uploaded.
    #   "no_answer"    -- passages were found and generate_answer ran, but
    #                     every segment was either returned empty by the
    #                     model or dropped during citation resolution
    #   "refusal"      -- FR-10/OD-2: every retrieved passage's relevance
    #                     score fell below RELEVANCE_THRESHOLD
    #                     (shared/llm_client), so generate_answer was
    #                     never called at all. The one case the frontend
    #                     must render as a real bubble, never the plain
    #                     notice paragraph the other two use (UX-DR15) --
    #                     it is a designed, correct outcome, not an error
    #                     and not an empty answer.
    empty_reason: Literal["no_documents", "empty_scope", "no_answer", "refusal"] | None = None


class ChatHistoryMessageResponse(BaseModel):
    """One persisted `ChatMessage` row (Story 3.4/FR-17/AD-10), as
    rendered by `GET /chat/history`.

    Built directly from the ORM row via `model_validate` (`from_attributes
    =True`, unlike `AskResponse` above, which is hand-assembled) --
    `segments`' stored shape (a JSON list of dicts matching
    `AnswerSegmentResponse`, written by `chat/service.py::_finish`) is
    exactly what `AnswerSegmentResponse`'s own field validation expects,
    so no manual reshaping is needed here.

    `role="user"` rows carry `question` (`segments`/`empty_reason` both
    `None`); `role="assistant"` rows carry `segments` (always present,
    possibly `[]`) and/or `empty_reason` (`question` `None`) -- the same
    two-shape duality `ChatMessage` itself documents, surfaced verbatim
    rather than reshaped into one merged "message" concept, so the
    frontend can render each exactly the way `ChatMessage.jsx` already
    renders a live turn's `user`/`assistant`/`notice`/`refusal` roles.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    question: str | None = None
    segments: list[AnswerSegmentResponse] | None = None
    empty_reason: Literal["no_documents", "empty_scope", "no_answer", "refusal"] | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """`GET /chat/history`'s response (Story 3.4/AD-10): a newest-first
    page of this account's single ongoing conversation, cursor-paginated
    -- never the full history as one unbounded blob (AD-10's explicit
    requirement)."""

    messages: list[ChatHistoryMessageResponse]
    # Opaque token (an encoded `(created_at, id)` pair -- see
    # `chat/service.py`'s cursor encode/decode helpers); pass verbatim as
    # the next request's `cursor` query param to fetch the next-older
    # page. `None` when there is nothing older to fetch.
    next_cursor: str | None = None
    has_more: bool
