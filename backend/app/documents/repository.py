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

from sqlalchemy import desc, update
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


def claim_failed_document_for_reingest(db: Session, document_id: uuid.UUID) -> bool:
    """Atomically flip a `Failed` document back to `Uploaded` so its
    ingestion can be retried in place (Story 2.6). Returns `True` if this
    caller won the claim, `False` if the row was no longer `Failed`.

    A conditional `UPDATE ... WHERE id = :id AND status = 'Failed'`, not a
    read-then-write on the ORM object, because this *is* AD-1's retry lock
    made real: two concurrent re-uploads of the same failed document could
    both read `status == "Failed"` before either wrote, and both schedule
    `ingest_document` against one row -- two pipelines racing on the same
    document, exactly what the retry lock exists to prevent. A single
    conditional statement makes the check and the claim one atomic
    operation, so `rowcount` is an honest answer to "did I win?".

    `failed_reason` and `chapter_breakdown` are cleared in the same
    statement: a row that is about to be re-ingested must not keep
    displaying the previous attempt's failure text (Story 2.5's field), and
    `chapter_breakdown` is only ever repopulated on a successful `Ready`
    commit anyway.

    Does not commit -- the caller (service layer) owns the transaction
    boundary, mirroring `create_document` above.
    """
    result = db.execute(
        update(Document)
        .where(Document.id == document_id, Document.status == "Failed")
        .values(status="Uploaded", failed_reason=None, chapter_breakdown=None)
    )
    return result.rowcount == 1


def get_document_by_content_hash(db: Session, user_id: uuid.UUID, content_hash: str) -> Document | None:
    """One document by content hash, scoped to its owner (Story 2.6).

    Mirrors `get_document_for_user`'s tenancy-scoped pattern -- hash lookup
    never crosses users (AD-2, spec's "Never: no dedupe across users"), so
    this goes through `user_scoped_select` rather than a bare
    `content_hash` filter. Used both for the pre-create dedupe check in
    `service.upload_document` and again after an `IntegrityError` on the
    concurrent-upload race, to fetch the row the other request just won.
    """
    stmt = user_scoped_select(Document, user_id).where(Document.content_hash == content_hash)
    return db.execute(stmt).scalars().first()
