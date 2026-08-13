"""Pydantic request/response models for the chat module (Story 3.1).

Mirrors `documents/schemas.py`'s pattern where applicable. Unlike that
module, `AskResponse` is hand-assembled by `service.py` rather than built
from an ORM row, so `from_attributes` isn't needed here.
"""

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


class CitationResponse(BaseModel):
    chapter: str
    document_filename: str


class AnswerSegmentResponse(BaseModel):
    text: str
    citations: list[CitationResponse]


class AskResponse(BaseModel):
    segments: list[AnswerSegmentResponse]
    # None when segments is non-empty. Distinguishes three otherwise-
    # identical-looking "nothing to show" cases so the frontend can render
    # three different things, none of which may look like Story 3.2's
    # not-yet-designed refusal (UX-DR15):
    #   "no_documents" -- search_passages returned zero results (empty or
    #                     not-yet-ingested library)
    #   "no_answer"    -- passages were found and generate_answer ran, but
    #                     every segment was either returned empty by the
    #                     model or dropped during citation resolution
    empty_reason: Literal["no_documents", "no_answer"] | None = None
