"""`POST /chat/sessions/{session_id}/messages/{message_id}/edit` tests.

Mirrors `test_chat_message_feedback_route.py`'s IDOR coverage: a
cross-tenant/nonexistent message id, a message from a *different* session,
and a `role="assistant"` id all come back as the same 404 `"Chat message
not found."` -- never a distinct error that would let a caller probe which
id belongs to which role/session. The core behavior under test is
`chat/service.py::edit_message`'s "discard this question and everything
after it, then ask fresh" contract, verified both via the response and by
reading persisted rows directly.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.chat import service as chat_service_module
from app.shared.data_access.shapes import WeaviateSearchResult
from app.shared.llm_client import AnswerResult, AnswerSegment
from app.shared.models import ChatMessage


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


def _edit_url(session_id, message_id):
    return f"/chat/sessions/{session_id}/messages/{message_id}/edit"


def _stub_generation(monkeypatch, *, document_id, answer_text="The refund window is 30 days."):
    passages = [
        WeaviateSearchResult(
            chunk_id="chunk-0",
            document_id=document_id,
            chapter="Chapter 4",
            chunk_index=0,
            text="passage text",
            distance=0.1,
        )
    ]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text=answer_text, passage_numbers=[1])],
            included_passages=passages,
        ),
    )


def _ask(client, token, session_id, question):
    response = client.post(
        f"/chat/sessions/{session_id}/ask", headers=_auth_headers(token), json={"question": question}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _ask_at_tick(client, db_session, token, session_id, question, tick):
    """Same as `_ask`, but pins the resulting turn's `created_at` to a
    value `tick` seconds after a fixed epoch, same precedent as
    `test_chat_ask_route.py::_seed_turn`'s own docstring: real successive
    `/ask` calls within one fast-running test would all tie on SQLite's
    whole-second-resolution clock, and `delete_messages_from`'s own
    "compare stored values against each other" fix (see its docstring)
    only produces the *right* order when there's a real order to find --
    it can't invent one between turns whose timestamps are, in the test
    DB, genuinely identical. Spacing them out here is a test-only
    concern; production Postgres timestamps never collide this way."""
    result = _ask(client, token, session_id, question)
    when = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=tick)
    ids = [uuid.UUID(result["user_message_id"]), uuid.UUID(result["message_id"])]
    db_session.query(ChatMessage).filter(ChatMessage.id.in_(ids)).update(
        {"created_at": when}, synchronize_session=False
    )
    db_session.commit()
    return result


def _setup_session_with_document(client, token):
    session_response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["id"]

    document_response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf")},
    )
    assert document_response.status_code == 201, document_response.text
    return session_id, document_response.json()["id"]


def test_edit_requires_authentication(client):
    response = client.post(_edit_url(uuid.uuid4(), uuid.uuid4()), json={"question": "q"})
    assert response.status_code == 401


def test_edit_unknown_message_returns_404(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-1@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)

    response = client.post(_edit_url(session_id, uuid.uuid4()), headers=_auth_headers(token), json={"question": "q"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Chat message not found."


def test_edit_unknown_session_returns_404(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-2@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token, session_id, "What is the refund window?")

    response = client.post(
        _edit_url(uuid.uuid4(), first["user_message_id"]), headers=_auth_headers(token), json={"question": "q"}
    )
    assert response.status_code == 404
    # Session is resolved first (sessions_service.get_session, same order
    # ask_question uses) -- an unknown session_id 404s on the *session*,
    # before the message is ever looked up, even though the message id
    # itself is real.
    assert response.json()["detail"] == "Chat session not found."


def test_edit_an_assistant_message_id_is_404(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-3@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token, session_id, "What is the refund window?")

    response = client.post(
        _edit_url(session_id, first["message_id"]), headers=_auth_headers(token), json={"question": "q"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Chat message not found."


def test_edit_a_message_from_a_different_session_is_404(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-4@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token, session_id, "What is the refund window?")

    other_session_response = client.post("/chat/sessions", headers=_auth_headers(token))
    other_session_id = other_session_response.json()["id"]

    response = client.post(
        _edit_url(other_session_id, first["user_message_id"]),
        headers=_auth_headers(token),
        json={"question": "q"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Chat message not found."


def test_edit_cross_tenant_is_the_same_404_as_unknown(client, monkeypatch):
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-edit@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-edit@example.com", password="password-account-b"
    )
    session_id, document_id = _setup_session_with_document(client, token_a)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token_a, session_id, "What is the refund window?")

    cross_tenant = client.post(
        _edit_url(session_id, first["user_message_id"]), headers=_auth_headers(token_b), json={"question": "q"}
    )
    unknown = client.post(
        _edit_url(session_id, uuid.uuid4()), headers=_auth_headers(token_b), json={"question": "q"}
    )
    assert cross_tenant.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_edit_discards_the_old_answer_and_asks_the_edited_question_fresh(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-5@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id, answer_text="The refund window is 30 days.")
    first = _ask(client, token, session_id, "What is the refund window?")

    _stub_generation(monkeypatch, document_id=document_id, answer_text="The warranty period is one year.")
    edit_response = client.post(
        _edit_url(session_id, first["user_message_id"]),
        headers=_auth_headers(token),
        json={"question": "What is the warranty period?"},
    )

    assert edit_response.status_code == 200
    body = edit_response.json()
    assert body["segments"][0]["text"] == "The warranty period is one year."
    # A fresh id, not the edited row reused -- edit_message deletes the
    # old row outright rather than mutating it in place.
    assert body["user_message_id"] != first["user_message_id"]

    rows = db_session.query(ChatMessage).filter_by(session_id=uuid.UUID(session_id)).all()
    assert len(rows) == 2
    user_row = next(r for r in rows if r.role == "user")
    assistant_row = next(r for r in rows if r.role == "assistant")
    assert user_row.question == "What is the warranty period?"
    assert assistant_row.segments[0]["text"] == "The warranty period is one year."


def test_edit_discards_every_later_turn_in_the_same_session(client, db_session, monkeypatch):
    """Editing the *first* of three turns must discard turns two and
    three too, not just the edited one -- "everything after it", not
    "only it"."""
    token = _register_and_login(client, full_name="Maria", email="maria-edit-6@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask_at_tick(client, db_session, token, session_id, "Question one?", tick=0)
    _ask_at_tick(client, db_session, token, session_id, "Question two?", tick=10)
    _ask_at_tick(client, db_session, token, session_id, "Question three?", tick=20)

    edit_response = client.post(
        _edit_url(session_id, first["user_message_id"]),
        headers=_auth_headers(token),
        json={"question": "Edited question one?"},
    )
    assert edit_response.status_code == 200

    rows = db_session.query(ChatMessage).filter_by(session_id=uuid.UUID(session_id)).all()
    assert len(rows) == 2
    questions = [r.question for r in rows if r.role == "user"]
    assert questions == ["Edited question one?"]


def test_edit_leaves_an_earlier_turn_in_the_same_session_untouched(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-7@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    _ask_at_tick(client, db_session, token, session_id, "Question one?", tick=0)
    second = _ask_at_tick(client, db_session, token, session_id, "Question two?", tick=10)

    edit_response = client.post(
        _edit_url(session_id, second["user_message_id"]),
        headers=_auth_headers(token),
        json={"question": "Edited question two?"},
    )
    assert edit_response.status_code == 200

    rows = db_session.query(ChatMessage).filter_by(session_id=uuid.UUID(session_id)).all()
    questions = [r.question for r in rows if r.role == "user"]
    assert questions == ["Question one?", "Edited question two?"]


def test_edit_leaves_another_sessions_turns_untouched(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-8@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token, session_id, "Question one?")

    other_session_response = client.post("/chat/sessions", headers=_auth_headers(token))
    other_session_id = other_session_response.json()["id"]
    _ask(client, token, other_session_id, "A question in another session?")

    client.post(
        _edit_url(session_id, first["user_message_id"]),
        headers=_auth_headers(token),
        json={"question": "Edited question one?"},
    )

    other_rows = db_session.query(ChatMessage).filter_by(session_id=uuid.UUID(other_session_id)).all()
    other_questions = [r.question for r in other_rows if r.role == "user"]
    assert other_questions == ["A question in another session?"]


def test_edit_rejects_a_blank_question_with_422(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-edit-9@example.com", password="password12345")
    session_id, document_id = _setup_session_with_document(client, token)
    _stub_generation(monkeypatch, document_id=document_id)
    first = _ask(client, token, session_id, "What is the refund window?")

    response = client.post(
        _edit_url(session_id, first["user_message_id"]), headers=_auth_headers(token), json={"question": "   "}
    )
    assert response.status_code == 422
