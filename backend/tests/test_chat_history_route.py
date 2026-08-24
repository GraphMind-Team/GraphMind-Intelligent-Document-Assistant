"""`GET /chat/sessions/{session_id}/history` tests (Story 3.4/FR-17/AD-10;
session-nested for multi-session chat): auth requirement, the empty-session
case, newest-first ordering, cursor pagination walking the full history down
to `has_more: false`/`next_cursor: null`, an invalid cursor's 422,
cross-tenant/cross-session isolation, and session-ownership 404s.

Messages are seeded directly via `db_session` (mirrors
`test_chat_ask_route.py`'s own `_seed_turn` convention) rather than via
real `/chat/sessions/{id}/ask` round-trips, so each turn gets an explicit,
strictly increasing `created_at` -- sidesteps SQLite's whole-second
`CURRENT_TIMESTAMP` resolution, which would otherwise tie every turn
seeded within the same fast test run onto the same timestamp (see
`app/chat/repository.py`'s `_TURN_ROLE_RANK` comment for the full
reasoning, including why this is a production-safe assumption too: two
rows of the *same* turn are expected to tie -- that's what
`_TURN_ROLE_RANK` itself resolves -- but two different turns, each its own
transaction, are not, in real Postgres usage).
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.shared.models import ChatMessage


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"], uuid.UUID(register_response.json()["id"])


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_session_id(client, token):
    response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _seed_turn(db_session, user_id, session_id, *, question, answer_text, empty_reason=None, created_at):
    db_session.add(
        ChatMessage(
            user_id=user_id, session_id=session_id, role="user", question=question, created_at=created_at
        )
    )
    db_session.add(
        ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            segments=[{"text": answer_text, "citations": []}] if answer_text else [],
            empty_reason=empty_reason,
            created_at=created_at,
        )
    )
    db_session.commit()


def test_history_requires_authentication(client):
    response = client.get(f"/chat/sessions/{uuid.uuid4()}/history")
    assert response.status_code == 401


def test_history_unknown_session_returns_404(client):
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-404@example.com", password="password12345"
    )

    response = client.get(f"/chat/sessions/{uuid.uuid4()}/history", headers=_auth_headers(token))

    assert response.status_code == 404


def test_history_new_session_returns_empty_messages_and_has_more_false(client):
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-1@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


def test_history_returns_messages_newest_first(client, db_session):
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _seed_turn(db_session, user_id, session_id, question="Q1?", answer_text="A1.", created_at=base)
    _seed_turn(
        db_session, user_id, session_id, question="Q2?", answer_text="A2.", created_at=base + timedelta(seconds=1)
    )

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    # Newest first: turn 2's assistant reply, then its question, then
    # turn 1's assistant reply, then its question.
    assert [(m["role"], m["question"]) for m in body["messages"]] == [
        ("assistant", None),
        ("user", "Q2?"),
        ("assistant", None),
        ("user", "Q1?"),
    ]
    assert body["messages"][0]["segments"] == [{"text": "A2.", "citations": []}]
    assert body["has_more"] is False


def test_history_cursor_pagination_walks_the_full_thread_to_exhaustion(client, db_session):
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-3@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        _seed_turn(
            db_session,
            user_id,
            session_id,
            question=f"Q{i}?",
            answer_text=f"A{i}.",
            created_at=base + timedelta(seconds=i),
        )
    # 5 turns = 10 rows total.

    seen_ids = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 3}
        if cursor:
            params["cursor"] = cursor
        response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params=params)
        assert response.status_code == 200
        body = response.json()
        seen_ids.extend(m["id"] for m in body["messages"])
        pages += 1
        assert pages <= 10, "pagination did not terminate"
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        assert body["next_cursor"] is not None
        cursor = body["next_cursor"]

    # Every row visited exactly once across all pages, none skipped or
    # duplicated at a page boundary.
    assert len(seen_ids) == 10
    assert len(set(seen_ids)) == 10


def test_history_invalid_cursor_returns_422(client):
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-4@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    response = client.get(
        f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"cursor": "not-a-real-cursor"}
    )

    assert response.status_code == 422


def test_history_empty_string_cursor_returns_422_not_the_newest_page(client, db_session):
    """`?cursor=` (present, empty) is a malformed cursor, not "no cursor
    supplied" -- must 422 like any other malformed value rather than
    silently restarting from the newest page (a query-string-present
    empty string is falsy in Python, which a naive `if cursor:` check
    would treat as "no cursor")."""
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-empty-cursor@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="Q?",
        answer_text="A.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"cursor": ""})

    assert response.status_code == 422


def test_history_cursor_with_out_of_range_role_rank_returns_422(client):
    """A cursor's role-rank component only ever means 0 (user) or 1
    (assistant) -- a syntactically-parseable but out-of-range value
    (e.g. `7`) must 422 the same as any other malformed cursor, not
    silently "decode" into a value that anchors nowhere any real row
    could sort to."""
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-bad-role-rank@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    bad_cursor = f"2026-01-01T00:00:00+00:00|7|{uuid.uuid4()}"

    response = client.get(
        f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"cursor": bad_cursor}
    )

    assert response.status_code == 422


def test_history_cross_tenant_isolation(client, db_session):
    token_a, user_id_a = _register_and_login(
        client, full_name="Account A", email="account-a-history@example.com", password="password-account-a"
    )
    token_b, user_id_b = _register_and_login(
        client, full_name="Account B", email="account-b-history@example.com", password="password-account-b"
    )
    session_id_a = _create_session_id(client, token_a)
    session_id_b = _create_session_id(client, token_b)
    _seed_turn(
        db_session,
        user_id_a,
        session_id_a,
        question="Account A's own question",
        answer_text="Account A's own answer.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    # Account B's own session is empty either way, but the load-bearing
    # assertion is the 404 below -- B can't even name A's session to read
    # from it, let alone see A's messages through it.
    response_b = client.get(f"/chat/sessions/{session_id_b}/history", headers=_auth_headers(token_b))
    assert response_b.status_code == 200
    assert response_b.json()["messages"] == []

    cross_tenant_response = client.get(f"/chat/sessions/{session_id_a}/history", headers=_auth_headers(token_b))
    assert cross_tenant_response.status_code == 404


def test_history_persisted_refusal_renders_with_its_empty_reason(client, db_session):
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-5@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="Something unrelated?",
        answer_text=None,
        empty_reason="refusal",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token))

    assert response.status_code == 200
    assistant_message = response.json()["messages"][0]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["empty_reason"] == "refusal"
    assert assistant_message["segments"] == []


def test_history_row_with_real_citations_round_trips_through_the_response(client, db_session):
    """`_seed_turn`'s own helper always writes `citations: []` -- every
    other test in this file only exercises plain text/refusal history
    rows. A real answer's `segments` carry actual
    `{chapter, document_filename, chunk_indexes}` citation data (exactly
    what `chat/service.py::_finish` persists via
    `segment.model_dump()`), and this is the one place asserting that
    shape survives a full round trip through `ChatMessage.segments` (a
    JSON column) -> `ChatHistoryMessageResponse.model_validate` ->
    the API response, unchanged."""
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-citations@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    db_session.add(
        ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="user",
            question="What is the refund window?",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            segments=[
                {
                    "text": "The refund window is 30 days.",
                    "citations": [
                        {
                            "chapter": "Chapter 4",
                            "document_filename": "Vendor_Agreement_2026.pdf",
                            "chunk_indexes": [0, 3],
                        }
                    ],
                }
            ],
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token))

    assert response.status_code == 200
    assistant_message = response.json()["messages"][0]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["segments"] == [
        {
            "text": "The refund window is 30 days.",
            "citations": [
                {
                    "chapter": "Chapter 4",
                    "document_filename": "Vendor_Agreement_2026.pdf",
                    "chunk_indexes": [0, 3],
                }
            ],
        }
    ]


def test_history_respects_the_requested_limit(client, db_session):
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-6@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(3):
        _seed_turn(
            db_session,
            user_id,
            session_id,
            question=f"Q{i}?",
            answer_text=f"A{i}.",
            created_at=base + timedelta(seconds=i),
        )

    # UX-DR29: initial load requests limit=3 (messages, not turns).
    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"limit": 3})

    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 3
    assert body["has_more"] is True


def test_history_rejects_limit_zero_with_422(client):
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-limit-zero@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"limit": 0})

    assert response.status_code == 422


def test_history_rejects_limit_above_fifty_with_422(client):
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-limit-over@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"limit": 51})

    assert response.status_code == 422


def test_history_accepts_limit_at_the_fifty_boundary(client):
    """The upper edge of `le=50` -- must succeed, not 422, distinguishing
    this from `test_history_rejects_limit_above_fifty_with_422` above."""
    token, _ = _register_and_login(
        client, full_name="Maria", email="maria-history-limit-boundary@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    response = client.get(f"/chat/sessions/{session_id}/history", headers=_auth_headers(token), params={"limit": 50})

    assert response.status_code == 200


def test_history_scoped_to_one_session_never_mixes_another_sessions_messages(client, db_session):
    """Multi-session chat's core isolation guarantee: two sessions
    belonging to the SAME account never bleed into each other's
    history, even though both share one `user_id`."""
    token, user_id = _register_and_login(
        client, full_name="Maria", email="maria-history-multi-session@example.com", password="password12345"
    )
    session_id_1 = _create_session_id(client, token)
    session_id_2 = _create_session_id(client, token)
    _seed_turn(
        db_session,
        user_id,
        session_id_1,
        question="Session 1's question",
        answer_text="Session 1's answer.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _seed_turn(
        db_session,
        user_id,
        session_id_2,
        question="Session 2's question",
        answer_text="Session 2's answer.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response_1 = client.get(f"/chat/sessions/{session_id_1}/history", headers=_auth_headers(token))
    response_2 = client.get(f"/chat/sessions/{session_id_2}/history", headers=_auth_headers(token))

    assert response_1.status_code == 200 and response_2.status_code == 200
    questions_1 = [m["question"] for m in response_1.json()["messages"] if m["role"] == "user"]
    questions_2 = [m["question"] for m in response_2.json()["messages"] if m["role"] == "user"]
    assert questions_1 == ["Session 1's question"]
    assert questions_2 == ["Session 2's question"]
