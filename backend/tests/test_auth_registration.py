def _valid_payload(**overrides):
    payload = {
        "full_name": "Maria Ivanova",
        "email": "maria@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(overrides)
    return payload


def test_register_success(client):
    response = client.post("/auth/register", json=_valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Maria Ivanova"
    assert body["email"] == "maria@example.com"
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_email_returns_409(client):
    client.post("/auth/register", json=_valid_payload())
    response = client.post("/auth/register", json=_valid_payload(full_name="Someone Else"))

    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists."}


def test_register_duplicate_email_case_insensitive(client):
    client.post("/auth/register", json=_valid_payload(email="Maria@Example.com"))
    response = client.post("/auth/register", json=_valid_payload(email="maria@example.com"))

    assert response.status_code == 409


def test_register_rejects_blank_full_name(client):
    response = client.post("/auth/register", json=_valid_payload(full_name="   "))
    assert response.status_code == 422


def test_register_rejects_invalid_email(client):
    response = client.post("/auth/register", json=_valid_payload(email="not-an-email"))
    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post("/auth/register", json=_valid_payload(password="short"))
    assert response.status_code == 422


def test_register_rejects_overlong_password(client):
    response = client.post("/auth/register", json=_valid_payload(password="x" * 129))
    assert response.status_code == 422


def test_register_stores_hashed_password_not_plaintext(client, db_session):
    payload = _valid_payload(password="correct horse battery staple")
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201

    from app.shared.models import User

    user = db_session.query(User).filter_by(email=payload["email"]).one()
    assert user.password_hash != payload["password"]
    assert user.password_hash.startswith("$bcrypt-sha256$")


def test_register_rate_limited_after_five_attempts(client):
    """Per-IP, not per-email -- unlike login, a 6th *distinct*-email attempt
    from the same source is still blocked, since the attack this guards
    against (enumeration via 409 vs. 201, or mass account creation) is one
    source rotating emails, not one source retrying the same email."""
    for i in range(5):
        response = client.post("/auth/register", json=_valid_payload(email=f"user{i}@example.com"))
        assert response.status_code == 201

    response = client.post("/auth/register", json=_valid_payload(email="user5@example.com"))
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many registration attempts. Try again later."}


def test_register_integrity_error_race_returns_409(client, monkeypatch):
    """Simulates the TOCTOU race the defense-in-depth code exists for: the
    pre-check says "no such user" even though the DB already has one, so
    the DB-level unique constraint must be what actually catches it."""
    client.post("/auth/register", json=_valid_payload())

    from app.auth import repository

    monkeypatch.setattr(repository, "get_user_by_email", lambda db, email: None)

    response = client.post("/auth/register", json=_valid_payload(full_name="Racer"))
    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists."}
