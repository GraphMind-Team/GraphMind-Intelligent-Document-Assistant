"""Chat module data access (Story 3.1).

Per architecture decision AD-2, Postgres access here goes through
`shared/data_access/tenancy.py`'s `user_scoped_select` rather than a
hand-written `select(Document).where(...)` -- same pattern
`documents/repository.py` uses.
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, case, delete, desc, or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.shared.data_access.tenancy import user_scoped_select
from app.shared.models import ChatMessage, Document

# Both rows of one turn are written inside a single transaction --
# `chat/service.py::_finish` calls `save_message` twice, then commits
# once -- and Postgres's `now()` (this table's `created_at`
# server_default) returns the *transaction's* start time, not the
# individual statement's, so a turn's `user` row and its `assistant` row
# always share the exact same `created_at` value. (SQLite's own
# `CURRENT_TIMESTAMP`, used in this project's test suite, is coarser
# still -- whole-second resolution -- so the identical tie shows up
# there too, not only in production.) `role` is what actually
# distinguishes "the question" from "the answer that followed it" when
# `created_at` alone can't: 0 for `user` (chronologically first within a
# tied pair), 1 for `assistant` (second). Every ordering/cursor
# comparison below sorts on `(created_at, _TURN_ROLE_RANK, id)`, never
# `created_at` alone, so a tied pair's rows can never come back in the
# wrong relative order -- which would otherwise silently corrupt
# `chat/service.py::_pair_messages_into_turns`'s strict-alternation
# assumption.
#
# `turn_role_rank` is the one place that 0/1 rule is actually defined --
# `_TURN_ROLE_RANK` (the SQL `case` expression the ORDER BY/cursor
# WHERE clauses use) is built from it below, and
# `chat/service.py::_encode_cursor` calls this same function (via
# `repository.turn_role_rank`, since `service.py` already imports this
# module) to encode a cursor's role-rank component -- two independent
# hardcodings of "assistant sorts after user" could silently drift apart
# (e.g. one gets flipped during a refactor and not the other), which a
# single shared function makes structurally impossible. `VALID_
# TURN_ROLE_RANKS` is the matching validation set `service.py::
# _decode_cursor` checks a parsed cursor's role-rank against, for the
# same "one definition, not two" reason.
def turn_role_rank(role: str) -> int:
    """0 for `role="user"`, 1 for `role="assistant"` -- the sort rank a
    tied-`created_at` pair's rows resolve to."""
    return 1 if role == "assistant" else 0


VALID_TURN_ROLE_RANKS = frozenset(turn_role_rank(role) for role in ("user", "assistant"))

_TURN_ROLE_RANK = case(
    (ChatMessage.role == "assistant", turn_role_rank("assistant")), else_=turn_role_rank("user")
)


def _strictly_before(ordered_columns_and_values: list[tuple]) -> ColumnElement:
    """`(c0, c1, ..., cn) < (v0, v1, ..., vn)` in lexicographic order, via
    nested OR/AND rather than a SQL row-value comparison (`(a, b) < (x,
    y)`) -- portable across SQLite/Postgres without depending on either's
    row-value comparison support."""
    conditions = []
    for i, (column, value) in enumerate(ordered_columns_and_values):
        equalities = [c == v for c, v in ordered_columns_and_values[:i]]
        conditions.append(and_(*equalities, column < value) if equalities else column < value)
    return or_(*conditions)


def get_filenames_for_documents(
    db: Session, user_id: uuid.UUID, document_ids: set[str]
) -> dict[str, str]:
    """`document_id` (string, matching Weaviate's string-typed
    `document_id` property) -> `filename`, scoped to documents this user
    owns via `user_scoped_select` (AD-2) -- never a bare
    `select(Document).where(Document.id.in_(...))`.

    A `document_id` present in `document_ids` but absent from the
    returned dict means either the document was deleted after its
    passages were indexed, or -- in principle, shouldn't happen since
    Weaviate's own query was already `user_id`-filtered -- doesn't belong
    to this user. Either way, the caller (`chat/service.py`) must treat a
    missing filename as "drop this citation," never crash or fabricate a
    filename. Malformed ids (shouldn't occur -- every id was written by
    `documents/service.py`'s `ingest_document` as `str(document.id)`) are
    skipped the same defensive way rather than raising.
    """
    if not document_ids:
        return {}

    parsed_ids: list[uuid.UUID] = []
    for document_id in document_ids:
        try:
            parsed_ids.append(uuid.UUID(document_id))
        except ValueError:
            continue

    if not parsed_ids:
        return {}

    stmt = user_scoped_select(Document, user_id).where(Document.id.in_(parsed_ids))
    rows = db.execute(stmt).scalars().all()
    return {str(row.id): row.filename for row in rows}


def save_message(db: Session, message: ChatMessage) -> ChatMessage:
    """Stage `message` for insert and flush to surface any integrity error
    immediately. Does not commit -- the caller (`chat/service.py`) owns
    the transaction boundary, mirroring `documents/repository.py`'s
    `create_document`."""
    db.add(message)
    db.flush()
    return message


def get_recent_turn_messages(db: Session, user_id: uuid.UUID, max_turns: int) -> list[ChatMessage]:
    """Up to `max_turns` completed (user, assistant) row-pairs for this
    account's single ongoing conversation (Story 3.4/FR-17), returned
    oldest-first.

    Fetches the newest `max_turns * 2` rows (a completed turn is always
    exactly one `role="user"` row followed by one `role="assistant"` row
    -- `chat/service.py::_finish` only ever persists both together, in
    the same request, so rows always arrive in that strict alternating
    order once `_TURN_ROLE_RANK` breaks the `created_at` tie -- see its
    own comment above) and reverses to chronological order --
    `chat/service.py` pairs them into `ChatHistoryTurn`s from there.
    `user_scoped_select` (AD-2), never a hand-written
    `select(ChatMessage).where(...)`.
    """
    if max_turns <= 0:
        return []
    stmt = (
        user_scoped_select(ChatMessage, user_id)
        .order_by(desc(ChatMessage.created_at), desc(_TURN_ROLE_RANK), desc(ChatMessage.id))
        .limit(max_turns * 2)
    )
    rows = list(db.execute(stmt).scalars().all())
    rows.reverse()
    return rows


def list_messages_for_user(
    db: Session,
    user_id: uuid.UUID,
    cursor: tuple[datetime, int, uuid.UUID] | None,
    limit: int,
) -> tuple[list[ChatMessage], bool]:
    """A newest-first page of this account's conversation, at most `limit`
    rows, optionally starting strictly after `cursor` (Story 3.4/AD-10).

    `cursor` anchors on a `(created_at, turn_role_rank, id)` tuple rather
    than a raw offset (Design Notes): new messages only ever append at
    the newest end of this account's single conversation, so a cursor
    into older history never drifts even if new turns arrive
    concurrently -- an offset-based page would, since inserting new rows
    above an offset page shifts every row below it. `turn_role_rank`
    (see `_TURN_ROLE_RANK`'s comment) breaks a turn's `created_at` tie
    correctly (its assistant row is "newer" than its own user row even
    though both share one timestamp); `id` is the final tiebreaker for
    the two rows sharing both a timestamp and a role, which shouldn't
    happen but costs nothing to guard.

    Returns `(messages, has_more)` -- fetches one extra row beyond
    `limit` to answer `has_more` without a second COUNT query; that extra
    row is trimmed back off before returning.
    """
    stmt = user_scoped_select(ChatMessage, user_id).order_by(
        desc(ChatMessage.created_at), desc(_TURN_ROLE_RANK), desc(ChatMessage.id)
    )
    if cursor is not None:
        cursor_created_at, cursor_role_rank, cursor_id = cursor
        stmt = stmt.where(
            _strictly_before(
                [
                    (ChatMessage.created_at, cursor_created_at),
                    (_TURN_ROLE_RANK, cursor_role_rank),
                    (ChatMessage.id, cursor_id),
                ]
            )
        )
    stmt = stmt.limit(limit + 1)
    rows = list(db.execute(stmt).scalars().all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


def delete_all_messages_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Bulk-deletes every `chat_messages` row owned by `user_id` in one
    statement (Story 5.3's account-deletion cascade, extended here for
    Story 3.4's new table) -- mirrors
    `documents/repository.py::delete_all_documents_for_user`'s same
    single-`DELETE`-statement shape, not a loop calling `save_message`'s
    opposite once per row.

    Required, not optional: `chat_messages.user_id` is a `NOT NULL`
    foreign key into `users.id` with no `ON DELETE CASCADE` (Story 3.4's
    migration doesn't declare one), so `auth/service.py::delete_account`
    deleting the `users` row without first deleting this account's
    `chat_messages` rows fails with a `ForeignKeyViolation` -- this
    function is what `delete_account` must call, in the same fixed
    delete order as `delete_all_documents_for_user`, before the `users`
    row delete.

    Does not commit -- the caller (`auth/service.py::delete_account`)
    owns the transaction boundary, alongside the Weaviate/Neo4j deletes
    and the `documents`/`users` row deletes it also runs in the same
    commit, mirroring `save_message`'s own convention.

    Returns the number of rows deleted, mirroring
    `delete_all_documents_for_user`'s own return -- no caller acts on it
    today, but it costs nothing extra to surface.
    """
    result = db.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
    return result.rowcount
