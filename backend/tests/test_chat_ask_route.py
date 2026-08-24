"""`POST /chat/sessions/{session_id}/ask` tests (Stories 3.1, 3.2;
session-nested for multi-session chat): auth requirement, session-ownership
404s, Pydantic-level question validation (422, not a manual 400), the three
distinct empty_reason outcomes ("no_documents", "no_answer", "refusal"), the
exact 503 point for an LLM-wrapper failure, cross-tenant isolation of
citation resolution, and a full success path resolving real
`{chapter, document_filename}` citations.

`search_passages`/`generate_answer` are mocked at their
`app.chat.service`-bound names (the module-level names that module imported
them under) -- this file never touches a real Weaviate or OpenRouter.

There is no embedding call to mock: `search_passages` now takes the query
*text* and Weaviate embeds it server-side, so the retrieval query is
observable directly as that function's first argument. Tests that used to
assert on an `embed_texts` call assert on it there instead.

Story 3.4/FR-17 adds conversational-memory coverage at the bottom of this
file: persistence round-tripping (and the one documented non-persisted
path, a 503), history threading into the retrieval query text and into
`generate_answer`'s `history` param, the empty-history/pre-3.4-identical
case, the 3-turn/2000-char budget, and scope-change-mid-conversation --
every seeded turn there now belongs to the same session the test's own
`/ask` call targets, so history threading is exercised the same
session-scoped way production resolves it.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.chat import service as chat_service_module
from app.shared.data_access.shapes import WeaviateSearchResult
from app.shared.llm_client import RELEVANCE_THRESHOLD, AnswerResult, AnswerSegment, ChatCompletionError
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


def _create_session_id(client, token):
    response = client.post("/chat/sessions", headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _ask_url(session_id):
    return f"/chat/sessions/{session_id}/ask"


def _upload(client, token, filename="report.pdf", content=b"%PDF-1.4 fake pdf bytes"):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _passage(
    document_id, chapter="Chapter One", chunk_id="chunk-0", chunk_index=0, text="passage text", distance=0.1
):
    return WeaviateSearchResult(
        chunk_id=chunk_id,
        document_id=document_id,
        chapter=chapter,
        chunk_index=chunk_index,
        text=text,
        distance=distance,
    )


def _seed_turn(db_session, user_id, session_id, *, question, answer_text, created_at):
    """Directly inserts a completed (user, assistant) turn -- bypassing
    `/chat/sessions/{id}/ask` entirely -- with an explicit `created_at` on
    both rows, against the given `session_id`.

    Real successive `/ask` calls within one fast-running test would
    all tie on SQLite's `CURRENT_TIMESTAMP` (whole-second resolution --
    see `app/chat/repository.py`'s `_TURN_ROLE_RANK` comment for why
    Postgres has the same tie *within* one turn, by design, but not
    *across* separate turns/transactions the way SQLite's coarse clock
    does in a test run). Giving each seeded turn its own explicit,
    strictly increasing timestamp here mirrors production's real
    per-transaction timestamps rather than fighting the test DB's clock
    granularity.
    """
    db_session.add(
        ChatMessage(user_id=user_id, session_id=session_id, role="user", question=question, created_at=created_at)
    )
    db_session.add(
        ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            segments=[{"text": answer_text, "citations": []}] if answer_text else [],
            created_at=created_at,
        )
    )
    db_session.commit()


def test_ask_requires_authentication(client):
    response = client.post(_ask_url(uuid.uuid4()), json={"question": "What is the refund window?"})
    assert response.status_code == 401


def test_ask_unknown_session_returns_404(client):
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-404@example.com", password="password12345"
    )

    response = client.post(
        _ask_url(uuid.uuid4()), headers=_auth_headers(token), json={"question": "Anything in my docs?"}
    )

    assert response.status_code == 404


def test_ask_rejects_blank_question_with_422_not_400(client):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-1@example.com", password="password12345")
    session_id = _create_session_id(client, token)

    response = client.post(_ask_url(session_id), headers=_auth_headers(token), json={"question": "   "})

    assert response.status_code == 422


def test_ask_rejects_over_length_question_with_422(client):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-2@example.com", password="password12345")
    session_id = _create_session_id(client, token)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "x" * 2001}
    )

    assert response.status_code == 422


def test_ask_zero_passages_returns_no_documents_reason(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-3@example.com", password="password12345")
    session_id = _create_session_id(client, token)
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    response = client.post(_ask_url(session_id), headers=_auth_headers(token), json={"question": "Anything in my docs?"})

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "no_documents"

    # Still "the resulting assistant message" for this turn (spec's own
    # phrasing) -- persisted like every other outcome except the 503 path.
    rows = db_session.query(ChatMessage).all()
    user_rows = [r for r in rows if r.role == "user"]
    assistant_rows = [r for r in rows if r.role == "assistant"]
    assert len(user_rows) == 1 and user_rows[0].question == "Anything in my docs?"
    assert len(assistant_rows) == 1
    assert assistant_rows[0].segments == []
    assert assistant_rows[0].empty_reason == "no_documents"


def test_ask_generation_producing_no_answerable_segments_returns_no_answer_reason(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-4@example.com", password="password12345")
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )
    monkeypatch.setattr(
        chat_service_module, "generate_answer", lambda *a, **k: AnswerResult(segments=[])
    )

    response = client.post(_ask_url(session_id), headers=_auth_headers(token), json={"question": "Unanswerable?"})

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "no_answer"

    rows = db_session.query(ChatMessage).all()
    user_rows = [r for r in rows if r.role == "user"]
    assistant_rows = [r for r in rows if r.role == "assistant"]
    assert len(user_rows) == 1 and user_rows[0].question == "Unanswerable?"
    assert len(assistant_rows) == 1
    assert assistant_rows[0].segments == []
    assert assistant_rows[0].empty_reason == "no_answer"


def test_ask_refuses_when_every_passage_is_below_the_relevance_threshold(client, monkeypatch):
    """FR-10/OD-2: every retrieved passage too dissimilar to trust -->
    refuse, and `generate_answer` must never be called at all (AD-6) --
    the one thing a plain-lambda stub can't prove, which is why this test
    uses a Mock with assert_not_called() instead."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-refusal-1@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    passages = [
        _passage(document["id"], distance=RELEVANCE_THRESHOLD + 0.2),
        _passage(document["id"], chunk_id="chunk-1", chunk_index=1, distance=RELEVANCE_THRESHOLD + 0.4),
    ]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    generate_answer_mock = Mock()
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "Something unrelated to my documents?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "refusal"
    generate_answer_mock.assert_not_called()


def test_ask_proceeds_when_at_least_one_passage_clears_the_threshold(client, monkeypatch):
    """Mixed distances -- the check is "any", not "all". A regression guard
    that one relevant passage among several irrelevant ones still reaches
    generate_answer, unfiltered, exactly as Story 3.1's flow already did."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-refusal-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    passages = [
        _passage(document["id"], distance=RELEVANCE_THRESHOLD + 0.1),
        _passage(document["id"], chunk_id="chunk-1", chunk_index=1, distance=RELEVANCE_THRESHOLD - 0.1),
    ]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="A claim.", passage_numbers=[1])], included_passages=passages
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    assert response.json()["empty_reason"] is None


def test_ask_treats_exact_threshold_distance_as_relevant(client, monkeypatch):
    """Boundary: distance == RELEVANCE_THRESHOLD counts as relevant (<=),
    not refused."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-refusal-3@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    passages = [_passage(document["id"], distance=RELEVANCE_THRESHOLD)]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    generate_answer_mock = Mock(
        return_value=AnswerResult(
            segments=[AnswerSegment(text="A claim.", passage_numbers=[1])], included_passages=passages
        )
    )
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    assert response.json()["empty_reason"] is None
    generate_answer_mock.assert_called_once()


def test_ask_refuses_when_every_passage_has_no_distance_metadata(client, monkeypatch, caplog):
    """A `distance` of None can't be verified as relevant, so it never
    clears the bar -- documents the conservative default for a retrieval
    metadata gap that can't happen today but shouldn't fail open if it
    ever did. Also asserts the logger.warning fires: the refusal-response
    assertions alone would still pass if that diagnostic were deleted as
    "dead code" (its own comment says the gap "can't happen today"), and
    that diagnostic is the only reason this branch exists."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-refusal-4@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    passages = [_passage(document["id"], distance=None)]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    generate_answer_mock = Mock()
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "Anything in my docs?"}
    )

    assert response.status_code == 200
    assert response.json()["empty_reason"] == "refusal"
    generate_answer_mock.assert_not_called()
    assert "no distance metadata" in caplog.text


def test_ask_llm_wrapper_failure_surfaces_as_exactly_503(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-5@example.com", password="password12345")
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )

    def _raise_chat_completion_error(*a, **k):
        raise ChatCompletionError("OpenRouter chat generation failed after 2 attempts")

    monkeypatch.setattr(chat_service_module, "generate_answer", _raise_chat_completion_error)

    response = client.post(_ask_url(session_id), headers=_auth_headers(token), json={"question": "What is it?"})

    assert response.status_code == 503
    assert "detail" in response.json()


def test_ask_success_resolves_real_chapter_and_filename_citations(client, db_session, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-6@example.com", password="password12345")
    session_id = _create_session_id(client, token)
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    passages = [_passage(document["id"], chapter="Chapter 4")]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        # included_passages mirrors what the real generate_answer would
        # return: the (here, unbudgeted) list its prompt was built from --
        # chat/service.py resolves citations against this, not the
        # search_passages result directly.
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="The refund window is 30 days.", passage_numbers=[1])],
            included_passages=passages,
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What is the refund window?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty_reason"] is None
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "The refund window is 30 days."
    assert body["segments"][0]["citations"] == [
        {
            "chapter": "Chapter 4",
            "document_filename": "Vendor_Agreement_2026.pdf",
            "chunk_indexes": [0],
        }
    ]
    # `message_id` round-trips to the persisted assistant row's own id --
    # see AskResponse.message_id's docstring -- so a feedback PUT can
    # target this turn's answer without a reload first.
    assistant_row = db_session.query(ChatMessage).filter_by(role="assistant").one()
    assert body["message_id"] == str(assistant_row.id)


def test_ask_deduplicates_repeated_chapter_and_filename_citations(client, monkeypatch):
    """Two different chunks from the same chapter of the same document
    (routine at TOP_K_PASSAGES=8) -- or a model repeating a
    passage_number, e.g. [1, 1] -- must render as one citation chip, not
    two identical ones side by side."""
    token = _register_and_login(client, full_name="Maria", email="maria-chat-dedup@example.com", password="password12345")
    session_id = _create_session_id(client, token)
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    passages = [
        _passage(document["id"], chapter="Chapter 4", chunk_id="chunk-a", chunk_index=0, text="first chunk"),
        _passage(document["id"], chapter="Chapter 4", chunk_id="chunk-b", chunk_index=1, text="second chunk"),
    ]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[
                AnswerSegment(text="A claim supported by both chunks.", passage_numbers=[1, 2]),
            ],
            included_passages=passages,
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["segments"]) == 1
    # One chip (the two chunks share chapter + filename), but BOTH
    # contributing chunk indexes survive the merge -- keeping only the
    # first would make the payload claim chunk 0 alone supported this
    # segment, which is more precision than the data actually has.
    assert body["segments"][0]["citations"] == [
        {
            "chapter": "Chapter 4",
            "document_filename": "Vendor_Agreement_2026.pdf",
            "chunk_indexes": [0, 1],
        }
    ]


def test_ask_does_not_duplicate_a_chunk_index_when_the_model_repeats_a_passage_number(
    client, monkeypatch
):
    """`chunk_indexes` merges distinct source chunks, not mentions -- a
    model answering with `passage_numbers=[1, 1]` names one chunk twice,
    which must not surface as `chunk_indexes: [0, 0]`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-repeat@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    passages = [_passage(document["id"], chapter="Chapter 4", chunk_index=7)]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="A claim citing one chunk twice.", passage_numbers=[1, 1])],
            included_passages=passages,
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    citations = response.json()["segments"][0]["citations"]
    assert citations == [
        {
            "chapter": "Chapter 4",
            "document_filename": "Vendor_Agreement_2026.pdf",
            "chunk_indexes": [7],
        }
    ]


def test_ask_keeps_separate_citations_for_different_chapters_of_one_document(client, monkeypatch):
    """The merge key is `(chapter, document_filename)`, so two chapters of
    the same document stay two citations -- each carrying only its own
    chunk indexes, never pooled across chapters."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-chapters@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    passages = [
        _passage(document["id"], chapter="Chapter 4", chunk_id="chunk-a", chunk_index=0),
        _passage(document["id"], chapter="Chapter 9", chunk_id="chunk-b", chunk_index=5),
    ]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="A claim spanning two chapters.", passage_numbers=[1, 2])],
            included_passages=passages,
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    assert response.json()["segments"][0]["citations"] == [
        {
            "chapter": "Chapter 4",
            "document_filename": "Vendor_Agreement_2026.pdf",
            "chunk_indexes": [0],
        },
        {
            "chapter": "Chapter 9",
            "document_filename": "Vendor_Agreement_2026.pdf",
            "chunk_indexes": [5],
        },
    ]


def test_ask_scopes_retrieval_to_the_authenticated_users_id(client, monkeypatch):
    """The other half of the tenancy guarantee this route's docstring
    promises: not just that `search_passages` filters server-side (that's
    `test_weaviate_client.py`'s job at the DAL level), but that
    `chat/service.py` actually resolves and passes THIS request's own
    authenticated user id -- not a stale one, not another account's. Every
    other test in this file stubs `search_passages` with `lambda *a, **k:
    [...]`, which would stay green even if the service passed the wrong id
    or none at all; this test is the one that would actually fail."""
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Maria",
            "email": "maria-chat-tenancy@example.com",
            "password": "password12345",
        },
    )
    assert register_response.status_code == 201, register_response.text
    user_id = register_response.json()["id"]

    login_response = client.post(
        "/auth/login",
        json={"email": "maria-chat-tenancy@example.com", "password": "password12345"},
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["access_token"]
    session_id = _create_session_id(client, token)

    document = _upload(client, token)

    captured = {}

    def _fake_search_passages(query_text, user_id_arg, **kwargs):
        captured["user_id"] = user_id_arg
        return [_passage(document["id"])]

    monkeypatch.setattr(chat_service_module, "search_passages", _fake_search_passages)
    monkeypatch.setattr(
        chat_service_module, "generate_answer", lambda *a, **k: AnswerResult(segments=[])
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "Anything in my docs?"}
    )

    assert response.status_code == 200
    assert captured["user_id"] == user_id


def test_ask_passes_document_ids_scope_to_search_passages(client, monkeypatch):
    """Story 3.3/FR-11: the request's `document_ids` must actually reach
    `search_passages` as its own `document_ids` kwarg -- not get dropped,
    not get merged into `user_id`. Mirrors
    `test_ask_scopes_retrieval_to_the_authenticated_users_id`'s
    capture-the-argument shape for the same reason: a stub returning
    canned passages would stay green even if scope were silently ignored."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-scope-1@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)

    captured = {}

    def _fake_search_passages(query_text, user_id_arg, **kwargs):
        captured["document_ids"] = kwargs.get("document_ids")
        return [_passage(document["id"])]

    monkeypatch.setattr(chat_service_module, "search_passages", _fake_search_passages)
    monkeypatch.setattr(
        chat_service_module, "generate_answer", lambda *a, **k: AnswerResult(segments=[])
    )

    response = client.post(
        _ask_url(session_id),
        headers=_auth_headers(token),
        json={"question": "What does this say?", "document_ids": [document["id"]]},
    )

    assert response.status_code == 200
    assert captured["document_ids"] == [document["id"]]


def test_ask_rejects_oversized_document_ids_with_422(client):
    """Story 3.3: `document_ids`'s `max_length=200` is a defensive cap, same
    spirit as `question`'s own `max_length` above -- mirrors
    `test_ask_rejects_over_length_question_with_422`'s shape for the other
    field. 201 ids must 422 before ever reaching `search_passages`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-scope-cap@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    oversized_ids = [str(uuid.uuid4()) for _ in range(201)]

    response = client.post(
        _ask_url(session_id),
        headers=_auth_headers(token),
        json={"question": "Anything in my docs?", "document_ids": oversized_ids},
    )

    assert response.status_code == 422


def test_ask_omitted_document_ids_defaults_to_empty_scope_list(client, monkeypatch):
    """An omitted `document_ids` field must still reach `search_passages`
    as an empty/None scope (FR-11's "search everything" default), not
    crash or silently vanish the kwarg."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-scope-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)

    captured = {}

    def _fake_search_passages(query_text, user_id_arg, **kwargs):
        captured["document_ids"] = kwargs.get("document_ids")
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _fake_search_passages)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "Anything in my docs?"}
    )

    assert response.status_code == 200
    assert not captured["document_ids"]


def test_ask_scoped_to_documents_with_no_passages_returns_empty_scope_not_no_documents(
    client, db_session, monkeypatch
):
    """Story 3.3: a non-empty scope that matches zero passages must read
    as "empty_scope", not "no_documents" -- the user's library isn't
    empty, their selected documents just have nothing matching. Distinct
    from `test_ask_zero_passages_returns_no_documents_reason`, which
    covers the unscoped case and must stay "no_documents"."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-scope-3@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    response = client.post(
        _ask_url(session_id),
        headers=_auth_headers(token),
        json={"question": "Anything in scope?", "document_ids": [document["id"]]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "empty_scope"

    rows = db_session.query(ChatMessage).all()
    user_rows = [r for r in rows if r.role == "user"]
    assistant_rows = [r for r in rows if r.role == "assistant"]
    assert len(user_rows) == 1 and user_rows[0].question == "Anything in scope?"
    assert len(assistant_rows) == 1
    assert assistant_rows[0].segments == []
    assert assistant_rows[0].empty_reason == "empty_scope"


def test_ask_cross_tenant_citation_is_dropped_not_leaked(client, monkeypatch):
    """Account B's request must never resolve a filename that belongs to
    account A -- even if a (mocked) retrieval result names account A's
    document_id, `get_filenames_for_documents`'s own user-scoping means
    that citation can't resolve, and the whole segment is dropped rather
    than leaking account A's filename to account B."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-chat@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-chat@example.com", password="password-account-b"
    )
    session_id_b = _create_session_id(client, token_b)
    document_a = _upload(client, token_a, filename="account-a-only.pdf")

    passages = [_passage(document_a["id"])]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="A claim about account A's document.", passage_numbers=[1])],
            included_passages=passages,
        ),
    )

    response_b = client.post(
        _ask_url(session_id_b), headers=_auth_headers(token_b), json={"question": "What does it say?"}
    )

    assert response_b.status_code == 200
    body = response_b.json()
    # The segment's only citation couldn't resolve (document isn't B's), so
    # the segment -- and therefore the whole answer -- is dropped.
    assert body["segments"] == []
    assert body["empty_reason"] == "no_answer"


def test_ask_cross_tenant_cannot_ask_into_another_accounts_session(client, monkeypatch):
    """Naming account A's own `session_id` from account B's token must
    404, the same IDOR-safe outcome as any other cross-tenant resource
    access in this codebase -- never a 403 that would confirm the id
    exists, and never silently answered into A's session."""
    token_a = _register_and_login(
        client, full_name="Account A", email="account-a-chat-session@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="account-b-chat-session@example.com", password="password-account-b"
    )
    session_id_a = _create_session_id(client, token_a)

    response = client.post(
        _ask_url(session_id_a), headers=_auth_headers(token_b), json={"question": "What does it say?"}
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Story 3.4/FR-17: persistence and history threading.
# ---------------------------------------------------------------------------


def test_pair_messages_into_turns_pairs_a_clean_alternating_sequence():
    messages = [
        ChatMessage(role="user", question="Q1?"),
        ChatMessage(role="assistant", segments=[{"text": "A1.", "citations": []}]),
        ChatMessage(role="user", question="Q2?"),
        ChatMessage(role="assistant", segments=[{"text": "A2.", "citations": []}]),
    ]

    turns = chat_service_module._pair_messages_into_turns(messages)

    assert [(t.question, t.answer) for t in turns] == [("Q1?", "A1."), ("Q2?", "A2.")]


def test_pair_messages_into_turns_skips_defensively_on_a_non_alternating_shape():
    """`_pair_messages_into_turns` assumes strict user/assistant
    alternation -- a shape this codebase's own writer (`_finish`) never
    produces, since it always persists a turn's two rows together. The
    defensive `else: i += 1` branch exists so a future writer bug
    degrades to "history threading silently skips a row" rather than a
    crash that would take the whole question down with it -- pinned
    here directly since nothing else in the test suite exercises it.

    An assistant row immediately followed by a user row (reversed
    order) can never satisfy the pairing condition at any offset -- `i`
    just advances by 1 through the whole list, producing zero turns."""
    reversed_pair = [
        ChatMessage(role="assistant", segments=[{"text": "Orphaned answer.", "citations": []}]),
        ChatMessage(role="user", question="Orphaned question?"),
    ]

    assert chat_service_module._pair_messages_into_turns(reversed_pair) == []


def test_pair_messages_into_turns_recovers_after_a_malformed_leading_row():
    """A malformed leading row (two `user` rows back to back) is skipped
    one position at a time -- but a valid pairing later in the list
    still comes through; the defensive branch doesn't poison the rest
    of the list, only the malformed prefix."""
    messages = [
        ChatMessage(role="user", question="Orphaned first question?"),
        ChatMessage(role="user", question="Q2?"),
        ChatMessage(role="assistant", segments=[{"text": "A2.", "citations": []}]),
    ]

    turns = chat_service_module._pair_messages_into_turns(messages)

    assert [(t.question, t.answer) for t in turns] == [("Q2?", "A2.")]


def test_ask_persists_user_and_assistant_messages_on_success(client, db_session, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-persist-1@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    passages = [_passage(document["id"], chapter="Chapter 4")]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="The refund window is 30 days.", passage_numbers=[1])],
            included_passages=passages,
        ),
    )

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What is the refund window?"}
    )
    assert response.status_code == 200

    rows = db_session.query(ChatMessage).all()
    user_rows = [r for r in rows if r.role == "user"]
    assistant_rows = [r for r in rows if r.role == "assistant"]
    assert len(user_rows) == 1
    assert len(assistant_rows) == 1
    assert user_rows[0].question == "What is the refund window?"
    assert assistant_rows[0].empty_reason is None
    assert assistant_rows[0].segments == [
        {
            "text": "The refund window is 30 days.",
            "citations": [
                {"chapter": "Chapter 4", "document_filename": "Vendor_Agreement_2026.pdf", "chunk_indexes": [0]}
            ],
        }
    ]


def test_ask_persists_a_refusal_as_a_message_too(client, db_session, monkeypatch):
    """A refusal is still "the resulting assistant message" for this turn
    (the spec's own phrasing) -- a returning visit must show the same
    refusal the user saw live, not a silently-dropped turn."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-persist-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    passages = [_passage(document["id"], distance=RELEVANCE_THRESHOLD + 0.5)]
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: passages)
    generate_answer_mock = Mock()
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "Something unrelated?"}
    )
    assert response.status_code == 200
    assert response.json()["empty_reason"] == "refusal"

    assistant_rows = [r for r in db_session.query(ChatMessage).all() if r.role == "assistant"]
    assert len(assistant_rows) == 1
    assert assistant_rows[0].empty_reason == "refusal"
    assert assistant_rows[0].segments == []


def test_ask_does_not_persist_any_message_on_llm_wrapper_failure(client, db_session, monkeypatch):
    """The one documented non-persisted path (this story's I/O matrix):
    a `ChatCompletionError` -> 503 leaves zero rows behind, not a
    half-written turn (an orphaned question with no reply)."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-persist-3@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )

    def _raise_chat_completion_error(*a, **k):
        raise ChatCompletionError("OpenRouter chat generation failed after 2 attempts")

    monkeypatch.setattr(chat_service_module, "generate_answer", _raise_chat_completion_error)

    response = client.post(_ask_url(session_id), headers=_auth_headers(token), json={"question": "What is it?"})

    assert response.status_code == 503
    assert db_session.query(ChatMessage).count() == 0


def test_ask_fresh_conversation_retrieves_with_exactly_the_question(client, monkeypatch):
    """Boundaries: "a fresh conversation with zero prior turns behaves
    identically to today's stateless flow" -- asserted on the actual
    retrieval query, not just the response shape. Post-text2vec-weaviate
    that query is the string handed to `search_passages`; it used to be
    the list handed to `embed_texts`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-1@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    captured = {}

    def _capturing_search(query_text, *a, **k):
        captured["texts"] = [query_text]
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _capturing_search)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "First question ever?"}
    )

    assert response.status_code == 200
    assert captured["texts"] == ["First question ever?"]


def test_ask_fresh_conversation_calls_generate_answer_with_falsy_history(client, monkeypatch):
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )
    generate_answer_mock = Mock(
        return_value=AnswerResult(
            segments=[AnswerSegment(text="An answer.", passage_numbers=[1])],
            included_passages=[_passage(document["id"])],
        )
    )
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "First question ever?"}
    )

    assert response.status_code == 200
    _, kwargs = generate_answer_mock.call_args
    assert not kwargs["history"]


def test_ask_threads_prior_question_into_retrieval_query_text(client, db_session, monkeypatch):
    """Design Notes: retrieval query text = prior questions only, joined,
    then the current question -- never prior answer prose."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-3@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="Who is the vendor?",
        answer_text="TechCorp is the vendor.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    captured = {}

    def _capturing_search(query_text, *a, **k):
        captured["texts"] = [query_text]
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _capturing_search)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What about its refund window?"}
    )

    assert response.status_code == 200
    assert captured["texts"] == ["Who is the vendor?\nWhat about its refund window?"]
    # Never the prior answer text -- that would dilute the embedding with
    # answer prose instead of topical/entity words (the Boundaries' own
    # reasoning).
    assert "TechCorp" not in captured["texts"][0]


def test_ask_threads_full_prior_turn_into_generate_answer_history(client, db_session, monkeypatch):
    """Design Notes: the generation prompt gets full Q+A (citations
    stripped), unlike retrieval's questions-only text -- the LLM needs
    prior answer content to resolve "its"."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-4@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="Who is the vendor?",
        answer_text="TechCorp is the vendor.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )
    generate_answer_mock = Mock(
        return_value=AnswerResult(
            segments=[AnswerSegment(text="An answer.", passage_numbers=[1])],
            included_passages=[_passage(document["id"])],
        )
    )
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "What about its refund window?"}
    )

    assert response.status_code == 200
    args, kwargs = generate_answer_mock.call_args
    history = kwargs["history"]
    assert len(history) == 1
    assert history[0].question == "Who is the vendor?"
    assert history[0].answer == "TechCorp is the vendor."


def test_ask_history_window_capped_at_three_turns(client, db_session, monkeypatch):
    """Boundaries: "never exceeds 3 turns / 2000 characters" -- five prior
    turns exist, but only the newest 3 are threaded into
    `generate_answer`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-5@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        _seed_turn(
            db_session,
            user_id,
            session_id,
            question=f"Question {i}?",
            answer_text=f"Answer {i}.",
            created_at=base + timedelta(seconds=i),
        )
    document = _upload(client, token)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )
    generate_answer_mock = Mock(
        return_value=AnswerResult(
            segments=[AnswerSegment(text="An answer.", passage_numbers=[1])],
            included_passages=[_passage(document["id"])],
        )
    )
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "A sixth question?"}
    )

    assert response.status_code == 200
    _, kwargs = generate_answer_mock.call_args
    history = kwargs["history"]
    assert len(history) == 3
    # The newest 3 of the 5 seeded turns, oldest-first.
    assert [t.question for t in history] == ["Question 2?", "Question 3?", "Question 4?"]


def test_ask_scope_change_mid_conversation_retrieves_only_current_scope(client, db_session, monkeypatch):
    """Boundaries: retrieval always uses the *current* scope selection;
    history supplies conversational context only, never widens/narrows
    the document boundary -- even though turn 1 was scoped to document A,
    turn 2's scope (document B only) is all that reaches `search_passages`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-6@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document_a = _upload(client, token, filename="doc-a.pdf")
    document_b = _upload(client, token, filename="doc-b.pdf", content=b"%PDF-1.4 different bytes entirely")
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="What does document A say?",
        answer_text="Document A says X.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    captured = {}

    def _fake_search_passages(query_text, user_id_arg, **kwargs):
        captured["document_ids"] = kwargs.get("document_ids")
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _fake_search_passages)

    response = client.post(
        _ask_url(session_id),
        headers=_auth_headers(token),
        json={"question": "What about it?", "document_ids": [document_b["id"]]},
    )

    assert response.status_code == 200
    # Only document B's scope reaches search_passages -- document A (used
    # by the earlier turn) never widens it back in.
    assert captured["document_ids"] == [document_b["id"]]


def test_ask_scope_change_with_multiple_prior_turns_still_respects_current_scope(
    client, db_session, monkeypatch
):
    """The single-prior-turn variant above proves the scope boundary
    isn't widened by history; this proves the same holds when there's an
    actual multi-turn window in play (2 prior turns, within
    HISTORY_MAX_TURNS=3) -- scope narrows to document B on turn 3, but
    the history window itself (built from turns scoped to document A)
    must still thread through unaffected, since history supplies
    conversational context only and is never itself scope-filtered."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-multi-scope@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    document_a = _upload(client, token, filename="doc-a-multi.pdf", content=b"%PDF-1.4 doc a multi")
    document_b = _upload(
        client, token, filename="doc-b-multi.pdf", content=b"%PDF-1.4 doc b multi entirely different"
    )
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="What does document A say about pricing?",
        answer_text="Document A's price is 100 USD.",
        created_at=base,
    )
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="What about delivery?",
        answer_text="Delivery takes 5 days.",
        created_at=base + timedelta(seconds=1),
    )
    captured = {}

    def _fake_search_passages(query_text, user_id_arg, **kwargs):
        captured["query_text"] = query_text
        captured["document_ids"] = kwargs.get("document_ids")
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _fake_search_passages)

    response = client.post(
        _ask_url(session_id),
        headers=_auth_headers(token),
        json={"question": "What about warranty?", "document_ids": [document_b["id"]]},
    )

    assert response.status_code == 200
    # Scope still narrows to document B alone, exactly as the single-turn
    # case -- two prior turns in the window don't change that.
    assert captured["document_ids"] == [document_b["id"]]
    # But the history window itself (built from turns scoped to document
    # A) still threads through unaffected -- both prior questions appear
    # in the retrieval query text, proving scope-narrowing on this turn
    # didn't also silently drop the multi-turn history window.
    query_text = captured["query_text"]
    assert "What does document A say about pricing?" in query_text
    assert "What about delivery?" in query_text
    assert "What about warranty?" in query_text


def test_ask_does_not_thread_another_sessions_history(client, db_session, monkeypatch):
    """Multi-session chat's core isolation guarantee applied to history
    threading specifically: a prior turn seeded into a DIFFERENT session
    of the same account must never appear in this session's retrieval
    query text or `generate_answer` history, even though both sessions
    share one `user_id`."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-history-isolation@example.com", password="password12345"
    )
    other_session_id = _create_session_id(client, token)
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    _seed_turn(
        db_session,
        user_id,
        other_session_id,
        question="Who is the vendor?",
        answer_text="TechCorp is the vendor.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    captured = {}

    def _capturing_search(query_text, *a, **k):
        captured["texts"] = [query_text]
        return []

    monkeypatch.setattr(chat_service_module, "search_passages", _capturing_search)

    response = client.post(
        _ask_url(session_id), headers=_auth_headers(token), json={"question": "First question in this session?"}
    )

    assert response.status_code == 200
    # Exactly the fresh-conversation shape -- the other session's turn
    # never leaked in.
    assert captured["texts"] == ["First question in this session?"]


def test_ask_with_use_history_false_skips_the_history_read_entirely(client, db_session, monkeypatch):
    """Story 3.4: `use_history=False` (the flag `scripts/eval_harness.py`
    passes so Epic 6's measurement stays single-question, as OD-3's
    baseline and OD-2's threshold calibration both assume) must make the
    retrieval/generation calls byte-identical to the fresh-conversation
    shapes -- and must not even query for the window, so an opted-out
    caller can't drift with whatever happens to be persisted on its
    account."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-nohistory@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    _seed_turn(
        db_session,
        user_id,
        session_id,
        question="Who is the vendor?",
        answer_text="TechCorp is the vendor.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    document = _upload(client, token)
    captured = {}

    def _capturing_search(query_text, *a, **k):
        captured["texts"] = [query_text]
        return [_passage(document["id"])]

    monkeypatch.setattr(chat_service_module, "search_passages", _capturing_search)
    generate_answer_mock = Mock(
        return_value=AnswerResult(
            segments=[AnswerSegment(text="An answer.", passage_numbers=[1])],
            included_passages=[_passage(document["id"])],
        )
    )
    monkeypatch.setattr(chat_service_module, "generate_answer", generate_answer_mock)
    recent_turns_mock = Mock(return_value=[])
    monkeypatch.setattr(
        chat_service_module.repository, "get_recent_turn_messages", recent_turns_mock
    )

    from app.shared.models import User

    user = db_session.get(User, user_id)
    response = chat_service_module.ask_question(
        db_session, user, session_id, "What about its refund window?", [], use_history=False
    )

    assert response.empty_reason is None
    # The DB round-trip itself is skipped, not merely its result ignored.
    recent_turns_mock.assert_not_called()
    # Exactly the pre-3.4 shapes: the bare question, and falsy history.
    assert captured["texts"] == ["What about its refund window?"]
    assert not generate_answer_mock.call_args.kwargs["history"]


def test_ask_still_persists_the_turn_when_use_history_is_false(client, db_session, monkeypatch):
    """The opt-out gates the *read* half only -- `_finish`'s "every path
    except the 503 path persists" invariant holds for every caller,
    without an exception carved out for this flag."""
    token = _register_and_login(
        client, full_name="Maria", email="maria-chat-nohistory-2@example.com", password="password12345"
    )
    session_id = _create_session_id(client, token)
    user_id = uuid.UUID(client.get("/auth/me", headers=_auth_headers(token)).json()["id"])
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    from app.shared.models import User

    user = db_session.get(User, user_id)
    chat_service_module.ask_question(db_session, user, session_id, "Any documents?", [], use_history=False)

    rows = (
        db_session.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.role.desc())
        .all()
    )
    assert [r.role for r in rows] == ["user", "assistant"]
    assert rows[0].question == "Any documents?"
    assert rows[1].empty_reason == "no_documents"
