"""Documents module business logic: upload validation and orchestration.

Raises `HTTPException` directly (AD-3: no custom error envelope), mirroring
`auth/service.py`. Validation happens here, before any repository call --
the route layer stays thin and a rejected file never reaches the DB.
"""

import logging
import pathlib
import uuid
from collections import Counter
from collections.abc import Callable
from typing import Final

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.documents import repository
from app.documents.parsing import parse_document
from app.shared.data_access.neo4j_client import write_entities_and_relationships
from app.shared.data_access.session import get_session_factory
from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship, WeaviatePassage
from app.shared.data_access.weaviate_client import (
    PASSAGE_BATCH_SIZE,
    delete_passages_for_document,
    write_passages,
)
from app.shared.embeddings import embed_texts
from app.shared.llm_client import extract_entities_and_relationships
from app.shared.models import Document, User

logger = logging.getLogger(__name__)

# Story 2.4, Design Notes: a conservative fit under free-tier context
# limits alongside the extraction prompt itself -- not benchmarked against
# a real long document (see deferred-work.md). Truncation is for
# extraction only; Weaviate already holds every passage untruncated by
# the time this budget is applied.
EXTRACTION_CHAR_BUDGET: Final = 12_000

# 20MB per the story's Boundaries -- named here once so the reason cited in
# a rejection message and the actual enforced limit can never drift apart.
MAX_FILE_SIZE_BYTES: Final = 20 * 1024 * 1024

# Extension -> the FR-4-vocabulary-adjacent `file_type` value stored on the
# row. `.md`/`.markdown` both map to "markdown", `.html`/`.htm` both map to
# "html" -- the extension is what the user sees rejected/accepted, the
# stored `file_type` is the normalized value the rest of the app (Story
# 2.2+'s list/detail UI) keys off.
_EXTENSION_TO_FILE_TYPE: Final = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
}

# Content-Type sets are permissive by design, not just by extension: real
# browsers/OSes frequently have no mime mapping for .md (and sometimes
# .html) and fall back to "application/octet-stream" or "text/plain" --
# rejecting those would break the valid, common case. What this still
# catches is a file whose Content-Type actively disagrees with its
# extension (e.g. a .pdf upload sent as "application/msword").
#
# Compared against a normalized Content-Type (parameters like
# "; charset=utf-8" stripped, lowercased) -- browsers routinely send
# "text/plain; charset=utf-8" for .md/.html, which would otherwise fail an
# exact-string match against the bare "text/plain" entry below and reject
# a legitimate upload.
_ALLOWED_CONTENT_TYPES: Final = {
    "pdf": {"application/pdf", "application/octet-stream"},
    "markdown": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
    "html": {"text/html", "application/xhtml+xml", "application/octet-stream"},
}

_SUPPORTED_FORMATS_LABEL: Final = ".pdf, .md, .markdown, .html, .htm"


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return content_type
    return content_type.split(";", 1)[0].strip().lower()


def validate_format(filename: str, content_type: str | None) -> str:
    """Returns the normalized `file_type`, or raises `HTTPException(400)`
    with a plain-language reason (UX-DR19) -- format/content-type only, no
    size check. Split out from size validation so the route layer can
    reject a bad format/content-type *before* reading the request body at
    all, per the story's Boundaries ("Validate before any DB write, not
    after") -- the size limit still needs bytes in hand to enforce, but
    format never does."""
    extension = pathlib.Path(filename).suffix.lower()
    file_type = _EXTENSION_TO_FILE_TYPE.get(extension)
    if file_type is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {_SUPPORTED_FORMATS_LABEL}.",
        )

    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type and normalized_content_type not in _ALLOWED_CONTENT_TYPES[file_type]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Supported formats: {_SUPPORTED_FORMATS_LABEL}.",
        )

    return file_type


def validate_size(size: int) -> None:
    """Raises `HTTPException(400)` for an empty or oversized file. Called
    by the route layer *during* the bounded chunked read (aborting as soon
    as `MAX_FILE_SIZE_BYTES` is exceeded, never buffering a full oversized
    body) and again here for the empty-file case, which only the final
    size can reveal."""
    if size == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    if size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 20MB size limit.")


def upload_document(
    db: Session,
    current_user: User,
    *,
    filename: str,
    file_type: str,
    content: bytes,
) -> Document:
    """Stores one already-validated upload as a `Uploaded`-status row.

    Format/content-type (`validate_format`) and size (`validate_size`) are
    validated by the caller (route layer) before this runs -- by the time
    `content` is fully in hand, both checks have already passed.
    `current_user` (resolved only from `get_current_user`, per AD-2) is
    the sole source of `user_id` written to the row -- never anything
    client-supplied. No parsing/indexing happens here (Story 2.3's job);
    the row lands at `status="Uploaded"` and stays there.
    """
    document = Document(
        id=uuid.uuid4(),
        user_id=current_user.id,
        filename=filename,
        file_type=file_type,
        file_size_bytes=len(content),
        status="Uploaded",
        content=content,
    )

    document = repository.create_document(db, document)
    db.commit()
    db.refresh(document)
    return document


def _build_extraction_text(chunks: list, budget: int = EXTRACTION_CHAR_BUDGET) -> str:
    """Concatenates the already-parsed `chunks`' text (Story 2.4) into one
    string for entity extraction, in parse order, truncated to `budget`
    characters -- the same `chunks` list already produced for the Weaviate
    write above, never re-parsed. One extraction call per document over
    this text (Design Notes), not per-passage."""
    parts: list[str] = []
    remaining = budget
    for chunk in chunks:
        if remaining <= 0:
            break
        piece = chunk.text[:remaining]
        parts.append(piece)
        remaining -= len(piece)
    return "\n\n".join(parts)


def ingest_document(
    document_id: uuid.UUID,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Parse, embed, and index one document's passages, then extract its
    entities/relationships into the graph (Story 2.3 + Story 2.4).

    Runs as a `BackgroundTasks` job scheduled by the upload route, after
    the request's own `db` session has already been closed -- this opens
    its own session via `session_factory` (defaulting to the real
    `get_session_factory`). The explicit parameter, not just monkeypatching
    the shared factory, is what lets tests call this function directly
    with a controlled session rather than depending on a patched global.

    A plain `def`, not `async def`: Starlette runs sync background tasks in
    a threadpool, off the event loop -- `async def` here would block the
    loop for the seconds an embedding/LLM call takes, stalling every other
    in-flight request.

    Sets `status="Extracting"` before parsing starts, then `status=
    "Graphing"` once the Weaviate write has fully succeeded and before the
    entity-extraction call starts (AC3's "when parsing/graphing runs, then
    it advances" is about to happen, not already done), and finally
    `status="Ready"` -- with `chapter_breakdown` populated in the *same*
    commit -- once the Neo4j write has fully succeeded too. Any failure
    anywhere in parse/embed/write/extract/graph-write is caught by the same
    `except` block and marks the row `Failed` (after deleting this
    document's Weaviate passages, AD-1's compensating rollback -- a Neo4j
    write failure leaves the identical broken state a Weaviate failure
    would, so it needs identical cleanup): AD-1's documented retry-lock
    ("retry only accepted from Failed") would otherwise have no way to ever
    unlock a row that failed mid-pipeline. `chapter_breakdown` is only ever
    assigned on the `Ready` line below -- any failure before that point
    leaves it at its column default (`None`), never a partial value. This
    only covers in-process exceptions -- a hard process crash/restart
    mid-task still leaves a row stuck at `Extracting`/`Graphing` with no
    safety net; a known, accepted gap from Story 2.3 (would need a
    heartbeat/lease or a startup reconciliation pass to close).

    Embeds and writes in batches of `PASSAGE_BATCH_SIZE` rather than
    embedding every chunk up front into one `vectors` list: a large
    document (the 20MB upload cap) can run to thousands of chunks, and
    holding every chunk's 384-dim vector in memory simultaneously before
    the first one even reaches Weaviate is the more likely OOM path on a
    512MB instance -- the batched `write_passages` call on the Weaviate
    side alone doesn't help if everything already piled up in Python
    memory before any of it got sent.
    """
    session_factory = session_factory or get_session_factory()
    db = session_factory()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return  # deleted between upload and background-task run

        # Captured before the try block, not read off `document` again in
        # the except block: after a DB-caused failure, `db.rollback()`
        # can leave the session's objects expired, and re-accessing
        # `document.id`/`document.user_id` at that point would try to
        # re-fetch from a session that may itself be why this failed in
        # the first place -- precisely the case where the cleanup delete
        # below matters most, and precisely the case an attribute access
        # could quietly skip it in. Both are already loaded by the time
        # parsing starts, so capturing them here costs nothing.
        document_id_str = str(document.id)
        user_id_str = str(document.user_id)

        try:
            document.status = "Extracting"
            db.commit()

            chunks = parse_document(document.file_type, document.content)
            delete_passages_for_document(document_id_str, user_id_str)
            for batch_start in range(0, len(chunks), PASSAGE_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + PASSAGE_BATCH_SIZE]
                vectors = embed_texts([chunk.text for chunk in batch])
                passages = [
                    WeaviatePassage(
                        chunk_id=str(
                            uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id_str}:{chunk.chunk_index}")
                        ),
                        document_id=document_id_str,
                        user_id=user_id_str,
                        chapter=chunk.chapter,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        embedding=vector,
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ]
                write_passages(passages)

            # Story 2.4: the Weaviate write has fully succeeded by this
            # point -- advance to Graphing before the extraction call, per
            # AD-1's fixed write order (Weaviate first, Neo4j second).
            document.status = "Graphing"
            db.commit()

            extraction_text = _build_extraction_text(chunks)
            extraction_result = extract_entities_and_relationships(extraction_text)

            neo4j_entities = [
                Neo4jEntity(name=entity.name, type=entity.type, user_id=user_id_str)
                for entity in extraction_result.entities
            ]
            neo4j_relationships = [
                Neo4jRelationship(
                    source_entity_name=relationship.source,
                    target_entity_name=relationship.target,
                    relationship_type=relationship.type,
                    user_id=user_id_str,
                )
                for relationship in extraction_result.relationships
            ]
            write_entities_and_relationships(neo4j_entities, neo4j_relationships, user_id_str)

            # `chapter_breakdown` is built from the same `chunks` list the
            # Weaviate write already used above -- no re-parsing. Counter
            # preserves insertion order of first appearance, matching
            # document reading order with no server-side sort needed later.
            chapter_breakdown = dict(Counter(chunk.chapter for chunk in chunks))

            document.status = "Ready"
            document.chapter_breakdown = chapter_breakdown
            db.commit()
        except Exception:
            logger.exception("Ingestion failed for document %s", document_id)
            try:
                # Best-effort: a failure partway through the batch loop
                # above (say batch 30 of 50) leaves the first 29 batches'
                # passages sitting in Weaviate under a document that's
                # about to be marked Failed. Epic 3's retrieval filters by
                # user_id only, not status, so an orphaned partial set
                # would otherwise be read as a complete, valid document.
                # Idempotent and safe to call even if the failure happened
                # before any passage was ever written (deletes zero rows).
                # Uses the locals captured above, not `document.id`/
                # `document.user_id` again -- see the comment there.
                delete_passages_for_document(document_id_str, user_id_str)
            except Exception:
                # If Weaviate is what's unreachable, this cleanup attempt
                # fails too -- logged, not re-raised, since the primary
                # failure below still needs to be recorded either way.
                logger.exception(
                    "Failed to clean up partially-written passages for document %s",
                    document_id,
                )
            try:
                db.rollback()
                document.status = "Failed"
                db.commit()
            except Exception:
                # The recovery path itself can fail -- e.g. the DB
                # connection dropped, quite plausibly the very reason
                # ingestion failed in the first place. Left unguarded, that
                # second exception would propagate out of this background
                # task unhandled, leaving the row stuck at `Extracting`:
                # exactly the outcome this whole except block exists to
                # prevent. Logged and swallowed rather than re-raised --
                # there's no caller here to hand it to.
                logger.exception(
                    "Failed to mark document %s as Failed after an ingestion error",
                    document_id,
                )
    finally:
        db.close()


def list_documents(db: Session, current_user: User) -> list[Document]:
    return repository.list_documents_for_user(db, current_user.id)


def get_document(db: Session, current_user: User, document_id: uuid.UUID) -> Document:
    """One document by id, or `HTTPException(404)`.

    404 -- not 403 -- for another account's document: a 403 would confirm
    the id exists, which is itself a disclosure. The repository's
    user-scoped query returns `None` for both "no such document" and "not
    yours", so the two cases are indistinguishable from here by
    construction, not by a remembered convention.
    """
    document = repository.get_document_for_user(db, current_user.id, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
