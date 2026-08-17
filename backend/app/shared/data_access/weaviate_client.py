"""Weaviate connection and the passage write path (Story 2.3, AD-2).

Per architecture decision AD-2, this is the sole place a Weaviate client is
constructed and the sole place a Weaviate query is written -- `documents/`
(and any future reader, e.g. Epic 3's chat retrieval) calls `write_passages`
(or a future `search_passages`) rather than importing `weaviate` itself.

The client is built on first use, not at import time, so importing this
module never opens a real network connection on its own (needed for
tests, and for `app.main` importing every route module at startup
regardless of whether Weaviate is configured). Deliberately *not*
`@lru_cache` (see `_get_client`'s docstring) -- same reasoning, and same
double-checked-locking shape, as `shared/embeddings/model.py`'s
`_get_model`.
"""

import logging
import os
import threading

import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.data import DataObject
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.client import WeaviateClient

from app.shared.data_access.shapes import WeaviatePassage, WeaviateSearchResult

logger = logging.getLogger(__name__)

PASSAGE_COLLECTION = "Passage"

# A large document (the 20MB upload cap, thousands of chunks) would
# otherwise go through `insert_many` as one gRPC call carrying every
# object -- both a single oversized request Weaviate may reject outright,
# and a spike in resident memory for the whole batch's text+embedding
# payload at once. Batched insert avoids both; not tuned against a real
# large-document benchmark, just a conservative, documented default.
#
# Public (not `_`-prefixed): `documents/service.py` batches its own
# embed-then-write loop by this same size, so the two batching layers --
# embedding memory on the caller's side, insert_many payload size here --
# stay in lockstep off one source of truth instead of two magic numbers
# that could silently drift apart.
PASSAGE_BATCH_SIZE = 100

# Story 3.1's default candidate count for chat retrieval -- large enough that
# a question spanning multiple documents/chapters has a real chance of
# pulling passages from more than one, small enough to keep the downstream
# chat-completion prompt (shared/llm_client's generate_answer) short. A
# tunable default, not a hard architectural commitment -- Story 3.2 may
# revisit this alongside its relevance threshold.
TOP_K_PASSAGES = 8


_client_lock = threading.Lock()
_client_instance: WeaviateClient | None = None


def get_weaviate_client() -> WeaviateClient:
    """The process-wide Weaviate client singleton.

    A hand-rolled double-checked-locking singleton, not `@lru_cache`: like
    `shared/embeddings/model.py`'s model singleton, this is built inside
    Starlette's background-task threadpool, where two uploads processed
    concurrently could both miss an empty `lru_cache` before either
    finishes connecting -- `lru_cache` holds no lock across the wrapped
    call itself. Two live clients here isn't just wasted memory the way a
    duplicate embedding model is: the second one would leak, unclosed,
    past `close_weaviate_client()`'s single `close()` call at shutdown.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:  # re-check: lost the race, not the need
                url = os.environ.get("WEAVIATE_URL")
                api_key = os.environ.get("WEAVIATE_API_KEY")
                if not url or not api_key:
                    raise RuntimeError(
                        "Missing required environment variable(s): WEAVIATE_URL, "
                        "WEAVIATE_API_KEY. See backend/.env.example."
                    )
                _client_instance = weaviate.connect_to_weaviate_cloud(
                    cluster_url=url,
                    auth_credentials=Auth.api_key(api_key),
                )
    return _client_instance


def close_weaviate_client() -> None:
    """Closes the client singleton, if one was ever built. Safe to call
    unconditionally (e.g. from `app.main`'s shutdown) whether or not
    ingestion ever ran -- calling this never itself opens a connection
    just to immediately close it.

    Also resets `_collection_ready`: that flag describes "the collection
    was confirmed to exist over the client we currently hold" -- it
    belongs to the connection being closed here, not to the process. No
    caller reconnects after closing today, so this is a no-op in
    practice, but leaving it True would describe a world that no longer
    exists the moment a future reconnect path is added.
    """
    global _client_instance, _collection_ready
    with _client_lock:
        if _client_instance is not None:
            _client_instance.close()
            _client_instance = None
        with _collection_lock:
            _collection_ready = False


_collection_lock = threading.Lock()
_collection_ready = False


def _ensure_passage_collection(client: WeaviateClient) -> None:
    """Idempotent, race-tolerant, and cheap after the first confirmation.

    Two problems with a bare check-then-create, both real under
    concurrent background tasks in Starlette's threadpool: (1) against a
    fresh Weaviate instance, two uploads landing at once can both see
    `exists() == False` and both call `create()` -- the loser gets a real
    error and its document fails ingestion for no actual reason, not a
    hypothetical race. (2) even once the collection exists, every
    `write_passages`/`delete_passages_for_document` call re-checks
    `exists()` -- for a document with thousands of chunks split into many
    batches, that's dozens of redundant round-trips for a fact that never
    changes after the first confirmation.

    `_collection_ready` (guarded by its own lock, separate from the
    client's) short-circuits both: once True, no further Weaviate calls
    happen here at all. Getting there tolerates losing the create() race
    outright -- rather than only avoiding it -- by re-checking `exists()`
    if `create()` raises, so a concurrent creator winning is treated as
    success, not propagated as this call's own failure.
    """
    global _collection_ready
    if _collection_ready:
        return
    with _collection_lock:
        if _collection_ready:
            return
        if client.collections.exists(PASSAGE_COLLECTION):
            _collection_ready = True
            return
        try:
            # vectorizer_config=none: embeddings are computed by the app
            # (shared/embeddings) and supplied on every write, never
            # generated by a Weaviate-side vectorizer module.
            client.collections.create(
                PASSAGE_COLLECTION,
                properties=[
                    Property(name="chunk_id", data_type=DataType.TEXT),
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="user_id", data_type=DataType.TEXT),
                    Property(name="chapter", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    Property(name="text", data_type=DataType.TEXT),
                ],
                vectorizer_config=Configure.Vectorizer.none(),
            )
        except Exception:
            if client.collections.exists(PASSAGE_COLLECTION):
                # Lost the create() race to another process/thread -- the
                # collection exists either way, which is all this
                # function promises.
                pass
            else:
                raise
        _collection_ready = True


def ensure_ready() -> None:
    """Connects and ensures the `Passage` collection exists, once, up
    front. Meant to be called from `app.main`'s startup: doing this before
    the app starts serving requests means the collection almost always
    already exists by the time any upload can race on it, structurally
    avoiding `_ensure_passage_collection`'s create() race in the common
    case rather than only tolerating it after the fact. Raises whatever
    `get_weaviate_client`/`_ensure_passage_collection` raise -- the
    caller decides whether a startup failure here should be fatal or
    just logged (Weaviate being unconfigured/unreachable at boot must not
    crash the whole app, since ingestion already degrades gracefully to
    `Failed` when it can't reach Weaviate).
    """
    _ensure_passage_collection(get_weaviate_client())


def delete_passages_for_document(document_id: str, user_id: str) -> None:
    """Deletes every existing passage for `(document_id, user_id)`.

    A separate call from `write_passages` (rather than folded into it) so
    a caller ingesting a large document can delete once up front, then
    call `write_passages` repeatedly with successive batches -- folding
    the delete into every `write_passages` call would wipe out whatever
    the previous batch just inserted. Filtered on `user_id` too (not just
    `document_id`, which alone would already be correct in practice) to
    keep `shapes.py`'s documented rule -- `user_id` required on every
    write *and* every query filter -- true for every Weaviate operation
    this module performs.
    """
    client = get_weaviate_client()
    _ensure_passage_collection(client)
    collection = client.collections.get(PASSAGE_COLLECTION)
    result = collection.data.delete_many(
        where=Filter.by_property("document_id").equal(document_id)
        & Filter.by_property("user_id").equal(user_id)
    )
    # Weaviate caps a single batch delete (10k objects by default) --
    # `insert_many`'s result is checked for errors, so this should be
    # too, rather than assuming every matched object was actually
    # removed. No caller retries a delete today, so a nonzero `failed`
    # count can't be acted on yet beyond making it visible; logged, not
    # raised, so a failed delete of stale data doesn't also block the
    # fresh write that follows it.
    if getattr(result, "failed", 0):
        logger.warning(
            "delete_passages_for_document: %s of %s matched objects failed to delete "
            "for document_id=%s user_id=%s",
            result.failed,
            result.matches,
            document_id,
            user_id,
        )


def delete_passages_for_user(user_id: str) -> None:
    """Deletes every existing passage owned by `user_id`, across every
    document they own -- the user-scoped sibling to
    `delete_passages_for_document`'s per-document delete, added for Story
    5.3's account-deletion cascade (AD-2: the sole place a Weaviate filter
    for this is written, not a one-off query under `auth/`).

    Idempotent, like `delete_passages_for_document`: a user with zero
    passages (or a retry after a partial earlier failure) matches zero
    rows on `delete_many`, which is success, not an error.
    """
    client = get_weaviate_client()
    _ensure_passage_collection(client)
    collection = client.collections.get(PASSAGE_COLLECTION)
    result = collection.data.delete_many(where=Filter.by_property("user_id").equal(user_id))
    # Same failed/matches accounting as delete_passages_for_document --
    # logged, not raised, since no caller retries a delete today beyond
    # re-running the whole cascade, which is itself idempotent.
    if getattr(result, "failed", 0):
        logger.warning(
            "delete_passages_for_user: %s of %s matched objects failed to delete "
            "for user_id=%s",
            result.failed,
            result.matches,
            user_id,
        )


def write_passages(passages: list[WeaviatePassage]) -> None:
    """The only function `documents/` calls to reach Weaviate (AD-2) -- no
    raw collection/query call may appear anywhere in `documents/`.

    Insert-only -- does not delete anything first (see
    `delete_passages_for_document` for that, called once up front by a
    caller that's about to write a document's passages in batches).
    Batches `insert_many` itself in chunks of `PASSAGE_BATCH_SIZE` even if
    called with a single large list, so this stays safe to call directly
    with everything at once too, not just from a pre-batched loop.

    Requires every passage in `passages` to share the same
    `(document_id, user_id)` pair -- a caller that's meant to batch by
    document (as `documents/service.py`'s `ingest_document` does) getting
    this wrong is exactly the mixed-batch case worth catching here rather
    than writing under the wrong owner.
    """
    if not passages:
        return

    document_id = passages[0].document_id
    user_id = passages[0].user_id
    if any(p.document_id != document_id or p.user_id != user_id for p in passages):
        raise ValueError(
            "write_passages requires every passage to share the same "
            "(document_id, user_id) -- got a mixed batch."
        )

    client = get_weaviate_client()
    _ensure_passage_collection(client)
    collection = client.collections.get(PASSAGE_COLLECTION)

    for batch_start in range(0, len(passages), PASSAGE_BATCH_SIZE):
        batch = passages[batch_start : batch_start + PASSAGE_BATCH_SIZE]
        objects = [
            DataObject(
                properties={
                    "chunk_id": p.chunk_id,
                    "document_id": p.document_id,
                    "user_id": p.user_id,
                    "chapter": p.chapter,
                    "chunk_index": p.chunk_index,
                    "text": p.text,
                },
                uuid=p.chunk_id,
                vector=p.embedding,
            )
            for p in batch
        ]
        result = collection.data.insert_many(objects)
        if result.has_errors:
            raise RuntimeError(f"Weaviate write failed: {result.errors}")


def search_passages(
    query_vector: list[float],
    user_id: str,
    limit: int = TOP_K_PASSAGES,
    document_ids: list[str] | None = None,
) -> list[WeaviateSearchResult]:
    """The `documents/`-anticipated future reader function this module's own
    docstring named up front -- Epic 3's chat retrieval (Story 3.1) calls
    this rather than importing `weaviate` itself, same as `documents/`
    calls `write_passages`.

    Vector search over `Passage`, filtered to `user_id` server-side (AD-2,
    FR-2) -- the caller must have already resolved `user_id` from
    `get_current_user`, never from client input, per this file's own
    module docstring and `shapes.py`'s tenancy-rule comment.

    `document_ids` (Story 3.3/FR-11): when a non-empty list, ANDs a
    `contains_any` filter onto the `user_id` filter, same combined-filter
    shape `delete_passages_for_document` already uses -- so scoping can
    never widen retrieval past `user_id`, only narrow it further. `None`
    or an empty list means the FR-11 default (search everything), matching
    this function's pre-Story-3.3 behavior exactly.

    Returns results ordered nearest-first (Weaviate's own default order
    for `near_vector`). An empty list is a valid, non-error outcome -- an
    account with zero passages (or zero within its own tenancy/scope) is
    the caller's (chat/service.py's) degenerate case to handle, not this
    function's.
    """
    client = get_weaviate_client()
    _ensure_passage_collection(client)
    collection = client.collections.get(PASSAGE_COLLECTION)

    filters = Filter.by_property("user_id").equal(user_id)
    if document_ids:
        filters = filters & Filter.by_property("document_id").contains_any(document_ids)

    response = collection.query.near_vector(
        near_vector=query_vector,
        limit=limit,
        filters=filters,
        return_metadata=MetadataQuery(distance=True),
    )

    return [
        WeaviateSearchResult(
            chunk_id=obj.properties["chunk_id"],
            document_id=obj.properties["document_id"],
            chapter=obj.properties["chapter"],
            chunk_index=obj.properties["chunk_index"],
            text=obj.properties["text"],
            distance=obj.metadata.distance if obj.metadata else None,
        )
        for obj in response.objects
    ]
