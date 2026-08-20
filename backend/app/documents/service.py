"""Documents module business logic: upload validation and orchestration.

Raises `HTTPException` directly (AD-3: no custom error envelope), mirroring
`auth/service.py`. Validation happens here, before any repository call --
the route layer stays thin and a rejected file never reaches the DB.
"""

import hashlib
import logging
import pathlib
import uuid
from collections import Counter
from collections.abc import Callable
from typing import Final, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.documents import repository
from app.documents.parsing import CHUNK_OVERLAP_WORDS, parse_document
from app.shared.data_access.neo4j_client import (
    prune_document_from_graph,
    write_entities_and_relationships,
)
from app.shared.data_access.session import get_session_factory
from app.shared.data_access.shapes import Neo4jEntity, Neo4jRelationship, WeaviatePassage
from app.shared.data_access.weaviate_client import (
    PASSAGE_BATCH_SIZE,
    delete_passages_for_document,
    write_passages,
)
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

# Story 2.6: what `upload_document` did with this upload. See that
# function's docstring for how the route maps each to a status code and
# to whether ingestion is scheduled.
UploadOutcome = Literal["created", "duplicate", "reingested"]

# Story 2.5: short, human-readable, stage-aware labels prefixed onto a
# truncated `str(exc)` to build `Document.failed_reason` -- never a raw
# traceback or provider payload. In pipeline order; `_reason` below joins
# whichever one was current when the exception was caught.
_STAGE_LABEL_PARSING: Final = "Could not read this document"
_STAGE_LABEL_INDEXING: Final = "Could not index this document's content"
_STAGE_LABEL_EXTRACTION: Final = "Could not extract entities from this document"
_STAGE_LABEL_GRAPH_WRITE: Final = "Could not save extracted entities to the graph"

# Long tracebacks or provider payloads never land in the DB or UI.
_FAILED_REASON_MAX_CHARS: Final = 300


def _reason(stage_label: str, exc: Exception) -> str:
    return f"{stage_label}: {str(exc)[:_FAILED_REASON_MAX_CHARS]}"


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
) -> tuple[Document, UploadOutcome]:
    """Stores one already-validated upload as a `Uploaded`-status row, or
    (Story 2.6) returns an existing byte-identical document instead of
    creating a new one.

    Format/content-type (`validate_format`) and size (`validate_size`) are
    validated by the caller (route layer) before this runs -- by the time
    `content` is fully in hand, both checks have already passed.
    `current_user` (resolved only from `get_current_user`, per AD-2) is
    the sole source of `user_id` written to the row -- never anything
    client-supplied. No parsing/indexing happens here (Story 2.3's job);
    a newly-created row lands at `status="Uploaded"` and stays there.

    Returns the document plus one of three outcomes, which is what the
    route maps to a status code and to whether ingestion gets scheduled:

    - `"created"` -- a genuinely new document. 201, ingestion scheduled.
    - `"duplicate"` -- a byte-identical match that needs no work. 200, no
      ingestion (NFR-7: no parse/embed/LLM call for a duplicate).
    - `"reingested"` -- a byte-identical match against a *`Failed`*
      document, reset to `Uploaded` and retried in place. 200 (no row was
      created), ingestion scheduled.

    A three-state outcome rather than the `is_duplicate` boolean this
    story originally specified: re-uploading a failed document is neither
    a creation nor a no-op, and collapsing it into either one produces a
    visibly wrong answer (see the Spec Change Log). Retrying a *failed*
    ingestion is not the duplicated work NFR-7 forbids -- it is the first
    attempt that gets to succeed -- and it still creates no second row.

    The hash is computed from raw bytes only (never `filename`), so a
    byte-identical re-upload under a different name still dedupes (AC3).
    The pre-create lookup runs before any `Document(...)` is constructed --
    a non-`Failed` hash match returns the *existing* row untouched and
    never reaches the repository's insert at all, so the caller can never
    schedule ingestion for it.

    On the rare race where two concurrent uploads of the identical new file
    both miss this pre-create lookup, the composite unique index on
    `(user_id, content_hash)` rejects the second `INSERT` with an
    `IntegrityError`. Caught here: roll back, re-query by hash (the winning
    request's commit is visible by now), and return that row as a
    duplicate -- never let the exception propagate as a 500.
    """
    content_hash = hashlib.sha256(content).hexdigest()

    existing = repository.get_document_by_content_hash(db, current_user.id, content_hash)
    if existing is not None:
        if existing.status == "Failed":
            # Re-uploading a failed document retries it in place rather
            # than being swallowed as a duplicate -- see this function's
            # docstring for why that isn't a violation of NFR-7.
            if repository.claim_failed_document_for_reingest(db, existing.id):
                db.commit()
                db.refresh(existing)
                return existing, "reingested"
            # Lost the claim to a concurrent re-upload that is already
            # retrying this row -- fall through to the duplicate response
            # rather than scheduling a second pipeline against it.
            db.rollback()
            db.refresh(existing)
        return existing, "duplicate"

    document = Document(
        id=uuid.uuid4(),
        user_id=current_user.id,
        filename=filename,
        file_type=file_type,
        file_size_bytes=len(content),
        status="Uploaded",
        content=content,
        content_hash=content_hash,
    )

    try:
        document = repository.create_document(db, document)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = repository.get_document_by_content_hash(db, current_user.id, content_hash)
        if existing is None:
            # The unique constraint fired for some other reason than the
            # expected concurrent-duplicate race -- re-raise rather than
            # silently returning `None` as if it were a duplicate.
            raise
        return existing, "duplicate"

    db.refresh(document)
    return document, "created"


def _build_extraction_text(chunks: list, budget: int = EXTRACTION_CHAR_BUDGET) -> str:
    """Concatenates the already-parsed `chunks`' text (Story 2.4) into one
    string for entity extraction, in parse order, truncated to `budget`
    characters -- the same `chunks` list already produced for the Weaviate
    write above, never re-parsed. One extraction call per document over
    this text (Design Notes), not per-passage.

    Consecutive chunks *within a chapter* deliberately overlap by
    `parsing.CHUNK_OVERLAP_WORDS` words, so that a passage straddling a
    chunk boundary is still retrievable whole (Story 2.3). That overlap
    earns its keep in the vector index, but concatenating chunks naively
    here would re-send those words to the LLM -- ~16% of the character
    budget spent re-reading text the model already saw, for a budget whose
    entire purpose is fitting as much *distinct* document content as
    possible into one call. The overlap is dropped back off, so the budget
    buys real coverage instead.

    Dropped by word count rather than by matching text: the overlap is
    defined in words by the chunker, and `" ".join` on a word slice is not
    guaranteed to reproduce the original whitespace byte-for-byte, so a
    string-suffix comparison would silently fail to strip anything.

    Gated on `chunk.is_chapter_start`, not a `chapter == previous_chapter`
    title comparison: two distinct chapters can share the exact same title
    (e.g. two "Overview" sections under different parts of one document),
    which a title comparison reads as one chapter continuing and wrongly
    strips real, non-overlapping words off the second section's opening
    chunk. `is_chapter_start` is set by the chunker itself, the only code
    that actually knows whether overlap was applied to a given chunk.
    """
    parts: list[str] = []
    remaining = budget
    for chunk in chunks:
        if remaining <= 0:
            break
        text = chunk.text
        if not chunk.is_chapter_start:
            text = " ".join(text.split(" ")[CHUNK_OVERLAP_WORDS:])
        if not text:
            continue
        piece = text[:remaining]
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

    Writes in batches of `PASSAGE_BATCH_SIZE`. No vectors are computed
    here any more -- Weaviate embeds each passage's `text` server-side on
    insert -- so this loop now only bounds the size of a single
    `insert_many` payload, not Python-side vector memory. It also bounds
    Weaviate Embeddings request count: one batch is one billed request
    against the free tier's 2,000/day, so a 1,000-chunk document costs 10
    requests rather than 1,000.
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

        # Story 2.5: reassigned immediately before each risky call below
        # (mirroring how `document.status` is already reassigned inline
        # through this same function) -- whichever value is current when
        # the `except` below catches an exception identifies which stage
        # was in flight, without restructuring into per-stage try/except
        # blocks that would fragment the single outer `except` AD-1's
        # rollback logic already depends on.
        stage = _STAGE_LABEL_PARSING
        try:
            document.status = "Extracting"
            db.commit()

            chunks = parse_document(document.file_type, document.content)
            # Release the raw upload (up to the 20MB cap) as soon as it's
            # been parsed: the session's identity map would otherwise hold
            # those bytes resident until `db.close()` in the `finally`,
            # which since Story 2.4 spans the embedding loop *and* the LLM
            # extraction call (up to 2x30s on retries) -- the longest,
            # least memory-headroom part of the pipeline, on a 512MB
            # instance that also allows concurrent uploads. Expired, not
            # `del`'d: the attribute stays valid and would simply re-load
            # from the DB if anything below touched it. Nothing does.
            db.expire(document, ["content"])
            stage = _STAGE_LABEL_INDEXING
            delete_passages_for_document(document_id_str, user_id_str)
            for batch_start in range(0, len(chunks), PASSAGE_BATCH_SIZE):
                batch = chunks[batch_start : batch_start + PASSAGE_BATCH_SIZE]
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
                    )
                    for chunk in batch
                ]
                write_passages(passages)

            # Story 2.4: the Weaviate write has fully succeeded by this
            # point -- advance to Graphing before the extraction call, per
            # AD-1's fixed write order (Weaviate first, Neo4j second).
            # Story 2.5: `stage` flips to extraction here, not right before
            # `_build_extraction_text` below -- a failure in this
            # `db.commit()` (or anything between the Weaviate write loop
            # finishing and the extraction call starting) is a
            # Graphing-transition failure, not an indexing one, and must
            # not be mislabeled as "Could not index this document's
            # content".
            stage = _STAGE_LABEL_EXTRACTION
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
            stage = _STAGE_LABEL_GRAPH_WRITE
            # Story 2.8 follow-up: clear this document's own prior graph
            # attribution before writing its new extraction, mirroring the
            # `delete_passages_for_document` call above the batch loop --
            # without this, a reingest (Story 2.6's retry-from-Failed path,
            # or any future retry feature) only ever appends. Extraction is
            # LLM-driven and non-deterministic, so an entity the previous
            # run produced but this run doesn't would otherwise stay
            # attributed to this document forever, silently surviving under
            # `source_document_ids` even though nothing currently in the
            # document supports it. Idempotent and safe on a document's
            # first-ever ingestion too (prunes zero rows).
            prune_document_from_graph(document_id_str, user_id_str)
            write_entities_and_relationships(
                neo4j_entities, neo4j_relationships, user_id_str, document_id_str
            )

            # `chapter_breakdown` is built from the same `chunks` list the
            # Weaviate write already used above -- no re-parsing. Counter
            # preserves insertion order of first appearance, matching
            # document reading order with no server-side sort needed later.
            chapter_breakdown = dict(Counter(chunk.chapter for chunk in chunks))

            document.status = "Ready"
            document.chapter_breakdown = chapter_breakdown
            db.commit()
        except Exception as exc:
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
                # Same reasoning as the Weaviate cleanup directly above,
                # for the graph half of AD-1: if the failure happened after
                # `write_entities_and_relationships` already committed (e.g.
                # the final `db.commit()` that sets `Ready` is what failed),
                # this document's entities/relationships are live in Neo4j,
                # attributed via `source_document_ids` to a row that's about
                # to be marked `Failed`. Left unpruned, they'd survive
                # indefinitely -- unreachable by any future successful
                # reingest's own pre-write prune, since that only fires on
                # the *next* run, which may never come. Idempotent and safe
                # even if the failure happened before any graph write this
                # run (prunes zero rows).
                prune_document_from_graph(document_id_str, user_id_str)
            except Exception:
                logger.exception(
                    "Failed to clean up partially-written graph data for document %s",
                    document_id,
                )
            try:
                db.rollback()
                document.status = "Failed"
                # Story 2.5: set in the exact same commit as `status =
                # "Failed"` above -- never a separate write, so the two
                # fields can never disagree about whether a reason exists.
                document.failed_reason = _reason(stage, exc)
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


# Story 2.7 (Spec Change Log): the only two statuses guaranteed to have no
# background task concurrently writing to this row. `ingest_document` (see
# its own docstring) runs as a real concurrent `BackgroundTasks` job and
# writes Weaviate passages while `status` is `Extracting`, then Neo4j while
# `status` is `Graphing` -- deleting mid-flight would let that task keep
# writing *after* `delete_document`'s own Weaviate delete already ran,
# orphaning fresh passages under a document id no longer in Postgres. This
# mirrors `claim_failed_document_for_reingest`'s existing retry-lock
# precedent (Story 2.6): only act on a document when no background task
# could be concurrently touching it.
# Public (no leading underscore): `auth/service.py::delete_account` (Story
# 5.3) also imports this, to apply the identical guard across every
# document a whole account owns rather than redefining the same set.
DELETABLE_STATUSES: Final = {"Ready", "Failed"}


def delete_document(db: Session, current_user: User, document_id: uuid.UUID) -> None:
    """Hard-deletes one document, its Weaviate passages, and its graph
    attribution (Story 2.7 + Story 2.8). Raises `HTTPException(404)` for a
    missing/not-owned document, via the same `get_document` lookup and
    message the read path already uses -- so "not yours" and "doesn't
    exist" stay indistinguishable here too. Raises `HTTPException(409)` if
    the document is still mid-ingestion (`Uploaded`, `Extracting`, or
    `Graphing`) -- see `DELETABLE_STATUSES`.

    Delete order is fixed and load-bearing: `delete_passages_for_document`
    (Weaviate) runs first, then `prune_document_from_graph` (Neo4j), then
    the row is deleted and committed. Each step only runs once the previous
    one has succeeded, so a mid-failure never leaves a document row
    pointing at partially-cleaned stores -- e.g. if the Neo4j prune raises,
    the row still exists and the user can safely retry the same delete
    (`prune_document_from_graph` is idempotent, so re-running it after a
    partial success matches zero additional rows the second time).

    `prune_document_from_graph` (Story 2.8, OD-4) reverses Story 2.7's
    original boundary: entities/relationships unique to this document are
    removed from the graph, while ones a surviving document still
    contributes to are kept, reference-counted via `source_document_ids`.
    """
    document = get_document(db, current_user, document_id)
    if document.status not in DELETABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Document is still being processed and can't be deleted yet.",
        )
    delete_passages_for_document(str(document.id), str(current_user.id))
    prune_document_from_graph(str(document.id), str(current_user.id))
    repository.delete_document_for_user(db, current_user.id, document_id)
    db.commit()
