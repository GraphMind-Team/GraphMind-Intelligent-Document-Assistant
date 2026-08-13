"""`POST /chat/ask` tests (Story 3.1): auth requirement, Pydantic-level
question validation (422, not a manual 400), the two distinct empty_reason
outcomes ("no_documents" vs "no_answer"), the exact 503 point for an
LLM-wrapper failure, cross-tenant isolation of citation resolution, and a
full success path resolving real `{chapter, document_filename}` citations.

`embed_texts`/`search_passages`/`generate_answer` are mocked at their
`app.chat.service`-bound names (the module-level names that module imported
them under), mirroring `test_documents_parse_and_index.py`'s
`_stub_embeddings` convention -- this file never touches a real embedding
model, Weaviate, or OpenRouter.
"""

from app.chat import service as chat_service_module
from app.shared.data_access.shapes import WeaviateSearchResult
from app.shared.llm_client import AnswerResult, AnswerSegment, ChatCompletionError


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


def _upload(client, token, filename="report.pdf"):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, b"%PDF-1.4 fake pdf bytes", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _stub_embed(monkeypatch):
    monkeypatch.setattr(chat_service_module, "embed_texts", lambda texts: [[0.0] * 384 for _ in texts])


def _passage(document_id, chapter="Chapter One", chunk_id="chunk-0", text="passage text"):
    return WeaviateSearchResult(
        chunk_id=chunk_id, document_id=document_id, chapter=chapter, chunk_index=0, text=text, distance=0.1
    )


def test_ask_requires_authentication(client):
    response = client.post("/chat/ask", json={"question": "What is the refund window?"})
    assert response.status_code == 401


def test_ask_rejects_blank_question_with_422_not_400(client):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-1@example.com", password="password12345")

    response = client.post("/chat/ask", headers=_auth_headers(token), json={"question": "   "})

    assert response.status_code == 422


def test_ask_rejects_over_length_question_with_422(client):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-2@example.com", password="password12345")

    response = client.post(
        "/chat/ask", headers=_auth_headers(token), json={"question": "x" * 2001}
    )

    assert response.status_code == 422


def test_ask_zero_passages_returns_no_documents_reason(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-3@example.com", password="password12345")
    _stub_embed(monkeypatch)
    monkeypatch.setattr(chat_service_module, "search_passages", lambda *a, **k: [])

    response = client.post("/chat/ask", headers=_auth_headers(token), json={"question": "Anything in my docs?"})

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "no_documents"


def test_ask_generation_producing_no_answerable_segments_returns_no_answer_reason(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-4@example.com", password="password12345")
    document = _upload(client, token)
    _stub_embed(monkeypatch)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )
    monkeypatch.setattr(
        chat_service_module, "generate_answer", lambda *a, **k: AnswerResult(segments=[])
    )

    response = client.post("/chat/ask", headers=_auth_headers(token), json={"question": "Unanswerable?"})

    assert response.status_code == 200
    body = response.json()
    assert body["segments"] == []
    assert body["empty_reason"] == "no_answer"


def test_ask_llm_wrapper_failure_surfaces_as_exactly_503(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-5@example.com", password="password12345")
    document = _upload(client, token)
    _stub_embed(monkeypatch)
    monkeypatch.setattr(
        chat_service_module, "search_passages", lambda *a, **k: [_passage(document["id"])]
    )

    def _raise_chat_completion_error(*a, **k):
        raise ChatCompletionError("OpenRouter chat generation failed after 2 attempts")

    monkeypatch.setattr(chat_service_module, "generate_answer", _raise_chat_completion_error)

    response = client.post("/chat/ask", headers=_auth_headers(token), json={"question": "What is it?"})

    assert response.status_code == 503
    assert "detail" in response.json()


def test_ask_success_resolves_real_chapter_and_filename_citations(client, monkeypatch):
    token = _register_and_login(client, full_name="Maria", email="maria-chat-6@example.com", password="password12345")
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    _stub_embed(monkeypatch)
    monkeypatch.setattr(
        chat_service_module,
        "search_passages",
        lambda *a, **k: [_passage(document["id"], chapter="Chapter 4")],
    )
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="The refund window is 30 days.", passage_numbers=[1])]
        ),
    )

    response = client.post(
        "/chat/ask", headers=_auth_headers(token), json={"question": "What is the refund window?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["empty_reason"] is None
    assert len(body["segments"]) == 1
    assert body["segments"][0]["text"] == "The refund window is 30 days."
    assert body["segments"][0]["citations"] == [
        {"chapter": "Chapter 4", "document_filename": "Vendor_Agreement_2026.pdf"}
    ]


def test_ask_deduplicates_repeated_chapter_and_filename_citations(client, monkeypatch):
    """Two different chunks from the same chapter of the same document
    (routine at TOP_K_PASSAGES=8) -- or a model repeating a
    passage_number, e.g. [1, 1] -- must render as one citation chip, not
    two identical ones side by side."""
    token = _register_and_login(client, full_name="Maria", email="maria-chat-dedup@example.com", password="password12345")
    document = _upload(client, token, filename="Vendor_Agreement_2026.pdf")
    _stub_embed(monkeypatch)
    monkeypatch.setattr(
        chat_service_module,
        "search_passages",
        lambda *a, **k: [
            _passage(document["id"], chapter="Chapter 4", chunk_id="chunk-a", text="first chunk"),
            _passage(document["id"], chapter="Chapter 4", chunk_id="chunk-b", text="second chunk"),
        ],
    )
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[
                AnswerSegment(text="A claim supported by both chunks.", passage_numbers=[1, 2]),
            ]
        ),
    )

    response = client.post(
        "/chat/ask", headers=_auth_headers(token), json={"question": "What does it say?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["segments"]) == 1
    assert body["segments"][0]["citations"] == [
        {"chapter": "Chapter 4", "document_filename": "Vendor_Agreement_2026.pdf"}
    ]


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
    document_a = _upload(client, token_a, filename="account-a-only.pdf")

    _stub_embed(monkeypatch)
    monkeypatch.setattr(
        chat_service_module,
        "search_passages",
        lambda *a, **k: [_passage(document_a["id"])],
    )
    monkeypatch.setattr(
        chat_service_module,
        "generate_answer",
        lambda *a, **k: AnswerResult(
            segments=[AnswerSegment(text="A claim about account A's document.", passage_numbers=[1])]
        ),
    )

    response_b = client.post(
        "/chat/ask", headers=_auth_headers(token_b), json={"question": "What does it say?"}
    )

    assert response_b.status_code == 200
    body = response_b.json()
    # The segment's only citation couldn't resolve (document isn't B's), so
    # the segment -- and therefore the whole answer -- is dropped.
    assert body["segments"] == []
    assert body["empty_reason"] == "no_answer"
