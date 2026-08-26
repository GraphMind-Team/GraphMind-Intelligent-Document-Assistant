"""`POST/GET /folders`, `PATCH/DELETE /folders/{folder_id}` tests
(folder-grouping feature).

Mirrors `test_documents_detail.py`/`test_documents_delete.py`'s IDOR
coverage: a cross-tenant or nonexistent folder id must come back as the
same 404 `"Folder not found."`, never a 403 that would confirm the id
exists.
"""

import uuid

from app.folders import service as folders_service


def _register_and_login(client, *, full_name, email, password):
    register_response = client.post(
        "/auth/register",
        json={"full_name": full_name, "email": email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = client.post("/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200, login_response.text
    return login_response.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_folder(client, token, name="Contracts", color="mint"):
    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": name, "color": color}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_folder_returns_201_with_the_new_folder(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-create@example.com", password="password12345"
    )

    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": "Тестове", "color": "mint"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Тестове"
    assert body["color"] == "mint"
    assert "id" in body
    assert "created_at" in body


def test_create_folder_with_empty_name_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-empty-name@example.com", password="password12345"
    )

    response = client.post("/folders", headers=_auth_headers(token), json={"name": "", "color": "mint"})

    assert response.status_code == 400
    assert "blank" in response.json()["detail"].lower()


def test_create_folder_with_whitespace_only_name_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-ws-name@example.com", password="password12345"
    )

    response = client.post("/folders", headers=_auth_headers(token), json={"name": "   ", "color": "mint"})

    assert response.status_code == 400


def test_create_folder_with_name_over_255_chars_is_400(client):
    # `FolderModal.jsx` caps the name input at 255 chars via `maxLength`,
    # but that only stops the in-app form -- a direct API call bypasses it
    # entirely since `Folder.name` is an unbounded `String` column, so the
    # same ceiling must be enforced server-side too.
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-long-name@example.com", password="password12345"
    )

    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": "x" * 256, "color": "mint"}
    )

    assert response.status_code == 400
    assert "255" in response.json()["detail"]


def test_create_folder_with_name_exactly_255_chars_is_accepted(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-max-name@example.com", password="password12345"
    )

    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": "x" * 255, "color": "mint"}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "x" * 255


def test_create_folder_with_invalid_color_key_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-bad-color@example.com", password="password12345"
    )

    response = client.post(
        "/folders", headers=_auth_headers(token), json={"name": "x", "color": "#ff0000"}
    )

    assert response.status_code == 400
    assert "color" in response.json()["detail"].lower()


def test_create_folder_requires_authentication(client):
    response = client.post("/folders", json={"name": "x", "color": "mint"})
    assert response.status_code == 401


def test_list_folders_is_scoped_to_the_calling_account(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="folders-list-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="folders-list-b@example.com", password="password-account-b"
    )
    _create_folder(client, token_a, name="Account A Folder")

    response_b = client.get("/folders", headers=_auth_headers(token_b))
    assert response_b.status_code == 200
    assert response_b.json() == []

    response_a = client.get("/folders", headers=_auth_headers(token_a))
    assert response_a.status_code == 200
    assert len(response_a.json()) == 1
    assert response_a.json()[0]["name"] == "Account A Folder"


def test_list_folders_with_none_created_returns_empty_list(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-list-empty@example.com", password="password12345"
    )

    response = client.get("/folders", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json() == []


def test_update_folder_renames_and_recolors(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-update@example.com", password="password12345"
    )
    folder = _create_folder(client, token, name="Old Name", color="mint")

    response = client.patch(
        f"/folders/{folder['id']}",
        headers=_auth_headers(token),
        json={"name": "New Name", "color": "sky"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "New Name"
    assert body["color"] == "sky"
    assert body["id"] == folder["id"]


def test_update_folder_partial_rename_only_leaves_color_untouched(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-update-partial@example.com", password="password12345"
    )
    folder = _create_folder(client, token, name="Old Name", color="peach")

    response = client.patch(
        f"/folders/{folder['id']}", headers=_auth_headers(token), json={"name": "Renamed"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["color"] == "peach"


def test_update_folder_with_empty_name_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-update-empty@example.com", password="password12345"
    )
    folder = _create_folder(client, token)

    response = client.patch(
        f"/folders/{folder['id']}", headers=_auth_headers(token), json={"name": ""}
    )

    assert response.status_code == 400


def test_update_folder_with_name_over_255_chars_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-update-long@example.com", password="password12345"
    )
    folder = _create_folder(client, token)

    response = client.patch(
        f"/folders/{folder['id']}", headers=_auth_headers(token), json={"name": "x" * 256}
    )

    assert response.status_code == 400
    assert "255" in response.json()["detail"]


def test_update_folder_with_invalid_color_is_400(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-update-bad-color@example.com", password="password12345"
    )
    folder = _create_folder(client, token)

    response = client.patch(
        f"/folders/{folder['id']}", headers=_auth_headers(token), json={"color": "crimson"}
    )

    assert response.status_code == 400


def test_update_another_accounts_folder_is_404_not_403(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="folders-update-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="folders-update-b@example.com", password="password-account-b"
    )
    folder_a = _create_folder(client, token_a, name="Account A Secret")

    response = client.patch(
        f"/folders/{folder_a['id']}", headers=_auth_headers(token_b), json={"name": "Hijacked"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Folder not found."}
    assert "Account A Secret" not in response.text


def test_update_unknown_folder_is_the_same_404_as_cross_tenant(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="folders-update-unknown-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="folders-update-unknown-b@example.com", password="password-account-b"
    )
    folder_a = _create_folder(client, token_a)

    cross_tenant = client.patch(
        f"/folders/{folder_a['id']}", headers=_auth_headers(token_b), json={"name": "x"}
    )
    unknown = client.patch(
        f"/folders/{uuid.uuid4()}", headers=_auth_headers(token_b), json={"name": "x"}
    )

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_delete_folder_returns_204_and_removes_it(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-delete@example.com", password="password12345"
    )
    folder = _create_folder(client, token)

    response = client.delete(f"/folders/{folder['id']}", headers=_auth_headers(token))

    assert response.status_code == 204
    assert response.content == b""

    listing = client.get("/folders", headers=_auth_headers(token))
    assert listing.json() == []


def test_delete_folder_with_documents_unfiles_them_instead_of_deleting_them(client, db_session):
    """I/O matrix: deleting a folder with 3 documents assigned -> 204, and
    those documents' `folder_id` becomes `null` -- no data is lost."""
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-delete-with-docs@example.com", password="password12345"
    )
    folder = _create_folder(client, token)

    document_ids = []
    for i in range(3):
        upload = client.post(
            "/documents",
            headers=_auth_headers(token),
            files={"file": (f"doc-{i}.pdf", f"%PDF-1.4 doc {i}".encode(), "application/pdf")},
        )
        assert upload.status_code == 201, upload.text
        document_id = upload.json()["id"]
        assign = client.patch(
            f"/documents/{document_id}",
            headers=_auth_headers(token),
            json={"folder_id": folder["id"]},
        )
        assert assign.status_code == 200, assign.text
        document_ids.append(document_id)

    response = client.delete(f"/folders/{folder['id']}", headers=_auth_headers(token))
    assert response.status_code == 204

    for document_id in document_ids:
        get_response = client.get(f"/documents/{document_id}", headers=_auth_headers(token))
        assert get_response.status_code == 200
        assert get_response.json()["folder_id"] is None


def test_delete_another_accounts_folder_is_404_not_403(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="folders-delete-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="folders-delete-b@example.com", password="password-account-b"
    )
    folder_a = _create_folder(client, token_a, name="Account A Secret")

    response = client.delete(f"/folders/{folder_a['id']}", headers=_auth_headers(token_b))

    assert response.status_code == 404
    assert response.json() == {"detail": "Folder not found."}

    # Still there for account A.
    listing_a = client.get("/folders", headers=_auth_headers(token_a))
    assert len(listing_a.json()) == 1


def test_delete_unknown_folder_is_the_same_404_as_cross_tenant(client):
    token_a = _register_and_login(
        client, full_name="Account A", email="folders-delete-unknown-a@example.com", password="password-account-a"
    )
    token_b = _register_and_login(
        client, full_name="Account B", email="folders-delete-unknown-b@example.com", password="password-account-b"
    )
    folder_a = _create_folder(client, token_a)

    cross_tenant = client.delete(f"/folders/{folder_a['id']}", headers=_auth_headers(token_b))
    unknown = client.delete(f"/folders/{uuid.uuid4()}", headers=_auth_headers(token_b))

    assert unknown.status_code == 404
    assert unknown.status_code == cross_tenant.status_code
    assert unknown.json() == cross_tenant.json()


def test_delete_folder_requires_authentication(client):
    response = client.delete(f"/folders/{uuid.uuid4()}")
    assert response.status_code == 401


def test_folder_malformed_id_is_422(client):
    token = _register_and_login(
        client, full_name="Maria Ivanova", email="folders-malformed@example.com", password="password12345"
    )

    response = client.patch(
        "/folders/not-a-uuid", headers=_auth_headers(token), json={"name": "x"}
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Per-account folder cap. `POST /folders` was the one user-facing creation
# path with nothing bounding it: `documents` is bounded by the upload
# limiters and the unique (user_id, content_hash) index, and `chat_sessions`
# by create_session's reuse of an existing blank session, but folders
# inserted unconditionally.
# ---------------------------------------------------------------------------


def _make_folder(client, token, name):
    return client.post(
        "/folders",
        headers=_auth_headers(token),
        json={"name": name, "color": "rose"},
    )


def test_creating_a_folder_past_the_cap_is_refused(client, monkeypatch):
    monkeypatch.setattr(folders_service, "MAX_FOLDERS_PER_USER", 3)
    token = _register_and_login(
        client, full_name="Maria", email="maria-folder-cap@example.com", password="password12345"
    )

    for i in range(3):
        assert _make_folder(client, token, f"Folder {i}").status_code == 201

    refused = _make_folder(client, token, "One too many")
    assert refused.status_code == 409
    assert "limit of 3 folders" in refused.json()["detail"]


def test_the_cap_is_per_account(client, monkeypatch):
    monkeypatch.setattr(folders_service, "MAX_FOLDERS_PER_USER", 2)
    first = _register_and_login(
        client, full_name="Maria", email="maria-folder-scope@example.com", password="password12345"
    )
    for i in range(2):
        _make_folder(client, first, f"Folder {i}")
    assert _make_folder(client, first, "Over").status_code == 409

    second = _register_and_login(
        client, full_name="Ivan", email="ivan-folder-scope@example.com", password="password12345"
    )
    assert _make_folder(client, second, "My first folder").status_code == 201


def test_deleting_a_folder_frees_a_slot(client, monkeypatch):
    """The 409 tells the user to delete one to make room -- that has to be
    true, so the count must reflect deletions rather than being a
    high-water mark."""
    monkeypatch.setattr(folders_service, "MAX_FOLDERS_PER_USER", 2)
    token = _register_and_login(
        client, full_name="Maria", email="maria-folder-free@example.com", password="password12345"
    )
    first = _make_folder(client, token, "Keep").json()
    _make_folder(client, token, "Discard")
    assert _make_folder(client, token, "Over").status_code == 409

    assert client.delete(f"/folders/{first['id']}", headers=_auth_headers(token)).status_code == 204
    assert _make_folder(client, token, "Now it fits").status_code == 201


def test_a_malformed_request_at_the_cap_still_reports_the_field(client, monkeypatch):
    """Field validation runs first on purpose: reporting the cap for a
    blank name would send the user deleting folders to satisfy a request
    that would fail anyway."""
    monkeypatch.setattr(folders_service, "MAX_FOLDERS_PER_USER", 1)
    token = _register_and_login(
        client, full_name="Maria", email="maria-folder-order@example.com", password="password12345"
    )
    _make_folder(client, token, "Only one")

    response = _make_folder(client, token, "   ")
    assert response.status_code == 400
    assert "blank" in response.json()["detail"]
