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
    """A new, titleless session -- auto-titled from its first question by
    `chat/service.py::_finish` (via `sessions_repository.touch_session`),
    not here. Starts with no messages, so it is immediately listable
    (`list_sessions`) but reads as empty until the first `ask`."""
    session = ChatSession(id=uuid.uuid4(), user_id=current_user.id, title=None)
    session = repository.create_session(db, session)
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
    .delete_session_for_user` handles the fixed messages-then-session
    delete order)."""
    get_session(db, current_user, session_id)
    repository.delete_session_for_user(db, current_user.id, session_id)
    db.commit()
