"""Pydantic request/response models for the folders module.

`name`/`color` are left as plain `str` here rather than pydantic-validated
(e.g. `min_length=1`, a `Literal` for color) -- the spec's I/O matrix
requires an empty name or an invalid color key to come back as a plain 400
`{"detail": ...}`, not a 422 pydantic-validation envelope, so that
enforcement lives in `service.py` (mirrors `documents/service.py`'s
`validate_format`/`validate_size`, which do the same thing for the same
reason). `FolderUpdateRequest`'s fields are both optional so a rename-only
or recolor-only PATCH doesn't have to resend the field it isn't changing.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FolderCreateRequest(BaseModel):
    name: str
    color: str


class FolderUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None


class FolderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    created_at: datetime
