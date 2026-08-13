"""`shared/data_access/weaviate_client.py` tests (Story 2.3): the missing-
config error, the empty-batch no-op, and that a write batch deletes any
existing objects for the same (document_id, user_id) before inserting --
all isolated from a real Weaviate connection via mocks.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.shared.data_access.shapes import WeaviatePassage
from app.shared.data_access.weaviate_client import get_weaviate_client, write_passages


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


def test_write_passages_deletes_existing_then_inserts_new_batch(monkeypatch):
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

    fake_collection.data.delete_many.assert_called_once()
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
