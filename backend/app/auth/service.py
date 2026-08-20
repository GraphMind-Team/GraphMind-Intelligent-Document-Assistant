"""Auth business logic: password hashing, registration, login, and JWTs.

Raises `HTTPException` directly (AD-3: no custom error envelope) -- this is
the first module to implement the route -> service -> repository ->
shared.data_access chain, so it sets the precedent other modules mirror.
"""

import logging
import os
import uuid
from collections.abc import Callable
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
from app.chat import repository as chat_repository
from app.documents import repository as documents_repository
from app.shared.data_access.session import get_session_factory
from app.shared.email import send_email
# Safe import direction (Design Notes): `documents/` never imports `auth/`,
# so `auth/service.py -> documents/service.py` introduces no cycle. Reuses
# `DELETABLE_STATUSES` (public -- both modules read it) rather than
# redefining it, keeping the deletable-status set single-sourced between
# `delete_document` and `delete_account`.
from app.documents.service import DELETABLE_STATUSES
from app.shared.data_access.neo4j_client import delete_entities_for_user
from app.shared.data_access.weaviate_client import delete_passages_for_user
from app.shared.models import User

logger = logging.getLogger(__name__)

# The one place the JWT algorithm is named -- every encode/decode call in
# this module uses this constant, and no other module ever imports or
# passes an algorithm string of its own. Hardcoded rather than
# env-configurable: there's no legitimate MVP need to change it, and this
# removes any path to a misconfigured or attacker-influenced algorithm
# (e.g. accidentally allowing "none").
JWT_ALGORITHM: Final = "HS256"

_DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Story 1.6: the `typ` claim that separates a login bearer token from a
# verify-email token -- both are signed with the same JWT_SECRET, so
# without this claim either token would be freely replayable as the
# other (a verification link forwarded to an attacker would double as a
# session token; a stolen access token would double as a way to
# "re-verify" -- harmless today, but a needless privilege blur). Access
# tokens are minted with no `typ` at all (see create_access_token) rather
# than "typ": "access", so every access token issued before this story
# shipped -- and every hand-crafted token in tests/test_auth_login.py --
# keeps decoding exactly as before.
EMAIL_VERIFICATION_TOKEN_TYPE: Final = "email_verify"
_DEFAULT_VERIFICATION_TOKEN_EXPIRE_HOURS = 24

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


def _verification_token_expire_hours() -> int:
    raw = os.environ.get("EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS")
    if not raw:
        return _DEFAULT_VERIFICATION_TOKEN_EXPIRE_HOURS
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_VERIFICATION_TOKEN_EXPIRE_HOURS


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        # PyJWT >=2.10 requires `sub` to be a string, not a UUID object.
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=_access_token_expire_minutes()),
        # No "typ" claim -- see EMAIL_VERIFICATION_TOKEN_TYPE's docstring
        # above for why absence (not "typ": "access") is deliberate.
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Raises HTTPException(401) for any invalid/expired/malformed token --
    never returns a value that isn't a genuine, verified user id."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Not authenticated.") from None

    # A verify-email token carries "typ": "email_verify" and must never be
    # accepted here -- otherwise a verification link (which can end up
    # forwarded, logged, or leaked far more casually than a session token)
    # would double as a working bearer credential. An access token has no
    # "typ" claim at all, so this only rejects tokens explicitly minted for
    # some other purpose.
    if payload.get("typ") is not None:
        raise HTTPException(status_code=401, detail="Not authenticated.") from None

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Not authenticated.") from None


def create_email_verification_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=_verification_token_expire_hours()),
        "typ": EMAIL_VERIFICATION_TOKEN_TYPE,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_email_verification_token(token: str) -> uuid.UUID:
    """Raises HTTPException(400) for any invalid/expired/malformed token,
    or one that isn't actually a verification token (e.g. an access token
    replayed here) -- 400, not 401, since the caller of
    `POST /auth/verify-email` is never expected to be authenticated."""
    invalid = HTTPException(
        status_code=400, detail="This verification link is invalid or has expired."
    )
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise invalid from None

    if payload.get("typ") != EMAIL_VERIFICATION_TOKEN_TYPE:
        raise invalid

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise invalid from None


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


def delete_account(db: Session, current_user: User) -> None:
    """Hard-deletes `current_user`'s account and everything they own
    (Story 5.3): every owned `documents` row, every owned `chat_messages`
    row (Story 3.4 -- `chat_messages.user_id` is a `NOT NULL` FK with no
    `ON DELETE CASCADE`, so skipping this step fails the `users` delete
    below with a `ForeignKeyViolation`), then the `users` row itself, plus
    their Weaviate passages and Neo4j entities/relationships. Mirrors
    `documents/service.py::delete_document`'s fixed delete order --
    Weaviate first, then Neo4j, then Postgres, one commit -- widened from
    one document's stores to every store this account owns.

    Raises `HTTPException(409)` and deletes nothing if any owned document
    is outside `DELETABLE_STATUSES` (the same guard `delete_document`
    already applies, for the same reason): a mid-ingestion background task
    could otherwise keep writing Weaviate passages or Neo4j entities for
    this user after this cascade's own store-deletes already ran,
    orphaning fresh state under a user id no longer in Postgres.

    Postgres is never committed before both external-store deletes have
    succeeded -- if either raises, the exception propagates, nothing here
    has committed, and every row (documents and the user) is untouched and
    safe to retry: `delete_passages_for_user`/`delete_entities_for_user`
    are both idempotent, so a retry after a partial failure matches zero
    additional rows for whichever store already succeeded.
    """
    documents = documents_repository.list_documents_for_user(db, current_user.id)
    for document in documents:
        if document.status not in DELETABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail="Document is still being processed and can't be deleted yet.",
            )

    user_id_str = str(current_user.id)
    delete_passages_for_user(user_id_str)
    delete_entities_for_user(user_id_str)
    documents_repository.delete_all_documents_for_user(db, current_user.id)
    chat_repository.delete_all_messages_for_user(db, current_user.id)
    repository.delete_user(db, current_user.id)
    db.commit()


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Raises one generic 401 for both "no such email" and "wrong
    password" -- this is the message that actually matters for account
    enumeration (unlike registration's necessarily-revealing 409).

    Story 1.6: once credentials check out, an unverified account is
    blocked with a 403 -- deliberately a different status than the 401
    above. By this point the caller has already proven they know the
    password, so there's no enumeration concern left to protect (unlike
    the 401 case, which must stay identical for "no such email" and
    "wrong password"); a distinct status lets the frontend show a
    "verify your email" prompt with a resend action instead of a flat
    "wrong password" message.
    """
    user = repository.get_user_by_email(db, email)
    hash_to_check = user.password_hash if user is not None else _dummy_password_hash()
    password_ok = bcrypt_sha256.verify(password, hash_to_check)
    if user is None or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if _require_email_verification() and user.email_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before logging in. We sent a link when you registered.",
        )

    return user


def _require_email_verification() -> bool:
    # Defaults to true (verified-only login) so production is safe by
    # default; the escape hatch exists for local dev without a reachable
    # mailbox and lets the existing ~80 `POST /auth/login` call sites
    # across the test suite keep passing unchanged (tests/conftest.py sets
    # this false at import time; test_auth_email_verification.py turns it
    # on explicitly where it's actually testing the gate).
    raw = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "true").strip().lower()
    return raw not in ("false", "0", "no")


def _verification_email_body(full_name: str, verify_url: str) -> str:
    return (
        f"Hi {full_name},\n\n"
        "Thanks for signing up for GraphMind. Confirm your email address "
        "by opening the link below:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in {_verification_token_expire_hours()} hours. "
        "If you didn't create a GraphMind account, you can ignore this email.\n"
    )


def send_verification_email(user_id: uuid.UUID, email: str, full_name: str) -> None:
    """Builds a verify-email link and sends it (Story 1.6).

    Takes primitives, not the ORM `User` -- this runs as a Starlette
    `BackgroundTask` scheduled from `routes.register`, after the request's
    DB session has already closed (mirrors `documents/service.py
    ::ingest_document`'s own "no request-scoped session/ORM object survives
    into the background task" rule). Swallows and logs any send failure,
    the same way `main.py`'s startup warmups do -- a mail outage must not
    turn an already-committed, successful registration into a 500 with
    nothing left to roll back; the account can still request a resend.
    """
    token = create_email_verification_token(user_id)
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    verify_url = f"{frontend_origin}/verify-email?token={token}"

    try:
        send_email(
            to=email,
            subject="Verify your GraphMind email address",
            body=_verification_email_body(full_name, verify_url),
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", email)


def verify_email(db: Session, token: str) -> User:
    """Idempotent: verifying an already-verified account still succeeds
    (a double-clicked link, or the link opened again after already
    verifying elsewhere) rather than surfacing a confusing error for
    something that isn't actually a problem."""
    user_id = decode_email_verification_token(token)
    user = repository.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=400, detail="This verification link is invalid or has expired."
        )

    if user.email_verified_at is None:
        repository.mark_email_verified(db, user)
        db.commit()
        db.refresh(user)
    return user


def resend_verification(
    email: str,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Sends a fresh verification email only if the account exists and
    isn't already verified -- but always returns normally either way.
    `routes.resend_verification` answers the exact same response body
    regardless of what happened here, so this can't be used to enumerate
    registered emails (mirrors `authenticate_user`'s own generic-401
    reasoning, applied to a route with no password to check at all).

    Runs as a `BackgroundTasks` job (mirrors `documents/service.py
    ::ingest_document`'s pattern, reused here for the same reason
    `send_verification_email` above takes primitives, not an ORM object):
    opens its own DB session via `session_factory` rather than taking the
    request's `db`, because that session is already closed by the time a
    background task runs. The explicit parameter (not just a module-level
    default) is what lets tests call this directly with a controlled
    session instead of depending on a patched global.
    """
    session_factory = session_factory or get_session_factory()
    db = session_factory()
    try:
        user = repository.get_user_by_email(db, email)
        if user is None or user.email_verified_at is not None:
            return
        send_verification_email(user.id, user.email, user.full_name)
    finally:
        db.close()
