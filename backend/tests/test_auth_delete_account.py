"""`DELETE /auth/me` tests (Story 5.3).

Mirrors `test_documents_delete.py`'s conventions: `delete_passages_for_user`
and `delete_entities_for_user` are both monkeypatched to a `Mock` here (no
test Weaviate/Neo4j instance in this environment) -- what's pinned down
instead is that each is called with the right `user_id`, that both run
*before* the `users`/`documents` rows are gone (so a store failure never
leaves an orphaned account with wiped external state but a surviving
Postgres row, or vice versa), and the I/O matrix's edge cases (zero
documents, N deletable documents, a mid-ingestion 409, unauthenticated,
double-submit).
"""

import uuid
from unittest.mock import Mock

import pytest

from app.auth import repository as auth_repository
from app.shared.models import ChatMessage, Document, User


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


def _upload(
    client, token, filename="report.pdf", content_type="application/pdf", content=b"%PDF-1.4 fake pdf bytes"
):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mark_ready(db_session, document_id):
    """Flips a freshly-uploaded (`Uploaded`) row to `Ready` directly on the
    row -- `_stub_ingestion_pipeline` (conftest.py, autouse) no-ops the real
    background pipeline, so a test that needs a *deletable* document has to
    make that transition itself rather than waiting on ingestion that will
    never run. Mirrors `test_documents_delete.py`'s own helper."""
    row = db_session.get(Document, uuid.UUID(document_id))
    row.status = "Ready"
    db_session.commit()
    return row


@pytest.fixture(autouse=True)
def _stub_weaviate_delete(monkeypatch):
    """Replaces `service.delete_passages_for_user` with a `Mock` for every
    test in this file -- see the module docstring for why."""
    import app.auth.service as service_module

    fake_delete_passages = Mock()
    monkeypatch.setattr(service_module, "delete_passages_for_user", fake_delete_passages)
    return fake_delete_passages


@pytest.fixture(autouse=True)
def _stub_neo4j_delete(monkeypatch):
    """Replaces `service.delete_entities_for_user` with a `Mock` for every
    test in this file -- see the module docstring for why."""
    import app.auth.service as service_module

    fake_delete_entities = Mock()
    monkeypatch.setattr(service_module, "delete_entities_for_user", fake_delete_entities)
    return fake_delete_entities


def test_delete_account_with_no_documents_returns_204_and_removes_the_user(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-empty@example.com",
        password="password12345",
    )
    me = client.get("/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(User, uuid.UUID(user_id)) is None

    _stub_weaviate_delete.assert_called_once_with(user_id)
    _stub_neo4j_delete.assert_called_once_with(user_id)


def test_delete_account_with_deletable_documents_removes_everything_in_one_commit(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-docs@example.com",
        password="password12345",
    )
    doc_a = _upload(client, token, filename="a.pdf", content=b"%PDF-1.4 a")
    doc_b = _upload(client, token, filename="b.pdf", content=b"%PDF-1.4 b")
    _mark_ready(db_session, doc_a["id"])
    row_b = db_session.get(Document, uuid.UUID(doc_b["id"]))
    row_b.status = "Failed"
    db_session.commit()

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 204
    assert db_session.get(User, uuid.UUID(user_id)) is None
    assert db_session.get(Document, uuid.UUID(doc_a["id"])) is None
    assert db_session.get(Document, uuid.UUID(doc_b["id"])) is None

    # Called once each, for the whole account -- not once per document.
    _stub_weaviate_delete.assert_called_once_with(user_id)
    _stub_neo4j_delete.assert_called_once_with(user_id)


def test_delete_account_calls_weaviate_and_neo4j_before_rows_are_gone(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """Delete order is fixed: Weaviate, then Neo4j, then Postgres (both the
    documents rows and the user row) in one commit. Asserted by making each
    mock record whether the user row is still present at the moment it
    runs -- the only way to observe "before" without instrumenting the
    route, mirroring test_documents_delete.py's own approach."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-order@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="order-check.pdf")
    _mark_ready(db_session, uploaded["id"])

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_uuid = uuid.UUID(me.json()["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    call_order = []

    def _weaviate_side_effect(*a):
        call_order.append("weaviate")
        assert db_session.get(User, user_uuid) is not None
        assert db_session.get(Document, document_uuid) is not None

    def _neo4j_side_effect(*a):
        call_order.append("neo4j")
        assert db_session.get(User, user_uuid) is not None
        assert db_session.get(Document, document_uuid) is not None

    _stub_weaviate_delete.side_effect = _weaviate_side_effect
    _stub_neo4j_delete.side_effect = _neo4j_side_effect

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 204
    assert call_order == ["weaviate", "neo4j"]
    assert db_session.get(User, user_uuid) is None
    assert db_session.get(Document, document_uuid) is None


def test_delete_account_refuses_when_a_document_is_mid_ingestion_with_409(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """If any owned document is still mid-ingestion, nothing is deleted --
    same guard, same reasoning as `documents/service.py::delete_document`'s
    own 409 (a background task could otherwise keep writing to a store
    whose rows for this user are being wiped)."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-mid-ingestion@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="still-extracting.pdf")
    row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    row.status = "Extracting"
    db_session.commit()

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_id = me.json()["id"]

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Document is still being processed and can't be deleted yet."
    }
    _stub_weaviate_delete.assert_not_called()
    _stub_neo4j_delete.assert_not_called()

    # Nothing touched -- the user and the document both still exist.
    db_session.expire_all()
    assert db_session.get(User, uuid.UUID(user_id)) is not None
    surviving_row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    assert surviving_row is not None
    assert surviving_row.status == "Extracting"


@pytest.mark.parametrize("status", ["Uploaded", "Extracting", "Graphing"])
def test_delete_account_refuses_every_non_terminal_status_with_409(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete, status
):
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email=f"maria-delete-account-409-{status.lower()}@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename=f"{status.lower()}.pdf")
    row = db_session.get(Document, uuid.UUID(uploaded["id"]))
    row.status = status
    db_session.commit()

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 409
    _stub_weaviate_delete.assert_not_called()
    _stub_neo4j_delete.assert_not_called()


def test_delete_account_without_token_returns_401(client):
    response = client.delete("/auth/me")
    assert response.status_code == 401


def test_delete_account_with_invalid_token_returns_401(client):
    response = client.delete("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_delete_account_when_weaviate_raises_leaves_everything_intact_for_retry(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """If the Weaviate delete raises, nothing has been committed -- the
    user row and every document row must still exist so a retry is safe."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-weaviate-fails@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="retry-me.pdf")
    _mark_ready(db_session, uploaded["id"])

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_uuid = uuid.UUID(me.json()["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    _stub_weaviate_delete.side_effect = RuntimeError("Weaviate unreachable")

    with pytest.raises(RuntimeError):
        client.delete("/auth/me", headers=_auth_headers(token))

    db_session.expire_all()
    assert db_session.get(User, user_uuid) is not None
    assert db_session.get(Document, document_uuid) is not None
    _stub_neo4j_delete.assert_not_called()


def test_delete_account_when_neo4j_raises_leaves_everything_intact_for_retry(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """Same as the Weaviate case, one step later: if Neo4j raises after
    Weaviate already succeeded, Postgres must still never have committed."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-neo4j-fails@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="retry-me-2.pdf")
    _mark_ready(db_session, uploaded["id"])

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_uuid = uuid.UUID(me.json()["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    _stub_neo4j_delete.side_effect = RuntimeError("Neo4j unreachable")

    with pytest.raises(RuntimeError):
        client.delete("/auth/me", headers=_auth_headers(token))

    db_session.expire_all()
    assert db_session.get(User, user_uuid) is not None
    assert db_session.get(Document, document_uuid) is not None
    _stub_weaviate_delete.assert_called_once()


def test_delete_account_retry_after_partial_failure_is_safe(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """A retry after a partial failure (both store-delete functions are
    idempotent per their own docstrings) must still succeed and leave
    nothing behind -- the account-deletion equivalent of
    `test_documents_delete.py`'s single-document retry-safety coverage."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-retry-safe@example.com",
        password="password12345",
    )
    uploaded = _upload(client, token, filename="retry-safe.pdf")
    _mark_ready(db_session, uploaded["id"])

    me = client.get("/auth/me", headers=_auth_headers(token))
    user_uuid = uuid.UUID(me.json()["id"])
    document_uuid = uuid.UUID(uploaded["id"])

    _stub_weaviate_delete.side_effect = RuntimeError("transient failure")
    with pytest.raises(RuntimeError):
        client.delete("/auth/me", headers=_auth_headers(token))
    db_session.expire_all()
    assert db_session.get(User, user_uuid) is not None

    # Retry: the transient failure is gone now.
    _stub_weaviate_delete.side_effect = None
    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 204
    assert db_session.get(User, user_uuid) is None
    assert db_session.get(Document, document_uuid) is None
    assert _stub_weaviate_delete.call_count == 2
    _stub_neo4j_delete.assert_called_once()


def test_delete_account_with_persisted_chat_messages_removes_them_too(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """Story 3.4 regression: `chat_messages.user_id` is a `NOT NULL`
    foreign key into `users.id` with no `ON DELETE CASCADE` -- deleting
    the `users` row while this account still owns `chat_messages` rows
    must not surface as an unhandled `IntegrityError`/500 (real Postgres
    enforces this FK; this project's SQLite test DB doesn't, by default,
    which is exactly why this needs its own explicit assertion rather
    than relying on the DB to catch a regression here)."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-chat-messages@example.com",
        password="password12345",
    )
    me = client.get("/auth/me", headers=_auth_headers(token))
    user_id = uuid.UUID(me.json()["id"])
    db_session.add(ChatMessage(user_id=user_id, role="user", question="A question?"))
    db_session.add(
        ChatMessage(user_id=user_id, role="assistant", segments=[{"text": "An answer.", "citations": []}])
    )
    db_session.commit()

    response = client.delete("/auth/me", headers=_auth_headers(token))

    assert response.status_code == 204
    assert db_session.get(User, user_id) is None
    assert db_session.query(ChatMessage).filter(ChatMessage.user_id == user_id).count() == 0


def test_repository_delete_user_is_a_no_op_when_the_row_is_already_gone(db_session):
    """`auth.repository.delete_user` guards against `db.get` returning
    `None` -- a real case, not hypothetical: a second concurrent
    `DELETE /auth/me` for the same account (two tabs, a retried request)
    can race behind a first one that already committed. Without the guard,
    `db.delete(None)` raises; with it, the loser of the race just no-ops."""
    auth_repository.delete_user(db_session, uuid.uuid4())  # must not raise
    db_session.commit()


def test_delete_account_second_concurrent_call_is_a_clean_401_not_a_500(
    client, db_session, _stub_weaviate_delete, _stub_neo4j_delete
):
    """Simulates the loser of a race between two `DELETE /auth/me` calls
    for the same account: by the time this second call's `get_current_user`
    dependency re-authenticates, the row is already gone, so it 401s before
    ever reaching `delete_account` -- it must not surface as an unhandled
    500 from `repository.delete_user`."""
    token = _register_and_login(
        client,
        full_name="Maria Ivanova",
        email="maria-delete-account-concurrent@example.com",
        password="password12345",
    )
    first = client.delete("/auth/me", headers=_auth_headers(token))
    assert first.status_code == 204

    second = client.delete("/auth/me", headers=_auth_headers(token))

    assert second.status_code == 401
