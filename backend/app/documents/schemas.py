"""Pydantic response models for the documents module.

Mirrors `auth/schemas.py`'s pattern: `from_attributes=True` so a
`Document` ORM instance can be validated directly into the response model
without a manual field-by-field mapping. No request schema here -- the
upload endpoint takes a multipart file, not a JSON body.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    created_at: datetime
    # Story 2.4: `dict[chapter_name] -> passage_count`, only ever populated
    # in the same commit that sets `status = "Ready"`. `None` for every
    # other status -- the frontend's Document Detail page renders "Pending"
    # rather than treating `None`/missing as zero (UX-DR8).
    chapter_breakdown: dict[str, int] | None = None
    # Story 2.5: a short, human-readable, stage-aware reason, populated
    # straight from the model -- `None` for every status other than
    # `Failed` (set only in the same commit as `status = "Failed"`).
    failed_reason: str | None = None
    # Story 2.6: additive-only field, defaults to `False`, so no existing
    # response consumer needs to change. `True` only when this response
    # body is the *existing* document returned in place of creating a new
    # one -- the route sets the 200 status code alongside this.
    is_duplicate: bool = False
    # Folder-grouping feature: `None` means "Unfiled". Additive-only field,
    # same reasoning as `is_duplicate` above -- every existing response
    # consumer is unaffected by its presence.
    folder_id: uuid.UUID | None = None


class UpdateDocumentFolderRequest(BaseModel):
    """Body for `PATCH /documents/{document_id}`. `folder_id: null`
    unassigns the document (back to "Unfiled") -- this is the one and only
    field this endpoint accepts (the spec's Boundaries: no server-side
    sort/filter param, and this PATCH exists solely for folder assignment).
    No default -- the caller must state its intent explicitly, either a
    folder id or `null`, rather than an omitted field silently unassigning."""

    folder_id: uuid.UUID | None
