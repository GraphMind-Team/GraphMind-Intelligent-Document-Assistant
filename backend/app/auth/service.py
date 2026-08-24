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
from app.chat import sessions_repository as chat_sessions_repository
from app.documents import repository as documents_repository
from app.folders import repository as folders_repository
from app.shared.data_access.session import get_session_factory
from app.shared.email import send_email
from app.shared.email.templates import REQUIRED_COPY_KEYS, verification_email_html
from app.shared.i18n.catalogs import DEFAULT_LANGUAGE, t
from app.shared.i18n.errors import localized_error
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


def register_user(db: Session, data: RegisterRequest, *, language: str = DEFAULT_LANGUAGE) -> User:
    # data.email is already stripped+lowercased by RegisterRequest's
    # validator, so this and any other consumer of the schema agree on the
    # same casing. `language` is the registration request's resolved
    # Accept-Language (routes.register), used both for the new account's
    # initial `User.language` (so its first verification email and Settings
    # default already match the browser) and for this 409's own detail text.
    existing = repository.get_user_by_email(db, data.email)
    if existing is not None:
        if existing.email_verified_at is not None:
            raise localized_error(409, "error.email_exists", language)

        # Story 1.6: an *unverified* row is exactly the problem this story
        # exists to fix -- nobody has ever proven they control that inbox,
        # so treating it as a permanently claimed account would let a
        # typo'd or malicious registration lock the real owner out of
        # their own address forever (a 409 with no recourse). Instead,
        # reclaim it in place: overwrite the name/password with this
        # registration's own values and leave `email_verified_at` NULL
        # (unchanged) -- whoever next proves control of the inbox by
        # clicking a verify link (this one, sent below, or an older one
        # for the same user id -- both still work, since neither is
        # single-use-tracked beyond `email_verified_at` itself) is the one
        # who actually gets the account, which is the same guarantee a
        # brand-new registration gives. `created_at` is deliberately left
        # untouched -- this is the same row, not a new account.
        user = repository.update_user_profile(db, existing, data.full_name)
        user = repository.update_user_password(db, user, hash_password(data.password))
        user = repository.update_user_language(db, user, language)
        db.commit()
        db.refresh(user)
        return user

    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        language=language,
    )

    try:
        user = repository.create_user(db, user)
        db.commit()
    except IntegrityError:
        # Defense-in-depth against a concurrent registration racing the
        # pre-check above -- the DB-level unique constraint on email caught
        # what the pre-check missed. Only reachable for a genuinely new
        # email now (the existing-row branch above already handles the
        # "someone else got there first, but it's unverified" case without
        # touching the insert path at all).
        db.rollback()
        raise localized_error(409, "error.email_exists", language) from None

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


def update_language(db: Session, user: User, language: str) -> None:
    repository.update_user_language(db, user, language)
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
        raise localized_error(400, "error.current_password_incorrect", user.language)

    new_hash = hash_password(data.new_password)
    repository.update_user_password(db, user, new_hash)
    db.commit()


def delete_account(db: Session, current_user: User) -> None:
    """Hard-deletes `current_user`'s account and everything they own
    (Story 5.3): every owned `documents` row, every owned `chat_messages`
    row (Story 3.4 -- `chat_messages.user_id` is a `NOT NULL` FK with no
    `ON DELETE CASCADE`, so skipping this step fails the `users` delete
    below with a `ForeignKeyViolation`), every owned `chat_sessions` row
    (multi-session chat -- `ChatSession.user_id` is the identical kind of
    FK, for the identical reason; must run *after* the `chat_messages`
    delete above, since `chat_messages.session_id` is itself a `NOT NULL`
    FK into `chat_sessions.id` with no cascade either), every owned
    `folders` row (folder-grouping feature -- `Folder.user_id` is the
    identical kind of FK, for the identical reason; `documents.folder_id`
    itself needs no separate cleanup here, since it's already gone along
    with the `documents` rows above), then the `users` row itself, plus
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
            raise localized_error(409, "error.document_still_processing", current_user.language)

    user_id_str = str(current_user.id)
    delete_passages_for_user(user_id_str)
    delete_entities_for_user(user_id_str)
    documents_repository.delete_all_documents_for_user(db, current_user.id)
    chat_repository.delete_all_messages_for_user(db, current_user.id)
    chat_sessions_repository.delete_all_sessions_for_user(db, current_user.id)
    folders_repository.delete_all_folders_for_user(db, current_user.id)
    repository.delete_user(db, current_user.id)
    db.commit()


def authenticate_user(db: Session, email: str, password: str, *, language: str = DEFAULT_LANGUAGE) -> User:
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
        raise localized_error(401, "error.invalid_credentials", language)

    if _require_email_verification() and user.email_verified_at is None:
        # `user.language` (not the request's `language`) once the account is
        # known to exist -- an unverified account's own saved preference is
        # a better guess than the login request's Accept-Language, which may
        # be a different device/browser than the one that registered it.
        raise localized_error(403, "error.email_not_verified", user.language)

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


def _verification_email_body(full_name: str, verify_url: str, language: str) -> str:
    return t(
        "verify_email.body",
        language,
        full_name=full_name,
        verify_url=verify_url,
        expire_hours=_verification_token_expire_hours(),
    )


def _verification_email_html(
    full_name: str, verify_url: str, language: str, frontend_origin: str
) -> str:
    """The HTML alternative for the same message `_verification_email_body`
    renders as plain text -- see `shared/email/templates.py` for the layout
    itself; this just gathers the translated copy it needs.

    The copy keys come from that module's own `REQUIRED_COPY_KEYS` rather
    than being listed again here, so adding a section to the template can't
    leave this function silently passing an incomplete mapping. Both format
    arguments are passed to every key: none of the other strings contain
    braces, so the extra kwargs are harmless.

    `robot_src` points at the deployed frontend's static asset:
    `frontend_origin` is already the one publicly reachable origin this
    function has on hand (it's how `verify_url` itself is built), and a
    data: URI big enough to draw the mascot risks the whole message being
    clipped or spam-flagged by clients that cap inline-image size. It must
    stay a **PNG** -- Gmail and Outlook refuse to render `<img>` pointing
    at an SVG, which is what broke the first version of this email.
    """
    copy = {
        key: t(
            f"verify_email.{key}",
            language,
            full_name=full_name,
            expire_hours=_verification_token_expire_hours(),
        )
        for key in REQUIRED_COPY_KEYS
    }
    return verification_email_html(
        verify_url=verify_url,
        robot_src=f"{frontend_origin}/email-robot.png",
        copy=copy,
    )


def send_verification_email(
    user_id: uuid.UUID, email: str, full_name: str, language: str = DEFAULT_LANGUAGE
) -> None:
    """Builds a verify-email link and sends it (Story 1.6).

    Takes primitives, not the ORM `User` -- this runs as a Starlette
    `BackgroundTask` scheduled from `routes.register`, after the request's
    DB session has already closed (mirrors `documents/service.py
    ::ingest_document`'s own "no request-scoped session/ORM object survives
    into the background task" rule). Swallows and logs any send failure,
    the same way `main.py`'s startup warmups do -- a mail outage must not
    turn an already-committed, successful registration into a 500 with
    nothing left to roll back; the account can still request a resend.

    `language` defaults to English for callers that don't have a resolved
    one on hand, but both real callers pass an explicit value: `routes
    .register` passes the registration request's resolved Accept-Language
    (the new account has no saved preference yet), `resend_verification`
    below passes the already-registered `user.language`.
    """
    token = create_email_verification_token(user_id)
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    verify_url = f"{frontend_origin}/verify-email?token={token}"

    try:
        send_email(
            to=email,
            subject=t("verify_email.subject", language),
            body=_verification_email_body(full_name, verify_url, language),
            html_body=_verification_email_html(full_name, verify_url, language, frontend_origin),
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
        raise localized_error(400, "error.invalid_verification_link", DEFAULT_LANGUAGE)

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
        send_verification_email(user.id, user.email, user.full_name, user.language)
    finally:
        db.close()
