"""Chat sessions module data access (multi-session chat).

Per architecture decision AD-2, all Postgres access goes through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than
hand-writing `select(ChatSession).where(...)` -- mirrors
`folders/repository.py`'s own convention and the reason stated there.
"""

import uuid
from typing import Final

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.chat.repository import delete_messages_for_session
from app.shared.data_access.tenancy import user_scoped_select
from app.shared.models import ChatMessage, ChatSession

# The one place auto-titling's truncation length is defined. Both
# `derive_title` below and `chat/service.py::edit_message` (which must
# recognize whether a session's *current* title still matches what
# auto-titling would have produced from a question being replaced) key
# off this same constant -- two independent `[:80]` literals could drift
# apart silently (e.g. one gets bumped to 120 during a redesign and not
# the other), which would make `edit_message`'s "was this an auto-title"
# check simply stop matching, with no error, just a title that quietly
# stops updating on edit.
MAX_AUTO_TITLE_LENGTH: Final = 80


def derive_title(question: str | None) -> str | None:
    """A session's auto-title from one of its own questions -- `None` if
    `question` is `None`/blank once stripped.

    The one function that actually performs the truncation described in
    `MAX_AUTO_TITLE_LENGTH`'s own comment; `touch_session` (live
    auto-titling) and `chat/service.py::edit_message` (recognizing a
    still-auto-titled session) both call this rather than each hardcoding
    their own `[:MAX_AUTO_TITLE_LENGTH].strip()`.
    """
    if question is None:
        return None
    return question[:MAX_AUTO_TITLE_LENGTH].strip() or None


def create_session(db: Session, session: ChatSession) -> ChatSession:
    """Stage `session` for insert and flush to surface any integrity
    error immediately. Does not commit -- the caller (service layer) owns
    the transaction boundary, mirroring `folders/repository.py`'s
    `create_folder`."""
    db.add(session)
    db.flush()
    return session


def get_reusable_empty_session_for_user(db: Session, user_id: uuid.UUID) -> ChatSession | None:
    """This account's most recent session that has no messages and no
    title yet, or `None`.

    "No title" is part of the definition, not an extra: a renamed but
    still-empty session is one the user deliberately set up, and handing
    it back as the target of an unrelated "New chat" would silently
    hijack it.

    `chat/sessions_service.py::create_session` uses this to hand back an
    existing blank session instead of inserting another one -- without
    it, every "New chat" click (and every `/chat` visit that redirects
    through `ChatIndexRedirect`) permanently adds a row that reads as
    "New chat" forever, since nothing ever cleans an unused session up.
    """
    stmt = (
        user_scoped_select(ChatSession, user_id)
        .where(
            ChatSession.title.is_(None),
            ~select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists(),
        )
        .order_by(desc(ChatSession.updated_at))
    )
    return db.execute(stmt).scalars().first()


def list_sessions_for_user(db: Session, user_id: uuid.UUID) -> list[ChatSession]:
    """Most-recently-active first (`updated_at` desc) -- matches the
    sidebar's own "recent chats bubble to the top" ordering, not creation
    order (see `ChatSession`'s own docstring for why `updated_at` is
    bumped explicitly on every turn rather than left to an ORM
    `onupdate=`)."""
    stmt = user_scoped_select(ChatSession, user_id).order_by(desc(ChatSession.updated_at))
    return list(db.execute(stmt).scalars().all())


def get_session_for_user(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession | None:
    """One session by id, scoped to its owner.

    Deliberately not a bare `db.get(ChatSession, session_id)` -- narrowing
    `user_scoped_select` by id instead makes "not yours" and "doesn't
    exist" the same result (`None`) by construction, which is what lets
    the service layer answer both with an identical 404 rather than a 403
    that would confirm the id exists (mirrors
    `folders/repository.py::get_folder_for_user`).
    """
    stmt = user_scoped_select(ChatSession, user_id).where(ChatSession.id == session_id)
    return db.execute(stmt).scalars().first()


def delete_session(db: Session, session: ChatSession) -> None:
    """Deletes an already-resolved, already-ownership-checked session and
    every message it owns.

    Takes the `ChatSession` the service layer just fetched rather than
    re-selecting it by id (`chat/sessions_service.py::delete_session`
    calls `get_session` first, which 404s on a foreign/nonexistent id) --
    one read, and the ownership check stays in exactly one place.

    Messages are deleted first (`chat/repository.py
    ::delete_messages_for_session`) -- `chat_messages.session_id` has no
    `ON DELETE CASCADE`, so deleting the `chat_sessions` row first would
    fail with a `ForeignKeyViolation`.

    Does not commit -- the caller owns the transaction boundary.
    """
    delete_messages_for_session(db, session.user_id, session.id)
    db.delete(session)


def delete_session_for_user(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Resolve-by-id wrapper around `delete_session` above, for callers
    that don't already hold the row.

    Messages are deleted first (`chat/repository.py
    ::delete_messages_for_session`) -- `chat_messages.session_id` has no
    `ON DELETE CASCADE`, so deleting the `chat_sessions` row first would
    fail with a `ForeignKeyViolation`.

    Returns `True` if a session row was found and staged for delete,
    `False` otherwise. Does not commit -- the caller owns the transaction
    boundary.
    """
    session = get_session_for_user(db, user_id, session_id)
    if session is None:
        return False
    delete_session(db, session)
    return True


def delete_all_sessions_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Bulk-deletes every `chat_sessions` row owned by `user_id`
    (`auth/service.py::delete_account`'s cascade, extended for
    multi-session chat) -- `ChatSession.user_id` is a `NOT NULL` FK into
    `users.id` with no `ON DELETE CASCADE`, so this must run before the
    `users` row delete. Must also run *after*
    `chat/repository.py::delete_all_messages_for_user` in that same
    cascade, for the identical FK reason `delete_session_for_user` above
    orders its own two deletes.

    One statement, not a loop over `delete_session_for_user`. Does not
    commit -- the caller owns the transaction boundary.
    """
    result = db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    return result.rowcount


def touch_session(db: Session, session: ChatSession, title: str | None = None) -> None:
    """Bumps `session.updated_at` to now, and -- only the first time,
    while `session.title` is still `None` -- sets `title` (multi-session
    chat's auto-titling: `chat/service.py::_finish` passes
    `derive_title(question)` here, already truncated). A later call with
    `title` set never overwrites an already-titled session, whether that
    title came from auto-titling or a user's own rename
    (`chat/sessions_service.py::rename_session`).

    Does not commit or flush -- the caller (`chat/service.py::_finish`)
    already flushes/commits its own two `ChatMessage` inserts in the same
    transaction, and this session update rides along in that same commit.
    """
    session.updated_at = func.now()
    if session.title is None and title:
        session.title = title
