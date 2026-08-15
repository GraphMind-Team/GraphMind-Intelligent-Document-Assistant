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


def _register_and_login(client, **overrides):
    client.post("/auth/register", json=_valid_register_payload(**overrides))
    login_response = client.post("/auth/login", json=_login_payload(**overrides))
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_update_profile_happy_path_persists_full_name(client):
    headers = _register_and_login(client)

    response = client.patch("/auth/me", json={"full_name": "Maria Petrova"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["full_name"] == "Maria Petrova"

    me_response = client.get("/auth/me", headers=headers)
    assert me_response.json()["full_name"] == "Maria Petrova"


def test_update_profile_blank_full_name_returns_422(client):
    headers = _register_and_login(client)

    response = client.patch("/auth/me", json={"full_name": ""}, headers=headers)

    assert response.status_code == 422


def test_update_profile_whitespace_only_full_name_returns_422(client):
    headers = _register_and_login(client)

    response = client.patch("/auth/me", json={"full_name": "   "}, headers=headers)

    assert response.status_code == 422


def test_update_profile_without_token_returns_401(client):
    response = client.patch("/auth/me", json={"full_name": "Someone"})
    assert response.status_code == 401


def test_change_password_happy_path(client):
    headers = _register_and_login(client)

    response = client.post(
        "/auth/me/password",
        json={"current_password": "correct horse battery staple", "new_password": "new secure password"},
        headers=headers,
    )

    assert response.status_code == 200

    # Old password no longer works.
    old_login = client.post("/auth/login", json=_login_payload())
    assert old_login.status_code == 401

    # New password works.
    new_login = client.post(
        "/auth/login", json=_login_payload(password="new secure password")
    )
    assert new_login.status_code == 200


def test_change_password_wrong_current_password_returns_400(client):
    headers = _register_and_login(client)

    response = client.post(
        "/auth/me/password",
        json={"current_password": "not the right password", "new_password": "new secure password"},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Current password is incorrect."}

    # Password unchanged -- original still logs in.
    login_response = client.post("/auth/login", json=_login_payload())
    assert login_response.status_code == 200


def test_change_password_too_short_new_password_returns_422(client):
    headers = _register_and_login(client)

    response = client.post(
        "/auth/me/password",
        json={"current_password": "correct horse battery staple", "new_password": "short1"},
        headers=headers,
    )

    assert response.status_code == 422

    # Password unchanged -- original still logs in.
    login_response = client.post("/auth/login", json=_login_payload())
    assert login_response.status_code == 200


def test_change_password_without_token_returns_401(client):
    response = client.post(
        "/auth/me/password",
        json={"current_password": "x", "new_password": "new secure password"},
    )
    assert response.status_code == 401


def test_change_password_rate_limited_after_five_attempts(client):
    """A stolen-but-valid access token shouldn't be able to grind
    current_password with unlimited guesses -- mirrors
    test_login_rate_limited_after_five_attempts, but keyed by user id
    (not IP) since the caller here is already authenticated."""
    headers = _register_and_login(client)

    for _ in range(5):
        response = client.post(
            "/auth/me/password",
            json={"current_password": "wrong password", "new_password": "new secure password"},
            headers=headers,
        )
        assert response.status_code == 400

    response = client.post(
        "/auth/me/password",
        json={"current_password": "wrong password", "new_password": "new secure password"},
        headers=headers,
    )
    assert response.status_code == 429
    assert response.json() == {"detail": "Too many password change attempts. Try again later."}

    # The real password still works -- the account itself wasn't locked out.
    login_response = client.post("/auth/login", json=_login_payload())
    assert login_response.status_code == 200


def test_change_password_rate_limit_is_per_user(client):
    """One account exhausting its budget doesn't block a different
    account's own change-password attempts -- the limiter is keyed by
    user id, not shared globally."""
    headers_a = _register_and_login(client)
    headers_b = _register_and_login(
        client, full_name="Second User", email="second@example.com"
    )

    for _ in range(5):
        response = client.post(
            "/auth/me/password",
            json={"current_password": "wrong password", "new_password": "new secure password"},
            headers=headers_a,
        )
        assert response.status_code == 400

    blocked = client.post(
        "/auth/me/password",
        json={"current_password": "wrong password", "new_password": "new secure password"},
        headers=headers_a,
    )
    assert blocked.status_code == 429

    # A different user, unaffected.
    other = client.post(
        "/auth/me/password",
        json={
            "current_password": "correct horse battery staple",
            "new_password": "new secure password",
        },
        headers=headers_b,
    )
    assert other.status_code == 200
