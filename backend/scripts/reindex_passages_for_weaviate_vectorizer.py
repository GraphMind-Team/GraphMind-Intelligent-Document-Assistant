"""One-time operational rebuild: recreate the `Passage` collection with
Weaviate-side embeddings, then re-index every `Ready` document into it.

Why this exists: passages used to be vectorized in-process by fastembed
(`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim) and written to a
`Passage` collection configured `vectorizer=none`. That model needed
~554MB resident on top of a ~143MB app, which OOM-restarted the service
on Render's 512MB free instance on every boot. Embedding now happens
inside Weaviate (`text2vec-weaviate`, see `weaviate_client
.EMBEDDING_MODEL`), which the app cannot retrofit onto the existing
collection for two reasons:

  1. A collection's vectorizer is fixed at creation. It cannot be
     changed by an update -- the collection has to be dropped and
     remade.
  2. The vectors themselves are from a different model in a different
     number of dimensions (384 -> 1024). Even if the vectorizer could be
     swapped, every stored vector would be meaningless under the new
     one: query embeddings and passage embeddings would live in
     unrelated spaces, and retrieval would return effectively random
     passages rather than failing loudly.

`_ensure_passage_collection` deliberately cannot do this itself. It
short-circuits on `exists()`, so against an already-created collection it
will happily keep using the OLD 384-dim `vectorizer=none` schema forever
and never report a problem -- which is the correct behaviour for a
concurrency guard and the wrong behaviour for a migration. Dropping a
collection full of a user's data is not something an app should do
implicitly at startup; it is a human decision, which is why it lives here
behind `--yes`.

This is NOT run automatically -- not at app startup, not as a background
job, not on a schedule. It is a standalone script, run by a human, once,
against one deployment at a time. Requires an explicit `--yes` flag;
without it, this prints what it *would* do and exits without touching
anything.

Usage:
    python -m scripts.reindex_passages_for_weaviate_vectorizer --yes

Run from `backend/` (so `app` and `scripts` are both importable) with the
same environment (`.env` / real env vars) the app itself would use --
`DATABASE_URL`, `WEAVIATE_URL`, and `WEAVIATE_API_KEY`. Unlike
`rebuild_graph_with_provenance.py` this needs no `OPENROUTER_API_KEY`: it
re-parses and re-writes passages, and Weaviate does the embedding, so no
LLM call is made at any point.

Free-tier quota: Weaviate Embeddings allows 2,000 requests/day and this
script spends one per `PASSAGE_BATCH_SIZE` chunks. A library of a few
dozen documents is comfortably inside that; a very large one may need to
be resumed the next day, which is safe -- see `--skip-recreate`.

Ask First (spec Boundaries): running this against the real Weaviate
cluster deletes every user's passages before rewriting them. Between the
drop and the end of the run, chat retrieval returns nothing for everyone.
Get explicit human go-ahead before running it for real -- same as Story
2.6's real-database migration and `rebuild_graph_with_provenance.py`.
"""

import argparse
import logging
import sys
import uuid

from sqlalchemy import select

from app.documents.parsing import parse_document
from app.shared.data_access.session import get_session_factory
from app.shared.data_access.shapes import WeaviatePassage
from app.shared.data_access.weaviate_client import (
    EMBEDDING_MODEL,
    PASSAGE_BATCH_SIZE,
    PASSAGE_COLLECTION,
    close_weaviate_client,
    ensure_ready,
    get_weaviate_client,
    write_passages,
)
from app.shared.models import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _drop_passage_collection() -> None:
    """Deletes the `Passage` collection outright, if it exists.

    `delete_many`-ing every object would not be enough: the objects are
    not the problem, the collection's fixed `vectorizer=none` config is.
    An emptied-but-not-dropped collection would be silently repopulated
    under the old schema by the very next `write_passages`, since
    `_ensure_passage_collection` only checks that the collection exists,
    never what it is configured with.
    """
    client = get_weaviate_client()
    if not client.collections.exists(PASSAGE_COLLECTION):
        logger.info("Collection %s does not exist -- nothing to drop.", PASSAGE_COLLECTION)
        return
    client.collections.delete(PASSAGE_COLLECTION)
    logger.info("Dropped collection %s (old vectorizer=none schema).", PASSAGE_COLLECTION)

    # `_ensure_passage_collection` caches "this collection exists" in a
    # module-level flag and short-circuits on it. Nothing in this script's
    # current order sets that flag before the drop, but if anything ever
    # did, the `ensure_ready()` that follows would skip creation entirely
    # and every subsequent write would fail against a collection that no
    # longer exists. `close_weaviate_client` clears the flag as part of
    # its documented contract, so this resets it without reaching into a
    # private global; `ensure_ready()` transparently reconnects.
    close_weaviate_client()


def _reindex(db) -> tuple[int, int]:
    """Re-parses and re-writes every `Ready` document's passages. Returns
    `(succeeded, failed)` document counts.

    A per-document failure (parse error, Weaviate write error, quota
    exhaustion) is logged and skipped rather than aborting the whole run
    -- one bad document must not block re-indexing every other one. This
    mirrors `rebuild_graph_with_provenance.py`'s per-document tolerance
    for the same reason.

    `Ready` is the only status considered: `Failed`/mid-ingestion
    documents have no reliable extracted content to rebuild from, and a
    later real upload/retry will index them the normal way.

    Chunk ids are recomputed with the same `uuid5(NAMESPACE_URL,
    f"{document_id}:{chunk_index}")` derivation `ingest_document` uses, so
    a passage keeps the id it had before -- citations already persisted in
    chat history still resolve to the same chunk. That also makes this
    script idempotent per document: re-running it overwrites each object
    by id rather than accumulating duplicates.
    """
    documents = list(db.execute(select(Document).where(Document.status == "Ready")).scalars().all())
    logger.info("Found %d Ready document(s) to re-index.", len(documents))

    succeeded = 0
    failed = 0
    for document in documents:
        document_id_str = str(document.id)
        user_id_str = str(document.user_id)
        try:
            chunks = parse_document(document.file_type, document.content)
            # No delete_passages_for_document call: the whole collection
            # was just dropped, so there is nothing stale to remove, and
            # the uuid5 ids above make a partial re-run overwrite rather
            # than duplicate.
            for batch_start in range(0, len(chunks), PASSAGE_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + PASSAGE_BATCH_SIZE]
                write_passages(
                    [
                        WeaviatePassage(
                            chunk_id=str(
                                uuid.uuid5(
                                    uuid.NAMESPACE_URL,
                                    f"{document_id_str}:{chunk.chunk_index}",
                                )
                            ),
                            document_id=document_id_str,
                            user_id=user_id_str,
                            chapter=chunk.chapter,
                            chunk_index=chunk.chunk_index,
                            text=chunk.text,
                        )
                        for chunk in batch
                    ]
                )
            logger.info(
                "Re-indexed document %s: %d passage(s) in %d batch(es).",
                document_id_str,
                len(chunks),
                (len(chunks) + PASSAGE_BATCH_SIZE - 1) // PASSAGE_BATCH_SIZE,
            )
            succeeded += 1
        except Exception:
            logger.exception("Failed to re-index document %s -- skipped.", document_id_str)
            failed += 1

    return succeeded, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually run. Without it, this is a no-op that only prints what would happen.",
    )
    parser.add_argument(
        "--skip-recreate",
        action="store_true",
        help=(
            "Skip the drop/recreate and only re-index documents. Use this to resume a run "
            "that stopped partway (e.g. hitting the daily embedding quota) -- the collection "
            "already has the new schema by then, and re-writing a document is idempotent."
        ),
    )
    args = parser.parse_args()

    if not args.yes:
        print(
            f"Dry run only -- this would DROP the Weaviate '{PASSAGE_COLLECTION}' collection "
            f"(deleting every user's passages), recreate it with server-side embeddings via "
            f"{EMBEDDING_MODEL}, then re-parse and re-index every 'Ready' document.\n"
            "Chat retrieval returns nothing for every user between the drop and the end of "
            "the run.\n"
            "Re-run with --yes to actually do it."
        )
        return

    session_factory = get_session_factory()
    db = session_factory()
    try:
        if args.skip_recreate:
            logger.info("--skip-recreate: leaving the existing collection in place.")
            ensure_ready()
        else:
            _drop_passage_collection()
            # Recreates it with the current schema -- the same code path
            # the app itself uses at startup, so this script can never
            # create a collection shaped differently from what the app
            # expects.
            ensure_ready()
            logger.info("Recreated %s with vectorizer %s.", PASSAGE_COLLECTION, EMBEDDING_MODEL)

        succeeded, failed = _reindex(db)
    finally:
        db.close()
        close_weaviate_client()

    logger.info("Done. %d document(s) re-indexed, %d failed.", succeeded, failed)
    if failed:
        # Non-zero exit so a partial run is visible to whoever ran it
        # rather than reading as success in a scrollback.
        sys.exit(1)


if __name__ == "__main__":
    main()
