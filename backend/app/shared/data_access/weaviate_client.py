"""Weaviate connection and the passage write path (Story 2.3, AD-2).

Per architecture decision AD-2, this is the sole place a Weaviate client is
constructed and the sole place a Weaviate query is written -- `documents/`
(and any future reader, e.g. Epic 3's chat retrieval) calls `write_passages`
(or a future `search_passages`) rather than importing `weaviate` itself.

The client is built on first use, not at import time, so importing this
module never opens a real network connection on its own (needed for
tests, and for `app.main` importing every route module at startup
regardless of whether Weaviate is configured). Deliberately *not*
`@lru_cache` -- see `get_weaviate_client`'s docstring.

Embeddings are computed by Weaviate itself (text2vec-weaviate), not by
this app -- see `_ensure_passage_collection` for why the in-process
fastembed model was removed.
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
from app.shared.env import env_str

logger = logging.getLogger(__name__)

PASSAGE_COLLECTION = "Passage"

# The text2vec-weaviate model that vectorizes `Passage.text` server-side.
# Multilingual (~50 languages), 1024-dim by default. Included in Weaviate
# Cloud's free tier at 2,000 embedding requests/day -- each `insert_many`
# batch and each `near_text` query is one request, so a document of N
# chunks costs ceil(N / PASSAGE_BATCH_SIZE) requests, not N.
EMBEDDING_MODEL = "Snowflake/snowflake-arctic-embed-l-v2.0"

# A large document (the 20MB upload cap, thousands of chunks) would
# otherwise go through `insert_many` as one gRPC call carrying every
# object -- a single oversized request Weaviate may reject outright.
# Batched insert avoids that; not tuned against a real large-document
# benchmark, just a conservative, documented default.
#
# Since embedding moved server-side this also bounds Weaviate Embeddings
# *request* count, which is the metered resource on the free tier (2,000
# per day): one batch is one request, so a 1,000-chunk document costs 10
# requests rather than 1,000. Lowering this number therefore costs quota
# rather than saving memory -- the opposite of the tradeoff it used to
# represent, when the caller held a whole batch of vectors in memory.
#
# Public (not `_`-prefixed): `documents/service.py` batches its own write
# loop by this same size, so both layers stay in lockstep off one source
# of truth instead of two magic numbers that could silently drift apart.
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

    A hand-rolled double-checked-locking singleton, not `@lru_cache`: this
    is built inside Starlette's background-task threadpool, where two
    uploads processed concurrently could both miss an empty `lru_cache`
    before either finishes connecting -- `lru_cache` holds no lock across
    the wrapped call itself. Two live clients here isn't merely wasted
    memory: the second one would leak, unclosed, past
    `close_weaviate_client()`'s single `close()` call at shutdown.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:  # re-check: lost the race, not the need
                url = env_str("WEAVIATE_URL")
                api_key = env_str("WEAVIATE_API_KEY")
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
    belongs to the connection being closed here, not to the process.
    `_with_reconnect` below is a caller that does reconnect afterwards, so
    this is load-bearing, not just tidy: leaving it True would let the
    rebuilt client skip `_ensure_passage_collection` on a fact confirmed
    over a connection that no longer exists.
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


# Failures that mean "this connection is dead", as opposed to "this
# request was wrong". Only these are worth reconnecting for -- retrying a
# schema or validation error on a fresh connection would just fail again,
# slower, and hide the real cause behind a reconnect that looks like a
# network blip.
#
# `WeaviateQueryError` is deliberately in this list even though it also
# covers genuine query errors: the observed production failure surfaced
# as exactly that, wrapping a gRPC "sendmsg: Connection reset by peer
# (104)", and the client offers no narrower type for it. The cost of
# including it is one wasted retry on a malformed query; the cost of
# leaving it out is every Weaviate operation failing until someone
# restarts the process.
_CONNECTION_ERRORS = (
    weaviate.exceptions.WeaviateConnectionError,
    weaviate.exceptions.WeaviateClosedClientError,
    weaviate.exceptions.WeaviateGRPCUnavailableError,
    weaviate.exceptions.WeaviateQueryError,
    weaviate.exceptions.WeaviateDeleteManyError,
    weaviate.exceptions.WeaviateTimeoutError,
)


def _with_reconnect(operation):
    """Runs `operation()`, rebuilding the client once if the connection
    turns out to be dead.

    The client singleton is built once and cached for the life of the
    process, and nothing invalidated it: when the platform dropped the
    idle gRPC connection underneath it, every subsequent Weaviate call --
    ingestion *and* chat retrieval, which share this client -- failed
    with "Connection reset by peer (104)" until the service was manually
    restarted. A cached handle to a socket that no longer exists is not a
    state the app should need a human to notice.

    `operation` must call `get_weaviate_client()` itself rather than
    closing over a client, so the retry actually picks up the rebuilt one
    rather than re-using the dead handle it just failed on.

    Exactly one retry, not a loop with backoff: if a freshly built
    connection also fails, the cluster is genuinely unreachable and the
    caller's own error handling (ingestion marks the document Failed,
    chat surfaces an error) is the right outcome -- not this function
    silently absorbing a real outage into a longer wait.
    """
    try:
        return operation()
    except _CONNECTION_ERRORS as exc:
        logger.warning(
            "Weaviate call failed on a stale connection (%s) -- reconnecting and retrying once: %s",
            type(exc).__name__,
            str(exc)[:200],
        )
        close_weaviate_client()
        return operation()


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
            # Weaviate computes the embeddings server-side (text2vec-weaviate),
            # rather than the app computing them and supplying a vector on
            # every write. The app previously ran fastembed's
            # paraphrase-multilingual-MiniLM-L12-v2 in-process, which needed
            # ~554MB resident on top of a ~143MB app -- roughly 700MB against
            # Render's 512MB free instance, which OOM-restarted the service.
            # Measured, and not fixable by batch size or ONNX thread/arena
            # tuning: the model load alone is the overage. Weaviate Embeddings
            # is included in the free tier (2,000 requests/day) and runs on
            # Weaviate's hardware, so the backend holds no model at all.
            #
            # arctic-embed-l-v2.0 is text2vec-weaviate's default and is
            # multilingual -- the property that motivated the earlier switch
            # away from an English-only model (commit f85f1d5, so Bulgarian
            # documents embed under a model actually trained on them). Named
            # explicitly rather than left to the module default so a change in
            # Weaviate's default can't silently re-vectorize this collection
            # under a different model than DEFAULT_VECTOR_DIMENSIONS assumes.
            client.collections.create(
                PASSAGE_COLLECTION,
                properties=[
                    Property(name="chunk_id", data_type=DataType.TEXT),
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="user_id", data_type=DataType.TEXT),
                    Property(name="chapter", data_type=DataType.TEXT),
                    Property(name="chunk_index", data_type=DataType.INT),
                    # vectorize_property_name=False: without it Weaviate
                    # prepends the literal property name ("text") to the
                    # value before embedding it.
                    Property(
                        name="text",
                        data_type=DataType.TEXT,
                        vectorize_property_name=False,
                    ),
                ],
                # source_properties=["text"] is load-bearing, not a tidy
                # default: text2vec-weaviate vectorizes *every* text
                # property unless told otherwise, so without it the UUID
                # strings in document_id/user_id and the chapter label
                # would all be concatenated into the embedded text and
                # degrade retrieval for every query. Naming the one source
                # property keeps the embedded unit exactly what the app
                # used to embed itself (`chunk.text` alone), so retrieval
                # semantics carry over unchanged.
                #
                # vectorize_collection_name=False for the same reason: the
                # literal string "Passage" is not part of any chunk's
                # meaning and would otherwise be prepended to all of them.
                #
                # `vector_config=`, not the older `vectorizer_config=`,
                # which the client deprecates (Dep024).
                vector_config=Configure.Vectors.text2vec_weaviate(
                    model=EMBEDDING_MODEL,
                    source_properties=["text"],
                    vectorize_collection_name=False,
                ),
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
    def _delete():
        client = get_weaviate_client()
        _ensure_passage_collection(client)
        collection = client.collections.get(PASSAGE_COLLECTION)
        return collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id)
            & Filter.by_property("user_id").equal(user_id)
        )

    result = _with_reconnect(_delete)
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
    def _delete():
        client = get_weaviate_client()
        _ensure_passage_collection(client)
        collection = client.collections.get(PASSAGE_COLLECTION)
        return collection.data.delete_many(where=Filter.by_property("user_id").equal(user_id))

    result = _with_reconnect(_delete)
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
                # No `vector=`: text2vec-weaviate embeds `text` server-side
                # on insert (see _ensure_passage_collection). Passing one
                # here would override the vectorizer with a client-supplied
                # vector and silently reintroduce a second embedding space.
            )
            for p in batch
        ]

        def _insert(objects=objects):
            client = get_weaviate_client()
            _ensure_passage_collection(client)
            return client.collections.get(PASSAGE_COLLECTION).data.insert_many(objects)

        # Per batch, not around the whole loop: a reconnect mid-document
        # then re-runs only the batch that failed. Re-running the loop from
        # the start would be harmless for correctness (object uuids are
        # deterministic, so a repeat is an overwrite) but would re-send
        # every earlier batch to be embedded again, spending Weaviate
        # Embeddings quota on work already done.
        result = _with_reconnect(_insert)
        if result.has_errors:
            raise RuntimeError(f"Weaviate write failed: {result.errors}")


def search_passages(
    query_text: str,
    user_id: str,
    limit: int = TOP_K_PASSAGES,
    document_ids: list[str] | None = None,
) -> list[WeaviateSearchResult]:
    """The `documents/`-anticipated future reader function this module's own
    docstring named up front -- Epic 3's chat retrieval (Story 3.1) calls
    this rather than importing `weaviate` itself, same as `documents/`
    calls `write_passages`.

    Takes the query *text*, not a vector: text2vec-weaviate embeds it
    server-side with the same model that vectorized the stored passages,
    which is what keeps query and passage in one embedding space. The
    caller no longer computes (or can mismatch) the query embedding.

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
    for `near_text`). An empty list is a valid, non-error outcome -- an
    account with zero passages (or zero within its own tenancy/scope) is
    the caller's (chat/service.py's) degenerate case to handle, not this
    function's.
    """
    filters = Filter.by_property("user_id").equal(user_id)
    if document_ids:
        filters = filters & Filter.by_property("document_id").contains_any(document_ids)

    def _query():
        client = get_weaviate_client()
        _ensure_passage_collection(client)
        return client.collections.get(PASSAGE_COLLECTION).query.near_text(
            query=query_text,
            limit=limit,
            filters=filters,
            return_metadata=MetadataQuery(distance=True),
        )

    # Read-only and idempotent, so retrying on a rebuilt connection is
    # free -- and this is the path a user actually waits on, where a dead
    # connection would otherwise surface as a failed question rather than
    # a retried one.
    response = _with_reconnect(_query)

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


# Story 3.5 (document-overview chat intent): a generous cap on how many
# passages `fetch_passages_for_documents` will ever pull for one overview
# request. Not tuned against a real large-document benchmark -- like
# `PASSAGE_BATCH_SIZE` above, a conservative, documented default. Sits
# well above what `_OVERVIEW_MAX_PROMPT_CHARS` (shared/llm_client) could
# ever fit in the prompt anyway; the char budget there is what actually
# bounds the block sent to the model, so this only bounds how much data
# leaves Weaviate before that trim happens.
OVERVIEW_FETCH_LIMIT = 300


def fetch_passages_for_documents(
    document_ids: list[str], user_id: str, limit: int = OVERVIEW_FETCH_LIMIT
) -> list[WeaviateSearchResult]:
    """Every passage belonging to `document_ids` (server-side tenancy-
    filtered to `user_id`, same AD-2/FR-2 guarantee `search_passages`
    enforces), ordered `(document_id, chunk_index)` -- reading order
    within each document, not relevance order.

    This is a *retrieval*, not a *search*: `fetch_objects`, not
    `near_text` -- no query embedding is computed, and nothing here is
    scored against anything. That is deliberate. The document-overview
    chat intent this function exists for ("summarize this document",
    "outline it") needs the document's own content, not the handful of
    chunks that happen to sit nearest some embedded query text -- and
    critically, it must never produce a `distance`, since `chat/service.py`
    only ever applies `RELEVANCE_THRESHOLD` to results that carry one.
    Every `WeaviateSearchResult` this returns has `distance=None` for
    exactly that reason -- not because Weaviate failed to compute one, but
    because none was asked for, so the refusal short-circuit's `not
    passages or not any(p.distance is not None and ...)` check on the
    caller's side can never accidentally fire against an overview result.

    `document_ids` must be non-empty -- unlike `search_passages`, where an
    empty scope means "search everything", an unscoped document-wide
    fetch has no equivalent "everything" here without either loading a
    user's entire library into one prompt or silently guessing which
    documents they meant; resolving "no explicit scope" to a concrete
    document set (e.g. every Ready document) is `chat/service.py`'s job,
    using data this module doesn't have (`Document.status`).

    Weaviate's `fetch_objects` does not sort server-side (no `near_text`,
    no `Sort` requested), and paginates internally, so the returned object
    order is not guaranteed reading order on its own even within one
    document, let alone across several requested at once -- hence the
    explicit sort below rather than trusting whatever order the response
    already came back in.
    """
    if not document_ids:
        raise ValueError("fetch_passages_for_documents requires a non-empty document_ids list")

    filters = Filter.by_property("user_id").equal(user_id) & Filter.by_property(
        "document_id"
    ).contains_any(document_ids)

    def _query():
        client = get_weaviate_client()
        _ensure_passage_collection(client)
        return client.collections.get(PASSAGE_COLLECTION).query.fetch_objects(
            filters=filters,
            limit=limit,
        )

    response = _with_reconnect(_query)

    results = [
        WeaviateSearchResult(
            chunk_id=obj.properties["chunk_id"],
            document_id=obj.properties["document_id"],
            chapter=obj.properties["chapter"],
            chunk_index=obj.properties["chunk_index"],
            text=obj.properties["text"],
            distance=None,
        )
        for obj in response.objects
    ]
    results.sort(key=lambda r: (r.document_id, r.chunk_index))
    return results
