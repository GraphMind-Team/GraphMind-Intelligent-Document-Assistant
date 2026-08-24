"""Tests the backfill logic in the `chat_sessions` migration (multi-session
chat).

Mirrors `test_content_hash_migration.py`'s approach and its own stated
reason: the rest of this project's migrations aren't executed in the test
suite (`conftest.py`'s `db_session` fixture builds SQLite schemas straight
from the ORM models), and this migration's `NOT NULL`/FK steps need
Alembic's batch mode to run on SQLite at all -- so running the whole
migration end-to-end isn't practical here. What *is* practical: the
backfill loop's actual per-user session-creation and message-reassignment
logic, which is what determines whether a pre-migration account's history
survives intact as exactly one session. `op` is mocked (create_table/
add_column/alter_column/create_foreign_key/create_index/drop_index are
no-ops here -- schema DDL isn't what's under test) and `get_bind()` returns
a fake connection whose `execute()` both serves the per-user
`SELECT ... GROUP BY user_id` and records every backfill INSERT/UPDATE, so
the assertions below check the exact values each session/message row was
backfilled with.

The real end-to-end verification of this migration -- run against the QA
account's actual pre-existing chat history -- happens manually
(`alembic upgrade head` against the dev DB), per this feature's own
rollout plan, not here.
"""

import importlib.util
import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "c8d3f5a1b7e9_add_chat_sessions_and_session_id.py"
)
_spec = importlib.util.spec_from_file_location("chat_sessions_migration", _MIGRATION_PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


class _FakeBoundsRow:
    def __init__(self, user_id, first_created_at, last_created_at):
        self.user_id = user_id
        self.first_created_at = first_created_at
        self.last_created_at = last_created_at


def _run_backfill(monkeypatch, per_user_bounds_rows):
    # Two distinct kinds of `execute()` call happen in `upgrade()`'s
    # backfill section, in order: (1) the initial per-user
    # `SELECT user_id, min(created_at), max(created_at) ... GROUP BY
    # user_id`, then (2) one INSERT (new chat_sessions row) + one UPDATE
    # (that user's chat_messages.session_id) per distinct user, in that
    # order, repeated per row.
    select_result = MagicMock()
    select_result.fetchall.return_value = per_user_bounds_rows

    fake_connection = MagicMock()
    fake_connection.execute.side_effect = [select_result] + [
        MagicMock() for _ in range(len(per_user_bounds_rows) * 2)
    ]

    fake_op = MagicMock()
    fake_op.get_bind.return_value = fake_connection
    monkeypatch.setattr(migration, "op", fake_op)

    migration.upgrade()

    return fake_connection


def _rendered(call):
    return call.args[0].compile(compile_kwargs={"literal_binds": True}).string


def test_backfill_creates_exactly_one_session_per_distinct_user(monkeypatch):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _FakeBoundsRow(user_a, base, base),
        _FakeBoundsRow(user_b, base, base),
    ]

    fake_connection = _run_backfill(monkeypatch, rows)

    # select, then (insert, update) per user, in order.
    assert fake_connection.execute.call_count == 1 + 2 * len(rows)
    insert_calls = [fake_connection.execute.call_args_list[1], fake_connection.execute.call_args_list[3]]
    rendered_inserts = [_rendered(call) for call in insert_calls]
    # SQLite's UUID literal rendering strips dashes -- compare against the
    # bare hex form rather than str(uuid), matching
    # test_content_hash_migration.py's own convention.
    assert any(user_a.hex in sql for sql in rendered_inserts)
    assert any(user_b.hex in sql for sql in rendered_inserts)


def test_backfill_session_spans_that_users_first_and_last_message_timestamps(monkeypatch):
    user_id = uuid.uuid4()
    first_created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    last_created_at = datetime(2026, 3, 15, tzinfo=timezone.utc)

    fake_connection = _run_backfill(
        monkeypatch, [_FakeBoundsRow(user_id, first_created_at, last_created_at)]
    )

    insert_sql = _rendered(fake_connection.execute.call_args_list[1])
    # Rendered as naive ISO text once `literal_binds` inlines a
    # timezone-aware value through SQLite's dialect -- the date/time
    # component itself is still present and enough to pin the right
    # bound landed in the right column.
    assert "2026-01-01" in insert_sql
    assert "2026-03-15" in insert_sql


def test_backfill_session_starts_titleless(monkeypatch):
    user_id = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    fake_connection = _run_backfill(monkeypatch, [_FakeBoundsRow(user_id, base, base)])

    insert_sql = _rendered(fake_connection.execute.call_args_list[1])
    assert "NULL" in insert_sql.upper()


def test_backfill_reassigns_every_one_of_that_users_messages_to_the_new_session(monkeypatch):
    user_id = uuid.uuid4()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    fake_connection = _run_backfill(monkeypatch, [_FakeBoundsRow(user_id, base, base)])

    insert_sql = _rendered(fake_connection.execute.call_args_list[1])
    update_sql = _rendered(fake_connection.execute.call_args_list[2])
    # The UPDATE's own WHERE clause scopes to this user's rows...
    assert user_id.hex in update_sql
    assert "chat_messages" in update_sql.lower()
    assert "session_id" in update_sql.lower()
    # ...and both statements agree on the same new session id, since a
    # message must be reassigned to the session that was actually created
    # for its own user, never an unrelated one.
    new_session_id_hex = insert_sql.split("VALUES (")[1].split(",")[0].strip("'\"")
    assert new_session_id_hex in update_sql or new_session_id_hex.replace("-", "") in update_sql


def test_backfill_handles_no_existing_rows(monkeypatch):
    # An empty `chat_messages` table (a fresh install) must not error --
    # the loop simply does nothing.
    fake_connection = _run_backfill(monkeypatch, [])

    # Only the initial select ran; no INSERT/UPDATE calls landed after it.
    assert fake_connection.execute.call_count == 1
