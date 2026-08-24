"""`POST/GET /chat/sessions`, `PATCH/DELETE /chat/sessions/{session_id}`
tests (multi-session chat).

Mirrors `test_folders_routes.py`'s IDOR coverage: a cross-tenant or
nonexistent session id must come back as the same 404
`"Chat session not found."`, never a 403 that would confirm the id exists.
"""

import uuid
from datetime import timedelta


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_session(client, token):
    response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_session_returns_201_with_a_titleless_session(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-create@example.com", password="password12345"
    )

    response = client.post("/chat/sessions", headers=_auth_headers(token))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] is None
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_session_requires_authentication(client):
    response = client.post("/chat/sessions")
    assert response.status_code == 401


def test_list_sessions_is_scoped_to_the_calling_account(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="sessions-list-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="sessions-list-b@example.com", password="password-account-b"
    )
    _create_session(client, token_a)

    response_b = client.get("/chat/sessions", headers=_auth_headers(token_b))
    assert response_b.status_code == 200
    assert response_b.json() == []

    response_a = client.get("/chat/sessions", headers=_auth_headers(token_a))
    assert response_a.status_code == 200
    assert len(response_a.json()) == 1


def test_list_sessions_with_none_created_returns_empty_list(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-list-empty@example.com", password="password12345"
    )

    response = client.get("/chat/sessions", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json() == []


def test_list_sessions_orders_most_recently_active_first(client, db_session):
    """`updated_at desc` -- not creation order. `ChatSession.updated_at`
    is deliberately not ORM-`onupdate`-driven (see that model's own
    docstring) -- only `chat/sessions_repository.py::touch_session`
    (called from a live `/ask` turn) bumps it, a rename does not. Seeded
    directly here rather than mocking the RAG pipeline just to trigger a
    real turn."""
    from app.shared.models import ChatSession

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-list-order@example.com", password="password12345"
    )
    first = _create_session(client, token)
    second = _create_session(client, token)

    # Directly bump the first (chronologically older) session's
    # `updated_at` past the second's -- the one thing this test needs to
    # isolate, without depending on `touch_session`'s own auto-titling
    # side effect or a mocked `/ask` round trip.
    first_row = db_session.get(ChatSession, uuid.UUID(first["id"]))
    second_row = db_session.get(ChatSession, uuid.UUID(second["id"]))
    first_row.updated_at = second_row.updated_at + timedelta(seconds=1)
    db_session.commit()

    response = client.get("/chat/sessions", headers=_auth_headers(token))

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids == [first["id"], second["id"]]


def test_rename_session_sets_the_title(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-rename@example.com", password="password12345"
    )
    session = _create_session(client, token)

    response = client.patch(
        f"/chat/sessions/{session['id']}", headers=_auth_headers(token), json={"title": "Refund policy"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Refund policy"
    assert body["id"] == session["id"]


def test_rename_session_with_empty_title_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-rename-empty@example.com", password="password12345"
    )
    session = _create_session(client, token)

    response = client.patch(
        f"/chat/sessions/{session['id']}", headers=_auth_headers(token), json={"title": ""}
    )

    assert response.status_code == 422


def test_rename_session_with_whitespace_only_title_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-rename-ws@example.com", password="password12345"
    )
    session = _create_session(client, token)

    response = client.patch(
        f"/chat/sessions/{session['id']}", headers=_auth_headers(token), json={"title": "   "}
    )

    assert response.status_code == 400
    assert "blank" in response.json()["detail"].lower()


def test_rename_session_with_title_over_255_chars_is_422(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-rename-long@example.com", password="password12345"
    )
    session = _create_session(client, token)

    response = client.patch(
        f"/chat/sessions/{session['id']}", headers=_auth_headers(token), json={"title": "x" * 256}
    )

    assert response.status_code == 422


def test_rename_another_accounts_session_is_404_not_403(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="sessions-rename-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="sessions-rename-b@example.com", password="password-account-b"
    )
    session_a = _create_session(client, token_a)

    response = client.patch(
        f"/chat/sessions/{session_a['id']}", headers=_auth_headers(token_b), json={"title": "Hijacked"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat session not found."}


def test_rename_unknown_session_is_the_same_404_as_cross_tenant(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="sessions-rename-unknown-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="sessions-rename-unknown-b@example.com", password="password-account-b"
    )
    session_a = _create_session(client, token_a)

    cross_tenant = client.patch(
        f"/chat/sessions/{session_a['id']}", headers=_auth_headers(token_b), json={"title": "x"}
    )
    unknown = client.patch(
        f"/chat/sessions/{uuid.uuid4()}", headers=_auth_headers(token_b), json={"title": "x"}
    )

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_delete_session_returns_204_and_removes_it(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-delete@example.com", password="password12345"
    )
    session = _create_session(client, token)

    response = client.delete(f"/chat/sessions/{session['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert response.content == b""

    listing = client.get("/chat/sessions", headers=_auth_headers(token))
    assert listing.json() == []


def test_delete_session_also_removes_its_messages(client, db_session):
    """`chat_messages.session_id` has no `ON DELETE CASCADE` (this
    project's "cleanup is app code's job" convention) --
    `sessions_repository.delete_session_for_user` must delete the
    session's messages itself before the session row, or this would fail
    with a live-Postgres `ForeignKeyViolation` (the SQLite test DB
    doesn't enforce the FK, so this needs its own explicit row-count
    assertion rather than relying on the DB to catch a regression)."""
    from app.shared.models import ChatMessage

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-delete-messages@example.com", password="password12345"
    )
    session = _create_session(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    session_id = uuid.UUID(session["id"])
    db_session.add(ChatMessage(user_id=user_id, session_id=session_id, role="user", question="A question?"))
    db_session.add(
        ChatMessage(
            user_id=user_id, session_id=session_id, role="assistant", segments=[{"text": "An answer.", "citations": []}]
        )
    )
    db_session.commit()

    response = client.delete(f"/chat/sessions/{session['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert db_session.query(ChatMessage).filter(ChatMessage.session_id == session_id).count() == 0


def test_delete_another_accounts_session_is_404_not_403(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="sessions-delete-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="sessions-delete-b@example.com", password="password-account-b"
    )
    session_a = _create_session(client, token_a)

    response = client.delete(f"/chat/sessions/{session_a['id']}", headers=_auth_headers(token_b))

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat session not found."}

    listing_a = client.get("/chat/sessions", headers=_auth_headers(token_a))
    assert len(listing_a.json()) == 1


def test_delete_unknown_session_is_the_same_404_as_cross_tenant(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="sessions-delete-unknown-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="sessions-delete-unknown-b@example.com", password="password-account-b"
    )
    session_a = _create_session(client, token_a)

    cross_tenant = client.delete(f"/chat/sessions/{session_a['id']}", headers=_auth_headers(token_b))
    unknown = client.delete(f"/chat/sessions/{uuid.uuid4()}", headers=_auth_headers(token_b))

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_delete_session_requires_authentication(client):
    response = client.delete(f"/chat/sessions/{uuid.uuid4()}")
    assert response.status_code == 401


def test_session_malformed_id_is_422(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-malformed@example.com", password="password12345"
    )

    response = client.patch(
        "/chat/sessions/not-a-uuid", headers=_auth_headers(token), json={"title": "x"}
    )

    assert response.status_code == 422


def test_ask_auto_titles_a_titleless_session_from_the_first_question(client, monkeypatch):
    """Multi-session chat's auto-titling (decision #3): a session's title
    is set from its first question's text once that question is asked --
    never from `POST /chat/sessions` itself, which always starts a
    session titleless."""
    from app.chat import service as chat_service_module

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-autotitle@example.com", password="password12345"
    )
    session = _create_session(client, token)
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    ask_response = client.post(
        f"/chat/sessions/{session['id']}/ask",
        headers=_auth_headers(token),
        json={"question": "What is the refund window for annual plans?"},
    )
    assert ask_response.status_code == 200, ask_response.text

    listing = client.get("/chat/sessions", headers=_auth_headers(token))
    assert listing.json()[0]["title"] == "What is the refund window for annual plans?"


def test_ask_does_not_overwrite_an_already_titled_session(client, monkeypatch):
    """A user's own rename (or an earlier auto-title) must stick --
    `sessions_repository.touch_session` only ever sets `title` while it's
    still `None`, so a second question in the same session never
    overwrites it."""
    from app.chat import service as chat_service_module

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-autotitle-2@example.com", password="password12345"
    )
    session = _create_session(client, token)
    rename = client.patch(
        f"/chat/sessions/{session['id']}", headers=_auth_headers(token), json={"title": "My own title"}
    )
    assert rename.status_code == 200, rename.text
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    ask_response = client.post(
        f"/chat/sessions/{session['id']}/ask",
        headers=_auth_headers(token),
        json={"question": "A question that must not become the title"},
    )
    assert ask_response.status_code == 200, ask_response.text

    listing = client.get("/chat/sessions", headers=_auth_headers(token))
    assert listing.json()[0]["title"] == "My own title"


def test_ask_truncates_a_long_question_to_eighty_characters_for_the_title(client, monkeypatch):
    from app.chat import service as chat_service_module

    token = _register_and_login(
        client, full_name="Maria Ivanova", email="sessions-autotitle-long@example.com", password="password12345"
    )
    session = _create_session(client, token)
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])
    long_question = "x" * 200

    ask_response = client.post(
        f"/chat/sessions/{session['id']}/ask", headers=_auth_headers(token), json={"question": long_question}
    )
    assert ask_response.status_code == 200, ask_response.text

    listing = client.get("/chat/sessions", headers=_auth_headers(token))
    assert listing.json()[0]["title"] == "x" * 80
