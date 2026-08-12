"""Tenancy-isolation test (Story 1.5, SM-3).

Proves the guarantee `get_current_user` (backend/app/auth/dependencies.py)
is supposed to provide: `user_id` is resolved only from the caller's own
JWT, never from anything client-supplied. `/auth/me` is the only
authenticated endpoint that exists as of this story (documents/chat/kg
routers are still stubs with no endpoints -- see backend/app/{documents,
chat,kg}/routes.py), so it stands in for "every current authenticated
endpoint" per the spec's I/O matrix.
"""


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def test_me_returns_only_the_calling_account_own_data(client):
    """Two real accounts; account B's token must never surface account A's
    profile data, and the identity used is always the one baked into B's
    own JWT."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b@example.com", password="password-account-b"
    )

    response_a = client.get("/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    response_b = client.get("/auth/me", headers={"Authorization": f"Bearer {token_b}"})

    assert response_a.status_code == response_b.status_code == 200
    body_a, body_b = response_a.json(), response_b.json()

    # Each account sees only its own identity.
    assert body_a["email"] == "account-a@example.com"
    assert body_b["email"] == "account-b@example.com"
    assert body_a["id"] != body_b["id"]

    # Account B's response contains no trace of account A's data.
    assert body_b["email"] != body_a["email"]
    assert body_b["full_name"] != body_a["full_name"]
    assert body_b["id"] != body_a["id"]


def test_me_ignores_any_client_supplied_identity(client):
    """`/auth/me` takes no request body/query param at all, so there is no
    field for a caller to smuggle a different user_id into -- the response
    always comes from the token alone. This test pins that down: even
    when account B's request carries account A's id as a query param
    (something a naive future endpoint might accidentally read), the
    response is still resolved purely from B's JWT."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a2@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b2@example.com", password="password-account-b"
    )
    user_a_id = client.get("/auth/me", headers={"Authorization": f"Bearer {token_a}"}).json()["id"]

    # Account B's request tries to smuggle account A's id in as a query
    # param; the endpoint has no such parameter, so this proves it is
    # simply ignored rather than accidentally honored.
    response = client.get(
        f"/auth/me?user_id={user_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "account-b2@example.com"
    assert body["id"] != user_a_id
