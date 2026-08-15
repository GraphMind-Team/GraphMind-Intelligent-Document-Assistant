"""Auth module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly.
"""

import uuid

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
