"""Documents module business logic: upload validation and orchestration.

Raises `HTTPException` directly (AD-3: no custom error envelope), mirroring
`auth/service.py`. Validation happens here, before any repository call --
the route layer stays thin and a rejected file never reaches the DB.
"""

import pathlib
import uuid
from typing import Final

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.documents import repository
from app.shared.models import Document, User

# 20MB per the story's Boundaries -- named here once so the reason cited in
# a rejection message and the actual enforced limit can never drift apart.
MAX_FILE_SIZE_BYTES: Final = 20 * 1024 * 1024

# Extension -> the FR-4-vocabulary-adjacent `file_type` value stored on the
# row. `.md`/`.markdown` both map to "markdown", `.html`/`.htm` both map to
# "html" -- the extension is what the user sees rejected/accepted, the
# stored `file_type` is the normalized value the rest of the app (Story
# 2.2+'s list/detail UI) keys off.
_EXTENSION_TO_FILE_TYPE: Final = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
}

# Content-Type sets are permissive by design, not just by extension: real
# browsers/OSes frequently have no mime mapping for .md (and sometimes
# .html) and fall back to "application/octet-stream" or "text/plain" --
# rejecting those would break the valid, common case. What this still
# catches is a file whose Content-Type actively disagrees with its
# extension (e.g. a .pdf upload sent as "application/msword").
#
# Compared against a normalized Content-Type (parameters like
# "; charset=utf-8" stripped, lowercased) -- browsers routinely send
# "text/plain; charset=utf-8" for .md/.html, which would otherwise fail an
# exact-string match against the bare "text/plain" entry below and reject
# a legitimate upload.
_ALLOWED_CONTENT_TYPES: Final = {
    "pdf": {"application/pdf", "application/octet-stream"},
    "markdown": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
    "html": {"text/html", "application/xhtml+xml", "application/octet-stream"},
}

_SUPPORTED_FORMATS_LABEL: Final = ".pdf, .md, .markdown, .html, .htm"


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return content_type
    return content_type.split(";", 1)[0].strip().lower()


def validate_format(filename: str, content_type: str | None) -> str:
    """Returns the normalized `file_type`, or raises `HTTPException(400)`
    with a plain-language reason (UX-DR19) -- format/content-type only, no
    size check. Split out from size validation so the route layer can
    reject a bad format/content-type *before* reading the request body at
    all, per the story's Boundaries ("Validate before any DB write, not
    after") -- the size limit still needs bytes in hand to enforce, but
    format never does."""
    extension = pathlib.Path(filename).suffix.lower()
    file_type = _EXTENSION_TO_FILE_TYPE.get(extension)
    if file_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {_SUPPORTED_FORMATS_LABEL}.",
        )

    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type and normalized_content_type not in _ALLOWED_CONTENT_TYPES[file_type]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {_SUPPORTED_FORMATS_LABEL}.",
        )

    return file_type


def validate_size(size: int) -> None:
    """Raises `HTTPException(400)` for an empty or oversized file. Called
    by the route layer *during* the bounded chunked read (aborting as soon
    as `MAX_FILE_SIZE_BYTES` is exceeded, never buffering a full oversized
    body) and again here for the empty-file case, which only the final
    size can reveal."""
    if size == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    if size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 20MB size limit.")


def upload_document(
    db: Session,
    current_user: User,
    *,
    filename: str,
    file_type: str,
    content: bytes,
) -> Document:
    """Stores one already-validated upload as a `Uploaded`-status row.

    Format/content-type (`validate_format`) and size (`validate_size`) are
    validated by the caller (route layer) before this runs -- by the time
    `content` is fully in hand, both checks have already passed.
    `current_user` (resolved only from `get_current_user`, per AD-2) is
    the sole source of `user_id` written to the row -- never anything
    client-supplied. No parsing/indexing happens here (Story 2.3's job);
    the row lands at `status="Uploaded"` and stays there.
    """
    document = Document(
        id=uuid.uuid4(),
        user_id=current_user.id,
        filename=filename,
        file_type=file_type,
        file_size_bytes=len(content),
        status="Uploaded",
        content=content,
    )

    document = repository.create_document(db, document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, current_user: User) -> list[Document]:
    return repository.list_documents_for_user(db, current_user.id)


def get_document(db: Session, current_user: User, document_id: uuid.UUID) -> Document:
    """One document by id, or `HTTPException(404)`.

    404 -- not 403 -- for another account's document: a 403 would confirm
    the id exists, which is itself a disclosure. The repository's
    user-scoped query returns `None` for both "no such document" and "not
    yours", so the two cases are indistinguishable from here by
    construction, not by a remembered convention.
    """
    document = repository.get_document_for_user(db, current_user.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
