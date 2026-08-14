"""Chat module data access (Story 3.1).

Per architecture decision AD-2, Postgres access here goes through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than a
hand-written `select(Document).where(...)` -- same pattern
`documents/repository.py` uses.
"""

import uuid

from sqlalchemy.orm import Session

from app.shared.data_access.tenancy import user_scoped_select
from app.shared.models import Document


def get_filenames_for_documents(
    db: Session, user_id: uuid.UUID, document_ids: set[str]
) -> dict[str, str]:
    """`document_id` (string, matching Weaviate's string-typed
    `document_id` property) -> `filename`, scoped to documents this user
    owns via `user_scoped_select` (AD-2) -- never a bare
    `select(Document).where(Document.id.in_(...))`.

    A `document_id` present in `document_ids` but absent from the
    returned dict means either the document was deleted after its
    passages were indexed, or -- in principle, shouldn't happen since
    Weaviate's own query was already `user_id`-filtered -- doesn't belong
    to this user. Either way, the caller (`chat/service.py`) must treat a
    missing filename as "drop this citation," never crash or fabricate a
    filename. Malformed ids (shouldn't occur -- every id was written by
    `documents/service.py`'s `ingest_document` as `str(document.id)`) are
    skipped the same defensive way rather than raising.
    """
    if not document_ids:
        return {}

    parsed_ids: list[uuid.UUID] = []
    for document_id in document_ids:
        try:
            parsed_ids.append(uuid.UUID(document_id))
        except ValueError:
            continue

    if not parsed_ids:
        return {}

    stmt = user_scoped_select(Document, user_id).where(Document.id.in_(parsed_ids))
    rows = db.execute(stmt).scalars().all()
    return {str(row.id): row.filename for row in rows}
