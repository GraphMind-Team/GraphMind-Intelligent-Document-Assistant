import uuid

import pytest

from app.auth import service as auth_service


def _valid_register_payload(**overrides):
    payload = {
        "full_name": "Maria Ivanova",
        "email": "maria@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(overrides)
    return payload


def _login_payload(**overrides):
    payload = {"email": "maria@example.com", "password": "correct horse battery staple"}
    payload.update(overrides)
    return payload


def test_login_success_returns_jwt(client):
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    # Returned directly on login (Story 5.2) so the frontend never has to
    # make a second request just to learn the account's theme.
    assert body["theme"] == "light"


def test_login_token_works_against_me(client):
    client.post("/auth/register", json=_valid_register_payload())
    login_response = client.post("/auth/login", json=_login_payload())
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "maria@example.com"
    assert body["full_name"] == "Maria Ivanova"
    assert "id" in body
    assert "created_at" in body
    assert body["theme"] == "light"
    assert "password" not in body
    assert "password_hash" not in body


def test_login_wrong_email_returns_generic_401(client):
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload(email="nobody@example.com"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_login_wrong_password_returns_generic_401(client):
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload(password="wrong password"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_login_wrong_email_and_wrong_password_give_identical_body(client):
    """The two failure modes must be indistinguishable to the caller --
    otherwise the response itself becomes an account-enumeration oracle."""
    client.post("/auth/register", json=_valid_register_payload())

    wrong_email = client.post("/auth/login", json=_login_payload(email="nobody@example.com"))
    wrong_password = client.post("/auth/login", json=_login_payload(password="wrong password"))

    assert wrong_email.status_code == wrong_password.status_code == 401
    assert wrong_email.json() == wrong_password.json()


def test_login_unaffected_by_email_verification_when_flag_off(client):
    """Story 1.6 added a REQUIRE_EMAIL_VERIFICATION gate to authenticate_user
    -- conftest.py defaults it to "false" for the whole suite specifically
    so this file's other login tests (none of which verify an account)
    keep passing unmodified. This pins that default explicitly; the gate
    itself is exercised in test_auth_email_verification.py."""
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 200


def test_login_normalizes_email_case(client):
    client.post("/auth/register", json=_valid_register_payload(email="Maria@Example.com"))

    response = client.post("/auth/login", json=_login_payload(email="maria@example.com"))

    assert response.status_code == 200


def test_me_without_token_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_with_malformed_token_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_with_wrong_secret_token_returns_401(client):
    import jwt

    from app.auth.service import JWT_ALGORITHM

    token = jwt.encode({"sub": "00000000-0000-0000-0000-000000000000"}, "a-different-secret", algorithm=JWT_ALGORITHM)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_with_valid_token_for_deleted_user_returns_401(client, db_session):
    """Covers `get_current_user`'s second failure branch: the JWT itself
    decodes fine (right secret, not expired) but the account it names no
    longer exists -- e.g. deleted after the token was issued. Every other
    /auth/me 401 test above fails earlier, at the decode step itself, so
    none of them exercise `repository.get_user_by_id` returning None."""
    client.post("/auth/register", json=_valid_register_payload())
    login_response = client.post("/auth/login", json=_login_payload())
    token = login_response.json()["access_token"]

    from app.shared.models import User

    user = db_session.query(User).filter_by(email="maria@example.com").one()
    db_session.delete(user)
    db_session.commit()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_with_expired_token_returns_401(client):
    import os
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.auth.service import JWT_ALGORITHM

    expired_payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "iat": datetime.now(timezone.utc) - timedelta(minutes=120),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=60),
    }
    # Sign with the real JWT_SECRET so this test isolates expiry as the
    # failure cause, not an incidentally-wrong signature.
    token = jwt.encode(expired_payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_login_rate_limited_after_five_attempts(client):
    client.post("/auth/register", json=_valid_register_payload())

    for _ in range(5):
        response = client.post("/auth/login", json=_login_payload(password="wrong password"))
        assert response.status_code == 401

    response = client.post("/auth/login", json=_login_payload(password="wrong password"))
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many login attempts. Try again later."}


def test_login_success_resets_rate_limit_counter(client):
    client.post("/auth/register", json=_valid_register_payload())

    for _ in range(4):
        response = client.post("/auth/login", json=_login_payload(password="wrong password"))
        assert response.status_code == 401

    success = client.post("/auth/login", json=_login_payload())
    assert success.status_code == 200

    # The successful login reset the counter, so a 6th call right after
    # (which would have been blocked without the reset) succeeds instead.
    response = client.post("/auth/login", json=_login_payload())
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Token-lifetime env parsing. `app.main._validate_env` refuses to boot on a
# non-positive value, so in a deployed process these fallbacks are
# unreachable -- they exist so the getters are correct standing alone, called
# from a test, a script, or any entry point that doesn't run that check.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "getter, var, default",
    [
        (auth_service._access_token_expire_minutes, "ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        (auth_service._verification_token_expire_hours, "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS", 24),
    ],
)
@pytest.mark.parametrize("raw", ["0", "-1", "-30", "abc", "1440m", "", "   "])
def test_an_unusable_lifetime_value_falls_back_to_the_default(
    monkeypatch, getter, var, default, raw
):
    monkeypatch.setenv(var, raw)
    assert getter() == default


@pytest.mark.parametrize(
    "getter, var",
    [
        (auth_service._access_token_expire_minutes, "ACCESS_TOKEN_EXPIRE_MINUTES"),
        (auth_service._verification_token_expire_hours, "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS"),
    ],
)
def test_a_positive_lifetime_value_is_honoured(monkeypatch, getter, var):
    monkeypatch.setenv(var, "120")
    assert getter() == 120


def test_a_zero_lifetime_does_not_mint_an_already_expired_token(monkeypatch):
    """The bug this guards: `int()` parses "0" happily, so the getters'
    original `ValueError`-only guard let it through, and the resulting
    token was rejected by `decode_access_token` the instant it was
    issued -- login answering 200 with a credential that never worked."""
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "0")
    user_id = uuid.uuid4()

    token = auth_service.create_access_token(user_id)

    assert auth_service.decode_access_token(token) == user_id
