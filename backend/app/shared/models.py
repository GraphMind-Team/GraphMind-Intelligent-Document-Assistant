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
    # UI language, ISO 639-1 code ("en"/"bg"/"de"). Same Python-side-default
    # rationale as `theme` above. Unlike `theme`, new rows don't always start
    # at this default -- `auth/routes.py::register` overrides it per-request
    # with the registration's resolved Accept-Language before the User is
    # constructed, so this default only actually applies when that header is
    # absent/unparseable.
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    # Story 1.6: `None` means "not yet verified"; a timestamp means
    # verified at that instant. A nullable timestamp, not a boolean --
    # records *when*, which a boolean would throw away, and every existing
    # account is meant to read as unverified until the migration's backfill
    # runs (there is no "verified but we don't know when" state to invent a
    # sentinel for). No Python-side non-None default needed the way
    # `theme` has one: `None` is exactly what a freshly `create_all()`'d
    # SQLite test row and a freshly migrated pre-1.6 Postgres row should
    # both start as before anything sets it.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


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

    # Folder-grouping feature: one folder per document, or `None` for
    # "Unfiled" -- never a required field, and never a list (the spec's
    # Never section rules out multi-parent folders). `ondelete="SET NULL"`
    # so deleting a folder never deletes its documents (the spec's
    # Boundaries): the DB itself enforces that the row survives as unfiled
    # even if some future code path forgets to clear it explicitly.
    # `index=True` -- mirrors every other FK/user-scoping column in this
    # file (`Document.user_id`, `Folder.user_id`, `ChatMessage.user_id`):
    # Postgres doesn't auto-index FK columns, and `ON DELETE SET NULL`
    # needs one so deleting a folder doesn't force a full-table scan of
    # `documents` to find its members.
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        # Story 2.6: DB-level guard closing the concurrent-duplicate-upload
        # race that the pre-create hash lookup alone can't -- two requests
        # racing past `get_document_by_content_hash` before either commits
        # would otherwise both insert. The loser's `INSERT` raises
        # `IntegrityError`, which `service.upload_document` catches, rolls
        # back, and re-queries by hash to return the winner's row.
        Index("ix_documents_user_id_content_hash", "user_id", "content_hash", unique=True),
    )


class Folder(Base):
    """A user-owned folder documents can optionally belong to (folder
    grouping feature).

    One folder per document, never nested, never multi-parent (see the
    spec's Never section) -- enforced structurally by `Document.folder_id`
    being a single nullable scalar FK, not a join table. `color` stores one
    of the fixed pastel-vocabulary keys (`FOLDER_COLORS` in
    `folders/service.py`), the same "vocabulary enforced in service code,
    never a free-form client value" precedent `Document.status` already
    sets -- a plain `String`, not a DB enum.

    Queried exclusively through `user_scoped_select` (AD-2), same as every
    other per-user Postgres table.
    """

    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ChatSession(Base):
    """One of a user's separate chat conversations (multi-session chat).

    Supersedes `ChatMessage`'s old "one continuous conversation per user"
    model (FR-17's original scope boundary) -- every `ChatMessage` now
    belongs to exactly one `ChatSession` via `session_id`, and a user can
    have many sessions.

    `title` is nullable: `None` until the session's first question is
    asked, at which point `chat/service.py::_finish` (via
    `chat/sessions_repository.py::touch_session`) sets it from that
    question's own text (auto-titling) -- never overwritten after that
    first set, so a user's own rename (`chat/sessions_service.py
    ::rename_session`) always sticks.

    `updated_at` is deliberately *not* driven by an ORM `onupdate=` --
    `touch_session` bumps it explicitly on every turn (not just on a
    `ChatSession` row edit, which a new message never causes on its own),
    so `chat/sessions_repository.py::list_sessions_for_user`'s
    `ORDER BY updated_at DESC` reflects actual chat activity, matching the
    "most recently active first" ordering a chat-session sidebar needs.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # Serves `chat/sessions_repository.py::list_sessions_for_user`'s
        # `user_id` filter + `updated_at DESC` sort in one index, same
        # "filter column leads, sort column(s) follow" shape as
        # `ChatMessage`'s own composite index below.
        Index("ix_chat_sessions_user_id_updated_at", "user_id", "updated_at"),
    )


class ChatMessage(Base):
    """One turn of one of a user's chat sessions (Story 3.4/FR-17;
    multi-session chat).

    One row per message, same declarative pattern as `Document` above --
    Uuid PK w/ Python-side default, plain `JSON` (not JSONB) for the same
    SQLite-test-compat reason as `Document.chapter_breakdown`. Queried
    exclusively through `user_scoped_select` (AD-2), never a hand-written
    `select(ChatMessage).where(...)`.

    `session_id` identifies which of the user's `ChatSession`s a row
    belongs to -- every real query (`chat/repository.py`'s
    `get_recent_turn_messages`/`list_messages_for_user`) filters on it
    first, then sorts on `(created_at, role, id)`; see the composite index
    in `__table_args__` below. `user_id` is kept as a plain, unindexed-on-
    its-own column purely for `delete_all_messages_for_user`'s
    account-deletion bulk delete -- a session's own ownership (checked via
    `chat_sessions.user_id` before any message query ever runs) is what
    actually proves a message row is this user's.

    Two disjoint row shapes, both fitting this one table (mirrors
    `AskResponse`'s own "answer OR empty_reason" duality rather than a
    second table per row-shape):
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
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
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
    # 'up' | 'down' | `None` (no rating yet) -- same "vocabulary enforced
    # in code, not schema" precedent as `role` above. Only ever set on a
    # `role="assistant"` row (`chat/service.py::set_message_feedback`
    # 404s on a `role="user"` id); always `None` on a `role="user"` row.
    feedback: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # Covers every real query this table serves: `session_id` filter,
        # then `(created_at, role, id)` sort (see
        # `chat/repository.py`'s `_TURN_ROLE_RANK`/`_strictly_before` --
        # `role` is the literal column here, not the `CASE`-computed rank
        # those use, but for a two-valued column the tied `created_at`
        # group a plain index leaves unsorted is at most a couple of
        # rows, cheap to finish in memory; the win is skipping a full
        # per-session table scan for the `session_id` filter and the bulk
        # of the `created_at` ordering, which is the part that actually
        # grows with conversation length).
        Index("ix_chat_messages_session_id_created_at_role_id", "session_id", "created_at", "role", "id"),
    )
