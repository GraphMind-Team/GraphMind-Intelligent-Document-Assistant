"""Documents module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly. `list_documents_for_user` is built through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than
hand-writing `select(Document).where(Document.user_id == ...)` here --
that's the one place the tenancy filter is applied, so this call site
can't ship without it by omission.
"""

import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.shared.data_access.tenancy import user_scoped_select
from app.shared.models import Document


def create_document(db: Session, document: Document) -> Document:
    """Stage `document` for insert and flush to surface any integrity
    error immediately. Does not commit -- the caller (service layer) owns
    the transaction boundary, mirroring `auth/repository.py`'s
    `create_user`."""
    db.add(document)
    db.flush()
    return document


def list_documents_for_user(db: Session, user_id: uuid.UUID) -> list[Document]:
    stmt = user_scoped_select(Document, user_id).order_by(desc(Document.created_at))
    return list(db.execute(stmt).scalars().all())


def get_document_for_user(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    """One document by id, scoped to its owner (Story 2.2).

    Deliberately *not* `db.get(Document, document_id)` -- a bare primary-key
    fetch would return another account's row and leave tenancy to a
    hand-written check the caller could forget. Narrowing
    `user_scoped_select` by id instead makes "not yours" and "doesn't
    exist" the same result (`None`) by construction, which is what lets the
    service layer answer both with an identical 404 rather than a 403 that
    would confirm the id exists.
    """
    stmt = user_scoped_select(Document, user_id).where(Document.id == document_id)
    return db.execute(stmt).scalars().first()
