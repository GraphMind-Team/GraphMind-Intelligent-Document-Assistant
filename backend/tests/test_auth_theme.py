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


def _register_and_login(client):
    client.post("/auth/register", json=_valid_register_payload())
    login_response = client.post("/auth/login", json=_login_payload())
    return login_response.json()["access_token"]


def test_update_theme_persists(client):
    token = _register_and_login(client)

    response = client.patch(
        "/auth/theme",
        json={"theme": "dark"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"theme": "dark"}

    # Persisted against the account, not just echoed back -- a fresh GET
    # /me reflects it too.
    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.json()["theme"] == "dark"


def test_update_theme_survives_a_fresh_login(client):
    """The literal AC3 guarantee ('survives logout/login') -- distinct from
    test_update_theme_persists, which only checks GET /me on the *same*
    session/token the PATCH was made with. A regression isolated to the
    login path's theme lookup would pass that test while breaking this
    one."""
    token = _register_and_login(client)
    client.patch("/auth/theme", json={"theme": "dark"}, headers={"Authorization": f"Bearer {token}"})

    fresh_login = client.post("/auth/login", json=_login_payload())

    assert fresh_login.status_code == 200
    assert fresh_login.json()["theme"] == "dark"


def test_update_theme_without_token_returns_401(client):
    response = client.patch("/auth/theme", json={"theme": "dark"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_update_theme_with_invalid_value_returns_422(client):
    token = _register_and_login(client)

    response = client.patch(
        "/auth/theme",
        json={"theme": "blue"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
