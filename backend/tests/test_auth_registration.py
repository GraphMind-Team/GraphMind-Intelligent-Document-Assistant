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
