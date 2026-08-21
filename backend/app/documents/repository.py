"""Documents module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly. `list_documents_for_user` is built through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than
hand-writing `select(Document).where(Document.user_id == ...)` here --
that's the one place the tenancy filter is applied, so this call site
can't ship without it by omission.

`Document.content` (the raw uploaded bytes, up to the 20MB cap) is deferred
on every read below except `ingest_document`'s own `db.get(Document, ...)`
in `service.py`, which is the only caller that actually parses it. Without
`defer()`, a plain `select(Document)` loads that column on every row it
touches -- the list endpoint alone would pull the full bytes of every
document a user has just to render a card grid of filename/type/status/
date, and the content-hash dedupe lookup would pull it just to read a
column that isn't `content` at all.
"""

import uuid

from sqlalchemy import delete, desc, update
from sqlalchemy.orm import Session, defer

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
    stmt = (
        user_scoped_select(Document, user_id)
        .order_by(desc(Document.created_at))
        .options(defer(Document.content))
    )
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
    stmt = (
        user_scoped_select(Document, user_id)
        .where(Document.id == document_id)
        .options(defer(Document.content))
    )
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


def delete_document_for_user(db: Session, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    """Hard-deletes one document row, scoped to its owner (Story 2.7).

    Mirrors `get_document_for_user`'s tenancy-scoped lookup rather than a
    bare `db.get(Document, document_id)` + ownership check, for the same
    IDOR reason documented there: "not yours" and "doesn't exist" both
    resolve to `False` here, indistinguishably, so the service layer can
    answer both with an identical 404.

    Returns `True` if a row was found and staged for delete, `False`
    otherwise. Does not commit -- the caller (service layer) owns the
    transaction boundary, mirroring `create_document`'s convention, and
    deliberately runs the Weaviate passage delete *before* calling this,
    never after (see `service.delete_document`).

    No soft-delete flag, no `deleted_at` column -- a genuine `db.delete`.
    `Document` has no incoming FK from any other table (only `User` and
    `Document` exist), so there is no cascade to handle. Neo4j is never
    touched *here* -- the caller (`service.delete_document`) runs the
    Neo4j prune (Story 2.8's `prune_document_from_graph`) as its own step,
    before ever reaching this function.
    """
    document = get_document_for_user(db, user_id, document_id)
    if document is None:
        return False
    db.delete(document)
    return True


def delete_all_documents_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Bulk-deletes every `documents` row owned by `user_id` in one
    statement (Story 5.3's account-deletion cascade) -- deliberately not a
    loop calling `delete_document_for_user` once per row, which would be N
    `DELETE` statements (and N ORM identity-map loads) for work a single
    `DELETE ... WHERE user_id = :user_id` already does in one round-trip
    (see this story's Boundaries/Never).

    Does not commit -- the caller (`auth/service.py::delete_account`) owns
    the transaction boundary, alongside the Weaviate/Neo4j deletes and the
    `users` row delete it also runs in the same commit, mirroring
    `create_document`'s convention.

    Returns the number of rows deleted. No caller acts on that count
    today, but it's what `result.rowcount` already gives back for free,
    mirroring `claim_failed_document_for_reingest`'s own rowcount return.
    """
    result = db.execute(delete(Document).where(Document.user_id == user_id))
    return result.rowcount


def update_document_folder(db: Session, document: Document, folder_id: uuid.UUID | None) -> Document:
    """Sets `document.folder_id` to `folder_id` (or `None` to unassign).

    Takes the already-loaded, already-tenancy-checked `document` object
    (from `get_document_for_user`, via `service.get_document`) rather than
    an id -- the folder-ownership check (a different tenancy check, on a
    different table) happens in the service layer before this is ever
    called, mirroring `claim_failed_document_for_reingest`'s "the caller
    enforces the business rule, this function only does the write"
    convention. Does not commit -- the caller owns the transaction
    boundary.
    """
    document.folder_id = folder_id
    db.flush()
    return document


def get_document_by_content_hash(db: Session, user_id: uuid.UUID, content_hash: str) -> Document | None:
    """One document by content hash, scoped to its owner (Story 2.6).

    Mirrors `get_document_for_user`'s tenancy-scoped pattern -- hash lookup
    never crosses users (AD-2, spec's "Never: no dedupe across users"), so
    this goes through `user_scoped_select` rather than a bare
    `content_hash` filter. Used both for the pre-create dedupe check in
    `service.upload_document` and again after an `IntegrityError` on the
    concurrent-upload race, to fetch the row the other request just won.
    """
    stmt = (
        user_scoped_select(Document, user_id)
        .where(Document.content_hash == content_hash)
        .options(defer(Document.content))
    )
    return db.execute(stmt).scalars().first()
