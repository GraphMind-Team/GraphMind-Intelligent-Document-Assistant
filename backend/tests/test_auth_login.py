import pytest


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


@pytest.fixture(autouse=True)
def _fresh_rate_limiter(client):
    """Overrides the module-level rate limiter singleton with a fresh
    instance per test, so attempt counts from one test never leak into the
    next. Depends on `client` (not standalone) so it composes correctly
    with conftest.py's `client` fixture, which clears
    `app.dependency_overrides` in its own `finally` block on teardown."""
    from app.auth.rate_limiter import LoginRateLimiter, get_login_rate_limiter
    from app.main import app

    limiter = LoginRateLimiter(max_attempts=5, window_seconds=60.0)
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.pop(get_login_rate_limiter, None)


def test_login_success_returns_jwt(client):
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


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


def test_login_rate_limited_after_five_attempts(client, _fresh_rate_limiter):
    client.post("/auth/register", json=_valid_register_payload())

    for _ in range(5):
        response = client.post("/auth/login", json=_login_payload(password="wrong password"))
        assert response.status_code == 401

    response = client.post("/auth/login", json=_login_payload(password="wrong password"))
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many login attempts. Try again later."}


def test_login_success_resets_rate_limit_counter(client, _fresh_rate_limiter):
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
