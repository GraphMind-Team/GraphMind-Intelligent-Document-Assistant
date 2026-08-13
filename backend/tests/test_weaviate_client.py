"""`shared/data_access/weaviate_client.py` tests (Story 2.3): the missing-
config error, the empty-batch no-op, that `delete_passages_for_document`
and `write_passages` are separate calls (so a caller can delete once and
write in batches without each write wiping the previous batch), and that
`insert_many` itself is batched -- all isolated from a real Weaviate
connection via mocks.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.shared.data_access.shapes import WeaviatePassage
from app.shared.data_access.weaviate_client import (
    PASSAGE_BATCH_SIZE,
    delete_passages_for_document,
    get_weaviate_client,
    write_passages,
)


@pytest.fixture(autouse=True)
def _clear_client_cache():
    get_weaviate_client.cache_clear()
    yield
    get_weaviate_client.cache_clear()


def test_get_weaviate_client_raises_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("WEAVIATE_URL", raising=False)
    monkeypatch.delenv("WEAVIATE_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        get_weaviate_client()

    assert "WEAVIATE_URL" in str(excinfo.value)
    assert "WEAVIATE_API_KEY" in str(excinfo.value)


def test_write_passages_empty_list_never_touches_the_client():
    with patch("app.shared.data_access.weaviate_client.get_weaviate_client") as fake_getter:
        write_passages([])
        fake_getter.assert_not_called()


def _fake_passage(chunk_index=0, chunk_id="chunk-0"):
    return WeaviatePassage(
        chunk_id=chunk_id,
        document_id="doc-1",
        user_id="user-1",
        chapter="Chapter One",
        chunk_index=chunk_index,
        text="some passage text",
        embedding=[0.1, 0.2, 0.3],
    )


def test_delete_passages_for_document_filters_on_document_and_user_id(monkeypatch):
    fake_collection = MagicMock()
    fake_client = MagicMock()
    fake_client.collections.exists.return_value = True
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_document("doc-1", "user-1")

    fake_collection.data.delete_many.assert_called_once()


def test_delete_passages_for_document_creates_collection_when_missing(monkeypatch):
    fake_collection = MagicMock()
    fake_client = MagicMock()
    fake_client.collections.exists.return_value = False
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_document("doc-1", "user-1")

    fake_client.collections.create.assert_called_once()


def test_write_passages_does_not_delete_only_inserts(monkeypatch):
    """`write_passages` is insert-only -- deleting is
    `delete_passages_for_document`'s job, called once up front by a caller
    streaming a document's passages in batches. If `write_passages` also
    deleted, each batch call would wipe out whatever the previous batch in
    the same document just inserted."""
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=False)

    fake_client = MagicMock()
    fake_client.collections.exists.return_value = True
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    passages = [_fake_passage(0, "chunk-0"), _fake_passage(1, "chunk-1")]
    write_passages(passages)

    fake_collection.data.delete_many.assert_not_called()
    fake_collection.data.insert_many.assert_called_once()
    inserted = fake_collection.data.insert_many.call_args.args[0]
    assert len(inserted) == 2
    assert inserted[0].properties["document_id"] == "doc-1"
    assert inserted[0].properties["user_id"] == "user-1"
    assert "metadata" not in inserted[0].properties


def test_write_passages_creates_collection_when_missing(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=False)

    fake_client = MagicMock()
    fake_client.collections.exists.return_value = False
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    write_passages([_fake_passage()])

    fake_client.collections.create.assert_called_once()


def test_write_passages_raises_on_insert_errors(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(
        has_errors=True, errors={0: "boom"}
    )

    fake_client = MagicMock()
    fake_client.collections.exists.return_value = True
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    with pytest.raises(RuntimeError):
        write_passages([_fake_passage()])


def test_write_passages_rejects_a_mixed_document_id_or_user_id_batch():
    same_doc_different_user = [
        WeaviatePassage(
            chunk_id="chunk-0",
            document_id="doc-1",
            user_id="user-1",
            chapter="Chapter One",
            chunk_index=0,
            text="text",
            embedding=[0.1],
        ),
        WeaviatePassage(
            chunk_id="chunk-1",
            document_id="doc-1",
            user_id="user-2",  # different owner -- must be rejected
            chapter="Chapter One",
            chunk_index=1,
            text="text",
            embedding=[0.1],
        ),
    ]

    with patch("app.shared.data_access.weaviate_client.get_weaviate_client") as fake_getter:
        with pytest.raises(ValueError):
            write_passages(same_doc_different_user)
        # Rejected before ever touching the client -- no partial insert.
        fake_getter.assert_not_called()


def test_write_passages_batches_insert_many_for_large_documents(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=False)

    fake_client = MagicMock()
    fake_client.collections.exists.return_value = True
    fake_client.collections.get.return_value = fake_collection

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    passage_count = PASSAGE_BATCH_SIZE * 2 + 5
    passages = [_fake_passage(i, f"chunk-{i}") for i in range(passage_count)]
    write_passages(passages)

    # 3 batches: two full ones plus a small remainder -- never one call
    # carrying every object in a large document at once.
    assert fake_collection.data.insert_many.call_count == 3
    inserted_total = sum(
        len(call.args[0]) for call in fake_collection.data.insert_many.call_args_list
    )
    assert inserted_total == passage_count
    for call in fake_collection.data.insert_many.call_args_list:
        assert len(call.args[0]) <= PASSAGE_BATCH_SIZE
