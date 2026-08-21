"""Repository-level tests for `app.folders.repository` (folder-grouping
feature).

Exercises the repository directly against the `db_session` fixture -- no
HTTP layer -- to pin down tenancy scoping the way
`test_documents_repository.py` already does for `documents/repository.py`:
a folder must never be visible or deletable from any account but its own.
"""

import uuid

from app.auth.repository import create_user
from app.auth.service import hash_password
from app.folders import repository
from app.shared.models import Folder, User


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


def _make_folder(db_session, user, name="Contracts", color="mint"):
    folder = Folder(id=uuid.uuid4(), user_id=user.id, name=name, color=color)
    repository.create_folder(db_session, folder)
    db_session.commit()
    return folder


def test_list_folders_for_user_returns_only_owned_folders(db_session):
    owner = _make_user(db_session, "folders-owner@example.com")
    other = _make_user(db_session, "folders-other@example.com")
    _make_folder(db_session, owner, name="Owner Folder")
    _make_folder(db_session, other, name="Other Folder")

    found = repository.list_folders_for_user(db_session, owner.id)

    assert [folder.name for folder in found] == ["Owner Folder"]


def test_get_folder_for_user_finds_a_match_for_the_owner(db_session):
    user = _make_user(db_session, "folders-get-owner@example.com")
    folder = _make_folder(db_session, user)

    found = repository.get_folder_for_user(db_session, user.id, folder.id)

    assert found is not None
    assert found.id == folder.id


def test_get_folder_for_user_returns_none_for_an_unknown_id(db_session):
    user = _make_user(db_session, "folders-get-unknown@example.com")

    found = repository.get_folder_for_user(db_session, user.id, uuid.uuid4())

    assert found is None


def test_get_folder_for_user_never_matches_across_users(db_session):
    # The core tenancy guarantee: a real folder id, wrong owner -> None.
    owner = _make_user(db_session, "folders-cross-owner@example.com")
    other = _make_user(db_session, "folders-cross-other@example.com")
    folder = _make_folder(db_session, owner)

    found = repository.get_folder_for_user(db_session, other.id, folder.id)

    assert found is None


def test_delete_folder_for_user_removes_the_row_and_returns_true(db_session):
    user = _make_user(db_session, "folders-delete-owner@example.com")
    folder = _make_folder(db_session, user)

    deleted = repository.delete_folder_for_user(db_session, user.id, folder.id)
    db_session.commit()

    assert deleted is True
    assert db_session.get(Folder, folder.id) is None


def test_delete_folder_for_user_returns_false_and_touches_nothing_across_users(db_session):
    owner = _make_user(db_session, "folders-delete-cross-owner@example.com")
    other = _make_user(db_session, "folders-delete-cross-other@example.com")
    folder = _make_folder(db_session, owner)

    deleted = repository.delete_folder_for_user(db_session, other.id, folder.id)

    assert deleted is False
    assert db_session.get(Folder, folder.id) is not None


def test_delete_all_folders_for_user_removes_only_that_users_folders(db_session):
    owner = _make_user(db_session, "folders-delete-all-owner@example.com")
    other = _make_user(db_session, "folders-delete-all-other@example.com")
    _make_folder(db_session, owner, name="A")
    _make_folder(db_session, owner, name="B")
    other_folder = _make_folder(db_session, other, name="C")

    count = repository.delete_all_folders_for_user(db_session, owner.id)
    db_session.commit()

    assert count == 2
    assert repository.list_folders_for_user(db_session, owner.id) == []
    assert db_session.get(Folder, other_folder.id) is not None
