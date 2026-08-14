"""`ingest_document`'s Story 2.4 Graphing step: the full `Extracting ->
Graphing -> Ready` happy path (asserting `chapter_breakdown` ends up
populated from the same `chunks` list already used for the Weaviate write),
and both failure branches -- the LLM call exhausting retries, and the
Neo4j write failing -- each asserting AD-1's compensating rollback runs
(Weaviate passages deleted, status ends `Failed`) and that
`chapter_breakdown` stays `None` rather than a partial value.

Mirrors `test_documents_parse_and_index.py`'s harness: imports the real
`ingest_document` at module load time (before `conftest.py`'s autouse
`_stub_ingestion_pipeline` patches it to a no-op per test) and calls it
directly with an explicit `session_factory`, bypassing `BackgroundTasks`.
"""

import uuid
from unittest.mock import Mock

from sqlalchemy.orm import sessionmaker

from app.documents.parsing import CHUNK_OVERLAP_WORDS, ParsedChunk
from app.documents.service import _build_extraction_text
from app.documents.service import ingest_document as real_ingest_document
from app.shared.llm_client import ExtractedEntity, ExtractedRelationship, ExtractionError, ExtractionResult
from app.shared.models import Document

_MARKDOWN = (
    b"# Chapter One\n\nMaria Ivanova works at TechCorp.\n\n"
    b"## Chapter Two\n\nTechCorp is based in Sofia."
)

# Chapters deliberately in *reverse* alphabetical document order, and
# "Zebra Chapter" long enough (260 words, over the 250-word chunk size) to
# split into 2 chunks -- a `chapter_breakdown` bug that silently sorted
# keys instead of preserving first-appearance order would produce
# {"Alpha Chapter": 1, "Zebra Chapter": 2} here, indistinguishable by `==`
# from the correct {"Zebra Chapter": 2, "Alpha Chapter": 1} unless order
# is checked explicitly (dict `==` in Python ignores key order).
_MARKDOWN_REVERSE_CHAPTER_ORDER = (
    b"# Zebra Chapter\n\n" + b"word " * 260 + b"\n\n"
    b"## Alpha Chapter\n\nJust one short paragraph."
)


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


def _stub_pipeline(monkeypatch, *, write_passages=None, extract=None, write_graph=None):
    """Stubs every external call `ingest_document` makes -- embeddings,
    Weaviate, OpenRouter (via `llm_client`), Neo4j -- so a test can control
    exactly one of them (the one it's exercising) while the rest behave
    like a normal success. Returns the `delete_passages_for_document` mock
    so callers can assert on cleanup calls."""
    import app.documents.service as service_module

    monkeypatch.setattr(service_module, "embed_texts", lambda texts: [[0.0] * 384 for _ in texts])
    fake_delete = Mock()
    monkeypatch.setattr(service_module, "delete_passages_for_document", fake_delete)
    monkeypatch.setattr(service_module, "write_passages", write_passages or Mock())
    monkeypatch.setattr(
        service_module,
        "extract_entities_and_relationships",
        extract or (lambda text: ExtractionResult()),
    )
    monkeypatch.setattr(service_module, "write_entities_and_relationships", write_graph or Mock())
    return fake_delete


def test_extraction_text_drops_the_chunk_overlap_within_a_chapter():
    """Chunks overlap by `CHUNK_OVERLAP_WORDS` on purpose (Story 2.3, so a
    passage straddling a boundary stays retrievable whole), but re-sending
    those words to the LLM would spend ~16% of the extraction budget
    re-reading text the model already saw. The overlap must be stripped
    back off exactly once per same-chapter boundary."""
    first_words = [f"w{i}" for i in range(CHUNK_OVERLAP_WORDS + 5)]
    # How the chunker builds it: chunk 2 restarts `CHUNK_OVERLAP_WORDS`
    # words back into chunk 1's tail.
    overlap = first_words[-CHUNK_OVERLAP_WORDS:]
    second_only = ["fresh1", "fresh2", "fresh3"]

    chunks = [
        ParsedChunk(chapter="Chapter One", chunk_index=0, text=" ".join(first_words)),
        ParsedChunk(chapter="Chapter One", chunk_index=1, text=" ".join(overlap + second_only)),
    ]

    text = _build_extraction_text(chunks)

    # The duplicated words appear once (from chunk 1), not twice.
    assert text.count("w%d" % (CHUNK_OVERLAP_WORDS + 4)) == 1
    # The genuinely new words in chunk 2 all survive.
    for word in second_only:
        assert word in text


def test_extraction_text_keeps_a_new_chapters_first_chunk_intact():
    """Only chunks *after the first in the same chapter* carry overlap --
    a new chapter starts fresh. Stripping its opening words would silently
    delete real content (and, for a chapter shorter than the overlap, most
    of it)."""
    chunks = [
        ParsedChunk(chapter="Chapter One", chunk_index=0, text="alpha beta gamma"),
        ParsedChunk(chapter="Chapter Two", chunk_index=1, text="delta epsilon zeta"),
    ]

    text = _build_extraction_text(chunks)

    for word in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"):
        assert word in text


def test_extraction_text_respects_the_character_budget():
    chunks = [
        ParsedChunk(chapter="Chapter One", chunk_index=0, text="x" * 500),
        ParsedChunk(chapter="Chapter Two", chunk_index=1, text="y" * 500),
    ]

    text = _build_extraction_text(chunks, budget=600)

    # The joiner adds a couple of characters per boundary on top of the
    # sliced content; the budget bounds the content itself.
    assert len(text.replace("\n\n", "")) == 600


def test_full_pipeline_reaches_ready_with_populated_chapter_breakdown(client, db_session, monkeypatch):
    extraction_result = ExtractionResult(
        entities=[
            ExtractedEntity(name="Maria Ivanova", type="Person"),
            ExtractedEntity(name="TechCorp", type="Organization"),
        ],
        relationships=[
            ExtractedRelationship(source="Maria Ivanova", target="TechCorp", type="WORKS_AT"),
        ],
    )
    fake_write_graph = Mock()
    _stub_pipeline(monkeypatch, extract=lambda text: extraction_result, write_graph=fake_write_graph)

    token = _register_and_login(
        client, full_name="Graph User", email="graph-happy@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Ready"
    # Known chunk data: one chunk per chapter (each chapter is far under
    # the 250-word chunk size), so each chapter contributes exactly 1 --
    # computed from the same `chunks` list the Weaviate write already used,
    # not re-derived independently.
    assert row.chapter_breakdown == {"Chapter One": 1, "Chapter Two": 1}

    fake_write_graph.assert_called_once()
    written_entities, written_relationships, written_user_id = fake_write_graph.call_args.args
    assert {(e.name, e.type) for e in written_entities} == {
        ("Maria Ivanova", "Person"),
        ("TechCorp", "Organization"),
    }
    assert [(r.source_entity_name, r.target_entity_name, r.relationship_type) for r in written_relationships] == [
        ("Maria Ivanova", "TechCorp", "WORKS_AT")
    ]
    assert written_user_id == str(row.user_id)
    assert all(e.user_id == written_user_id for e in written_entities)
    assert all(r.user_id == written_user_id for r in written_relationships)


def test_chapter_breakdown_preserves_document_reading_order_not_sorted(client, db_session, monkeypatch):
    """`chapter_breakdown`'s key order must match the document's own
    chapter order (first-appearance order via `Counter`), not an
    alphabetical or otherwise re-sorted order -- the Detail page's chapter
    breakdown list renders this order as-is with no client-side sort."""
    _stub_pipeline(monkeypatch)

    token = _register_and_login(
        client, full_name="Graph User", email="graph-order@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN_REVERSE_CHAPTER_ORDER, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Ready"
    # "Zebra Chapter" (260 words) splits into 2 chunks; "Alpha Chapter"
    # into 1 -- and Zebra must come first, matching document order, even
    # though it sorts after Alpha alphabetically.
    assert list(row.chapter_breakdown.items()) == [("Zebra Chapter", 2), ("Alpha Chapter", 1)]


def test_empty_extraction_still_reaches_ready(client, db_session, monkeypatch):
    """"No notable entities" is a valid outcome, not a failure (the
    story's I/O matrix) -- the document must still reach `Ready` with its
    `chapter_breakdown` populated even though nothing was extracted."""
    _stub_pipeline(monkeypatch, extract=lambda text: ExtractionResult())

    token = _register_and_login(
        client, full_name="Graph User", email="graph-empty@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Ready"
    assert row.chapter_breakdown == {"Chapter One": 1, "Chapter Two": 1}


def test_llm_extraction_failure_deletes_weaviate_passages_and_marks_failed(client, db_session, monkeypatch):
    def _raise(text):
        raise ExtractionError("OpenRouter entity extraction failed after 2 attempts")

    fake_delete = _stub_pipeline(monkeypatch, extract=_raise)

    token = _register_and_login(
        client, full_name="Graph User", email="graph-llm-fail@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"
    assert row.chapter_breakdown is None
    assert row.failed_reason is not None
    assert row.failed_reason.startswith("Could not extract entities from this document")
    assert "OpenRouter entity extraction failed after 2 attempts" in row.failed_reason

    # Once up front (before the Weaviate batch loop) and once more as the
    # AD-1 compensating rollback after the Graphing-step failure.
    assert fake_delete.call_count == 2


def test_neo4j_write_failure_deletes_weaviate_passages_and_marks_failed(client, db_session, monkeypatch):
    def _raise(entities, relationships, user_id):
        raise RuntimeError("Neo4j is unreachable")

    fake_delete = _stub_pipeline(monkeypatch, write_graph=_raise)

    token = _register_and_login(
        client, full_name="Graph User", email="graph-neo4j-fail@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status == "Failed"
    assert row.chapter_breakdown is None
    assert row.failed_reason is not None
    assert row.failed_reason.startswith("Could not save extracted entities to the graph")
    assert "Neo4j is unreachable" in row.failed_reason
    assert fake_delete.call_count == 2


def test_neo4j_write_failure_does_not_leave_document_stuck_at_graphing(client, db_session, monkeypatch):
    """Regression guard for the retry-lock (AD-1): a document must never be
    left at `Graphing` after a failure -- that status refuses retry just
    like `Extracting` does, so a stuck `Graphing` row would be permanently
    unrecoverable."""

    def _raise(entities, relationships, user_id):
        raise RuntimeError("Neo4j is unreachable")

    _stub_pipeline(monkeypatch, write_graph=_raise)

    token = _register_and_login(
        client, full_name="Graph User", email="graph-not-stuck@example.com", password="password12345"
    )
    doc = _upload(client, token, "notes.md", _MARKDOWN, "text/markdown")

    real_ingest_document(uuid.UUID(doc["id"]), session_factory=_session_factory(db_session))

    row = db_session.get(Document, uuid.UUID(doc["id"]))
    assert row.status != "Graphing"
    assert row.status == "Failed"
    assert row.failed_reason is not None
    assert row.failed_reason.startswith("Could not save extracted entities to the graph")
