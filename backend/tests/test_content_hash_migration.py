"""Tests the backfill logic in the `content_hash` migration (Story 2.6).

The rest of this project's migrations aren't executed in the test suite --
`conftest.py`'s `db_session` fixture builds SQLite schemas straight from
the ORM models (see `deferred-work.md`'s standing note on that gap), and
this migration's `NOT NULL`/unique-index steps use plain `op.alter_column`/
`op.create_index`, which need Alembic's batch mode to run on SQLite at all
(the real target is Postgres, which doesn't need it) -- so running the
whole migration end-to-end isn't practical here without diverging the
migration itself just to make it testable.

What *is* practical, and closes the I/O matrix's "existing (pre-migration)
document re-uploaded" row: the backfill loop's actual hashing logic, which
is what determines whether a pre-2.6 document becomes correctly
dedupe-eligible. `op` is mocked (add_column/alter_column/create_index are
no-ops here -- schema DDL isn't what's under test) and `get_bind()` returns
a fake connection whose `execute()` both serves the row-select and records
every backfill UPDATE, so the assertions below check the exact hash each
row was backfilled with against `hashlib.sha256` computed independently.
"""

import hashlib
import importlib.util
import pathlib
import uuid
from unittest.mock import MagicMock

import pytest

_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "e1f5c8a2b4d7_add_content_hash_to_documents.py"
)
_spec = importlib.util.spec_from_file_location("content_hash_migration", _MIGRATION_PATH)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


class _FakeRow:
    def __init__(self, id_, content):
        self.id = id_
        self.content = content


def _run_backfill(monkeypatch, rows, collisions=None):
    # Three distinct kinds of `execute()` call happen in `upgrade()`, in
    # order: (1) the initial `SELECT id, content`, (2) one `UPDATE` per
    # backfilled row, (3) the post-backfill collision-check `GROUP BY ...
    # HAVING COUNT(*) > 1` query. `side_effect` gives each its own
    # `fetchall()` result rather than one shared `return_value` -- the
    # collision query must return an empty result by default (no
    # pre-existing duplicates), independent of whatever `rows` the select
    # returned, or every non-empty-`rows` test would spuriously trip the
    # new `RuntimeError` guard.
    select_result = MagicMock()
    select_result.fetchall.return_value = rows

    collision_result = MagicMock()
    collision_result.fetchall.return_value = collisions or []

    fake_connection = MagicMock()
    fake_connection.execute.side_effect = (
        [select_result] + [MagicMock() for _ in rows] + [collision_result]
    )

    fake_op = MagicMock()
    fake_op.get_bind.return_value = fake_connection
    monkeypatch.setattr(migration, "op", fake_op)

    migration.upgrade()

    return fake_connection


def test_backfill_computes_sha256_of_each_rows_stored_content(monkeypatch):
    row_a_id = uuid.uuid4()
    row_b_id = uuid.uuid4()
    row_a_content = b"first document's raw bytes"
    row_b_content = b"a completely different second document"
    rows = [_FakeRow(row_a_id, row_a_content), _FakeRow(row_b_id, row_b_content)]

    fake_connection = _run_backfill(monkeypatch, rows)

    # The select (first execute) and the collision-check query (last
    # execute) bracket one UPDATE per row in between.
    update_calls = fake_connection.execute.call_args_list[1:-1]
    assert len(update_calls) == len(rows)

    # `literal_binds` inlines values into the compiled SQL text directly,
    # which is more robust across SQLAlchemy versions than guessing bound
    # parameter names.
    rendered = [
        call.args[0].compile(compile_kwargs={"literal_binds": True}).string
        for call in update_calls
    ]
    expected_hash_a = hashlib.sha256(row_a_content).hexdigest()
    expected_hash_b = hashlib.sha256(row_b_content).hexdigest()
    # SQLite's UUID literal rendering strips dashes -- compare against the
    # bare hex form rather than `str(uuid)`.
    id_a_hex = row_a_id.hex
    id_b_hex = row_b_id.hex

    assert any(expected_hash_a in sql and id_a_hex in sql for sql in rendered)
    assert any(expected_hash_b in sql and id_b_hex in sql for sql in rendered)


def test_backfill_produces_a_full_length_hex_digest(monkeypatch):
    # `content_hash` is `String(64)` -- a truncated or malformed digest
    # would silently corrupt every pre-migration document's dedupe key.
    row_id = uuid.uuid4()
    content = b"some pdf bytes"
    fake_connection = _run_backfill(monkeypatch, [_FakeRow(row_id, content)])

    update_call = fake_connection.execute.call_args_list[1]
    rendered = update_call.args[0].compile(compile_kwargs={"literal_binds": True}).string
    expected_hash = hashlib.sha256(content).hexdigest()

    assert len(expected_hash) == 64
    assert expected_hash in rendered


def test_backfill_handles_no_existing_rows(monkeypatch):
    # An empty `documents` table (a fresh install) must not error --
    # the loop simply does nothing.
    fake_connection = _run_backfill(monkeypatch, [])

    # The initial select and the collision-check query ran; no UPDATE
    # calls landed in between.
    assert fake_connection.execute.call_count == 2


class _FakeCollisionRow:
    def __init__(self, user_id, content_hash, row_count):
        self.user_id = user_id
        self.content_hash = content_hash
        self.row_count = row_count


def test_upgrade_raises_and_never_creates_the_unique_index_when_collisions_exist(monkeypatch):
    # The safety-critical path: this is what stands between a confusing
    # driver-level IntegrityError (or worse, a silently-skipped index) and
    # a clear, actionable error naming exactly which rows need a human
    # decision. Confirmed against the real Neon database during this
    # story's review -- pre-existing duplicate content from before 2.6's
    # dedupe existed is a genuine, not just theoretical, scenario.
    user_id = uuid.uuid4()
    collision = _FakeCollisionRow(user_id, "a" * 64, 2)

    with pytest.raises(RuntimeError) as exc_info:
        _run_backfill(monkeypatch, [], collisions=[collision])

    message = str(exc_info.value)
    assert str(user_id) in message
    assert "a" * 64 in message

    # The whole point of raising before this call: the unique index must
    # never be created over data that would violate it.
    assert not migration.op.create_index.called
