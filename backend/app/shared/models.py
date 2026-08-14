"""Shared SQLAlchemy declarative base and ORM models.

`Base` is the single declarative base all ORM models attach to, and
`backend/alembic/env.py` points its autogenerate target metadata at
`Base.metadata`.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""


class User(Base):
    """A registered account (Story 1.3).

    `id` uses SQLAlchemy's dialect-agnostic `Uuid` type (native UUID on
    Postgres, portable elsewhere) with a Python-side default rather than a
    Postgres server-side default, so the same model works against SQLite in
    tests without a Postgres-only extension.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Document(Base):
    """An uploaded document (Story 2.1).

    Minimal columns this story needs -- later stories (2.2+) `ALTER` this
    table incrementally (content_hash in 2.6, failed_reason in 2.5,
    chapter/passage counts in 2.2/2.3) rather than guessing those fields
    now. `content` stores the raw uploaded bytes directly in Postgres
    (`LargeBinary` -> `bytea`) -- a deliberate zero-new-infra choice flagged
    in the story's "Ask First" section, not a default to assume for later
    stories without re-confirming.

    `status` stores the FR-4 five-value vocabulary verbatim
    (`Uploaded`/`Extracting`/`Graphing`/`Ready`/`Failed`) as a plain string,
    not a DB enum -- this story only ever writes `Uploaded`; Story 2.3+
    advances it.

    `chapter_breakdown` (Story 2.4, deferred from 2.2/2.3 -- see the spec
    change log in `spec-2-4-...md`) is `dict[chapter_name] -> passage_count`,
    populated once, only in the same commit that sets `status = "Ready"`.
    `sa.JSON` (the dialect-agnostic generic type), not `postgresql.JSONB`:
    `backend/tests/conftest.py` runs the suite against `sqlite:///:memory:`,
    which has no JSONB support, but both dialects support `JSON`. Nullable,
    defaulting to `None` -- a document that never reaches `Ready` (still
    `Extracting`/`Graphing`, or `Failed`) keeps this column `None`, never a
    fabricated `{}` (mirrors UX-DR8's "Pending, never a fabricated 0" rule
    on the frontend).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    chapter_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Story 2.5: a short, human-readable, stage-aware reason, set only in
    # the same commit that sets `status = "Failed"` (never a separate
    # write) -- see `documents/service.py::ingest_document`'s `except`
    # block. `None` for every other status. A plain `String`, not a typed
    # error taxonomy (no error codes/i18n keys) -- matches this project's
    # existing "reason goes to the logger" -> "reason goes to a text field"
    # precedent from 2.3/2.4.
    failed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # Story 2.6: sha256 of the raw uploaded bytes (`content`), hex-encoded
    # (64 chars) -- never derived from `filename`, so a byte-identical
    # rename still dedupes. Computed in `service.upload_document` before
    # this row is constructed. `nullable=False` at the model level; the
    # migration that adds this column adds it nullable first, backfills
    # every existing row, then alters to NOT NULL, so the column is never
    # briefly enforced against rows that don't have a value yet. Paired
    # with a composite unique index on `(user_id, content_hash)` (added in
    # the same migration) -- the DB-level guard against the concurrent-
    # duplicate-upload race, mirroring Story 2.4's Neo4j uniqueness
    # constraint for the identical race shape.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        # Story 2.6: DB-level guard closing the concurrent-duplicate-upload
        # race that the pre-create hash lookup alone can't -- two requests
        # racing past `get_document_by_content_hash` before either commits
        # would otherwise both insert. The loser's `INSERT` raises
        # `IntegrityError`, which `service.upload_document` catches, rolls
        # back, and re-queries by hash to return the winner's row.
        Index("ix_documents_user_id_content_hash", "user_id", "content_hash", unique=True),
    )
