"""Repository-level tests for `get_document_by_content_hash` (Story 2.6).

Exercises `app.documents.repository` directly against the `db_session`
fixture -- no HTTP layer -- to pin down tenancy scoping the way
`get_document_for_user` is already implicitly covered by the route-level
404-vs-403 tests: a hash match must never cross users, no matter how
identical the bytes are.
"""

import uuid

from app.auth.repository import create_user
from app.auth.service import hash_password
from app.documents import repository
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


def _make_document(db_session, user, content_hash, filename="report.pdf"):
    document = Document(
        id=uuid.uuid4(),
        user_id=user.id,
        filename=filename,
        file_type="pdf",
        file_size_bytes=4,
        status="Uploaded",
        content=b"data",
        content_hash=content_hash,
    )
    repository.create_document(db_session, document)
    db_session.commit()
    return document


def test_get_document_by_content_hash_finds_match_for_owner(db_session):
    user = _make_user(db_session, "repo-owner@example.com")
    document = _make_document(db_session, user, "a" * 64)

    found = repository.get_document_by_content_hash(db_session, user.id, "a" * 64)

    assert found is not None
    assert found.id == document.id


def test_get_document_by_content_hash_returns_none_when_no_match(db_session):
    user = _make_user(db_session, "repo-nomatch@example.com")
    _make_document(db_session, user, "a" * 64)

    found = repository.get_document_by_content_hash(db_session, user.id, "b" * 64)

    assert found is None


def test_get_document_by_content_hash_never_matches_across_users(db_session):
    # The core tenancy guarantee: identical hash, different owner -> None.
    # Mirrors `get_document_for_user`'s "not yours" behavior, but for the
    # hash-lookup path this story adds.
    owner = _make_user(db_session, "repo-cross-owner@example.com")
    other = _make_user(db_session, "repo-cross-other@example.com")
    _make_document(db_session, owner, "c" * 64)

    found = repository.get_document_by_content_hash(db_session, other.id, "c" * 64)

    assert found is None
