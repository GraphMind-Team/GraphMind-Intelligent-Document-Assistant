"""Story 1.6: registration schedules a verification email, login is
blocked for an unverified account when REQUIRE_EMAIL_VERIFICATION is on,
POST /auth/verify-email flips the account to verified, and
POST /auth/resend-verification never reveals whether an email exists.

`REQUIRE_EMAIL_VERIFICATION` defaults to "false" for the whole suite (see
conftest.py) so every other test file's existing `POST /auth/login` calls
keep passing unmodified -- tests here that actually exercise the gate
monkeypatch it to "true" explicitly.
"""

import re

import jwt


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


def _extract_token(mock_send_email) -> str:
    """Pulls the verify-email JWT out of the body passed to the stubbed
    `send_email` (see conftest.py's autouse `_stub_outbound_email`) --
    the same link a real recipient would click."""
    body = mock_send_email.call_args.kwargs["body"]
    match = re.search(r"/verify-email\?token=([^\s]+)", body)
    assert match, f"no verify-email link found in email body: {body!r}"
    return match.group(1)


def test_register_schedules_one_verification_email(client, _stub_outbound_email):
    response = client.post("/auth/register", json=_valid_register_payload())

    assert response.status_code == 201
    assert _stub_outbound_email.call_count == 1
    kwargs = _stub_outbound_email.call_args.kwargs
    assert kwargs["to"] == "maria@example.com"
    assert "/verify-email?token=" in kwargs["body"]


def test_login_blocked_when_unverified_and_required(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Please verify your email address before logging in. We sent a link when you registered."
    }


def test_login_unverified_succeeds_when_verification_not_required(client):
    """Pins the default (flag off) suite-wide path: registering and
    immediately logging in, with no verify step in between, still works
    -- the behavior every other test file already depends on."""
    client.post("/auth/register", json=_valid_register_payload())

    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 200


def test_verify_email_then_login_succeeds(client, monkeypatch, _stub_outbound_email):
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    client.post("/auth/register", json=_valid_register_payload())
    token = _extract_token(_stub_outbound_email)

    verify_response = client.post("/auth/verify-email", json={"token": token})
    assert verify_response.status_code == 200
    assert verify_response.json() == {"detail": "Email verified."}

    login_response = client.post("/auth/login", json=_login_payload())
    assert login_response.status_code == 200


def test_me_reports_email_verified(client, monkeypatch, _stub_outbound_email):
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    client.post("/auth/register", json=_valid_register_payload())
    token = _extract_token(_stub_outbound_email)

    # Verification happens before REQUIRE_EMAIL_VERIFICATION would even
    # block login, so drop the flag back off just to obtain a token via
    # /auth/me without entangling this test with the login gate itself.
    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    login_response = client.post("/auth/login", json=_login_payload())
    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    before = client.get("/auth/me", headers=headers)
    assert before.json()["email_verified"] is False

    client.post("/auth/verify-email", json={"token": token})

    after = client.get("/auth/me", headers=headers)
    assert after.json()["email_verified"] is True


def test_verify_email_is_idempotent(client, _stub_outbound_email):
    client.post("/auth/register", json=_valid_register_payload())
    token = _extract_token(_stub_outbound_email)

    first = client.post("/auth/verify-email", json={"token": token})
    second = client.post("/auth/verify-email", json={"token": token})

    assert first.status_code == second.status_code == 200


def test_verify_email_garbage_token_returns_400(client):
    response = client.post("/auth/verify-email", json={"token": "not-a-jwt"})

    assert response.status_code == 400
    assert response.json() == {"detail": "This verification link is invalid or has expired."}


def test_verify_email_expired_token_returns_400(client, db_session):
    import os
    from datetime import datetime, timedelta, timezone

    from app.auth.service import JWT_ALGORITHM
    from app.shared.models import User

    client.post("/auth/register", json=_valid_register_payload())
    user = db_session.query(User).filter_by(email="maria@example.com").one()

    expired_payload = {
        "sub": str(user.id),
        "iat": datetime.now(timezone.utc) - timedelta(hours=48),
        "exp": datetime.now(timezone.utc) - timedelta(hours=24),
        "typ": "email_verify",
    }
    token = jwt.encode(expired_payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)

    response = client.post("/auth/verify-email", json={"token": token})

    assert response.status_code == 400
    assert response.json() == {"detail": "This verification link is invalid or has expired."}


def test_verify_email_rejects_an_access_token(client):
    """An access token (no `typ` claim) must not double as a verification
    token, even though both are signed with the same JWT_SECRET."""
    register_response = client.post("/auth/register", json=_valid_register_payload())
    login_response = client.post("/auth/login", json=_login_payload())
    access_token = login_response.json()["access_token"]

    response = client.post("/auth/verify-email", json={"token": access_token})

    assert response.status_code == 400
    assert response.json() == {"detail": "This verification link is invalid or has expired."}
    assert register_response.status_code == 201  # sanity: registration itself succeeded


def test_me_rejects_a_verification_token(client, db_session):
    """The reverse cross-use guard: a verify-email token must not work as
    a bearer token against a protected route."""
    from app.auth.service import create_email_verification_token
    from app.shared.models import User

    client.post("/auth/register", json=_valid_register_payload())
    user = db_session.query(User).filter_by(email="maria@example.com").one()
    verification_token = create_email_verification_token(user.id)

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {verification_token}"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_resend_verification_returns_same_body_for_unknown_email(client):
    response = client.post("/auth/resend-verification", json={"email": "nobody@example.com"})

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If that account exists and isn't verified yet, we've sent a new link."
    }


def test_resend_verification_returns_same_body_for_unverified_email(client, _stub_outbound_email):
    client.post("/auth/register", json=_valid_register_payload())
    _stub_outbound_email.reset_mock()

    response = client.post("/auth/resend-verification", json={"email": "maria@example.com"})

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If that account exists and isn't verified yet, we've sent a new link."
    }
    assert _stub_outbound_email.call_count == 1


def test_resend_verification_returns_same_body_for_already_verified_email(client, _stub_outbound_email):
    client.post("/auth/register", json=_valid_register_payload())
    token = _extract_token(_stub_outbound_email)
    client.post("/auth/verify-email", json={"token": token})
    _stub_outbound_email.reset_mock()

    response = client.post("/auth/resend-verification", json={"email": "maria@example.com"})

    assert response.status_code == 202
    assert response.json() == {
        "detail": "If that account exists and isn't verified yet, we've sent a new link."
    }
    # Already verified -- no email actually sent, but the response is
    # identical to the unverified/unknown cases above either way.
    assert _stub_outbound_email.call_count == 0


def test_resend_verification_rate_limited_after_five_attempts(client):
    for _ in range(5):
        response = client.post("/auth/resend-verification", json={"email": "maria@example.com"})
        assert response.status_code == 202

    response = client.post("/auth/resend-verification", json={"email": "maria@example.com"})
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many verification email requests. Try again later."}


def test_resend_verification_ip_rate_limited_across_rotating_emails(client):
    """The (IP, email) pair limiter alone caps spam against one victim's
    inbox, but puts no ceiling on a single source rotating through many
    different target emails -- each gets its own fresh 5/window budget
    under the pair key. This pins the second, IP-only limiter that closes
    that gap: 20 requests from the same client, each for a distinct email
    (so the pair limiter never itself fires), still trips a 429."""
    for i in range(20):
        response = client.post(
            "/auth/resend-verification", json={"email": f"rotating-{i}@example.com"}
        )
        assert response.status_code == 202

    response = client.post("/auth/resend-verification", json={"email": "rotating-20@example.com"})
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many verification email requests. Try again later."}


def test_register_on_unverified_email_reclaims_the_account(client, db_session, _stub_outbound_email):
    """An unverified row is a placeholder nobody has proven control of yet
    -- a second registration attempt against the same address (a typo'd
    original, a malicious squat, or just the real owner trying again)
    updates the existing row's name/password in place rather than
    permanently locking the address behind a 409 no one can ever clear."""
    first = client.post(
        "/auth/register",
        json=_valid_register_payload(full_name="Wrong Person", password="original-password-123"),
    )
    assert first.status_code == 201
    first_id = first.json()["id"]
    first_created_at = first.json()["created_at"]

    second = client.post(
        "/auth/register",
        json=_valid_register_payload(full_name="Maria Ivanova", password="my-actual-password-456"),
    )

    assert second.status_code == 201
    assert second.json()["id"] == first_id  # same row, reclaimed -- not a new account
    assert second.json()["created_at"] == first_created_at
    assert second.json()["full_name"] == "Maria Ivanova"

    from app.shared.models import User

    row = db_session.query(User).filter_by(email="maria@example.com").one()
    assert row.email_verified_at is None
    # A second verification email was sent for the reclaimed registration.
    assert _stub_outbound_email.call_count == 2

    # The old password no longer works; the new one does.
    old_login = client.post("/auth/login", json=_login_payload(password="original-password-123"))
    assert old_login.status_code == 401

    new_login = client.post("/auth/login", json=_login_payload(password="my-actual-password-456"))
    assert new_login.status_code == 200


def test_register_on_verified_email_still_returns_409(client, db_session):
    """The reclaim behavior above only applies while the row is
    unverified -- once a real owner has proven control of the inbox, the
    address is genuinely taken and register must still refuse it."""
    from app.shared.models import User

    client.post("/auth/register", json=_valid_register_payload())
    user = db_session.query(User).filter_by(email="maria@example.com").one()
    user.email_verified_at = user.created_at
    db_session.commit()

    response = client.post("/auth/register", json=_valid_register_payload(full_name="Someone Else"))

    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists."}


def test_login_succeeds_for_backfilled_verified_at(client, db_session, monkeypatch):
    """Mirrors the migration's backfill shape (`email_verified_at` set to
    `created_at` for every pre-1.6 row) -- confirms such an account isn't
    blocked once the flag is on."""
    from app.shared.models import User

    client.post("/auth/register", json=_valid_register_payload())
    user = db_session.query(User).filter_by(email="maria@example.com").one()
    user.email_verified_at = user.created_at
    db_session.commit()

    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "true")
    response = client.post("/auth/login", json=_login_payload())

    assert response.status_code == 200
