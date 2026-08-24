"""Chat sessions module business logic (multi-session chat).

Raises `HTTPException` directly (AD-3: no custom error envelope), mirroring
`folders/service.py`/`auth/service.py`/`documents/service.py`. `title`
validation happens here rather than in a pydantic validator so a rejected
value comes back as a plain 400 (the spec's I/O matrix), not a 422
validation envelope -- the same split `folders/service.py::_validate_name`
already draws.
"""

import uuid
from typing import Final

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.chat import sessions_repository as repository
from app.shared.models import ChatSession, User

# Mirrors `folders/service.py::MAX_NAME_LENGTH` -- also matches
# `ChatSessionUpdateRequest.title`'s own `max_length` (chat/schemas.py),
# enforced again here so a direct API call can't bypass the Pydantic
# field constraint's cousin by relying on it alone (same defensive-
# duplication reasoning `folders/service.py` states for its own name
# length cap).
MAX_TITLE_LENGTH: Final = 255


def _validate_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Chat title must not be blank.")
    if len(stripped) > MAX_TITLE_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"Chat title must be at most {MAX_TITLE_LENGTH} characters."
        )
    return stripped


def list_sessions(db: Session, current_user: User) -> list[ChatSession]:
    return repository.list_sessions_for_user(db, current_user.id)


def get_session(db: Session, current_user: User, session_id: uuid.UUID) -> ChatSession:
    """One session by id, or `HTTPException(404)`.

    404 -- not 403 -- for another account's session, or an id that
    doesn't exist at all: same IDOR-safe convention
    `folders/service.py::get_folder`/`documents/service.py::get_document`
    already establish. This is the entry point every session-scoped chat
    operation (`chat/service.py::ask_question`/`get_history`) calls
    first, before any retrieval/generation work happens.
    """
    session = repository.get_session_for_user(db, current_user.id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return session


def create_session(db: Session, current_user: User) -> ChatSession:
    """A titleless session to start a new conversation in -- auto-titled
    from its first question by `chat/service.py::_finish` (via
    `sessions_repository.touch_session`), not here. Starts with no
    messages, so it is immediately listable (`list_sessions`) but reads
    as empty until the first `ask`.

    Reuses this account's existing blank session if it already has one
    (`sessions_repository.get_reusable_empty_session_for_user`: no
    messages, no title) rather than inserting a second identical row.
    Nothing in this app ever deletes an unused session, so without the
    reuse every "New chat" click -- and every `/chat` visit that
    redirects through `ChatIndexRedirect` -- would leave behind a
    permanent "New chat" entry in the sidebar. Reusing is
    indistinguishable to the caller: it gets back an empty, untitled
    session either way, and `updated_at` is bumped so the reused one
    still sorts to the top of the list.

    Idempotent for a client that retries, too: a repeat POST that lands
    before the first session has been used returns that same session
    instead of a duplicate.
    """
    session = repository.get_reusable_empty_session_for_user(db, current_user.id)
    if session is None:
        session = repository.create_session(db, ChatSession(id=uuid.uuid4(), user_id=current_user.id, title=None))
    else:
        repository.touch_session(db, session)
    db.commit()
    db.refresh(session)
    return session


def rename_session(db: Session, current_user: User, session_id: uuid.UUID, title: str) -> ChatSession:
    session = get_session(db, current_user, session_id)
    session.title = _validate_title(title)
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, current_user: User, session_id: uuid.UUID) -> None:
    """Deletes a session and every message it owns (`sessions_repository
    .delete_session` handles the fixed messages-then-session delete
    order) -- passed the row `get_session` already resolved and
    ownership-checked, so the session is read exactly once."""
    session = get_session(db, current_user, session_id)
    repository.delete_session(db, session)
    db.commit()
