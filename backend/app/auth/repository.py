"""Auth module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, user: User) -> User:
    """Stage `user` for insert and flush to surface a unique-constraint
    conflict as `IntegrityError` immediately. Does not commit or roll back
    -- the caller (service layer) owns the whole transaction boundary,
    since a future multi-write operation (e.g. Story 1.5) may need to
    commit or roll back several repository calls as one transaction."""
    db.add(user)
    db.flush()
    return user


def update_user_theme(db: Session, user: User, theme: str) -> User:
    user.theme = theme
    db.flush()
    return user


def update_user_language(db: Session, user: User, language: str) -> User:
    user.language = language
    db.flush()
    return user


def update_user_profile(db: Session, user: User, full_name: str) -> User:
    user.full_name = full_name
    db.flush()
    return user


def update_user_password(db: Session, user: User, password_hash: str) -> User:
    user.password_hash = password_hash
    db.flush()
    return user


def mark_email_verified(db: Session, user: User) -> User:
    """Story 1.6: stamps `email_verified_at` with the current time. Only
    ever called from `service.verify_email`, which already guards this
    against a re-verify (an already-verified `user` never reaches here) --
    this function itself doesn't re-check, matching this module's existing
    convention of trusting the caller to enforce the business rule and
    doing only the write here."""
    user.email_verified_at = datetime.now(timezone.utc)
    db.flush()
    return user


def delete_user(db: Session, user_id: uuid.UUID) -> None:
    """Hard-deletes the `users` row for `user_id` (Story 5.3's
    account-deletion cascade) -- no soft-delete flag, no `deleted_at`
    column, same convention as `documents/repository.py`'s
    `delete_document_for_user`.

    Takes an id (not the already-loaded `User` object every other function
    in this module takes) to match this story's Code Map, and because the
    caller (`service.delete_account`) already has `current_user.id` in
    hand from `get_current_user`. Does not commit -- the caller owns the
    transaction boundary, alongside the documents-table cascade and the
    Weaviate/Neo4j deletes it also runs in the same commit, mirroring
    `create_user`'s convention.

    `current_user.id` always names a real row at the start of the request
    (resolved from `get_current_user`'s own DB lookup moments earlier),
    never client input -- but a concurrent second `DELETE /auth/me` for the
    same account (two tabs, a retried request) could still race ahead and
    commit first, so `db.get` returning `None` here is a real, not
    hypothetical, case: a no-op rather than `db.delete(None)` raising, so
    the loser of that race sees the same clean outcome the winner did.
    """
    user = db.get(User, user_id)
    if user is None:
        return
    db.delete(user)
