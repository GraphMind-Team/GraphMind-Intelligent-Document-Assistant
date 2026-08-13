"""Ingestion pipeline tests (Story 2.3): parsing produces tagged passages,
the write goes through the flat-shape shared repository function with a
JWT-derived `user_id`, status advances Uploaded -> Extracting, and a
parse/write failure marks the row Failed instead of leaving it stuck.

`_stub_ingestion_pipeline` (conftest.py, autouse) replaces
`service.ingest_document` with a no-op `Mock` for every test by default,
so route-triggered uploads elsewhere in the suite don't exercise real
parsing. This file imports the *real* function at module load time --
before that per-test patch ever runs -- and calls it directly with an
explicit `session_factory` bound to the test's own SQLite engine,
bypassing `BackgroundTasks` (and the stub) entirely.
"""

import uuid

from sqlalchemy.orm import sessionmaker

from app.documents.service import ingest_document as real_ingest_document
from app.shared.models import Document

_MINIMAL_PDF = b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 200 200] /Contents 5 0 R >>endobj
4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
5 0 obj<< /Length 44 >>
stream
BT /F1 12 Tf 10 100 Td (Hello World) Tj ET
endstream
endobj
xref
0 6
trailer<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF"""

_MARKDOWN = b"# Chapter One\n\nSome intro text here.\n\n## Chapter Two\n\nMore content here."

_HTML = b"<html><body><h1>Intro</h1><p>Hello from HTML.</p></body></html>"


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    body = login_response.json()
    return body["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _upload(client, token, filename, content, content_type):
    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _session_factory(db_session):
    return sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)


def _stub_embeddings(monkeypatch):
    """`embed_texts` is stubbed here (rather than exercising the real
    `fastembed` model) so these tests stay fast and deterministic -- the
    real model is exercised separately in test_embeddings.py."""
    import app.documents.service as service_module

    monkeypatch.setattr(service_module, "embed_texts", lambda texts: [[0.0] * 384 for _ in texts])


def test_ingest_markdown_produces_passages_tagged_with_document_chapter_chunk_index(
    client, db_session, monkeypatch
):
    import app.documents.service as service_module

    from unittest.mock import Mock

    _stub_embeddings(monkeypatch)
    fake_write_passages = Mock()
    monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-md@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    fake_write_passages.assert_called_once()
    passages = fake_write_passages.call_args.args[0]
    assert len(passages) >= 1
    for index, passage in enumerate(passages):
        assert passage.document_id == doc["id"]
        assert passage.chunk_index == index
        assert passage.chapter
        assert passage.text.strip()
        assert passage.embedding == [0.0] * 384
    assert {p.chapter for p in passages} == {"Chapter One", "Chapter Two"}


def test_ingest_pdf_and_html_each_produce_at_least_one_passage(client, db_session, monkeypatch):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-pdf-html@example.com", password="password12345"
    )

    for filename, content, content_type in (
        ("report.pdf", _MINIMAL_PDF, "application/pdf"),
        ("page.html", _HTML, "text/html"),
    ):
        fake_write_passages = Mock()
        monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

        doc = _upload(client, token, filename, content, content_type)
        real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

        fake_write_passages.assert_called_once()
        passages = fake_write_passages.call_args.args[0]
        assert len(passages) >= 1


def test_ingest_writes_flat_shape_with_no_nested_dict(client, db_session, monkeypatch):
    import dataclasses
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    fake_write_passages = Mock()
    monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-shape@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    passages = fake_write_passages.call_args.args[0]
    for passage in passages:
        field_names = {f.name for f in dataclasses.fields(passage)}
        assert field_names == {
            "chunk_id",
            "document_id",
            "user_id",
            "chapter",
            "chunk_index",
            "text",
            "embedding",
        }
        for field_name in field_names:
            assert not isinstance(getattr(passage, field_name), dict)


def test_ingest_user_id_on_every_passage_is_jwt_derived_not_client_supplied(
    client, db_session, monkeypatch
):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    fake_write_passages = Mock()
    monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

    token = _register_and_login(
        client, full_name="Real Owner", email="ingest-owner@example.com", password="password12345"
    )
    me = client.get("/auth/me", headers=_auth_headers(token))
    assert me.status_code == 200, me.text
    real_owner_id = me.json()["id"]

    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")
    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    passages = fake_write_passages.call_args.args[0]
    assert passages
    for passage in passages:
        assert passage.user_id == real_owner_id


def test_ingest_advances_status_from_uploaded_to_extracting(client, db_session, monkeypatch):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    monkeypatch.setattr(service_module, "write_passages", Mock())

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-status@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")
    assert doc["status"] == "Uploaded"

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Extracting"


def test_ingest_corrupt_file_marks_failed_instead_of_stuck(client, db_session, monkeypatch):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    fake_write_passages = Mock()
    monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-corrupt@example.com", password="password12345"
    )
    # Extension/content-type checks pass (only format/size are validated at
    # upload time -- deferred-work.md's known, accepted gap); the bytes
    # themselves aren't a real PDF, so parsing must fail gracefully.
    doc = _upload(client, token, "report.pdf", b"not a real pdf", "application/pdf")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"
    fake_write_passages.assert_not_called()


def test_ingest_weaviate_write_failure_marks_failed(client, db_session, monkeypatch):
    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)

    def _raise(passages):
        raise RuntimeError("Weaviate is unreachable")

    monkeypatch.setattr(service_module, "write_passages", _raise)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-weaviate-fail@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"


def test_ingest_missing_document_returns_silently(db_session):
    real_ingest_document(uuid.uuid4(), session_factory=_session_factory(db_session))
