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
