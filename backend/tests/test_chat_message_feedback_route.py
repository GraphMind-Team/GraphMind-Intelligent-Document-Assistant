"""`PUT /chat/messages/{message_id}/feedback` tests.

Mirrors `test_chat_sessions_routes.py`'s IDOR coverage: a cross-tenant or
nonexistent message id must come back as the same 404
`"Chat message not found."`, never a 403 that would confirm the id exists
-- and a `role="user"` id gets the identical 404, since feedback only ever
exists on the answer half of a turn (never a distinct error that would let
a caller probe which id belongs to which role).
"""

import uuid

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


def _feedback_url(message_id):
    return f"/chat/messages/{message_id}/feedback"


def _ask_and_get_turn(client, monkeypatch, token, *, question="What is the refund window?"):
    """Real success path (mirrors test_chat_ask_route.py's own helper
    shape) -- returns `(message_id, user_message_id)` for the resulting
    assistant/user rows, via a session created fresh for this call."""
    session_response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert session_response.status_code == 201, session_response.text
    session_id = session_response.json()["id"]

    document_response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("report.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf")},
    )
    assert document_response.status_code == 201, document_response.text
    document_id = document_response.json()["id"]

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
            segments=[AnswerSegment(text="The refund window is 30 days.", passage_numbers=[1])],
            included_passages=passages,
        ),
    )

    ask_response = client.post(
        f"/chat/sessions/{session_id}/ask", headers=_auth_headers(token), json={"question": question}
    )
    assert ask_response.status_code == 200, ask_response.text
    message_id = ask_response.json()["message_id"]
    assert message_id is not None
    return message_id


def test_feedback_requires_authentication(client):
    response = client.put(_feedback_url(uuid.uuid4()), json={"rating": "up"})
    assert response.status_code == 401


def test_feedback_unknown_message_returns_404(client):
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-1@example.com", password="password12345"
    )
    response = client.put(_feedback_url(uuid.uuid4()), headers=_auth_headers(token), json={"rating": "up"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Chat message not found."


def test_feedback_sets_up_then_down_then_clears(client, db_session, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-2@example.com", password="password12345"
    )
    message_id = _ask_and_get_turn(client, monkeypatch, token)

    up_response = client.put(_feedback_url(message_id), headers=_auth_headers(token), json={"rating": "up"})
    assert up_response.status_code == 200
    assert up_response.json() == {"id": message_id, "feedback": "up"}

    down_response = client.put(_feedback_url(message_id), headers=_auth_headers(token), json={"rating": "down"})
    assert down_response.status_code == 200
    assert down_response.json()["feedback"] == "down"

    clear_response = client.put(_feedback_url(message_id), headers=_auth_headers(token), json={"rating": None})
    assert clear_response.status_code == 200
    assert clear_response.json()["feedback"] is None

    db_session.expire_all()
    row = db_session.get(ChatMessage, uuid.UUID(message_id))
    assert row.feedback is None


def test_feedback_persists_to_the_database(client, db_session, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-3@example.com", password="password12345"
    )
    message_id = _ask_and_get_turn(client, monkeypatch, token)

    response = client.put(_feedback_url(message_id), headers=_auth_headers(token), json={"rating": "up"})
    assert response.status_code == 200

    db_session.expire_all()
    row = db_session.get(ChatMessage, uuid.UUID(message_id))
    assert row.feedback == "up"


def test_feedback_on_a_user_role_message_is_404(client, db_session, monkeypatch):
    """Feedback only exists on the answer half of a turn -- the question's
    own row must 404 exactly like a foreign/nonexistent id, not surface a
    distinct error that would let a caller distinguish "wrong role" from
    "doesn't exist"."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-4@example.com", password="password12345"
    )
    _ask_and_get_turn(client, monkeypatch, token)

    user_row = db_session.query(ChatMessage).filter_by(role="user").one()

    response = client.put(_feedback_url(user_row.id), headers=_auth_headers(token), json={"rating": "up"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Chat message not found."


def test_feedback_cross_tenant_is_the_same_404_as_unknown(client, monkeypatch):
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-feedback@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-feedback@example.com", password="password-account-b"
    )
    message_id = _ask_and_get_turn(client, monkeypatch, token_a)

    cross_tenant = client.put(_feedback_url(message_id), headers=_auth_headers(token_b), json={"rating": "up"})
    unknown = client.put(_feedback_url(uuid.uuid4()), headers=_auth_headers(token_b), json={"rating": "up"})

    assert cross_tenant.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_feedback_rejects_an_invalid_rating_with_422(client, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-5@example.com", password="password12345"
    )
    message_id = _ask_and_get_turn(client, monkeypatch, token)

    response = client.put(_feedback_url(message_id), headers=_auth_headers(token), json={"rating": "sideways"})
    assert response.status_code == 422


def test_feedback_malformed_message_id_is_422(client):
    token = _register_and_login(
        client, full_name="Maria", email="maria-feedback-6@example.com", password="password12345"
    )
    response = client.put("/chat/messages/not-a-uuid/feedback", headers=_auth_headers(token), json={"rating": "up"})
    assert response.status_code == 422
