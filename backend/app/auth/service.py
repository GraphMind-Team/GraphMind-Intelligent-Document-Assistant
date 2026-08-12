"""Auth business logic: password hashing and registration.

Raises `HTTPException` directly (AD-3: no custom error envelope) -- this is
the first module to implement the route -> service -> repository ->
shared.data_access chain, so it sets the precedent other modules mirror.
"""

from passlib.hash import bcrypt_sha256
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.auth import repository
from app.auth.schemas import RegisterRequest
from app.shared.models import User


def hash_password(password: str) -> str:
    return bcrypt_sha256.hash(password)


def register_user(db: Session, data: RegisterRequest) -> User:
    # data.email is already stripped+lowercased by RegisterRequest's
    # validator, so this and any other consumer of the schema agree on the
    # same casing.
    if repository.get_user_by_email(db, data.email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
    )

    try:
        user = repository.create_user(db, user)
        db.commit()
    except IntegrityError:
        # Defense-in-depth against a concurrent registration racing the
        # pre-check above -- the DB-level unique constraint on email caught
        # what the pre-check missed.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists."
        ) from None

    db.refresh(user)
    return user
