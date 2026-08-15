"""Auth business logic: password hashing, registration, login, and JWTs.

Raises `HTTPException` directly (AD-3: no custom error envelope) -- this is
the first module to implement the route -> service -> repository ->
shared.data_access chain, so it sets the precedent other modules mirror.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Final

import jwt
from passlib.hash import bcrypt_sha256
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.auth import repository
from app.auth.schemas import ChangePasswordRequest, RegisterRequest, UpdateProfileRequest
from app.shared.models import User

# The one place the JWT algorithm is named -- every encode/decode call in
# this module uses this constant, and no other module ever imports or
# passes an algorithm string of its own. Hardcoded rather than
# env-configurable: there's no legitimate MVP need to change it, and this
# removes any path to a misconfigured or attacker-influenced algorithm
# (e.g. accidentally allowing "none").
JWT_ALGORITHM: Final = "HS256"

_DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

@lru_cache
def _dummy_password_hash() -> str:
    """Dummy hash so a login attempt against a nonexistent email still
    runs a bcrypt verify (same code path, roughly the same wall-clock time
    as a wrong-password attempt against a real account) -- avoids a timing
    side-channel that would otherwise reveal which emails are registered.

    Computed lazily and cached (mirrors `get_engine`'s pattern in
    shared/data_access/session.py), not eagerly at import time -- bcrypt
    hashing costs ~300ms, which every import of this module (including
    pytest collection, or any process that never calls
    `authenticate_user`) would otherwise pay up front for no reason, and
    which adds directly to Render's already-slow cold start."""
    return bcrypt_sha256.hash("dummy-password-for-timing-parity")


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


def _jwt_secret() -> str:
    # Presence is already guaranteed at boot by main._validate_env(); the
    # bracket access (not .get) here is a defensive belt-and-suspenders
    # read against this function ever being called before that check runs.
    return os.environ["JWT_SECRET"]


def _access_token_expire_minutes() -> int:
    raw = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES")
    if not raw:
        return _DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        # PyJWT >=2.10 requires `sub` to be a string, not a UUID object.
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_access_token_expire_minutes()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Raises HTTPException(401) for any invalid/expired/malformed token --
    never returns a value that isn't a genuine, verified user id."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Not authenticated.") from None

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Not authenticated.") from None


def update_theme(db: Session, user: User, theme: str) -> None:
    repository.update_user_theme(db, user, theme)
    db.commit()


def update_profile(db: Session, user: User, data: UpdateProfileRequest) -> User:
    user = repository.update_user_profile(db, user, data.full_name)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, data: ChangePasswordRequest) -> None:
    # Re-verifies the current password server-side (an in-session change,
    # not a reset flow) -- mirrors authenticate_user's bcrypt_sha256.verify
    # call, but against the already-known user rather than a
    # lookup-by-email, and with no dummy-hash timing shim since there's no
    # account-enumeration concern for an authenticated caller checking
    # their own password.
    if not bcrypt_sha256.verify(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_hash = hash_password(data.new_password)
    repository.update_user_password(db, user, new_hash)
    db.commit()


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Raises one generic 401 for both "no such email" and "wrong
    password" -- this is the message that actually matters for account
    enumeration (unlike registration's necessarily-revealing 409)."""
    user = repository.get_user_by_email(db, email)
    hash_to_check = user.password_hash if user is not None else _dummy_password_hash()
    password_ok = bcrypt_sha256.verify(password, hash_to_check)
    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return user
