"""Documents module routes.

Two endpoints this story needs: `POST /documents` (single-file multipart
upload) and `GET /documents` (minimal list -- just enough to prove a row
appears post-upload; the real list/detail UI is Story 2.2's job). Both
require `Depends(get_current_user)` so `user_id` never comes from
client-supplied input (AD-2).

Upload is one file per request by design (per the story's Boundaries) --
the frontend fires one `XMLHttpRequest` per queued file in parallel, which
is what makes each row's progress genuinely independent rather than
synthetic.
"""

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
