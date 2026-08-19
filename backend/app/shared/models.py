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
    # Python-side default (Story 5.2), mirroring `id` above -- tests build
    # the schema via Base.metadata.create_all() rather than Alembic, so
    # every ORM insert needs the value regardless of the migration's
    # server_default, which only exists to backfill pre-5.2 Postgres rows.
    theme: Mapped[str] = mapped_column(String(5), nullable=False, default="light")


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


class ChatMessage(Base):
    """One turn of a user's single, ongoing conversation (Story 3.4/FR-17).

    One row per message, same declarative pattern as `Document` above --
    Uuid PK w/ Python-side default, plain `JSON` (not JSONB) for the same
    SQLite-test-compat reason as `Document.chapter_breakdown`. Queried
    exclusively through `user_scoped_select` (AD-2), never a hand-written
    `select(ChatMessage).where(...)`.

    `user_id` is *not* separately `index=True` the way `Document.user_id`
    is -- every real query here (`chat/repository.py`'s
    `get_recent_turn_messages`/`list_messages_for_user`) filters on
    `user_id` and then sorts on `(created_at, role, id)`, so a plain
    single-column `user_id` index would only ever serve the filter half
    and leave the sort to a full pass over that user's rows. The
    composite index in `__table_args__` below covers both in one index
    (its leading column still serves a bare `user_id = ...` filter too,
    making a separate single-column index redundant).

    Two disjoint row shapes, both fitting this one table (mirrors
    `AskResponse`'s own "answer OR empty_reason" duality rather than
    inventing a second table for a per-account conversation that's always
    exactly one thread -- FR-17 explicitly rules out a multi-conversation
    model):
      - `role="user"`: `question` set, `segments`/`empty_reason` both
        `None`.
      - `role="assistant"`: `segments` (a JSON-serialized list of
        `AnswerSegmentResponse`-shaped dicts) set (possibly `[]` for a
        refusal/empty outcome) and/or `empty_reason` set, `question`
        `None`.
    Enforced by `chat/repository.py::save_message` (the only writer), not
    a DB constraint -- matches this codebase's existing "the writer
    upholds the shape, not the schema" precedent (e.g. `Document
    .failed_reason`, only ever set alongside `status="Failed"`).

    No `conversation_id` -- one continuous conversation per user account,
    per FR-17's explicit scope boundary (no multi-conversation/switcher
    concept exists or is being introduced). `user_id` alone is the whole
    thread's identity.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # 'user' | 'assistant' -- a plain string, not a DB enum, matching
    # `Document.status`'s own "vocabulary enforced in code, not schema"
    # precedent.
    role: Mapped[str] = mapped_column(String, nullable=False)
    # Set only on `role="user"` rows.
    question: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set only on `role="assistant"` rows -- a JSON list, always present
    # (possibly `[]`) on an assistant row, `None` on a user row.
    segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Set only on `role="assistant"` rows when the answer was empty
    # (mirrors `AskResponse.empty_reason`'s own four-value vocabulary);
    # `None` for a real answer or for any `role="user"` row.
    empty_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # Covers every real query this table serves: `user_id` filter,
        # then `(created_at, role, id)` sort (see
        # `chat/repository.py`'s `_TURN_ROLE_RANK`/`_strictly_before` --
        # `role` is the literal column here, not the `CASE`-computed rank
        # those use, but for a two-valued column the tied `created_at`
        # group a plain index leaves unsorted is at most a couple of
        # rows, cheap to finish in memory; the win is skipping a full
        # per-user table scan for the `user_id` filter and the bulk of
        # the `created_at` ordering, which is the part that actually
        # grows with conversation length).
        Index("ix_chat_messages_user_id_created_at_role_id", "user_id", "created_at", "role", "id"),
    )
