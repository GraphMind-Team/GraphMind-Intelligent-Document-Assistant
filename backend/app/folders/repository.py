"""Folders module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly. Every per-user query is built through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than
hand-writing `select(Folder).where(Folder.user_id == ...)` here -- mirrors
`documents/repository.py`'s own convention and the reason stated there:
this is the one place the tenancy filter is applied, so a call site can't
ship without it by omission.
"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.shared.data_access.tenancy import user_scoped_select
from app.shared.models import Folder


def create_folder(db: Session, folder: Folder) -> Folder:
    """Stage `folder` for insert and flush to surface any integrity error
    immediately. Does not commit -- the caller (service layer) owns the
    transaction boundary, mirroring `documents/repository.py`'s
    `create_document`."""
    db.add(folder)
    db.flush()
    return folder


def list_folders_for_user(db: Session, user_id: uuid.UUID) -> list[Folder]:
    stmt = user_scoped_select(Folder, user_id).order_by(Folder.created_at)
    return list(db.execute(stmt).scalars().all())


def count_folders_for_user(db: Session, user_id: uuid.UUID) -> int:
    """How many folders `user_id` owns (`service.create_folder`'s cap).

    A `COUNT(*)`, not `len(list_folders_for_user(...))` -- the caller only
    needs the number, and materializing every `Folder` row into ORM
    objects to then throw them away is work that grows with exactly the
    thing the cap exists to bound.

    Built through `user_scoped_select` like every other query here, rather
    than a hand-written `select(func.count()).where(...)`: the tenancy
    filter belongs in one place (this module's own docstring), and a count
    that quietly spanned all users would make the cap global instead of
    per-account without looking wrong at the call site.
    """
    stmt = select(func.count()).select_from(user_scoped_select(Folder, user_id).subquery())
    return db.execute(stmt).scalar_one()


def get_folder_for_user(db: Session, user_id: uuid.UUID, folder_id: uuid.UUID) -> Folder | None:
    """One folder by id, scoped to its owner.

    Deliberately not a bare `db.get(Folder, folder_id)` -- narrowing
    `user_scoped_select` by id instead makes "not yours" and "doesn't
    exist" the same result (`None`) by construction, which is what lets the
    service layer answer both with an identical 404 rather than a 403 that
    would confirm the id exists (mirrors `documents/repository.py`'s
    `get_document_for_user`).
    """
    stmt = user_scoped_select(Folder, user_id).where(Folder.id == folder_id)
    return db.execute(stmt).scalars().first()


def delete_folder_for_user(db: Session, user_id: uuid.UUID, folder_id: uuid.UUID) -> bool:
    """Deletes one folder row, scoped to its owner. `documents.folder_id`'s
    `ON DELETE SET NULL` handles unfiling that folder's documents at the DB
    level -- this function only ever deletes the `folders` row itself.

    Returns `True` if a row was found and staged for delete, `False`
    otherwise. Does not commit -- the caller owns the transaction boundary.
    """
    folder = get_folder_for_user(db, user_id, folder_id)
    if folder is None:
        return False
    db.delete(folder)
    return True


def delete_all_folders_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Bulk-deletes every `folders` row owned by `user_id` (account
    deletion cascade, `auth/service.py::delete_account`) -- `Folder.user_id`
    is a `NOT NULL` FK into `users.id` with no `ON DELETE CASCADE`, so this
    must run before the `users` row delete, mirroring
    `documents/repository.py`'s `delete_all_documents_for_user` and
    `chat/repository.py`'s equivalent for the identical reason. One
    statement, not a loop over `delete_folder_for_user`.

    Does not commit -- the caller owns the transaction boundary.
    """
    result = db.execute(delete(Folder).where(Folder.user_id == user_id))
    return result.rowcount
