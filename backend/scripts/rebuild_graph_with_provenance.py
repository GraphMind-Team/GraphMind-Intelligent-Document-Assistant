"""One-time operational rebuild: wipe Neo4j, re-extract every `Ready`
document with `source_document_ids` provenance (Story 2.8, OD-4).

Why this exists: `write_entities_and_relationships` only started stamping
`source_document_ids` in Story 2.8. Every entity/relationship written by
an earlier ingestion (Story 2.4) carries no document attribution at all --
`prune_document_from_graph`'s `coalesce(..., [])` treats those as
already-empty, so they can never be pruned, no matter how many times their
contributing document is deleted. The only way to close that gap for data
that already exists is to clear it and re-derive it with the new field
present from the start.

This is NOT run automatically -- not at app startup, not as a background
job, not on a schedule. It is a standalone script, run by a human, once,
against one database at a time. Requires an explicit `--yes` flag; without
it, this prints what it *would* do and exits without touching anything.

Usage:
    python -m scripts.rebuild_graph_with_provenance --yes

Run from `backend/` (so `app` and `scripts` are both importable) with the
same environment (`.env` / real env vars) the app itself would use --
`DATABASE_URL`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and
`OPENROUTER_API_KEY` (re-extraction makes one real LLM call per document).

Ask First (spec Boundaries): running this against the real Aura database
wipes every user's graph data. Get explicit human go-ahead before running
it for real -- same as Story 2.6's real-database migration required.
"""

import argparse
import logging
import sys

from sqlalchemy import select

from app.documents.parsing import parse_document
from app.documents.service import _build_extraction_text
from app.shared.data_access.neo4j_client import (
    wipe_all_entities_and_relationships,
    write_entities_and_relationships,
)
from app.shared.data_access.session import get_session_factory
from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship
from app.shared.llm_client import extract_entities_and_relationships
from app.shared.models import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _rebuild(db) -> tuple[int, int]:
    """Wipes the graph, then re-extracts + re-writes every `Ready`
    document. Returns `(succeeded, failed)` document counts.

    A per-document failure (parse error, LLM call exhausting retries,
    Neo4j write error) is logged and skipped rather than aborting the
    whole run -- one bad document must not block re-provenancing every
    other one. `Ready` is the only status considered: `Failed`/mid-
    ingestion documents have no reliable extracted content to rebuild
    from, and a later real upload/retry will produce provenanced entities
    for them the normal way.
    """
    documents = list(db.execute(select(Document).where(Document.status == "Ready")).scalars().all())
    logger.info("Found %d Ready document(s) to rebuild.", len(documents))

    wipe_all_entities_and_relationships()
    logger.info("Wiped all Entity nodes and relationships.")

    succeeded = 0
    failed = 0
    for document in documents:
        document_id_str = str(document.id)
        try:
            chunks = parse_document(document.file_type, document.content)
            extraction_text = _build_extraction_text(chunks)
            extraction_result = extract_entities_and_relationships(extraction_text)

            user_id_str = str(document.user_id)
            entities = [
                Neo4jEntity(name=entity.name, type=entity.type, user_id=user_id_str)
                for entity in extraction_result.entities
            ]
            relationships = [
                Neo4jRelationship(
                    source_entity_name=relationship.source,
                    target_entity_name=relationship.target,
                    relationship_type=relationship.type,
                    user_id=user_id_str,
                )
                for relationship in extraction_result.relationships
            ]
            write_entities_and_relationships(entities, relationships, user_id_str, document_id_str)
            logger.info(
                "Rebuilt document %s: %d entities, %d relationships.",
                document_id_str,
                len(entities),
                len(relationships),
            )
            succeeded += 1
        except Exception:
            logger.exception("Failed to rebuild document %s -- skipped.", document_id_str)
            failed += 1

    return succeeded, failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required to actually run. Without it, this is a no-op that only prints what would happen.",
    )
    args = parser.parse_args()

    if not args.yes:
        print(
            "Dry run only -- this would wipe ALL Neo4j entities/relationships for every user, "
            "then re-extract and re-write every 'Ready' document with source_document_ids "
            "provenance. Re-run with --yes to actually do this.",
            file=sys.stderr,
        )
        sys.exit(1)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        succeeded, failed = _rebuild(db)
    finally:
        db.close()

    logger.info("Rebuild complete: %d succeeded, %d failed.", succeeded, failed)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
