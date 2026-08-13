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
