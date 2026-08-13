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
