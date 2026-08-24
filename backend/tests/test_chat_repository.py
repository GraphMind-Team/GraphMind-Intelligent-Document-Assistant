"""Repository-level tests for `chat.repository.get_overview_documents`
(Story 3.5, `MAX_OVERVIEW_DOCUMENTS` follow-up).

Exercises the function directly against the `db_session` fixture -- no
HTTP layer -- mirroring `test_documents_repository.py`'s pattern, since
the cap and its ordering guarantee (newest-`created_at`-first, so a
truncated request is deterministic rather than whatever order Postgres
happened to return rows in) aren't observable through the route tests in
`test_chat_ask_route.py`, which only ever exercise 0-2 documents at once.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.auth.repository import create_user
from app.auth.service import hash_password
from app.chat import repository
from app.documents import repository as documents_repository
from app.shared.models import Document, User


def _make_user(db_session, email):
    user = create_user(
        db_session,
        User(
            id=uuid.uuid4(),
            full_name="Repo Tester",
            email=email,
            password_hash=hash_password("password12345"),
        ),
    )
    db_session.commit()
    return user


def _make_document(db_session, user, *, filename, content_hash, status="Ready", created_at=None):
    document = Document(
        id=uuid.uuid4(),
        user_id=user.id,
        filename=filename,
        file_type="pdf",
        file_size_bytes=4,
        status=status,
        content=b"data",
        content_hash=content_hash,
        created_at=created_at or datetime.now(timezone.utc),
    )
    documents_repository.create_document(db_session, document)
    db_session.commit()
    return document


def test_get_overview_documents_unscoped_caps_at_max_and_keeps_newest_first(db_session):
    user = _make_user(db_session, "overview-cap-unscoped@example.com")
    base = datetime.now(timezone.utc)
    # Explicit, strictly increasing `created_at` per document (same
    # reasoning `test_chat_ask_route.py::_seed_turn` documents for
    # `ChatMessage` rows) -- otherwise every row could tie on the test
    # DB's clock resolution, making "newest first" unverifiable.
    documents = [
        _make_document(
            db_session,
            user,
            filename=f"report-{i}.pdf",
            content_hash=f"{i:064d}",
            created_at=base + timedelta(seconds=i),
        )
        for i in range(5)
    ]

    result = repository.get_overview_documents(db_session, user.id, [])

    assert len(result) == repository.MAX_OVERVIEW_DOCUMENTS == 3
    assert [d.id for d in result] == [d.id for d in reversed(documents[-3:])]


def test_get_overview_documents_explicit_scope_also_caps_at_max(db_session):
    """The cap isn't only an unscoped-library safeguard -- an explicit
    `document_ids` scope wider than `MAX_OVERVIEW_DOCUMENTS` is narrowed
    the same way, so a caller can't bypass the prompt-size ceiling by
    simply scoping to more documents."""
    user = _make_user(db_session, "overview-cap-scoped@example.com")
    base = datetime.now(timezone.utc)
    documents = [
        _make_document(
            db_session,
            user,
            filename=f"report-{i}.pdf",
            content_hash=f"{i:064d}",
            status="Uploaded",
            created_at=base + timedelta(seconds=i),
        )
        for i in range(4)
    ]

    result = repository.get_overview_documents(db_session, user.id, [d.id for d in documents])

    assert len(result) == 3
    assert [d.id for d in result] == [d.id for d in reversed(documents[-3:])]


def test_get_overview_documents_below_the_cap_returns_all_of_them(db_session):
    user = _make_user(db_session, "overview-cap-under@example.com")
    documents = [
        _make_document(db_session, user, filename=f"report-{i}.pdf", content_hash=f"{i:064d}")
        for i in range(2)
    ]

    result = repository.get_overview_documents(db_session, user.id, [])

    assert {d.id for d in result} == {d.id for d in documents}
