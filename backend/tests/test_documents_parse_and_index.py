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
    """Stubs `delete_passages_for_document` -- `ingest_document` calls it
    directly (for real, not through `write_passages`) before its batch
    loop, so every test that doesn't stub it would otherwise try a real
    Weaviate connection, not just the ones that happen to mock
    `write_passages`.

    No longer stubs any embedding call: embeddings are computed by
    Weaviate server-side (text2vec-weaviate), so `ingest_document` does no
    embedding work in-process for a test to stub out. Kept under its
    original name, and still called by every test here, because the
    Weaviate-connection stubbing above is what those tests actually
    depend on."""
    from unittest.mock import Mock

    import app.documents.service as service_module

    monkeypatch.setattr(service_module, "delete_passages_for_document", Mock())


def _stub_graphing(monkeypatch):
    """Stubs Story 2.4's Graphing step (`extract_entities_and_relationships`
    + `write_entities_and_relationships`, and Story 2.8's own
    `prune_document_from_graph`, called by `ingest_document` right before
    the write) so tests in this file -- which predate Story 2.4 and only
    care about the Weaviate write path -- can let `ingest_document` run
    all the way to `Ready` without a real OpenRouter/Neo4j connection. An
    empty extraction result is a valid, successful outcome (the story's own
    "no notable entities" scenario), not a failure -- exactly what's wanted
    here, since these tests aren't exercising entity extraction at all."""
    from unittest.mock import Mock

    import app.documents.service as service_module
    from app.shared.llm_client import ExtractionResult

    monkeypatch.setattr(
        service_module, "extract_entities_and_relationships", lambda text: ExtractionResult()
    )
    monkeypatch.setattr(service_module, "write_entities_and_relationships", Mock())
    monkeypatch.setattr(service_module, "prune_document_from_graph", Mock())


def test_ingest_markdown_produces_passages_tagged_with_document_chapter_chunk_index(
    client, db_session, monkeypatch
):
    import app.documents.service as service_module

    from unittest.mock import Mock

    _stub_embeddings(monkeypatch)
    _stub_graphing(monkeypatch)
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
    assert {p.chapter for p in passages} == {"Chapter One", "Chapter Two"}


def test_ingest_pdf_and_html_each_produce_at_least_one_passage(client, db_session, monkeypatch):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    _stub_graphing(monkeypatch)

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
    _stub_graphing(monkeypatch)
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
        }
        for field_name in field_names:
            assert not isinstance(getattr(passage, field_name), dict)


def test_ingest_user_id_on_every_passage_is_jwt_derived_not_client_supplied(
    client, db_session, monkeypatch
):
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    _stub_graphing(monkeypatch)
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


def test_ingest_advances_status_from_uploaded_all_the_way_to_ready(client, db_session, monkeypatch):
    """Story 2.3 pinned the advance to `Extracting`; Story 2.4 extends the
    same pipeline past `Graphing` to `Ready` once the (here stubbed) Neo4j
    write succeeds too -- this test now pins the full chain rather than
    stopping partway, since `ingest_document` no longer stops at
    `Extracting` on success."""
    from unittest.mock import Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)
    _stub_graphing(monkeypatch)
    monkeypatch.setattr(service_module, "write_passages", Mock())

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-status@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")
    assert doc["status"] == "Uploaded"

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Ready"
    assert row.chapter_breakdown == {"Chapter One": 1, "Chapter Two": 1}


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
    assert row.failed_reason is not None
    assert row.failed_reason.startswith("Could not read this document")


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
    assert row.failed_reason is not None
    assert row.failed_reason.startswith("Could not index this document's content")
    # A driver's own message is NOT user-facing text -- Weaviate/Neo4j/
    # SQLAlchemy errors carry hostnames, ports and sometimes
    # credential-bearing URLs. Only the stage label reaches the row.
    assert "Weaviate is unreachable" not in row.failed_reason


def test_ingest_failure_from_an_opaque_exception_withholds_its_message(
    client, db_session, monkeypatch
):
    """Story 2.5: an exception this project didn't author for a user to
    read contributes its stage label only -- never its message, however
    short. Regression test for an OpenRouter 404 whose raw JSON body (with
    the account's provider `user_id` in it) reached the UI verbatim; the
    old behaviour truncated `str(exc)` to 300 chars, which bounded the
    length of that leak without preventing it."""
    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)

    secret = "postgres://admin:hunter2@db.internal:5432 -- " + "x" * 5000

    def _raise(passages):
        raise RuntimeError(secret)

    monkeypatch.setattr(service_module, "write_passages", _raise)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-long-fail@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"
    assert row.failed_reason is not None
    label = "Could not index this document's content"
    assert row.failed_reason == f"{label}. Please try uploading it again."
    assert "hunter2" not in row.failed_reason
    assert "x" * 50 not in row.failed_reason


def test_ingest_failure_from_an_unparseable_document_keeps_its_message(
    client, db_session, monkeypatch
):
    """The other side of the allowlist: `UnparseableDocument` is raised by
    this project with a message written to be read, so it still reaches the
    user -- that's the difference between redacting and going silent."""
    import app.documents.service as service_module
    from app.documents.parsing import UnparseableDocument

    _stub_embeddings(monkeypatch)

    def _raise(file_type, content):
        raise UnparseableDocument("Could not decode Markdown as UTF-8.")

    monkeypatch.setattr(service_module, "parse_document", _raise)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-unparseable@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"
    assert row.failed_reason == (
        "Could not read this document: Could not decode Markdown as UTF-8."
    )


def test_ingest_missing_document_returns_silently(db_session):
    real_ingest_document(uuid.uuid4(), session_factory=_session_factory(db_session))


def test_ingest_cleans_up_partially_written_passages_on_failure(client, db_session, monkeypatch):
    """A failure partway through the batch loop (batch 2 of many, say)
    must not leave the earlier batches' passages orphaned in Weaviate
    under a document that's about to be marked Failed -- Epic 3's
    retrieval filters by user_id only, not status, so an orphaned partial
    set would otherwise read as a complete, valid document."""
    from unittest.mock import ANY, Mock

    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)

    def _raise(passages):
        raise RuntimeError("Weaviate is unreachable")

    monkeypatch.setattr(service_module, "write_passages", _raise)
    fake_delete = Mock()
    monkeypatch.setattr(service_module, "delete_passages_for_document", fake_delete)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-orphan-cleanup@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    # Once up front (before the batch loop) and once more as cleanup after
    # the write failure -- both calls target the same (document_id,
    # user_id), so cleanup is idempotent with the initial delete either way.
    assert fake_delete.call_count == 2
    for call in fake_delete.call_args_list:
        assert call.args == (doc["id"], ANY)

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"


def test_ingest_embeds_and_writes_in_batches_not_all_chunks_at_once(
    client, db_session, monkeypatch
):
    """A large document must reach Weaviate in batches, not as one call
    carrying every chunk.

    The original reason was Python-side memory (a whole document's worth
    of 384-dim vectors alive at once). That's gone -- no vectors are built
    in this process any more -- but batching still matters for two other
    reasons, so the guarantee is still worth pinning: a single oversized
    `insert_many` payload Weaviate may reject, and Weaviate Embeddings
    request count, since each batch is one request against the free tier's
    daily allowance. `parse_document` is stubbed to return more chunks
    than `PASSAGE_BATCH_SIZE` without needing a genuinely huge upload."""
    from unittest.mock import Mock

    import app.documents.service as service_module
    from app.documents.parsing import ParsedChunk

    _stub_embeddings(monkeypatch)
    _stub_graphing(monkeypatch)

    chunk_count = service_module.PASSAGE_BATCH_SIZE * 2 + 5
    fake_chunks = [
        ParsedChunk(chapter="Chapter", chunk_index=i, text=f"chunk {i} text")
        for i in range(chunk_count)
    ]
    monkeypatch.setattr(service_module, "parse_document", lambda file_type, content: fake_chunks)

    fake_write_passages = Mock()
    monkeypatch.setattr(service_module, "write_passages", fake_write_passages)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-batching@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    service_module.delete_passages_for_document.assert_called_once()

    # 3 batches: two full PASSAGE_BATCH_SIZE ones plus a small remainder --
    # writing happens per batch, not once for everything.
    batch_size = service_module.PASSAGE_BATCH_SIZE
    assert fake_write_passages.call_count == 3
    assert [len(c.args[0]) for c in fake_write_passages.call_args_list] == [
        batch_size,
        batch_size,
        5,
    ]
    for call in fake_write_passages.call_args_list:
        assert len(call.args[0]) <= batch_size
    total_written = sum(len(call.args[0]) for call in fake_write_passages.call_args_list)
    assert total_written == chunk_count


class _FailSecondCommitSession:
    """Wraps a real `Session`, letting the first `commit()` through (the
    `Extracting` write) but raising on the second (the `Failed` recovery
    write) -- simulates the DB connection dropping mid-recovery, plausibly
    the very reason ingestion failed in the first place."""

    def __init__(self, real_session):
        self._real = real_session
        self._commit_calls = 0

    def commit(self):
        self._commit_calls += 1
        if self._commit_calls == 1:
            return self._real.commit()
        raise RuntimeError("simulated connection drop during recovery")

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_ingest_recovery_failure_does_not_propagate_and_row_stays_reachable(
    client, db_session, monkeypatch, caplog
):
    """The except block's own rollback/status=Failed/commit can itself
    raise (e.g. the connection is what dropped). That must be caught and
    logged, not left to escape `ingest_document` unhandled -- an escaping
    exception here would leave the row stuck at `Extracting` with no
    caller left to handle it, exactly what the except block exists to
    prevent."""
    import app.documents.service as service_module

    _stub_embeddings(monkeypatch)

    def _raise(passages):
        raise RuntimeError("Weaviate is unreachable")

    monkeypatch.setattr(service_module, "write_passages", _raise)

    token = _register_and_login(
        client, full_name="Ingest User", email="ingest-double-fail@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_session_factory = _session_factory(db_session)
    wrapped_factory = lambda: _FailSecondCommitSession(real_session_factory())  # noqa: E731

    with caplog.at_level("ERROR"):
        # Must not raise -- this is the assertion. A regression here means
        # the exception escaped the background task unhandled.
        real_ingest_document(uuid.UUID(doc["id"]), session_factory=wrapped_factory)

    assert "Ingestion failed for document" in caplog.text
    assert "Failed to mark document" in caplog.text
