"""Auth module data access.

Per architecture decision AD-2, all Postgres access goes through
`app.shared.data_access` (the `Session` passed in here) rather than opening
a connection directly.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.shared.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def create_user(db: Session, user: User) -> User:
    """Stage `user` for insert and flush to surface a unique-constraint
    conflict as `IntegrityError` immediately. Does not commit -- the caller
    (service layer) owns the transaction boundary, since a future
    multi-write operation (e.g. Story 1.5) may need to commit several
    repository calls as one transaction."""
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise
    return user
