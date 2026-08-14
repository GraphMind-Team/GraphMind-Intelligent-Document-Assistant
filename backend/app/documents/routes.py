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

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile
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
    response: Response,
    background_tasks: BackgroundTasks,
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
        document, outcome = service.upload_document(
            db,
            current_user,
            filename=file.filename or "",
            file_type=file_type,
            content=content,
        )
    # Story 2.6: a hash match reuses the *existing* document -- nothing was
    # created, so a "duplicate" outcome's response is 200, not the route's
    # default 201. "reingested" is also 200 (still no row created) but,
    # unlike "duplicate", schedules ingestion the same as a fresh "created"
    # upload -- retrying a *failed* document in place is not the duplicated
    # work NFR-7 forbids. The `response_model=DocumentResponse` declared
    # above still governs serialization regardless of which status code is
    # set here.
    if outcome == "duplicate":
        response.status_code = 200
        return DocumentResponse.model_validate(document).model_copy(update={"is_duplicate": True})

    if outcome == "reingested":
        response.status_code = 200
        background_tasks.add_task(service.ingest_document, document.id)
        return DocumentResponse.model_validate(document)

    # Scheduled after the response is prepared, not awaited here -- Story
    # 2.3's parse/embed/index pipeline runs after the upload response is
    # sent, so upload latency stays independent of parsing time. Only
    # `document.id` is passed; `ingest_document` re-derives everything else
    # (file_type, content, user_id) from the row it just wrote, so there's
    # no separate parameter that could ever drift from what was durably
    # persisted under the JWT-derived `current_user.id` above (AC4).
    background_tasks.add_task(service.ingest_document, document.id)
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
