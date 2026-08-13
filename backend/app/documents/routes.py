"""Documents module routes.

Three endpoints: `POST /documents` (single-file multipart upload) and
`GET /documents` (list) from Story 2.1, plus `GET /documents/{document_id}`
(Story 2.2) behind the Document Detail view. All three require
`Depends(get_current_user)` so `user_id` never comes from client-supplied
input (AD-2).

Upload is one file per request by design (per the story's Boundaries) --
the frontend fires one `XMLHttpRequest` per queued file in parallel, which
is what makes each row's progress genuinely independent rather than
synthetic.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.documents import service
from app.documents.rate_limiter import (
    get_upload_concurrency_limiter,
    get_upload_rate_limiter,
)
from app.documents.schemas import DocumentResponse
from app.shared.data_access import get_db_session
from app.shared.models import User
from app.shared.rate_limiter import ConcurrencyLimiter, RateLimiter

router = APIRouter(prefix="/documents", tags=["documents"])

# Read in bounded chunks rather than `await file.read()` so an oversized
# body is rejected as soon as it crosses the limit, not after being fully
# buffered -- format is checked first (cheap, no body needed at all), then
# this loop aborts the read itself rather than reading everything only to
# discard it on a post-hoc length check.
_READ_CHUNK_SIZE = 1024 * 1024


async def _read_bounded(file: UploadFile) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > service.MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=400, detail="File exceeds the 20MB size limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_upload_rate_limiter),
    concurrency_limiter: ConcurrencyLimiter = Depends(get_upload_concurrency_limiter),
) -> DocumentResponse:
    user_key = str(current_user.id)
    rate_limiter.check(user_key)
    # The concurrency slot wraps the body read specifically -- that's the
    # part that holds bytes in memory, so it's what needs bounding against
    # a parallel burst. Released via context manager even if validation
    # raises mid-read.
    with concurrency_limiter.slot(user_key):
        file_type = service.validate_format(file.filename or "", file.content_type)
        content = await _read_bounded(file)
        service.validate_size(len(content))
        document = service.upload_document(
            db,
            current_user,
            filename=file.filename or "",
            file_type=file_type,
            content=content,
        )
    return DocumentResponse.model_validate(document)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    documents = service.list_documents(db, current_user)
    return [DocumentResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """The by-id read behind Story 2.2's Document Detail.

    The codebase's first by-id document endpoint, so its first IDOR
    surface: `document_id` is client-supplied, `current_user` comes only
    from the JWT (AD-2), and the two are combined in a single user-scoped
    query in the repository -- never a bare primary-key fetch followed by
    an ownership `if`. Annotating `document_id` as `uuid.UUID` also means a
    non-uuid path segment is rejected by FastAPI as a 422 before any query
    runs.

    Responds with `DocumentResponse`, the same schema list/upload use --
    so the raw `content` bytes and `user_id` cannot be serialized here by
    accident.
    """
    document = service.get_document(db, current_user, document_id)
    return DocumentResponse.model_validate(document)
