import uuid

import pytest
from fastapi import HTTPException

from app.auth.service import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
)


def test_hash_password_round_trips():
    from passlib.hash import bcrypt_sha256

    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert bcrypt_sha256.verify("correct horse battery staple", hashed)


def test_hash_password_never_plaintext():
    hashed = hash_password("s3cret!")
    assert "s3cret!" not in hashed
    assert hashed.startswith("$bcrypt-sha256$")


def test_hash_password_handles_long_password():
    # bcrypt alone truncates at 72 bytes; bcrypt_sha256 exists specifically
    # so a long password isn't silently truncated before hashing.
    from passlib.hash import bcrypt_sha256

    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert bcrypt_sha256.verify(long_password, hashed)
    assert not bcrypt_sha256.verify("x" * 199, hashed)


def test_create_access_token_round_trips_via_decode():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_decode_access_token_rejects_garbage_string():
    with pytest.raises(HTTPException) as excinfo:
        decode_access_token("not-a-jwt")
    assert excinfo.value.status_code == 401


def test_authenticate_user_generic_error_for_missing_user(db_session):
    with pytest.raises(HTTPException) as excinfo:
        authenticate_user(db_session, "nobody@example.com", "whatever")
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid email or password."


def test_authenticate_user_generic_error_for_wrong_password(db_session):
    from app.auth.service import register_user
    from app.auth.schemas import RegisterRequest

    register_user(
        db_session,
        RegisterRequest(full_name="Maria Ivanova", email="maria@example.com", password="correct horse battery staple"),
    )

    with pytest.raises(HTTPException) as excinfo:
        authenticate_user(db_session, "maria@example.com", "wrong password")
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid email or password."
