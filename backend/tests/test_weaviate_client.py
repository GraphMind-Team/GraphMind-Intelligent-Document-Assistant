"""`shared/data_access/weaviate_client.py` tests (Story 2.3): the missing-
config error, the empty-batch no-op, that `delete_passages_for_document`
and `write_passages` are separate calls (so a caller can delete once and
write in batches without each write wiping the previous batch), that
`insert_many` itself is batched, that collection creation tolerates
losing a concurrent create() race instead of propagating it, and that the
client/collection-ready singletons reset cleanly between tests -- all
isolated from a real Weaviate connection via mocks.
"""

from unittest.mock import MagicMock, patch

import pytest
from weaviate.classes.query import Filter

from app.shared.data_access import weaviate_client as weaviate_client_module
from app.shared.data_access.shapes import WeaviatePassage, WeaviateSearchResult
from app.shared.data_access.weaviate_client import (
    PASSAGE_BATCH_SIZE,
    close_weaviate_client,
    delete_passages_for_document,
    delete_passages_for_user,
    ensure_ready,
    get_weaviate_client,
    search_passages,
    write_passages,
)


@pytest.fixture(autouse=True)
def _reset_module_singletons(monkeypatch):
    """`get_weaviate_client`'s client and `_ensure_passage_collection`'s
    readiness flag are both plain module-level globals now (not
    `@lru_cache`, precisely so concurrent access is lock-guarded rather
    than cache-guarded -- see `get_weaviate_client`'s docstring). Tests
    need a clean slate each time: without resetting `_collection_ready`,
    the first test to confirm the collection exists would make every
    later test silently skip `_ensure_passage_collection`'s exists()/
    create() calls entirely, since the flag short-circuits before either
    ever runs."""
    monkeypatch.setattr(weaviate_client_module, "_client_instance", None)
    monkeypatch.setattr(weaviate_client_module, "_collection_ready", False)


def test_get_weaviate_client_raises_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("WEAVIATE_URL", raising=False)
    monkeypatch.delenv("WEAVIATE_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        get_weaviate_client()

    assert "WEAVIATE_URL" in str(excinfo.value)
    assert "WEAVIATE_API_KEY" in str(excinfo.value)


def test_get_weaviate_client_returns_the_same_instance_on_repeat_calls(monkeypatch):
    created = []

    def _fake_connect(**kwargs):
        client = MagicMock()
        created.append(client)
        return client

    monkeypatch.setenv("WEAVIATE_URL", "https://example.weaviate.cloud")
    monkeypatch.setenv("WEAVIATE_API_KEY", "test-key")
    monkeypatch.setattr(weaviate_client_module.weaviate, "connect_to_weaviate_cloud", _fake_connect)

    first = get_weaviate_client()
    second = get_weaviate_client()

    assert first is second
    assert len(created) == 1


def test_close_weaviate_client_is_a_no_op_when_none_was_ever_built():
    close_weaviate_client()  # must not raise, must not connect


def test_close_weaviate_client_closes_and_clears_the_singleton(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setenv("WEAVIATE_URL", "https://example.weaviate.cloud")
    monkeypatch.setenv("WEAVIATE_API_KEY", "test-key")
    monkeypatch.setattr(
        weaviate_client_module.weaviate, "connect_to_weaviate_cloud", lambda **kwargs: fake_client
    )

    get_weaviate_client()
    close_weaviate_client()

    fake_client.close.assert_called_once()
    assert weaviate_client_module._client_instance is None


def test_close_weaviate_client_also_resets_collection_ready(monkeypatch):
    """`_collection_ready` describes readiness over the client being
    closed, not over the process -- leaving it True past `close()` would
    make a future reconnect skip `_ensure_passage_collection` entirely on
    a client that's never actually confirmed anything."""
    monkeypatch.setattr(weaviate_client_module, "_collection_ready", True)
    fake_client = MagicMock()
    monkeypatch.setattr(weaviate_client_module, "_client_instance", fake_client)

    close_weaviate_client()

    assert weaviate_client_module._collection_ready is False


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


def _fake_client(exists=True):
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=False)
    fake_collection.data.delete_many.return_value = MagicMock(failed=0, matches=0)

    fake_client = MagicMock()
    fake_client.collections.exists.return_value = exists
    fake_client.collections.get.return_value = fake_collection
    return fake_client, fake_collection


def test_delete_passages_for_document_filters_on_document_and_user_id(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=True)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_document("doc-1", "user-1")

    fake_collection.data.delete_many.assert_called_once()


def test_delete_passages_for_document_creates_collection_when_missing(monkeypatch):
    fake_client, _ = _fake_client(exists=False)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_document("doc-1", "user-1")

    fake_client.collections.create.assert_called_once()


def test_delete_passages_for_document_logs_a_warning_on_partial_delete_failure(
    monkeypatch, caplog
):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.data.delete_many.return_value = MagicMock(failed=2, matches=10)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    with caplog.at_level("WARNING"):
        delete_passages_for_document("doc-1", "user-1")  # must not raise

    assert "failed to delete" in caplog.text


def test_delete_passages_for_user_filters_on_user_id_only(monkeypatch):
    """Story 5.3's account-deletion cascade: scoped to `user_id` alone, no
    `document_id` filter -- unlike `delete_passages_for_document`, this
    must clear every document the user owns in one call."""
    fake_client, fake_collection = _fake_client(exists=True)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_user("user-1")

    fake_collection.data.delete_many.assert_called_once()
    where = fake_collection.data.delete_many.call_args.kwargs["where"]
    assert where.target == "user_id"
    assert where.value == "user-1"


def test_delete_passages_for_user_creates_collection_when_missing(monkeypatch):
    fake_client, _ = _fake_client(exists=False)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_user("user-1")

    fake_client.collections.create.assert_called_once()


def test_delete_passages_for_user_logs_a_warning_on_partial_delete_failure(monkeypatch, caplog):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.data.delete_many.return_value = MagicMock(failed=2, matches=10)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    with caplog.at_level("WARNING"):
        delete_passages_for_user("user-1")  # must not raise

    assert "failed to delete" in caplog.text


def test_delete_passages_for_user_is_idempotent_on_zero_matches(monkeypatch):
    """A user with no passages left (or a retry after a partial cascade
    failure) matches zero rows -- must not raise."""
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.data.delete_many.return_value = MagicMock(failed=0, matches=0)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    delete_passages_for_user("user-1")  # must not raise
    delete_passages_for_user("user-1")  # a second call, still must not raise

    assert fake_collection.data.delete_many.call_count == 2


def test_write_passages_does_not_delete_only_inserts(monkeypatch):
    """`write_passages` is insert-only -- deleting is
    `delete_passages_for_document`'s job, called once up front by a caller
    streaming a document's passages in batches. If `write_passages` also
    deleted, each batch call would wipe out whatever the previous batch in
    the same document just inserted."""
    fake_client, fake_collection = _fake_client(exists=True)
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
    fake_client, _ = _fake_client(exists=False)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    write_passages([_fake_passage()])

    fake_client.collections.create.assert_called_once()


def test_ensure_passage_collection_is_only_checked_once_per_process(monkeypatch):
    """After the first confirmation, later writes must not re-check
    `exists()` at all -- for a document split into many batches, each one
    re-checking would be dozens of redundant round-trips for a fact that
    never changes."""
    fake_client, _ = _fake_client(exists=True)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    write_passages([_fake_passage(0, "chunk-0")])
    write_passages([_fake_passage(1, "chunk-1")])

    fake_client.collections.exists.assert_called_once()


def test_ensure_passage_collection_tolerates_losing_the_create_race(monkeypatch):
    """Two concurrent first-ever uploads can both see `exists() == False`
    and both call `create()` -- the loser must not have its document fail
    ingestion just because it lost that race. Simulated here by making
    `create()` raise, then `exists()` report True on the re-check."""
    fake_collection = MagicMock()
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=False)

    fake_client = MagicMock()
    fake_client.collections.get.return_value = fake_collection
    fake_client.collections.exists.side_effect = [False, True]  # miss, then re-check after losing
    fake_client.collections.create.side_effect = RuntimeError("already exists")

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    write_passages([_fake_passage()])  # must not raise

    fake_collection.data.insert_many.assert_called_once()


def test_ensure_passage_collection_reraises_a_genuine_create_failure(monkeypatch):
    """If `create()` fails for a real reason (not a lost race -- the
    collection still doesn't exist on re-check), that failure must
    propagate rather than being swallowed as if it were benign."""
    fake_client = MagicMock()
    fake_client.collections.exists.side_effect = [False, False]
    fake_client.collections.create.side_effect = RuntimeError("quota exceeded")

    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    with pytest.raises(RuntimeError, match="quota exceeded"):
        write_passages([_fake_passage()])


def test_ensure_ready_connects_and_ensures_the_collection(monkeypatch):
    fake_client, _ = _fake_client(exists=False)
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    ensure_ready()

    fake_client.collections.create.assert_called_once()


def test_write_passages_raises_on_insert_errors(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.data.insert_many.return_value = MagicMock(has_errors=True, errors={0: "boom"})
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
    fake_client, fake_collection = _fake_client(exists=True)
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


def _fake_weaviate_object(chunk_id, document_id="doc-1", chapter="Chapter One", chunk_index=0, text="text", distance=0.1):
    obj = MagicMock()
    obj.properties = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "chapter": chapter,
        "chunk_index": chunk_index,
        "text": text,
    }
    obj.metadata = MagicMock(distance=distance)
    return obj


def test_search_passages_filters_on_user_id_and_returns_mapped_results(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.query.near_vector.return_value = MagicMock(
        objects=[_fake_weaviate_object("chunk-0", distance=0.05), _fake_weaviate_object("chunk-1", distance=0.2)]
    )
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    results = search_passages([0.1, 0.2, 0.3], "user-1", limit=8)

    fake_collection.query.near_vector.assert_called_once()
    call_kwargs = fake_collection.query.near_vector.call_args.kwargs
    assert call_kwargs["near_vector"] == [0.1, 0.2, 0.3]
    assert call_kwargs["limit"] == 8
    # Not just "a filters kwarg was passed" -- the actual tenancy guarantee
    # (FR-2/AD-2) is that it's scoped to THIS property, with THIS value. A
    # `Filter.by_property("user_id").equal(user_id)` call produces a
    # `_FilterValue` with `.target`/`.value`; asserting on those is what
    # would actually catch someone swapping the filtered property or
    # passing the wrong id, which "filters" in call_kwargs never could.
    filters = call_kwargs["filters"]
    assert filters.target == "user_id"
    assert filters.value == "user-1"
    assert "return_metadata" in call_kwargs

    assert len(results) == 2
    assert isinstance(results[0], WeaviateSearchResult)
    assert results[0].chunk_id == "chunk-0"
    assert results[0].document_id == "doc-1"
    assert results[0].distance == 0.05


def test_search_passages_returns_empty_list_for_no_matches(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.query.near_vector.return_value = MagicMock(objects=[])
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    results = search_passages([0.1], "user-1")

    assert results == []


def test_search_passages_creates_collection_when_missing(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=False)
    fake_collection.query.near_vector.return_value = MagicMock(objects=[])
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    search_passages([0.1], "user-1")

    fake_client.collections.create.assert_called_once()


def test_search_passages_default_limit_is_top_k_passages(monkeypatch):
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.query.near_vector.return_value = MagicMock(objects=[])
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    search_passages([0.1], "user-1")

    assert (
        fake_collection.query.near_vector.call_args.kwargs["limit"]
        == weaviate_client_module.TOP_K_PASSAGES
    )


def test_search_passages_filters_on_document_ids_when_provided(monkeypatch):
    """Story 3.3/FR-11: a non-empty `document_ids` must AND a
    `contains_any` filter onto the existing `user_id` filter -- not
    replace it, not OR it -- so scoping can only narrow retrieval, never
    widen it past the account's own tenancy boundary."""
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.query.near_vector.return_value = MagicMock(objects=[])
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    search_passages([0.1], "user-1", document_ids=["doc-1", "doc-2"])

    filters = fake_collection.query.near_vector.call_args.kwargs["filters"]
    assert filters.filters[0].target == "user_id"
    assert filters.filters[0].value == "user-1"
    assert filters.filters[1].target == "document_id"
    assert filters.filters[1].value == ["doc-1", "doc-2"]
    assert filters.filters[1].operator == Filter.by_property("document_id").contains_any(["x"]).operator


def test_search_passages_omits_document_id_filter_when_empty_list(monkeypatch):
    """An empty (not just `None`) `document_ids` must behave exactly like
    the pre-Story-3.3 unscoped call -- FR-11's default is "search
    everything," and an empty list is how the frontend spells that."""
    fake_client, fake_collection = _fake_client(exists=True)
    fake_collection.query.near_vector.return_value = MagicMock(objects=[])
    monkeypatch.setattr(
        "app.shared.data_access.weaviate_client.get_weaviate_client", lambda: fake_client
    )

    search_passages([0.1], "user-1", document_ids=[])

    filters = fake_collection.query.near_vector.call_args.kwargs["filters"]
    assert filters.target == "user_id"
    assert filters.value == "user-1"
